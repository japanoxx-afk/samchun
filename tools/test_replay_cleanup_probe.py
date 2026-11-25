"""Native cleanup boundary shadow tests; not a live-game exit test."""
import json,struct,sys
from unicorn import Uc,UC_ARCH_X86,UC_MODE_32
from unicorn.x86_const import *
p=json.load(open(sys.argv[1]))
for mode in ['active','loading','already-ended']:
    u=Uc(UC_ARCH_X86,UC_MODE_32)
    for a,s in [(p['code_address'],0x400000),(0x400000,0x400000),(0x800000,0x100000),(0x100000,0x100000)]:u.mem_map(a,s)
    u.mem_write(p['cleanup_code_address'],bytes.fromhex(p['cleanup_code_hex']))
    u.mem_write(0x583760,b'\xa1'+struct.pack('<I',p['header']+48)+b'\xa3'+struct.pack('<I',0x180100)+b'\xb8\xef\xbe\xad\xde\xc3')
    for a,v in [(p['state_header'],0 if mode=='loading' else 2),(p['header']+48,int(mode=='already-ended')),
                (0x8a1238,100),(0x733d64,0),(0x8578cc,55)]:u.mem_write(a,struct.pack('<I',v))
    u.reg_write(UC_X86_REG_ESP,0x190000);u.reg_write(UC_X86_REG_EBX,123)
    u.mem_write(0x190000,struct.pack('<I',0x180000))
    u.emu_start(p['cleanup_code_address'],0x180000,count=1000)
    assert u.reg_read(UC_X86_REG_EAX)==0xdeadbeef
    assert u.reg_read(UC_X86_REG_EBX)==123 and u.reg_read(UC_X86_REG_ESP)==0x190004
    assert struct.unpack('<I',u.mem_read(p['end_transition_header'],4))[0]==int(mode=='active')
    assert struct.unpack('<I',u.mem_read(0x180100,4))[0]==int(mode!='loading')
    if mode=='active':assert struct.unpack('<I',u.mem_read(p['end_transition_header']+16,4))[0]==2
print('PASS seal before native cleanup, preserve ABI, ignore initial load and duplicate end')
