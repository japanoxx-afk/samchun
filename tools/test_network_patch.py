"""Verify the Internet hook reaches native TCP/IP dispatch without stack changes."""
import struct
import pefile
from unicorn import Uc, UC_ARCH_X86, UC_MODE_32
from unicorn.x86_const import UC_X86_REG_ESP, UC_X86_REG_EBP, UC_X86_REG_EAX

for mode in ['host', 'join']:
    pe = pefile.PE('verification/network-' + mode + '.exe')
    u = Uc(UC_ARCH_X86, UC_MODE_32)
    u.mem_map(0x400000, 0x800000)
    u.mem_write(0x400000, pe.get_memory_mapped_image())
    u.reg_write(UC_X86_REG_ESP, 0xb00000)
    u.reg_write(UC_X86_REG_EBP, 0)
    u.emu_start(0x460a29, 0x460e82, count=40)
    read = lambda a: struct.unpack('<I', u.mem_read(a, 4))[0]
    assert read(0x851818) == 0 and read(0x733d70) == 0
    assert read(0x6c7da0) == (0x27 if mode == 'host' else 0x58)
    assert read(0x6c7da4) == 0
    assert u.mem_read(read(0x733d84), 7) == b'Player\0'
    assert u.mem_read(read(0x733d80), 10) == b'127.0.0.1\0'
    assert u.reg_read(UC_X86_REG_ESP) == 0xb00000
    if mode == 'host':
        assert read(0x6c78f4 + 0x27 * 12) == 0xb81400
        u.mem_write(0x4d83f0, bytes.fromhex('b8 01 00 00 00 c3'))
        u.emu_start(0xb81400, 0x4d2450, count=40)
        assert read(0x850dc4) == 1 and read(0x848d15) == 0x3f4
        assert u.reg_read(UC_X86_REG_ESP) == 0xb00000
    else:
        for target in [0x443b70, 0x4e87b0]:
            u.mem_write(target, b'\xc3')
        for branch in [0x4d678b, 0x4d6dc8]:
            u.reg_write(UC_X86_REG_ESP, 0xb00000)
            u.mem_write(0xb00000, struct.pack('<I', 0xb70000))
            u.mem_write(0x733d64, struct.pack('<I', 0))
            u.emu_start(branch, 0xb70000, count=40)
            assert read(0x6c7da0) == 1 and read(0x6c7da4) == 0
            assert read(0x733d64) == 0
            assert u.reg_read(UC_X86_REG_EAX) == 1
            assert u.reg_read(UC_X86_REG_ESP) == 0xb00004
    print(mode, 'deferred menu transition/constructor/stack checks passed')
