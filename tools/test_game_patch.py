from pathlib import Path
import struct,json,pefile
from unicorn import Uc,UC_ARCH_X86,UC_MODE_32
from unicorn.x86_const import *

p=pefile.PE(r'C:\Users\seo\Downloads\DGGL\Games\3KD2120g_Win\3kd2.exe')
metadata=json.loads(Path('dist/runtime/patches/metadata.json').read_text());BASE=metadata['base']
payload=Path('dist/runtime/patches/rally.bin').read_bytes()
UNIT,TABLE,TARGET,TTABLE,CMD,STACK,STUB,END=0x1000000,0x1010000,0x1020000,0x1030000,0x1040000,0x1058000,0x1060000,0x1070000
def n(v):return struct.pack('<I',v&0xffffffff)

class Case:
 def __init__(self,unit_id=0x402,target_id=0x614,amount=500,owner=0,target_owner=9):
  self.u=Uc(UC_ARCH_X86,UC_MODE_32);u=self.u
  data=p.get_memory_mapped_image();u.mem_map(0x400000,0x782000);u.mem_write(0x400000,data);u.mem_write(BASE,payload)
  u.mem_map(UNIT,0x80000);self.next=STUB
  u.mem_write(TABLE,p.get_data(0x29af80,0x780));u.mem_write(TTABLE,p.get_data(0x29af80,0x780))
  self.put(UNIT,TABLE);self.put(UNIT+4,unit_id);self.put(UNIT+0x26c,1)
  self.put(TARGET,TTABLE);self.put(TARGET+4,target_id)
  for obj,table,own in [(UNIT,TABLE,owner),(TARGET,TTABLE,target_owner)]:
   self.method(table,0x214,native=self.ret(own));self.method(table,0x1f0,native=self.ret(123 if obj==UNIT else 456))
  self.method(TTABLE,0x250,native=self.ret(0));self.method(TTABLE,0x324,native=self.ret(amount));self.method(TTABLE,0x328,native=self.ret(amount));self.method(TTABLE,0x350,native=self.ret(1))
  # Native IsBuilding uses the real type getter and original code.
  self.method(TABLE,0x128,native=0x503c10)
  self.method(TABLE,0x234,native=self.ret(0))
  self.method(TABLE,0x38,code=bytes.fromhex('b8 01 00 00 00 c2 04 00'))
  self.method(TABLE,0x1e8,native=0x542ec0)
  # Fallback combat/repair decision is outside this resource-only patch's scope.
  u.mem_write(0x542770,bytes.fromhex('b8 b8 0b 00 00 c2 08 00'))
  u.mem_write(0x453c80,b'\xb8'+n(TARGET)+bytes.fromhex('c2 08 00'))
  self.method(TTABLE,0xb8,code=bytes.fromhex('8b 44 24 04 c7 00')+n(0x00c80064)+bytes.fromhex('66 c7 40 04 0a 00 c2 04 00'))
  self.put(CMD+5,0xbb8);self.put(CMD+0x1a,0x00c80064);u.mem_write(CMD+0x1e,b'\x0a\x00')
 def put(self,a,v):self.u.mem_write(a,n(v))
 def read(self,a):return struct.unpack('<I',self.u.mem_read(a,4))[0]
 def ret(self,value,pop=0):return self.code(b'\xb8'+n(value)+(b'\xc2'+struct.pack('<H',pop) if pop else b'\xc3'))
 def code(self,b):a=self.next;self.u.mem_write(a,b);self.next+=0x40;return a
 def method(self,table,offset,native=None,code=None):self.put(table+offset,native if native is not None else self.code(code))
 def run(self,address,args=(),esi=0x1234,edx=TTABLE):
  u=self.u;sp=STACK;self.put(sp,END)
  for i,a in enumerate(args):self.put(sp+4+i*4,a)
  regs={UC_X86_REG_EBX:0x11223344,UC_X86_REG_EBP:0x55667788,UC_X86_REG_EDI:0x12345678,UC_X86_REG_ESI:esi,UC_X86_REG_ECX:UNIT,UC_X86_REG_EAX:TABLE,UC_X86_REG_EDX:edx}
  for r,v in regs.items():u.reg_write(r,v)
  u.reg_write(UC_X86_REG_ESP,sp);u.emu_start(address,END,count=20000)
  assert u.reg_read(UC_X86_REG_EIP)==END,'hook did not return'
  for r in [UC_X86_REG_EBX,UC_X86_REG_EBP,UC_X86_REG_EDI,UC_X86_REG_ESI]:assert u.reg_read(r)==regs[r],('register',r)
  return u.reg_read(UC_X86_REG_EAX),u.reg_read(UC_X86_REG_ESP)

