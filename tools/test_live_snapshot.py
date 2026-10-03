"""Read-only live game snapshot; execute candidate hooks in isolated Unicorn RAM.
No injected code and no writes to the running process. Not an in-game playtest.
"""
import ctypes as c, struct, sys, json
from pathlib import Path
from unicorn import Uc, UC_ARCH_X86, UC_MODE_32, UC_HOOK_MEM_UNMAPPED, UC_HOOK_CODE
from unicorn.x86_const import *
k=c.WinDLL('kernel32',use_last_error=True);k.OpenProcess.restype=c.c_void_p
k.ReadProcessMemory.argtypes=[c.c_void_p,c.c_void_p,c.c_void_p,c.c_size_t,c.c_void_p]
k.CloseHandle.argtypes=[c.c_void_p]
h=k.OpenProcess(0x410,False,int(sys.argv[1]))
def read(a,n):
 b=c.create_string_buffer(n)
 if not k.ReadProcessMemory(h,a,b,n,None):raise OSError(c.get_last_error(),hex(a))
 return b.raw
def num(a):return struct.unpack('<I',read(a,4))[0]
def n(v):return struct.pack('<I',v)
u=Uc(UC_ARCH_X86,UC_MODE_32)
def missing(uc,access,address,size,value,data):
 page=address&~4095
 for a in range(page,(address+size+4095)&~4095,4096):
  try:uc.mem_map(a,4096);uc.mem_write(a,read(a,4096))
  except Exception as e:print('map failed',hex(address),e);return False
 return True
u.hook_add(UC_HOOK_MEM_UNMAPPED,missing)
BASE=0xb80000;u.mem_map(BASE,4096);u.mem_write(BASE,Path('dist/runtime/patches/rally.bin').read_bytes())
TEMP=0x30000000;STACK=TEMP+0x8000;END=TEMP+0xf000;CMD=TEMP+0x100
u.mem_map(TEMP,0x10000)
def call(a,this=0,args=()):
 u.mem_write(STACK,n(END)+b''.join(n(x) for x in args))
 u.reg_write(UC_X86_REG_ESP,STACK);u.reg_write(UC_X86_REG_ECX,this)
 u.emu_start(a,END,count=1000000)
 assert u.reg_read(UC_X86_REG_EIP)==END,hex(u.reg_read(UC_X86_REG_EIP))
 return u.reg_read(UC_X86_REG_EAX)
