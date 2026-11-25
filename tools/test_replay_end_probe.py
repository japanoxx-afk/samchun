"""End-boundary ABI/ordering checks in shadow memory only."""
import json,struct,sys
from unicorn import Uc,UC_ARCH_X86,UC_MODE_32
from unicorn.x86_const import *
p=json.load(open(sys.argv[1]));u=Uc(UC_ARCH_X86,UC_MODE_32)
for address,size in [(p['code_address'],0x400000),(0x400000,0x400000),
                     (0x800000,0x100000),(0x100000,0x100000)]:u.mem_map(address,size)
u.mem_write(p['end_transition_code_address'],bytes.fromhex(p['end_transition_code_hex']))
# Capture observes the forced-final-sample flag and phase before the native
# result-screen call; result-screen RNG sees the stopped stream afterwards.
u.mem_write(p['state_targets']['sample'],b'\x89\x1d'+struct.pack('<I',0x180100)+
            b'\xa1'+struct.pack('<I',p['state_header']+44)+b'\xa3'+struct.pack('<I',0x180104)+b'\xc3')
u.mem_write(0x45fbb0,b'\xa1'+struct.pack('<I',p['header']+48)+b'\xa3'+struct.pack('<I',0x180108)+b'\xb8\xef\xbe\xad\xde\xc3')
for addr,value in [(0x8a1238,1501),(0x733d64,7),(0x8578cc,0)]:u.mem_write(addr,struct.pack('<I',value))
u.reg_write(UC_X86_REG_EBX,123);u.reg_write(UC_X86_REG_ESP,0x190000)
u.mem_write(0x190000,struct.pack('<I',0x180000))
u.emu_start(p['end_transition_code_address'],0x180000,count=10000)
assert u.reg_read(UC_X86_REG_ESP)==0x190004 and u.reg_read(UC_X86_REG_EBX)==123
assert u.reg_read(UC_X86_REG_EAX)==0xdeadbeef
assert struct.unpack('<III',u.mem_read(0x180100,12))==(1,1,1)
assert struct.unpack('<IIII',u.mem_read(p['end_transition_header'],16))==(1,1501,7,0)
print('PASS forced final state, stop before result screen, native return value/registers/stack; not an actual match end test')
