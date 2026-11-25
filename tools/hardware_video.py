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
    def ini_int(key):
        buf = c.create_unicode_buffer(16)
        k.GetPrivateProfileStringW('ddraw', key, '', buf, 16, str(directory/'ddraw.ini'))
        try:
            return int(buf.value)
        except ValueError:
            return 0
    # Keep a desktop-sized Glide render target even when starting windowed:
    # Alt+Enter must not switch the physical desktop to the native 800x600 mode.
    # Voodoo launch also disables DPI virtualization to avoid double scaling.
    voodoo = mode == 3
    # Windowed Voodoo: a desktop-sized Glide target made the window (client area +
    # title bar) taller than the screen, so the bottom of the game was cut off - also
    # after Alt+Enter, which keeps the window's position. Size the window to fit the
    # work area instead (launcher resolution, same aspect, never larger than the screen).
    glide_resolution = 'desktop' if voodoo else 'unforced'
    if voodoo and not fullscreen:
        fitted = window_fit(ini_int('width'), ini_int('height'))
        if fitted:
            glide_resolution = '%dx%d' % fitted
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
       glide_resolution)
    (target / 'dgVoodoo.conf').write_text(config, encoding='ascii')
    (target / 'README.txt').write_text(
        'dgVoodoo ' + VERSION + ' by Dege. Unmodified x86 components for the 3KD2 game patch.\n'
        'Official source: https://github.com/dege-diosg/dgVoodoo2/releases/tag/2.87.6\n'
        'Documentation and redistribution terms: https://dege.freeweb.hu/dgVoodoo2/ReadmeGeneral/\n', encoding='utf-8')
    return relative, fullscreen


def window_fit(width, height):
    """Largest (w, h) with the launcher's aspect ratio whose window (title bar and frame
    included) fits the primary monitor's work area, in physical pixels; None if unknown."""
    try:
        u = c.WinDLL('user32')
        class RECT(c.Structure):
            _fields_ = [('l', c.c_int32), ('t', c.c_int32), ('r', c.c_int32), ('b', c.c_int32)]
        W, U = c.c_uint16, c.c_uint32   # DEVMODEW: 220 bytes, dmPelsWidth at 172
        class DEVMODE(c.Structure):
            _fields_ = [('name', W*32), ('spec', W), ('drv', W), ('size', W), ('extra', W), ('fields', U),
                        ('pos', c.c_int32*2), ('orient', U), ('fixed', U), ('color', c.c_short), ('duplex', c.c_short),
                        ('yres', c.c_short), ('tt', c.c_short), ('collate', c.c_short), ('form', W*32), ('logpix', W),
                        ('bpp', U), ('w', U), ('h', U), ('flags', U), ('freq', U), ('icm', U*4), ('res', U*2), ('pan', U*2)]
        mode = DEVMODE(); mode.size = c.sizeof(DEVMODE)
        work = RECT()
        if not u.EnumDisplaySettingsW(None, -1, c.byref(mode)) or not u.SystemParametersInfoW(0x30, 0, c.byref(work), 0):
            return None
        logical_w = u.GetSystemMetrics(0) or 1
        scale = mode.w / logical_w           # this process may be DPI-virtualized; the game is DPI aware
        frame_x = (u.GetSystemMetrics(32) + u.GetSystemMetrics(92)) * 2
        frame_y = frame_x + u.GetSystemMetrics(4)
        max_w = int(((work.r - work.l) - frame_x) * scale) - 8
        max_h = int(((work.b - work.t) - frame_y) * scale) - 8
    except (OSError, AttributeError, ValueError):
        return None
    if max_w < 320 or max_h < 240:
        return None
    if width < 320 or height < 240:
        width, height = 4 * max_h // 3, max_h
    factor = min(1.0, max_w / width, max_h / height)
    w, h = int(width * factor) // 2 * 2, int(height * factor) // 2 * 2
    return (w, h) if w >= 320 and h >= 240 else None
