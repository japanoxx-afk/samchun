"""Shadow-RAM checks only; native save restoration still needs a game test."""
import json,struct,sys
from unicorn import Uc,UC_ARCH_X86,UC_MODE_32
from unicorn.x86_const import *
p=json.load(open(sys.argv[1]))
u=Uc(UC_ARCH_X86,UC_MODE_32)
for address,size in [(p['code_address'],0x400000),(0x400000,0x400000),(0x800000,0x100000),(0x100000,0x100000),(0,0x10000)]:u.mem_map(address,size)
u.mem_write(0x682178,struct.pack('<II',0x180500,0x180500));u.mem_write(0x180500,b'\xc2\x04\x00')
u.mem_write(0x43a7d0,b'\xb8'+struct.pack('<I',0x180200)+b'\xc3')
u.mem_write(0x180200,struct.pack('<I',3))
u.mem_write(0x72de40,struct.pack('<I',0))
u.mem_write(0xe10,struct.pack('<I',0x180300))
u.mem_write(0x180314,struct.pack('<I',0x12345678))
u.mem_write(0x8a1238,struct.pack('<I',4604))
u.mem_write(p['initial_save_code_address'],bytes.fromhex(p['initial_save_code_hex']))
u.mem_write(0x4ff390,b'\xff\x05'+struct.pack('<I',0x180000)+b'\xb8\x01\x00\x00\x00\xc3')
if p.get('order_capture_code_address'):u.mem_write(p['order_capture_code_address'],b'\xe9'+struct.pack('<i',p['state_targets']['before']-p['order_capture_code_address']-5))
u.mem_write(p['state_targets']['before'],b'\xff\x05'+struct.pack('<I',0x180004)+b'\xc3')
if p.get('initial_save_normalize'):
 u.mem_write(0x671413,b'\xc3')
 u.mem_write(p['normalize_after_guard'],bytes.fromhex(p['normalize_after_code_hex']))
 u.mem_write(p['state_targets']['after'],b'\xff\x05'+struct.pack('<I',0x180008)+b'\xc3')
 u.mem_write(p['normalize_load_complete'],bytes.fromhex(p['normalize_load_code_hex']))
 u.mem_write(0x4ff6b0,b'\x8b\x44\x24\x04\xa3'+struct.pack('<I',0x180010)+b'\xb8\x01\x00\x00\x00\xc3')
regs=[UC_X86_REG_EAX,UC_X86_REG_EBX,UC_X86_REG_ECX,UC_X86_REG_EDX,UC_X86_REG_ESI,UC_X86_REG_EDI,UC_X86_REG_EBP]
values=[11,22,33,44,55,66,77]
for iteration in range(2):
 if iteration==1 and p.get('initial_save_normalize'):
  u.reg_write(UC_X86_REG_ESP,0x190000)
  u.mem_write(0x190000,struct.pack('<II',0x180100,0x135000))
  u.emu_start(p['normalize_load_complete'],0x180100,count=1000)
  assert u.reg_read(UC_X86_REG_ESP)==0x190004
  assert u.reg_read(UC_X86_REG_EAX)==1
  assert struct.unpack('<I',u.mem_read(0x180010,4))[0]==0x135000
  assert struct.unpack('<I',u.mem_read(p['initial_save_header'],4))[0]==3
 for reg,value in zip(regs,values):u.reg_write(reg,value)
 u.reg_write(UC_X86_REG_ESP,0x190000);u.mem_write(0x190000,struct.pack('<I',0x180100))
 u.emu_start(p['initial_save_code_address'],0x180100,count=1000)
 assert [u.reg_read(reg) for reg in regs]==values
 assert u.reg_read(UC_X86_REG_ESP)==0x190004
 if p.get('initial_save_normalize'):
  u.reg_write(UC_X86_REG_ESP,0x190000);u.mem_write(0x190000,struct.pack('<I',0x180100))
  u.emu_start(p['normalize_after_guard'],0x180100,count=1000)
