"""Use the actual Windows Known Folder API, including OneDrive redirects."""
from __future__ import annotations
import os,sys,uuid
from pathlib import Path
FOLDERS={'desktop':'B4BFCC3A-DB2C-424C-B029-7FE99A87C641',
         'documents':'FDD39AD0-238F-46AF-ADB4-6C85480369C7',
         'downloads':'374DE290-123F-4565-9164-39C4925E467B'}

def known_folder(name:str)->Path:
    if name not in FOLDERS:raise ValueError('Unknown Windows known folder')
    if sys.platform!='win32':raise OSError('Windows known-folder API requires Windows')
    import ctypes
    from ctypes import wintypes
    class GUID(ctypes.Structure):
        _fields_=[('Data1',wintypes.DWORD),('Data2',wintypes.WORD),('Data3',wintypes.WORD),('Data4',ctypes.c_ubyte*8)]
    raw=uuid.UUID(FOLDERS[name]).bytes_le
    ident=GUID.from_buffer_copy(raw)
    result=ctypes.c_wchar_p()
    shell=ctypes.windll.shell32
    hr=shell.SHGetKnownFolderPath(ctypes.byref(ident),0,None,ctypes.byref(result))
    if hr!=0:raise OSError(f'SHGetKnownFolderPath failed HRESULT 0x{hr&0xffffffff:08X}')
    try:folder=Path(result.value).resolve(strict=True)
    finally:ctypes.windll.ole32.CoTaskMemFree(ctypes.cast(result,ctypes.c_void_p))
    if not folder.is_dir():raise FileNotFoundError('Windows known folder unavailable')
    return folder
