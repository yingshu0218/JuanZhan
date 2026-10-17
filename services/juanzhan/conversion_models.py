"""Converter wire contract, also validated by the Archive-side client."""
from typing import Annotated, Any, Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator

ID = Annotated[str, Field(pattern=r'^[A-Za-z0-9_-]{1,128}$')]
Ref = Annotated[str, Field(pattern=r'^[0-9a-f]{32}$')]


class Wire(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True, allow_inf_nan=False)


class Options(Wire):
    file_revision_id: ID
    parse_run_id: ID
    declared_mime: Annotated[str, Field(max_length=255)] = ''
    ocr_enabled: bool = False
    ocr_languages: Annotated[str, Field(max_length=255)] = ''
    generate_preview: bool = True


class Locator(Wire):
    kind: Literal['page', 'section', 'character', 'epub', 'unknown']
    page: Annotated[int, Field(ge=1)] | None = None
    spine_index: Annotated[int, Field(ge=0)] | None = None
    href: str | None = None
    heading_path: list[str] | None = None
    start: Annotated[int, Field(ge=0)] | None = None
    end: Annotated[int, Field(ge=0)] | None = None

    @model_validator(mode='after')
    def position(self):
        if self.kind == 'page' and self.page is None:
            raise ValueError('Page locator requires a page')
        if self.kind == 'character' and (self.start is None or self.end is None or self.end < self.start):
            raise ValueError('Character locator requires an ordered range')
        if self.kind == 'epub' and (self.spine_index is None or self.href is None):
            raise ValueError('EPUB locator requires chapter identity')
        return self


class Table(Wire):
    headers: list[str] = []
    rows: list[list[str]] = []


class Block(Wire):
    id: ID
    index: Annotated[int, Field(ge=0)]
    type: Literal['heading', 'paragraph', 'list_item', 'table', 'image', 'page_break', 'unknown']
    text: str
    locator: Locator
    level: Annotated[int, Field(ge=1, le=6)] | None = None
    table: Table | None = None
    confidence: Annotated[float, Field(ge=0, le=1)] | None = None


class Candidate(Wire):
    key: str
    value: Any
    source: Literal['document_properties', 'parsed_content', 'ocr', 'epub_manifest', 'html_meta']
    confidence: Annotated[float, Field(ge=0, le=1)] | None = None
    locator: Locator | None = None


class Artifact(Wire):
    kind: Literal['plain_text', 'markdown', 'json', 'preview_pdf', 'thumbnail', 'image']
    media_type: str
    artifact_ref: Ref
    sha256: Annotated[str, Field(pattern=r'^[0-9a-f]{64}$')]
    size_bytes: Annotated[int, Field(ge=0)]


class Parser(Wire):
    name: str
    version: str


class Extraction(Wire):
    text_available: bool
    ocr_used: bool
    ocr_languages: list[str]


class ParseResult(Wire):
    schema_version: Literal['1.0']
    file_revision_id: ID
    parse_run_id: ID
    source_mime: str
    parser: Parser
    status: Literal['completed', 'unsupported', 'failed']
    language: str | None = None
    page_count: Annotated[int, Field(ge=1)] | None = None
    extraction: Extraction
    blocks: Annotated[list[Block], Field(max_length=10000)]
    metadata_candidates: Annotated[list[Candidate], Field(max_length=1000)]
    artifacts: Annotated[list[Artifact], Field(max_length=100)]
    warnings: Annotated[list[str], Field(max_length=1000)]

    @model_validator(mode='after')
    def sequence(self):
        if [b.index for b in self.blocks] != list(range(len(self.blocks))):
            raise ValueError('Blocks must have contiguous ordered indices')
        for values in ([b.id for b in self.blocks], [a.artifact_ref for a in self.artifacts]):
            if len(set(values)) != len(values):
                raise ValueError('Duplicate result identity')
        return self
