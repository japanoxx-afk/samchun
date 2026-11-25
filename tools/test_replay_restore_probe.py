"""Shadow-memory ABI/one-shot checks, not actual game determinism."""
import json,struct,sys
from unicorn import Uc,UC_ARCH_X86,UC_MODE_32
from unicorn.x86_const import *
p=json.load(open(sys.argv[1]));u=Uc(UC_ARCH_X86,UC_MODE_32)
for address,size in [(p['code_address'],0x400000),(0x400000,0x300000),
                     (0x800000,0x100000),(0x100000,0x100000)]:u.mem_map(address,size)
u.mem_write(p['restore_code_address'],bytes.fromhex(p['restore_code_hex']))
if 'restore_order_code_address' in p:
 # The ordering helper has its own executable-memory tests. Isolate restore ABI here.
 u.mem_write(p['restore_order_code_address'],b'\xb8\x01\0\0\0\xc3')
# srand observes its argument and call count, leaving the cdecl stack intact.
u.mem_write(0x671413,b'\x8b\x44\x24\x04\xa3'+struct.pack('<I',0x180100)+
            b'\xff\x05'+struct.pack('<I',0x180104)+b'\xc3')
u.mem_write(p['state_targets']['before'],b'\xff\x05'+struct.pack('<I',0x180108)+b'\xc3')
regs=[UC_X86_REG_EAX,UC_X86_REG_EBX,UC_X86_REG_ECX,UC_X86_REG_EDX,
      UC_X86_REG_ESI,UC_X86_REG_EDI,UC_X86_REG_EBP]
values=[11,22,33,44,55,66,77]
for iteration in range(2):
 for reg,value in zip(regs,values):u.reg_write(reg,value)
 u.reg_write(UC_X86_REG_ESP,0x190000);u.mem_write(0x190000,struct.pack('<I',0x180000))
 u.emu_start(p['restore_code_address'],0x180000,count=1000)
 assert [u.reg_read(r) for r in regs]==values
 assert u.reg_read(UC_X86_REG_ESP)==0x190004
assert struct.unpack('<III',u.mem_read(0x180100,12))==(p['restored_checkpoint']['rng_state'],1,2)
assert struct.unpack('<I',u.mem_read(0x8a1238,4))[0]==p['restored_checkpoint']['native_frame']
print('PASS one-shot frame/seed restore, original drain, native registers/stack; shadow memory only')