try:
 count=num(0x6c3edc);assert 0<count<100000
 ptrs=struct.unpack('<'+str(count)+'I',read(num(0x838c98),count*4))
 entities=[]
 for i,p in enumerate(ptrs):
  if p:
   raw=read(p,0x60);vtable,typ=struct.unpack_from('<IH',raw)
   if 0x400000<=vtable<0x730000:entities.append((i,p,typ,struct.unpack_from('<hhh',raw,6),raw[0x5e]))
 workers=[e for e in entities if e[2] in (0x402,0x41b,0x438,0x464)]
 temples=[e for e in entities if e[2]==0x5eb]
 resources=[e for e in entities if e[2] in (0x614,0x615,0x616,0x617)]
 print('entities',len(entities),'workers',workers[:12],'temples',temples[:5])
 workers=[e for e in entities if num(num(e[1])+0x1ec)==0x567840]
 print('REAL WORKERS',workers[:15])
 worker=workers[0][1];table=num(worker);issue=num(table+0x38);observed=[]
 def trace(uc,a,size,data):
  if a==issue:
   sp=uc.reg_read(UC_X86_REG_ESP);ptr=struct.unpack('<I',uc.mem_read(sp+4,4))[0]
   raw=bytes(uc.mem_read(ptr,32));observed.append(raw)
   # Only stop at the final native dispatch boundary; map lookup/resolver are real.
   uc.reg_write(UC_X86_REG_ESP,sp+8);uc.reg_write(UC_X86_REG_EIP,END)
 trace_handle=u.hook_add(UC_HOOK_CODE,trace)
 results=[]
 for entity in resources[:12]:
  idx,target,typ,pos,owner=entity
  u.mem_write(CMD,bytes(32));u.mem_write(CMD+5,n(0xbb8));u.mem_write(CMD+0x1a,struct.pack('<hhh',*pos))
  observed.clear();u.reg_write(UC_X86_REG_EAX,table)
  call(BASE+0x200,worker,(CMD,))
  result=dict(resource_id=idx,type=hex(typ),pos=pos,dispatched=bool(observed))
  if observed:
   result.update(command=hex(struct.unpack_from('<I',observed[0],5)[0]),target=struct.unpack_from('<I',observed[0],14)[0])
   assert result['target']==idx,(result,'wrong resource')
  results.append(result)
 print(json.dumps(results,indent=2))
 assert any(r['dispatched'] for r in results),'No native map/resource resolution succeeded'
 # Run the ORIGINAL worker issue routine, not the interception stub, in shadow RAM.
 u.hook_del(trace_handle)
 worker=next((e[1] for e in workers if struct.unpack('<I',read(e[1]+0xae,4))[0] in (0xfa1,0xfa2) and num(e[1]+0xb7)==0),worker)
 table=num(worker);target=next(e for e in resources if e[2]==0x617)
 def shadow_state():return dict(command=hex(struct.unpack('<I',u.mem_read(worker+0xae,4))[0]),target=struct.unpack('<I',u.mem_read(worker+0xb7,4))[0],state=struct.unpack('<I',u.mem_read(worker+0xc9,4))[0])
 owner=call(num(table+0x214),worker)
 source=call(num(table+0x1f0),worker)
 print('shadow worker',hex(worker), 'owner',owner,'source',source, 'before',shadow_state())
 u.mem_write(CMD,bytes(32));u.mem_write(CMD+5,n(0xbb8));u.mem_write(CMD+9,bytes([owner]));u.mem_write(CMD+10,n(source));u.mem_write(CMD+0x1a,struct.pack('<hhh',*target[3]))
 u.reg_write(UC_X86_REG_EAX,table)
 call(BASE+0x200,worker,(CMD,))
 print('after native gather dispatch',shadow_state(),'queue',bytes(u.mem_read(worker+0x13a,65)).hex())
 u.mem_write(CMD+5,n(0xbb8));u.mem_write(CMD+14,n(0))
 call(num(table+0x38),worker,(CMD,))
 print('after native move override',shadow_state(),'queue',bytes(u.mem_read(worker+0x13a,65)).hex())
 for o in [0x69c,0x678,0x5b8,0x1dc]:print('state method',hex(o),hex(num(table+o)),call(num(table+o),worker))
 # Native cancellation tick must leave the bad old resource state so queued
 # player movement can be processed by the normal update loop.
 call(0x5664d0,worker)
 assert shadow_state()['command']=='0x0'
 print('native cancellation tick cleared the old invalid gather state')
 # Execute the real world input builder with the new branch hook.
 for hook in json.loads(Path('dist/runtime/patches/metadata.json').read_text())['hooks']:
  a=0x400000+hook['offset'];page=a&~4095
  try:u.mem_read(a,8)
  except Exception:missing(u,0,a,8,0,None)
  u.mem_write(a,(b'\xe9' if hook.get('kind')=='jump' else b'\xe8')+struct.pack('<i',hook['target']-(a+5))+b'\x90'*(len(bytes.fromhex(hook['expected']))-5))
 for a,size in [(0x8e1ad0,128),(0x8dfbcc,4)]:
  try:u.mem_read(a,size)
  except Exception:missing(u,0,a,size,0,None)
 u.mem_write(0x8e1ad0,n(temples[0][1])+bytes(124));u.mem_write(0x8dfbcc,n(1))
 for target_ptr in [0,resources[0][1]]:
  call(0x52f1a0,args=(1800|(400<<16),target_ptr,0))
  raw=bytes(u.mem_read(0x8dfbd0,32));assert struct.unpack_from('<I',raw,5)[0]==0xbc0
  pos=struct.unpack_from('<hhh',raw,26)
  if target_ptr:assert pos==resources[0][3]
  else:assert pos[:2]==(1800,400)
  print('native world input rally',hex(target_ptr),pos)
finally:k.CloseHandle(h)