cases=0
for unit_id,expected in [(0x402,0xfa1),(0x5e5,0xbc0),(0x5f2,0xbc0),(0x60b,0xbc0)]:
 c=Case(unit_id);result,sp=c.run(BASE,(0x00c80064,10,0),edx=TABLE);assert result==(0xbb8 if unit_id==0x402 else expected);assert sp==STACK+16;cases+=1
for unit_id,expected in [(0x402,0xfa1),(0x5e5,0xbc0),(0x5f2,0xbc0),(0x60b,0xbc0)]:
 c=Case(unit_id);result,sp=c.run(BASE+0x100,(TARGET,0),esi=CMD+0xe,edx=TABLE);assert result==expected;assert sp==STACK+12
 if expected==0xbc0:assert c.read(CMD+0x1a)==0x00c80064;assert c.u.mem_read(CMD+0x1e,2)==b'\x0a\x00'
 cases+=1
for worker in [0x402,0x41b,0x438,0x464]:
 for resource,expected in [(0x614,0xfa1),(0x615,0xfa1),(0x616,0xfa1),(0x617,0xfa2)]:
  c=Case(worker,resource);result,sp=c.run(BASE+0x200,(CMD,));assert c.read(CMD+5)==expected;assert c.read(CMD+0xe)==456;assert sp==STACK+8;cases+=1
for mode in ['empty','dead','ground','nonworker','specialworker','nonresource','attack']:
 c=Case()
 if mode=='empty':c.method(TTABLE,0x328,native=c.ret(0))
 if mode=='dead':c.method(TTABLE,0x250,native=c.ret(1))
 if mode=='ground':c.u.mem_write(0x453c80,bytes.fromhex('31 c0 c2 08 00'))
 if mode=='nonworker':c.method(TABLE,0x1ec,native=0x542770)
 if mode=='specialworker':c.put(UNIT+4,0x400)
 if mode=='nonresource':c.put(TARGET+4,0x450)
 if mode=='attack':c.put(CMD+5,0x7d0)
 c.run(BASE+0x200,(CMD,));assert c.read(CMD+5)==(0x7d0 if mode=='attack' else 0xbb8);assert c.read(CMD+0xe)==0;cases+=1
# Real production wrapper: verify cdecl argument copying, original rally lookup,
# source ID/owner, target ID in the field consumed by native Worker tick.
from unicorn import UC_HOOK_CODE
for rally_resource in [True,False]:
 c=Case();u=c.u;producer=UNIT+0x4000;building=UNIT+0x5000
 c.put(producer+0x49,building);c.put(building,TABLE)
 u.mem_write(building+0x2bc,struct.pack('<hhh',100,200,10))
 c.method(TABLE,0x38,code=bytes.fromhex('c2 04 00'))
 u.mem_write(0x54fef0,b'\xb8'+n(UNIT)+b'\xc3')
 if not rally_resource:u.mem_write(0x453c80,bytes.fromhex('31 c0 c2 08 00'))
 args=[0x12340001,0x00000020,0x56780002,0x00000030,0x402,0]
 observed=[]
 def trace(uc,a,size,data):
  sp=uc.reg_read(UC_X86_REG_ESP)
  if a==0x54fef0:assert list(struct.unpack('<6I',uc.mem_read(sp+4,24)))==args
  if a==0x453c80:assert struct.unpack('<2I',uc.mem_read(sp+4,8))==(100,200)
  if a==c.read(TABLE+0x38):
   cmd=c.read(sp+4);raw=bytes(uc.mem_read(cmd,32));observed.append(raw)
   assert struct.unpack_from('<I',raw,5)[0]==0xfa1
   assert struct.unpack_from('<I',raw,10)[0]==123
   assert struct.unpack_from('<I',raw,14)[0]==456
   assert struct.unpack_from('<I',raw,18)[0]==0
 u.hook_add(UC_HOOK_CODE,trace)
 c.put(STACK,END)
 for i,a in enumerate(args):c.put(STACK+4+i*4,a)
 u.reg_write(UC_X86_REG_ESP,STACK);u.reg_write(UC_X86_REG_EDI,producer)
 u.emu_start(BASE+0x400,END,count=20000)
 assert u.reg_read(UC_X86_REG_EAX)==UNIT
 assert u.reg_read(UC_X86_REG_EDI)==producer
 assert u.reg_read(UC_X86_REG_ESP)==STACK+4
 assert len(observed)==int(rally_resource)
 cases+=1
