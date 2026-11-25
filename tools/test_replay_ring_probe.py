"""Native wrap/stop invariants in shadow memory; not a performance/game test."""
import json,struct,sys
from unicorn import Uc,UC_ARCH_X86,UC_MODE_32
from unicorn.x86_const import *
p=json.load(open(sys.argv[1]));assert p['ring_buffers']
u=Uc(UC_ARCH_X86,UC_MODE_32)
for address,size in [(p['code_address'],0x400000),(0x400000,0x400000),
                     (0x800000,0x100000),(0x100000,0x100000),(0,0x10000)]:u.mem_map(address,size)
for address,code in [('code_address','code_hex'),('rng_code_address','rng_code_hex'),('state_code_address','state_code_hex')]:
 u.mem_write(p[address],bytes.fromhex(p[code]))
u.mem_write(0x8a1238,struct.pack('<I',77))
u.mem_write(0x120000,struct.pack('<I',0))
command=bytes(range(111));u.mem_write(0x121000,command)
u.mem_write(0x674743,b'\xb8'+struct.pack('<I',0x123000)+b'\xc3')
u.mem_write(0x123014,struct.pack('<I',42))
u.mem_write(0x44c200,b'\xff\x05'+struct.pack('<I',0x180100)+b'\xc3')
u.mem_write(0x6c3edc,struct.pack('<I',4));u.mem_write(0x838c98,struct.pack('<I',0x124000))
for stop in [0,1]:
 u.mem_write(p['header']+48,struct.pack('<I',stop))
 if stop==0:
  for key,cap in [('header','capacity'),('rng_header','rng_capacity'),('state_header','state_capacity')]:
   u.mem_write(p[key],struct.pack('<I',p[cap]))
 u.reg_write(UC_X86_REG_ECX,0x120000);u.reg_write(UC_X86_REG_ESP,0x190000)
 u.mem_write(0x190000,struct.pack('<II',0x180000,0x121000))
 u.emu_start(p['code_address'],p['resume'],count=10000)
 assert struct.unpack('<I',u.mem_read(p['header'],4))[0]==p['capacity']+1
 assert struct.unpack('<I',u.mem_read(p['storage'],4))[0]==p['capacity']
 assert bytes(u.mem_read(p['storage']+32,111))==command
 u.reg_write(UC_X86_REG_ESP,0x190000);u.mem_write(0x190000,struct.pack('<I',0x180000))
 u.emu_start(p['rng_code_address'],p['rng_resume'],count=10000)
 assert struct.unpack('<I',u.mem_read(p['rng_header'],4))[0]==p['rng_capacity']+1
 assert struct.unpack('<I',u.mem_read(p['rng_storage'],4))[0]==p['rng_capacity']
 u.reg_write(UC_X86_REG_ESP,0x190000);u.mem_write(0x190000,struct.pack('<I',0x180000))
 u.emu_start(p['state_targets']['before'],0x180000,count=100000)
 assert struct.unpack('<I',u.mem_read(p['state_header'],4))[0]==p['state_capacity']+1
 assert struct.unpack('<I',u.mem_read(p['state_storage'],4))[0]==p['state_capacity']
assert struct.unpack('<I',u.mem_read(0x180100,4))[0]==2
print('PASS command/RNG/state wrap with monotonic sequences; stop seals all streams while original native drain still runs')
