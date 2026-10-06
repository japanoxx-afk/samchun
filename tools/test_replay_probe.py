"""Native diagnostic-hook invariants; this does not test replay determinism."""
import json,struct,sys
from unicorn import Uc,UC_ARCH_X86,UC_MODE_32
from unicorn.x86_const import *

p=json.load(open(sys.argv[1],encoding='utf-8'))
registers=[UC_X86_REG_EAX,UC_X86_REG_EBX,UC_X86_REG_ECX,UC_X86_REG_EDX,
           UC_X86_REG_ESI,UC_X86_REG_EDI,UC_X86_REG_EBP]
for mode in ['normal','full','busy','extended','uninitialized']:
 u=Uc(UC_ARCH_X86,UC_MODE_32);u.mem_map(p['code_address'],0x100000)
 u.mem_map(0x800000,0x100000);u.mem_map(0x100000,0x100000)
 u.mem_write(p['code_address'],bytes.fromhex(p['code_hex']))
 values=[0x12345678,0x11223344,0x120000,0x44332211,0x170000,0x171000,0x180000]
 for r,v in zip(registers,values):u.reg_write(r,v)
 u.reg_write(UC_X86_REG_ESP,0x190000)
 u.mem_write(0x190000,struct.pack('<II',0xabcdef,0x121000))
 u.mem_write(0x120000,struct.pack('<I',3))
 command=bytes(range(111));u.mem_write(0x121000,command)
 u.mem_write(0x8a1238,struct.pack('<I',77))
 u.mem_map(0x720000,0x10000)
 u.mem_map(0,0x1000) # Unicorn's flat FS base represents the test TEB.
 u.mem_write(0x24,struct.pack('<I',234))
 u.mem_write(0x72de40,struct.pack('<I',65 if mode=='extended' else 2))
 u.mem_write(0x2c,struct.pack('<I',0x122000))
 u.mem_write(0xf94,struct.pack('<I',0x123000))
 u.mem_write(0xe18,struct.pack('<I',0 if mode=='uninitialized' else 0x124000))
 u.mem_write(0x123004,struct.pack('<I',0x124000))
 u.mem_write(0x124014,struct.pack('<I',0x98765432))
 count=p['capacity'] if mode=='full' else 0
 u.mem_write(p['header'],struct.pack('<IIII',count,0,0,int(mode=='busy')))
 u.emu_start(p['code_address'],p['resume'])
 assert [u.reg_read(r) for r in registers]==values
 assert u.reg_read(UC_X86_REG_ESP)==0x190000-0x918
 actual=struct.unpack('<IIII',u.mem_read(p['header'],16))
 if mode in ['normal','extended','uninitialized']:
  assert actual==(1,0,0,0)
  assert bytes(u.mem_read(p['storage'],16))==struct.pack('<IIII',0,77,3,111)
  assert bytes(u.mem_read(p['storage']+p.get('command_offset',16),111))==command
  if p['schema']>=2:
   expected_rng=(234,0,0) if mode=='uninitialized' else (234,0x98765432,1)
   assert struct.unpack('<III',u.mem_read(p['storage']+16,12))==expected_rng
 elif mode=='full':assert actual==(count,1,0,0)
 else:assert actual==(0,0,1,1)
print('PASS: native diagnostic copy, register/stack preservation, explicit overflow/concurrency counters.')
print('Playback/state equality and runtime performance have NOT been tested by this script.')
if p.get('rng_code_address'):
 for mode in ['normal','full','busy']:
  u=Uc(UC_ARCH_X86,UC_MODE_32)
  u.mem_map(p['code_address'],0x400000)
  u.mem_map(0x670000,0x10000);u.mem_map(0x800000,0x100000)
  u.mem_map(0x100000,0x100000);u.mem_map(0,0x1000)
  u.mem_write(p['rng_code_address'],bytes.fromhex(p['rng_code_hex']))
  # Stub only the TLS helper; the original LCG below is executed separately.
  u.mem_write(0x674743,b'\xb8'+struct.pack('<I',0x124000)+b'\xc3')
  for r,v in zip(registers,values):u.reg_write(r,v)
  u.reg_write(UC_X86_REG_ESP,0x190000)
  u.mem_write(0x190000,struct.pack('<I',0x444159))
  u.mem_write(0x24,struct.pack('<I',234))
  u.mem_write(0x124014,struct.pack('<I',0x98765432))
  u.mem_write(0x8a1238,struct.pack('<I',77))
  count=p['rng_capacity'] if mode=='full' else 0
  u.mem_write(p['rng_header'],struct.pack('<IIII',count,0,0,int(mode=='busy')))
  u.emu_start(p['rng_code_address'],p['rng_resume'])
  assert u.reg_read(UC_X86_REG_EAX)==0x124000
  assert [u.reg_read(r) for r in registers[1:]]==values[1:]
  assert u.reg_read(UC_X86_REG_ESP)==0x190000
  assert struct.unpack('<I',u.mem_read(0x124014,4))[0]==0x98765432
  actual=struct.unpack('<IIII',u.mem_read(p['rng_header'],16))
  if mode=='normal':
   assert actual==(1,0,0,0)
   assert struct.unpack('<IIIIII',u.mem_read(p['rng_storage'],24))==(0,77,234,0x124000,0x98765432,0x444159)
  elif mode=='full':assert actual==(count,1,0,0)
  else:assert actual==(0,0,1,1)
 print('PASS: actual RNG-helper return, caller, TLS state and register/stack preservation.')
if p.get('accepted_counter'):
 u=Uc(UC_ARCH_X86,UC_MODE_32)
 u.mem_map(p['code_address'],0x400000);u.mem_map(0x800000,0x100000);u.mem_map(0x100000,0x100000)
 u.mem_write(p['accepted_code_address'],bytes.fromhex(p['accepted_code_hex']))
 for r,v in zip(registers,values):u.reg_write(r,v)
 u.reg_write(UC_X86_REG_ESP,0x190000)
 u.mem_write(0x190010,struct.pack('<I',9));u.mem_write(0x8a1238,struct.pack('<I',77))
 u.emu_start(p['accepted_code_address'],p['accepted_resume'])
 assert u.reg_read(UC_X86_REG_ESP)==0x190000
 assert u.reg_read(UC_X86_REG_ECX)==9 and u.reg_read(UC_X86_REG_EAX)==0
 assert struct.unpack('<III',u.mem_read(p['accepted_counter'],12))==(1,9,77)
 for r,v in zip(registers,values):
  if r not in [UC_X86_REG_EAX,UC_X86_REG_ECX]:assert u.reg_read(r)==v
 assert u.reg_read(UC_X86_REG_EFLAGS)&0x40
 print('PASS: native decode/validation success boundary and displaced instructions.')