# Real temple vtable, rather than a Worker table with a building type ID.
for offset,args in [(0,(0x00c80064,10,0)),(0x100,(TARGET,0))]:
 c=Case(0x5eb);c.u.mem_write(TABLE,p.get_data(0x29d4f8,0x780))
 result,sp=c.run(BASE+offset,args,esi=CMD+0xe,edx=TABLE)
 assert result==0xbc0;cases+=1
# Restore old malformed gather commands, with native target validation.
for mode in ['gi','ore','valid_target','wrong_type','empty','out_of_range','not_gather']:
 c=Case(target_id=0x617 if mode=='ore' else 0x614);u=c.u
 c.put(UNIT+0xae,0xfa2 if mode=='ore' else 0xfa1);c.put(UNIT+0xb7,0);c.put(UNIT+0xbb,456)
 c.put(0x6c3edc,1000);c.put(0x838c98,UNIT+0x8000);c.put(UNIT+0x8000+456*4,TARGET)
 if mode=='valid_target':c.put(UNIT+0xb7,789)
 if mode=='wrong_type':c.put(TARGET+4,0x450)
 if mode=='empty':c.method(TTABLE,0x328,native=c.ret(0))
 if mode=='out_of_range':c.put(UNIT+0xbb,1000)
 if mode=='not_gather':c.put(UNIT+0xae,0xbb8)
 u.mem_write(0x5664d5,bytes.fromhex('5e c3')) # stop after replayed prologue
 result,sp=c.run(BASE+0x700)
 assert c.read(UNIT+0xb7)==(456 if mode in ['gi','ore'] else (789 if mode=='valid_target' else 0))
 assert c.read(UNIT+0xbb)==(0 if mode in ['gi','ore'] else (1000 if mode=='out_of_range' else 456))
 assert sp==STACK+4;cases+=1
# Save loader: keep the CURRENT lock's bytes while loading all other bytes,
# including failed loads and original save path argument forwarding.
for mode in ['load','failure','save']:
 c=Case();u=c.u;dest=0x8cc128;original=bytes([0x53])*0x1330;saved=bytes((i%251 for i in range(0x1330)))
 u.mem_write(dest,original);c.put(UNIT+0x24,0 if mode=='save' else 1)
 locks=[]
 enter=c.ret(0,4);leave=c.ret(0,4);c.put(0x682178,enter);c.put(0x68217c,leave)
 def load_trace(uc,a,size,data):
  if a==0x500380:
   sp=uc.reg_read(UC_X86_REG_ESP);out=c.read(sp+4);length=c.read(sp+8);assert length==0x1330
   if mode=='save':assert out==dest
   else:
    assert out!=dest
    if mode=='load':uc.mem_write(out,saved)
   uc.reg_write(UC_X86_REG_EAX,int(mode!='failure'));uc.reg_write(UC_X86_REG_EIP,c.read(sp));uc.reg_write(UC_X86_REG_ESP,sp+12)
  if a in [enter,leave]:
   assert bytes(uc.mem_read(dest+0x14,24))==original[0x14:0x2c]
   locks.append(a)
 u.hook_add(UC_HOOK_CODE,load_trace)
 result,sp=c.run(BASE+0x600,(dest,0x1330))
 expected=bytearray(saved if mode=='load' else original);expected[0x14:0x2c]=original[0x14:0x2c]
 assert bytes(u.mem_read(dest,0x1330))==expected
 assert locks==([enter,leave] if mode=='load' else [])
 assert sp==STACK+12 and result==int(mode!='failure');cases+=1
