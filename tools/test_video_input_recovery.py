"""Execute native DirectInput wrappers with mocked COM methods."""
import struct
from pathlib import Path
import pefile
from unicorn import Uc, UC_ARCH_X86, UC_MODE_32, UC_HOOK_CODE
from unicorn.x86_const import *
from video_runtime import install_input_recovery, install_input_wakeup

def run(base):
    data = bytearray(Path(base).read_bytes())
    install_input_recovery(data, {})
    pe = pefile.PE(data=bytes(data))
    cases = [(0, 0, 0), (0x8007001e, 0, 0), (0x8007000c, 0, 0),
             (0x8007000c, 0x80070005, 0), (0x8007001e, 0, 0x8007000c),
             (0x80070057, 0, 0)]
    for buffered in (False, True):
        for first, acquire, second in cases:
            u = Uc(UC_ARCH_X86, UC_MODE_32)
            u.mem_map(0x400000, (pe.OPTIONAL_HEADER.SizeOfImage+4095)&~4095)
            for s in pe.sections:
                u.mem_write(0x400000+s.VirtualAddress, bytes(data[s.PointerToRawData:s.PointerToRawData+s.SizeOfRawData]))
            u.mem_map(0x20000000, 0x10000)
            sp, stop, obj, dev, vt, buf, count = [0x20000000+x for x in (0x8000, 0x100, 0x1000, 0x1100, 0x1200, 0x2000, 0x3000)]
            read, acq = 0x20000400, 0x20000500
            put = lambda a, v: u.mem_write(a, struct.pack('<I', v))
            put(obj+4, 1); put(obj+0x18, dev); put(dev, vt)
            put(vt+0x28 if buffered else vt+0x24, read); put(vt+0x1c, acq)
            put(count, 17)
            args = [16, buf, count, 1] if buffered else [16, buf]
            u.mem_write(sp, struct.pack('<'+'I'*(len(args)+1), stop, *args))
            u.reg_write(UC_X86_REG_ESP, sp); u.reg_write(UC_X86_REG_ECX, obj)
            preserved = [UC_X86_REG_EBX, UC_X86_REG_EBP, UC_X86_REG_ESI, UC_X86_REG_EDI]
            for i, r in enumerate(preserved): u.reg_write(r, 0x1230+i)
            seen = []
            def hook(uc, address, size, unused):
                esp = uc.reg_read(UC_X86_REG_ESP)
                if address == stop: uc.emu_stop(); return
                if address not in (read, acq): return
                n = 1 if address == acq else (5 if buffered else 3)
                actual = list(struct.unpack('<'+'I'*n, uc.mem_read(esp+4, n*4)))
                assert actual == ([dev] if address == acq else [dev]+args), actual
                result = acquire if address == acq else (second if 'read' in seen else first)
                seen.append('acquire' if address == acq else 'read')
                uc.reg_write(UC_X86_REG_EAX, result)
                ret = struct.unpack('<I', uc.mem_read(esp, 4))[0]
                uc.reg_write(UC_X86_REG_ESP, esp+4+n*4); uc.reg_write(UC_X86_REG_EIP, ret)
            u.hook_add(UC_HOOK_CODE, hook)
            u.emu_start(0x590c80 if buffered else 0x590ce0, stop, count=300)
            expected = ['read']
            result = first
            if first in (0x8007001e, 0x8007000c):
                expected.append('acquire'); result = acquire
                if acquire < 0x80000000: expected.append('read'); result = second
            assert seen == expected, seen
            assert u.reg_read(UC_X86_REG_EIP) == stop
            assert u.reg_read(UC_X86_REG_ESP) == sp+4+len(args)*4
            for i, r in enumerate(preserved): assert u.reg_read(r) == 0x1230+i
            if buffered and result >= 0x80000000: assert bytes(u.mem_read(count, 4)) == bytes(4)
            if not buffered: assert u.reg_read(UC_X86_REG_EAX) == int(result < 0x80000000)
    print('PASS: 12 native recovery cases; bounded retry, error handling, zero stale events, COM arguments, stack and registers')
    install_input_wakeup(data, {})
    pe = pefile.PE(data=bytes(data))
    for result in (0, 258, 0xffffffff, 128):
        for enabled, inactive in ((1, 0), (0, 0), (1, 1)):
            u = Uc(UC_ARCH_X86, UC_MODE_32)
            u.mem_map(0x400000, (pe.OPTIONAL_HEADER.SizeOfImage+4095)&~4095)
            for s in pe.sections:
                u.mem_write(0x400000+s.VirtualAddress, bytes(data[s.PointerToRawData:s.PointerToRawData+s.SizeOfRawData]))
            u.mem_map(0x20000000, 0x10000)
            sp, obj, vt, wait, callback = [0x20000000+x for x in (0x8000, 0x1000, 0x1200, 0x400, 0x500)]
            put = lambda a, v: u.mem_write(a, struct.pack('<I', v))
            put(obj, vt); put(obj+8, enabled); put(vt+4, callback)
            put(0x838b14, inactive); put(0x6822cc, wait)
            u.mem_write(sp, struct.pack('<II', 0, obj)); u.reg_write(UC_X86_REG_ESP, sp)
            seen=[]
            def wake_hook(uc, address, size, unused):
                esp=uc.reg_read(UC_X86_REG_ESP)
                if address == wait:
                    assert list(struct.unpack('<4I', uc.mem_read(esp+4, 16))) == [1, obj+16, 0, 100]
                    if seen.count('wait'):
                        uc.emu_stop();return
                    seen.append('wait'); uc.reg_write(UC_X86_REG_EAX, result)
                    ret=struct.unpack('<I', uc.mem_read(esp, 4))[0]
                    uc.reg_write(UC_X86_REG_ESP,esp+20);uc.reg_write(UC_X86_REG_EIP,ret)
                elif address == callback:
                    assert uc.reg_read(UC_X86_REG_ECX)==obj
                    seen.append('dispatch')
                    ret=struct.unpack('<I', uc.mem_read(esp,4))[0]
                    uc.reg_write(UC_X86_REG_ESP,esp+4);uc.reg_write(UC_X86_REG_EIP,ret)
            u.hook_add(UC_HOOK_CODE,wake_hook);u.emu_start(0x590e70,0,count=150)
            assert seen==(['wait','dispatch'] if result in (0,258) and enabled and not inactive else ['wait']),seen
    print('PASS: 12 event-wait cases; 100ms timeout; no background, disabled or failed-wait dispatch')

if __name__ == '__main__':
    import sys
    run(sys.argv[1])
