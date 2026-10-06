"""Check state-hook boundaries and stable partial checksum in shadow RAM."""
import json,struct,sys
from unicorn import Uc,UC_ARCH_X86,UC_MODE_32
from unicorn.x86_const import *
p=json.load(open(sys.argv[1],encoding='utf-8'))
regs=[UC_X86_REG_EAX,UC_X86_REG_EBX,UC_X86_REG_ECX,UC_X86_REG_EDX,
      UC_X86_REG_ESI,UC_X86_REG_EDI,UC_X86_REG_EBP]
for phase in ['before','after']:
 u=Uc(UC_ARCH_X86,UC_MODE_32)
 for address,size in [(p['code_address'],0x400000),(0x400000,0x300000),
                      (0x800000,0x100000),(0x100000,0x100000)]:u.mem_map(address,size)
 u.mem_write(p['state_code_address'],bytes.fromhex(p['state_code_hex']))
 target=0x44c200 if phase=='before' else 0x502340
 # Stub verifies that the original callee is still invoked exactly once.
 u.mem_write(target,b'\xff\x05'+struct.pack('<I',0x180100)+b'\xb8\xef\xbe\xad\xde\xc3')
 u.mem_write(0x8a1238,struct.pack('<I',4604))
 u.mem_write(0x837dcc,struct.pack('<I',0x130000))
 u.mem_write(0x130008,struct.pack('<III',2,0x131000,0x132000))
 for slot,address in enumerate([0x131000,0x132000]):
  u.mem_write(address+0x18,struct.pack('<I',slot))
  u.mem_write(address+0x28,struct.pack('<III',100^0x36628020,200^0x36628020,300^0x36628020))
 u.mem_write(0x6c3edc,struct.pack('<I',4))
 u.mem_write(0x838c98,struct.pack('<I',0x120000))
 u.mem_write(0x120000,struct.pack('<IIII',0,0x121000,0x122000,0x123000))
 for address,typ in [(0x121000,0x402),(0x122000,0x617),(0x123000,0x7533)]:
  u.mem_write(address+4,struct.pack('<Hhhh',typ,100,200,0))
 u.mem_write(0x12105e,b'\x02');u.mem_write(0x1210a1,struct.pack('<HH',70,65))
 u.mem_write(0x1210ae,struct.pack('<I',3000));u.mem_write(0x1210b7,struct.pack('<I',2))
 u.mem_write(p['state_header']+24,struct.pack('<II',0xffffffff,0xffffffff))
 values=[111,222,333,444,555,666,777]
 for r,v in zip(regs,values):u.reg_write(r,v)
 u.reg_write(UC_X86_REG_ESP,0x190000);u.mem_write(0x190000,struct.pack('<I',0x180000))
 u.emu_start(p['state_targets'][phase],0x180000,count=100000)
 assert u.reg_read(UC_X86_REG_ESP)==0x190004
 assert [u.reg_read(r) for r in regs[1:]]==values[1:]
 assert u.reg_read(UC_X86_REG_EAX)==0xdeadbeef
 assert struct.unpack('<I',u.mem_read(0x180100,4))[0]==1
 row=struct.unpack('<IIIIIII',u.mem_read(p['state_storage'],28))
 expected=0x811c9dc5
 def mix(v):
  global expected
  expected=((expected^v)*16777619)&0xffffffff
 semantic_expected=None
 for index,address in [(1,0x121000),(2,0x122000),(3,0x123000)]:
  if index==3:semantic_expected=expected
  mix(index)
  for offset in [4,8]:mix(struct.unpack('<I',u.mem_read(address+offset,4))[0])
  if index==1:
   mix(2)
   for offset in [0xa1,0xae,0xb7]:mix(struct.unpack('<I',u.mem_read(address+offset,4))[0])
 assert row==(0,4604,int(phase=='after'),expected,3,1,4),row
 if p.get('state_digest_version',0)>=2:
  assert struct.unpack('<I',u.mem_read(p['state_storage']+28,4))[0]==semantic_expected
 if p.get('state_digest_version',0)>=3:
  count,resource_hash,slots,flags=struct.unpack('<IIII',u.mem_read(p['state_storage']+32,16))
  assert (count,slots,flags)==(2,2,0)
  assert struct.unpack('<IIhhhBBHHII',u.mem_read(p['state_storage']+48,28))==(1,0x402,100,200,0,2,0,70,65,3000,2)
  expected=0x811c9dc5
  for slot in range(2):
   for v in [slot,slot,100,200,300]:mix(v)
  assert resource_hash==expected
 # Repeated rendering/draining at the same frame cannot flood the sample buffer.
 u.reg_write(UC_X86_REG_ESP,0x190000)
 u.emu_start(p['state_targets'][phase],0x180000,count=100000)
 assert struct.unpack('<I',u.mem_read(p['state_header'],4))[0]==1
print('PASS: before/after boundary, native callee, registers, stable entity checksum, sampling limit.')
print('Not an actual game playback or complete simulation-state equality test.')
