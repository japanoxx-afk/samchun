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
BASE=0xb80000;u.mem_map(BASE,8192);u.mem_write(BASE,Path('dist/runtime/patches/rally.bin').read_bytes())
TEMP=0x30000000;STACK=TEMP+0x8000;END=TEMP+0xf000;CMD=TEMP+0x100
u.mem_map(TEMP,0x10000)
def call(a,this=0,args=()):
 u.mem_write(STACK,n(END)+b''.join(n(x) for x in args))
 u.reg_write(UC_X86_REG_ESP,STACK);u.reg_write(UC_X86_REG_ECX,this)
 u.emu_start(a,END,count=1000000)
 assert u.reg_read(UC_X86_REG_EIP)==END,hex(u.reg_read(UC_X86_REG_EIP))
 return u.reg_read(UC_X86_REG_EAX)

try:
 ptrs=struct.unpack('<'+str(num(0x6c3edc))+'I',read(num(0x838c98),num(0x6c3edc)*4))
 u.mem_map(0x8df000,4096);u.mem_write(0x8df000,read(0x8df000,4096))
 selects={num(num(a)+0x170) for a in ptrs if a};selected=[]
 def ret(value=1):
  sp=u.reg_read(UC_X86_REG_ESP);dest=struct.unpack('<I',u.mem_read(sp,4))[0];u.reg_write(UC_X86_REG_EIP,dest);u.reg_write(UC_X86_REG_ESP,sp+4);u.reg_write(UC_X86_REG_EAX,value)
 def hook(uc,a,size,data):
  if a==0x52c6f0:u.mem_write(0x8dfbcc,n(0));selected.clear();ret()
  elif a in selects:
   selected.append(u.reg_read(UC_X86_REG_ECX));u.mem_write(0x8dfbcc,n(len(selected)));ret()
  elif a in (0x40d270,0x40f2a0):ret()
 u.hook_add(UC_HOOK_CODE,hook)
 reports={}
 # Simulate the unobstructed battlefield in isolated RAM only; live UI is untouched.
 for addr in (0x838ca8,0x851854,0x8cd7f8):
  page=addr&~4095
  try:u.mem_map(page,4096);u.mem_write(page,read(page,4096))
  except Exception:pass
  u.mem_write(addr,bytes(1 if addr==0x8cd7f8 else 4))
 for mode,name in [(0,'army'),(1,'idle_workers')]:
  selected.clear();call(BASE+0x1000,args=(mode,));reports[name]=[dict(address=hex(a),type=hex(struct.unpack('<H',read(a+4,2))[0]),command=hex(num(a+0xae))) for a in selected]
 keyboard=num(0xaffb94);node=num(keyboard+0x524);bindings=[]
 while node:
  flags,scan,fn,nextnode=struct.unpack('<HBII',read(node,11))
  if scan in (0x3c,0x34):bindings.append(dict(scan=hex(scan),flags=flags,callback=hex(fn)))
  node=nextnode
 reports['bindings']=bindings
 Path('verification/live-hotkeys.json').write_text(json.dumps(reports,indent=2));print(json.dumps(reports,indent=2))
finally:k.CloseHandle(h)
