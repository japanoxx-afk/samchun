"""Game-specific, pinned dgVoodoo runtime for 3KD2's Direct3D and Glide paths."""
import hashlib
import os
from pathlib import Path
import sys
import ctypes as c

VERSION = '2.87.6'
HASHES = {
    'DDraw.dll': 'f68cd82bfb585c9b6676c6282b0fac713c9567eae624bc991c5bcfe5881c7bef',
    'D3DImm.dll': '85aa1d15d6880dbe927458f6a045a631264ba128528010b7296ec5c3a640e0ac',
    'Glide2x.dll': 'e629a3a1c82d7fa72fb3c264805c2bc1eb193430ed9483e91ab1db902307c637',
}


def prepare(directory, mode=1):
    source = (Path(sys._MEIPASS) / 'hardware-video' if hasattr(sys, '_MEIPASS')
              else Path(__file__).resolve().parent.parent / 'assets' / 'dgvoodoo')
    relative = Path('samchun-video') / ('dgvoodoo-' + VERSION)
    target = directory / relative
    target.mkdir(parents=True, exist_ok=True)
    for name, expected in HASHES.items():
        data = (source / name).read_bytes()
        if hashlib.sha256(data).hexdigest() != expected:
            raise ValueError('Hardware video component checksum mismatch: ' + name)
        path = target / name
        if not path.exists() or hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            temporary = path.with_suffix('.tmp')
            temporary.write_bytes(data)
            os.replace(temporary, path)
    windowed = c.create_unicode_buffer(32)
    k = c.WinDLL('kernel32')
    k.GetPrivateProfileStringW.argtypes = [c.c_wchar_p,c.c_wchar_p,c.c_wchar_p,c.c_wchar_p,c.c_uint,c.c_wchar_p]
    k.GetPrivateProfileStringW('ddraw','windowed','true',windowed,32,str(directory/'ddraw.ini'))
    fullscreen = windowed.value.lower() != 'true'
    # Keep a desktop-sized Glide render target even when starting windowed:
    # Alt+Enter must not switch the physical desktop to the native 800x600 mode.
    # Voodoo launch also disables DPI virtualization to avoid double scaling.
    voodoo = mode == 3
    config = '''Version = 0x287
[General]
OutputAPI = d3d11_fl11_0
FullScreenMode = %s
ScalingMode = %s
KeepWindowAspectRatio = false
CaptureMouse = true
CenterAppWindow = true
[GeneralExt]
PresentationModel = %s
FullscreenAttributes = %s
[Glide]
VideoCard = voodoo_2
OnboardRAM = 8
MemorySizeOfTMU = 4096
NumberOfTMUs = 2
Resolution = %s
3DfxWatermark = false
3DfxSplashScreen = false
[DirectX]
VideoCard = internal3D
VRAM = 256
Resolution = unforced
dgVoodooWatermark = false
''' % (str(fullscreen).lower(), 'stretched_ar' if voodoo else 'stretched',
       'flip_seq' if voodoo else 'discard', 'fake' if voodoo else '',
       'desktop' if voodoo else 'unforced')
    (target / 'dgVoodoo.conf').write_text(config, encoding='ascii')
    (target / 'README.txt').write_text(
        'dgVoodoo ' + VERSION + ' by Dege. Unmodified x86 components for the 3KD2 game patch.\n'
        'Official source: https://github.com/dege-diosg/dgVoodoo2/releases/tag/2.87.6\n'
        'Documentation and redistribution terms: https://dege.freeweb.hu/dgVoodoo2/ReadmeGeneral/\n', encoding='utf-8')
    return relative, fullscreen