assert struct.unpack('<II',u.mem_read(0x180000,8))==(1,1 if p.get('initial_save_normalize') else 2)
assert struct.unpack('<II',u.mem_read(p['initial_save_header'],8))==((4 if p.get('initial_save_normalize') else 2),1)
if p.get('initial_save_normalize'):assert struct.unpack('<I',u.mem_read(0x180008,4))[0]==1
assert struct.unpack('<IIII',u.mem_read(p['initial_save_header']+8,16))==(4604,0x12345678,1,3)
print('PASS one initial save, every native drain, registers/stack; not an actual save/load test')
if p.get('initial_save_normalize'):
 for mode,save_result in ([(1,1),(3,0)] if p.get('initial_save_multiplayer') else [(2,1),(1,1),(3,0)]):
  v=Uc(UC_ARCH_X86,UC_MODE_32)
  for address,size in [(p['code_address'],0x400000),(0x400000,0x400000),(0x800000,0x100000),(0x100000,0x100000)]:v.mem_map(address,size)
  v.mem_write(0x682178,struct.pack('<II',0x180500,0x180500));v.mem_write(0x180500,b'\xc2\x04\x00')
  v.mem_write(p['initial_save_code_address'],bytes.fromhex(p['initial_save_code_hex']))
  v.mem_write(0x43a7d0,b'\xb8'+struct.pack('<I',0x180200)+b'\xc3')
  v.mem_write(0x180200,struct.pack('<I',mode))
  v.mem_write(0x4ff390,b'\xff\x05'+struct.pack('<I',0x180000)+b'\xb8'+struct.pack('<I',save_result)+b'\xc3')
  if p.get('order_capture_code_address'):v.mem_write(p['order_capture_code_address'],b'\xe9'+struct.pack('<i',p['state_targets']['before']-p['order_capture_code_address']-5))
  v.mem_write(p['state_targets']['before'],b'\xff\x05'+struct.pack('<I',0x180004)+b'\xc3')
  v.reg_write(UC_X86_REG_ESP,0x190000);v.mem_write(0x190000,struct.pack('<I',0x180100))
  v.emu_start(p['initial_save_code_address'],0x180100,count=1000)
  assert struct.unpack('<I',v.mem_read(p['initial_save_header'],4))[0]==0xffffffff
  assert struct.unpack('<I',v.mem_read(p['header']+48,4))[0]==1
  assert struct.unpack('<II',v.mem_read(0x180000,8))==(int(mode==3),1)
  assert struct.unpack('<I',v.mem_read(0x733d64,4))[0]==0
 print('PASS unsupported multiplayer/campaign and failed save leave native gameplay running without normalization')

if p.get('initial_save_multiplayer'):
 v=Uc(UC_ARCH_X86,UC_MODE_32)
 for a,size in [(p['code_address'],0x400000),(0x400000,0x400000),(0x800000,0x100000),(0x100000,0x100000),(0,0x10000)]:v.mem_map(a,size)
 v.mem_write(0x682178,struct.pack('<II',0x180500,0x180500));v.mem_write(0x180500,b'\xc2\x04\x00')
 v.mem_write(p['initial_save_code_address'],bytes.fromhex(p['initial_save_code_hex']))
 v.mem_write(0x43a7d0,b'\xb8'+struct.pack('<I',0x180200)+b'\xc3');v.mem_write(0x180200,struct.pack('<I',2))
 v.mem_write(0x4ff390,b'\xb8\x01\0\0\0\xc3')
 if p.get('order_capture_code_address'):v.mem_write(p['order_capture_code_address'],b'\xe9'+struct.pack('<i',p['state_targets']['before']-p['order_capture_code_address']-5))
 v.mem_write(p['state_targets']['before'],b'\xc3')
 v.mem_write(0xe10,struct.pack('<I',0x180300));v.mem_write(0x180314,struct.pack('<I',0x12345678))
 for a,value in [(0x8a1238,45),(0x837f24,7),(0x6a455c,44)]:v.mem_write(a,struct.pack('<I',value))
 v.reg_write(UC_X86_REG_ESP,0x190000);v.mem_write(0x190000,struct.pack('<I',0x180100))
 v.emu_start(p['initial_save_code_address'],0x180100,count=2000)
 assert struct.unpack('<I',v.mem_read(p['initial_save_header'],4))[0]==4
 for a,value in [(0x8a1238,45),(0x837f24,7),(0x6a455c,44),(0x180314,0x12345678)]:assert struct.unpack('<I',v.mem_read(a,4))[0]==value
 assert struct.unpack('<I',v.mem_read(0x733d64,4))[0]==0
 print('PASS network checkpoint does not LOAD, reseed, pause or change simulation frame')
