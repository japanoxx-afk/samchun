"""Recorder rearm ABI tests in shadow RAM; not live multiplayer verification."""
import json,struct,sys
from unicorn import Uc,UC_ARCH_X86,UC_MODE_32
from unicorn.x86_const import *
p=json.load(open(sys.argv[1]))
for cleanup,ready in [(0,0),(0,1),(1,0),(1,1)]:
 u=Uc(UC_ARCH_X86,UC_MODE_32)
 for a,size in [(p['code_address'],0x400000),(0x400000,0x400000),(0x100000,0x100000)]:u.mem_map(a,size)
 u.mem_write(0x6822e0,struct.pack('<I',0x180500));u.mem_write(0x180500,b'\x31\xc0\xc3')
 u.mem_write(p['session_code_address'],bytes.fromhex(p['session_code_hex']))
 u.mem_write(0x444250,b'\xff\x05'+struct.pack('<I',0x180000)+b'\xb8\x2a\0\0\0\xc3')
 def put(a,v):u.mem_write(a,struct.pack('<I',v))
 def get(a):return struct.unpack('<I',u.mem_read(a,4))[0]
 put(p['session_cleanup_complete_address'],cleanup);put(p['session_ready_address'],ready)
 put(p['session_ack_address'],1);put(p['session_generation_address'],9);put(p['initial_save_header'],4);put(p['header']+48,1)
 u.reg_write(UC_X86_REG_ESP,0x190000);put(0x190000,0x180100);u.reg_write(UC_X86_REG_EBX,123)
 u.emu_start(p['session_code_address'],0x180100,count=1000)
 assert get(0x180000)==1 and u.reg_read(UC_X86_REG_EAX)==42
 assert u.reg_read(UC_X86_REG_ESP)==0x190004 and u.reg_read(UC_X86_REG_EBX)==123
 armed=cleanup and ready
 assert get(p['session_generation_address'])==9+int(armed)
 assert get(p['initial_save_header'])==(0 if armed else 4)
 assert get(p['header']+48)==(0 if armed else 1)
 assert get(p['session_cleanup_complete_address'])==0
print('PASS only rearm after completed cleanup + READY; preserve native initializer ABI')

from unicorn import UC_HOOK_CODE
for release in [False,True]:
 u=Uc(UC_ARCH_X86,UC_MODE_32)
 for a,size in [(p['code_address'],0x400000),(0x400000,0x400000),(0x100000,0x100000)]:u.mem_map(a,size)
 def put(a,v):u.mem_write(a,struct.pack('<I',v))
 def get(a):return struct.unpack('<I',u.mem_read(a,4))[0]
 u.mem_write(p['session_code_address'],bytes.fromhex(p['session_code_hex']))
 put(0x6822e0,0x180500);put(0x682180,0x180520)
 u.mem_write(0x180500,bytes.fromhex('a10000180005f4010000a300001800c3'))
 u.mem_write(0x180520,bytes.fromhex('c20400'));u.mem_write(0x444250,bytes.fromhex('b82a000000c3'))
 put(p['session_cleanup_complete_address'],1);put(p['session_ready_address'],1);put(p['session_generation_address'],9)
 put(p['initial_save_header'],4);put(p['header']+48,1)
 sleeps=[]
 def hook(u,address,size,user):
  if address==0x180520:
   sleeps.append(1)
   if release and len(sleeps)==3:put(p['session_ack_address'],1)
 u.hook_add(UC_HOOK_CODE,hook)
 u.reg_write(UC_X86_REG_ESP,0x190000);put(0x190000,0x180100)
 u.emu_start(p['session_code_address'],0x180100,count=10000)
 assert get(p['session_generation_address'])==(10 if release else 9)
 assert get(p['session_failure_address'])==(0 if release else 1)
 assert u.reg_read(UC_X86_REG_EAX)==42 and u.reg_read(UC_X86_REG_ESP)==0x190004
 assert len(sleeps)==(3 if release else 4)
print('PASS wait only between worlds until reader ACK, bounded wall-clock timeout, native initializer still returns safely')