print(str(cases)+' hook cases passed (production, native resource resolver, save lock preservation and old worker recovery).')

# Rally-facing spawn seed, native placement forwarding, and fallback preservation.
spawn_cases=0
for rally_pos in [(1000,500),(1000,1500),(500,1000),(1500,1000),(500,500),(1500,500),(500,1500),(1500,1500),(1000,1000),None]:
 for blocked in [False,True]:
  c=Case();u=c.u;producer=CMD+0x200;out=CMD+0x300
  c.put(producer+0x49,UNIT);c.method(TABLE,0x1fc,native=0x54ed90)
  u.mem_write(UNIT+0x2bc,struct.pack('<hhh',*(rally_pos+(64,) if rally_pos else (32767,32767,32767))))
  calls=[]
  def trace_spawn(uc,a,size,data):
   sp=uc.reg_read(UC_X86_REG_ESP)
   if a==0x54ed90:
    lo,hi=struct.unpack('<II',uc.mem_read(sp+4,8))
    uc.mem_write(lo,struct.pack('<hhh',900,900,64));uc.mem_write(hi,struct.pack('<hhh',1100,1100,64))
    uc.reg_write(UC_X86_REG_EAX,1);uc.reg_write(UC_X86_REG_EIP,c.read(sp));uc.reg_write(UC_X86_REG_ESP,sp+12)
   elif a==0x44eba0:
    uc.reg_write(UC_X86_REG_EAX,64);uc.reg_write(UC_X86_REG_EIP,c.read(sp));uc.reg_write(UC_X86_REG_ESP,sp+4)
   elif a==0x44f720:
    raw=bytes(uc.mem_read(sp+4,20));pos=struct.unpack_from('<hhh',raw);typ,ptr,flag=struct.unpack_from('<III',raw,8)
    assert (typ,ptr,flag)==(0x402,out,0)
    calls.append(pos);result=0 if blocked and len(calls)==1 and rally_pos not in [None,(1000,1000)] else 1
    if result:uc.mem_write(ptr,raw[:6])
    uc.reg_write(UC_X86_REG_EAX,result);uc.reg_write(UC_X86_REG_EIP,c.read(sp));uc.reg_write(UC_X86_REG_ESP,sp+4)
  u.hook_add(UC_HOOK_CODE,trace_spawn)
  args=[1000|(1100<<16),184,0x402,out,0]
  c.put(STACK,END)
  for i,a in enumerate(args):c.put(STACK+4+4*i,a)
  regs={UC_X86_REG_ESP:STACK,UC_X86_REG_EDI:producer,UC_X86_REG_EBP:120,UC_X86_REG_ESI:0,UC_X86_REG_EBX:0x402}
  for r,v in regs.items():u.reg_write(r,v)
  u.emu_start(BASE+0x800,END,count=20000)
  assert u.reg_read(UC_X86_REG_EIP)==END and u.reg_read(UC_X86_REG_ESP)==STACK+4
  for r in [UC_X86_REG_EDI,UC_X86_REG_EBP,UC_X86_REG_ESI,UC_X86_REG_EBX]:assert u.reg_read(r)==regs[r]
  if rally_pos in [None,(1000,1000)]:assert calls==[(1000,1100,184)]
  else:
   expected=tuple(max(868,min(1132,v)) for v in rally_pos)+(184,)
   assert calls[0]==expected,(calls,expected)
   assert len(calls)==(2 if blocked else 1)
   if blocked:assert calls[1]==(1000,1100,184)
  spawn_cases+=1
print(str(spawn_cases)+' spawn direction/fallback/altitude/stack cases passed.')
