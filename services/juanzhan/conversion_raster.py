"""Local raster decoding, rendering and optional OCR; used only inside bounded children."""
from contextlib import ExitStack
from functools import lru_cache
import hashlib
from importlib.util import find_spec
from io import BytesIO
import json
from pathlib import Path
import warnings

from .conversion_formats import FormatError

IMAGES = ['image/png','image/jpeg','image/tiff']

@lru_cache(maxsize=16)
def available_languages(directory):
    if find_spec('tesserocr') is None:return ()
    manifest = Path(__file__).resolve().parents[2]/'ocr-models.lock.json'
    try:
        models = json.loads(manifest.read_text())['models']
        return tuple(m['language'] for m in models
                     if (Path(directory)/(m['language']+'.traineddata')).is_file()
                     and (Path(directory)/(m['language']+'.traineddata')).stat().st_size==m['size_bytes']
                     and hashlib.sha256((Path(directory)/(m['language']+'.traineddata')).read_bytes()).hexdigest()==m['sha256'])
    except (OSError,ValueError,KeyError):return ()

class Raster:
    def __init__(self,data,mime,out,options):
        self.data,self.mime,self.out,self.options=data,mime,out,options
        self.stack=ExitStack()
        self.document=None
        self.ocr=None
        self.ocr_pages=0
        self.used=False
        self.languages=options['ocr_languages'].split(',') if options['ocr_languages'] else ['eng']

    def __enter__(self):
        try:return self.open()
        except BaseException:
            self.stack.close()
            raise

    def open(self):
        if self.mime=='application/pdf':
            from pypdf import PdfReader
            reader=PdfReader(BytesIO(self.data),strict=True)
            if reader.is_encrypted:raise FormatError('PDF_PASSWORD_REQUIRED')
            if len(reader.pages)>self.out.limits['max_pages']:raise FormatError('PAGE_LIMIT')
            import pypdfium2 as pdfium
            self.document=self.stack.enter_context(pdfium.PdfDocument(self.data))
            self.count=len(self.document)
        else:
            from PIL import Image
            # Header dimensions checked before any decode. Treat bomb warnings as errors.
            with warnings.catch_warnings():
                warnings.simplefilter('error',Image.DecompressionBombWarning)
                self.document=self.stack.enter_context(Image.open(BytesIO(self.data)))
            expected={'image/png':'PNG','image/jpeg':'JPEG','image/tiff':'TIFF'}[self.mime]
            if self.document.format!=expected:raise FormatError('INVALID_IMAGE')
            self.count=getattr(self.document,'n_frames',1)
        if not 1<=self.count<=self.out.limits['max_pages']:raise FormatError('PAGE_LIMIT')
        return self

    def __exit__(self,*args):
        self.stack.close()

    def image(self,index):
        from PIL import Image, ImageOps
        maximum=self.out.limits['max_image_pixels']
        if self.mime=='application/pdf':
            with ExitStack() as rendering:
                page=self.document[index]
                rendering.callback(page.close)
                width,height=page.get_size()
                scale=self.out.limits['render_dpi']/72
                if width<=0 or height<=0 or (int(width*scale)+1)*(int(height*scale)+1)>maximum:
                    raise FormatError('IMAGE_PIXEL_LIMIT')
                bitmap=page.render(scale=scale)
                rendering.callback(bitmap.close)
                image=bitmap.to_pil().copy()
        else:
            self.document.seek(index)
            if self.document.width*self.document.height>maximum:raise FormatError('IMAGE_PIXEL_LIMIT')
            image=ImageOps.exif_transpose(self.document).copy()
        # Composite transparency on white, strip input metadata and color profiles.
        try:
            rgba=image.convert('RGBA')
            clean=Image.new('RGB',rgba.size,'white')
            clean.paste(rgba,mask=rgba.getchannel('A'))
            rgba.close()
            return clean
        finally:image.close()

    def recognize(self,index):
        if self.ocr_pages>=self.out.limits['max_ocr_pages']:raise FormatError('OCR_PAGE_LIMIT')
        self.ocr_pages+=1
        if self.ocr is None:
            if not self.out.limits['enable_ocr']:raise FormatError('OCR_UNAVAILABLE')
            available=available_languages(self.out.limits['ocr_models_dir'])
            if not set(self.languages)<=set(available):raise FormatError('OCR_LANGUAGE_UNAVAILABLE')
            from tesserocr import PyTessBaseAPI,OEM,PSM
            self.ocr=self.stack.enter_context(PyTessBaseAPI(path=self.out.limits['ocr_models_dir'],
                       lang='+'.join(self.languages),oem=OEM.LSTM_ONLY,psm=PSM.AUTO))
        with self.image(index) as image:
            self.ocr.SetImage(image)
            text=self.ocr.GetUTF8Text().strip()
            confidence=self.ocr.MeanTextConf()/100 if text else None
            self.ocr.Clear()
        self.used=True
        self.out.warn('OCR_TEXT_REQUIRES_REVIEW')
        if not text:self.out.warn('OCR_NO_TEXT_DETECTED')
        elif confidence<.7:self.out.warn('OCR_LOW_CONFIDENCE')
        before=len(self.out.blocks)
        if text:self.out.prose(text,{'kind':'page','page':index+1})
        for block in self.out.blocks[before:]:block['confidence']=confidence

    def previews(self):
        assets=[]
        count=min(self.count,self.out.limits['max_preview_pages'])
        if count<self.count:self.out.warn('PREVIEW_TRUNCATED')
        # These are sanitized raster thumbnails, never active original PDF/image bytes.
        for index in range(count):
            with self.image(index) as image:
                image.thumbnail((1024,1024))
                buffer=BytesIO()
                image.save(buffer,format='PNG')
                assets.append(('thumbnail','image/png',buffer.getvalue()))
                if sum(len(a[2]) for a in assets)>self.out.limits['max_output_bytes']:raise FormatError('RESULT_LIMIT')
        self.out.warn('PREVIEW_THUMBNAILS_IN_SOURCE_ORDER')
        return assets
