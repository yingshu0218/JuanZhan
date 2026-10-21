"""Apply bounded native rendering limits and deny Internet sockets before exec."""
import ctypes
import ctypes.util
import errno
import os
from pathlib import Path
import platform
import resource
import sys

def restrict():
    if platform.machine() not in ('x86_64','aarch64'):raise RuntimeError('Unsupported sandbox architecture')
    libc=ctypes.CDLL(None,use_errno=True)
    if libc.prctl(38,1,0,0,0)!=0:raise OSError('Cannot disable privilege escalation')
    path=ctypes.util.find_library('seccomp')
    if not path:raise RuntimeError('Network sandbox unavailable')
    library=ctypes.CDLL(path,use_errno=True)
    class Compare(ctypes.Structure):
        _fields_=[('arg',ctypes.c_uint),('op',ctypes.c_int),('a',ctypes.c_uint64),('b',ctypes.c_uint64)]
    library.seccomp_init.argtypes=[ctypes.c_uint32];library.seccomp_init.restype=ctypes.c_void_p
    library.seccomp_syscall_resolve_name.argtypes=[ctypes.c_char_p];library.seccomp_syscall_resolve_name.restype=ctypes.c_int
    library.seccomp_rule_add_array.argtypes=[ctypes.c_void_p,ctypes.c_uint32,ctypes.c_int,ctypes.c_uint,ctypes.POINTER(Compare)]
    library.seccomp_load.argtypes=[ctypes.c_void_p];library.seccomp_release.argtypes=[ctypes.c_void_p]
    context=library.seccomp_init(0x7fff0000)
    if not context:raise RuntimeError('Cannot initialize network sandbox')
    try:
        number=library.seccomp_syscall_resolve_name(b'socket')
        if number<0:raise RuntimeError('Unsupported socket syscall')
        for family in (2,10,17,40):  # IPv4, IPv6, packet and virtual-machine sockets.
            compare=Compare(0,4,family,0)
            if library.seccomp_rule_add_array(context,0x00050000|errno.EPERM,number,1,ctypes.byref(compare))!=0:
                raise RuntimeError('Cannot restrict socket family')
        if library.seccomp_load(context)!=0:raise RuntimeError('Cannot activate network sandbox')
    finally:library.seccomp_release(context)
    resource.setrlimit(resource.RLIMIT_AS,(2*1024**3,2*1024**3))
    resource.setrlimit(resource.RLIMIT_CPU,(60,60))
    resource.setrlimit(resource.RLIMIT_FSIZE,(64*1024**2,64*1024**2))
    resource.setrlimit(resource.RLIMIT_NOFILE,(128,128))
    resource.setrlimit(resource.RLIMIT_CORE,(0,0))

def main():
    root=Path(sys.argv[1]).resolve();extension=sys.argv[2]
    from .office_types import EXTENSIONS
    if extension not in EXTENSIONS.values():return 2
    restrict()
    if extension=='tiff':
        from PIL import Image
        import warnings
        Image.MAX_IMAGE_PIXELS=12000000
        frames=[];pixels=0
        with warnings.catch_warnings():
            warnings.simplefilter('error',Image.DecompressionBombWarning)
            with Image.open(root/'input.tiff') as source:
                if source.n_frames>100:raise ValueError('Too many TIFF pages')
                for index in range(source.n_frames):
                    source.seek(index)
                    pixels+=source.width*source.height
                    if pixels>24000000:raise ValueError('TIFF pixel budget exceeded')
                    frame=source.convert('RGB');frame.load();frames.append(frame)
            if not frames:raise ValueError('Empty TIFF')
            frames[0].save(root/'output'/'input.pdf',format='PDF',save_all=True,append_images=frames[1:],resolution=144)
        for frame in frames:frame.close()
        return 0
    command=['/usr/bin/libreoffice','--headless','--nologo','--nodefault','--nolockcheck','--norestore','--nofirststartwizard',
             '-env:UserInstallation='+(root/'profile').as_uri(),'--convert-to','pdf','--outdir',str(root/'output'),str(root/('input.'+extension))]
    os.execv(command[0],command)

if __name__=='__main__':raise SystemExit(main())
