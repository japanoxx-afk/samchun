"""Emulate real hotkey code and native selection insertion with mixed entities."""
import struct
from pathlib import Path
import pefile
from unicorn import Uc,UC_ARCH_X86,UC_MODE_32,UC_HOOK_CODE
from unicorn.x86_const import *
P=pefile.PE(r'C:\Users\seo\Downloads\DGGL\Games\3KD2120g_Win\3kd2.exe')
PAYLOAD=Path('dist/runtime/patches/rally.bin').read_bytes()
BASE=0xb80000;STACK=0x1108000;END=0x110f000;EVENT=0x1109000
n=lambda x:struct.pack('<I',x)
def case(specs,mode=0,focus=0,modal=0,locked=0,entry=None):
 u=Uc(UC_ARCH_X86,UC_MODE_32);u.mem_map(0x400000,0x782000);u.mem_write(0x400000,P.get_memory_mapped_image());u.mem_write(BASE,PAYLOAD);u.mem_map(0x1000000,0x200000)
 def put(a,v):u.mem_write(a,n(v))
 def get(a):return struct.unpack('<I',u.mem_read(a,4))[0]
 put(0x838ca8,focus);put(0x851854,modal);u.mem_write(0x8cd7f8,bytes([locked]));put(0x838c98,0x1100000);put(0x6c3edc,len(specs));put(0x71f864,0x8cc128)
 # Real native AddSelection; mock virtual accessors only, with per-entity fields.
 st=0x1110000
 def stub(data):
  nonlocal st
  a=st;u.mem_write(a,data);st+=64;return a
 getters={0x24:stub(bytes.fromhex('0f b7 41 04 c3')),0x214:stub(bytes.fromhex('0f b6 41 5e c3'))}
 for off,field in [(0x128,0x60),(0x250,0x64),(0x69c,0x68),(0x678,0x6c),(0x5b8,0x70)]:getters[off]=stub(bytes([0x8b,0x41,field,0xc3]))
 getters[0x28]=stub(bytes.fromhex('8b 41 74 c3'))
 select=stub(bytes.fromhex('51 e8')+struct.pack('<i',0x52c690-(st+6))+bytes.fromhex('83 c4 04 c3'))
 # above relative call computed using stub address (st before allocation)
 cat=stub(bytes.fromhex('8b 41 04 c3'))
 for i,s in enumerate(specs):
  if s is None:continue
  obj=0x1000000+i*0x1000;table=obj+0x400;definition=obj+0x800;dt=obj+0x900
  put(0x1100000+i*4,obj);put(obj,table);put(obj+4,s.get('type',0x410));u.mem_write(obj+0x5e,bytes([s.get('owner',0)]))
  for field,key in [(0x60,'building'),(0x64,'dead'),(0x68,'hidden'),(0x6c,'transport'),(0x70,'exposed')]:put(obj+field,s.get(key,0))
  put(obj+0x74,definition);put(definition,dt);put(definition+4,s.get('category',0x20));put(dt+0xd4,cat)
  put(obj+0xae,s.get('command',0));u.mem_write(obj+0x13a,bytes([s.get('queue',0)]))
  for off,a in getters.items():put(table+off,a)
  put(table+0x170,select)
 calls=[];queued=[];registered=[]
 def ret(value=1,pop=0):
  sp=u.reg_read(UC_X86_REG_ESP);u.reg_write(UC_X86_REG_EAX,value);u.reg_write(UC_X86_REG_EIP,get(sp));u.reg_write(UC_X86_REG_ESP,sp+4+pop)
 def hook(uc,a,size,data):
  if a==0x5319e0:ret(int(get(u.reg_read(UC_X86_REG_ESP)+4)==0))
  elif a==0x52c6f0:u.mem_write(0x8e1ad0,bytes(132));put(0x8dfbcc,0);calls.append('clear');ret()
  elif a in (0x40d270,0x40f2a0):calls.append(hex(a));ret()
  elif a==0x518990:
   sp=u.reg_read(UC_X86_REG_ESP);queued.append((get(sp+4),get(sp+8)));ret(pop=8)
  elif a==0x5737a0:
   sp=u.reg_read(UC_X86_REG_ESP);registered.append(tuple(get(sp+i) for i in (4,8,12)));ret()
  elif a==0x517ac5:calls.append('native');u.emu_stop()
 u.hook_add(UC_HOOK_CODE,hook)
 put(STACK,END);put(STACK+4,mode);put(EVENT,0x100);put(EVENT+15,mode)
 if entry==0xf00:put(STACK+4,EVENT)
 if entry==0xd00:
  for i,v in enumerate((0,0xcf,0x52b4b0)):put(STACK+4+i*4,v)
 u.reg_write(UC_X86_REG_ESP,STACK)
 saved={UC_X86_REG_EBX:0x1234,UC_X86_REG_ESI:0x5678,UC_X86_REG_EDI:0x9abc,UC_X86_REG_EBP:0xdef0}
 for r,v in saved.items():u.reg_write(r,v)
 u.emu_start(BASE+(0x1000 if entry is None else entry),END,count=100000)
 assert u.reg_read(UC_X86_REG_EIP)==END
 assert u.reg_read(UC_X86_REG_ESP)==STACK+4
 for r,v in saved.items():assert u.reg_read(r)==v
 selected=[i for i,s in enumerate(specs) if s is not None and 0x1000000+i*0x1000 in struct.unpack('<32I',u.mem_read(0x8e1ad0,128))]
 assert get(0x8dfbcc)==len(selected)
 return selected,calls,queued,registered
army=[{},None,{'type':0x402},{'owner':1},{'dead':1},{'building':1},{'hidden':1},{'transport':1},{'transport':1,'exposed':1},{'category':0},{'type':0x450}]
assert case(army)[0]==[0,8,10]
workers=[{'type':t} for t in (0x402,0x438,0x464)]+[{'type':0x402,'command':c} for c in (0xbb8,0xfa1,0xfa2,0xfa3,0x7d0)]+[{'type':0x402,'queue':1},{'type':0x402,'owner':1},{'type':0x402,'dead':1},{}]
assert case(workers,1)[0]==[0,1,2]
for typ in (0x402,0x438,0x464):
 for cmd in (0,0x1770,0xbba):
  assert case([{'type':typ,'command':cmd}],1)[0]==[0]
  assert case([{'type':typ,'command':cmd,'queue':1}],1)[0]==[]
assert len(case([{}]*40)[0])==32
assert len(case([{'type':0x402}]*40,1)[0])==32
assert case([],1)[1]==[]
for kw in ({'focus':1},{'modal':1},{'locked':1}):
 assert case(army,**kw)[0]==[]
 for entry in (0xe00,0xe80):assert case([],entry=entry,**kw)[2]==[]
assert case([],entry=0xe00)[2]==[(0x100,0)]
assert case([],entry=0xe80)[2]==[(0x100,1)]
assert case(workers,mode=1,entry=0xf00)[0]==[0,1,2]
assert case([],entry=0xd00)[3]==[(0,0xcf,0x52b4b0),(0,0x34,BASE+0xe80)]
print('36 hotkey scenarios passed: mixed ownership, workers/tasks/queues, map-wide military, capacity, input guards, enqueue/dispatch and registration stack')
