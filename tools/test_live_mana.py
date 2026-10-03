"""Read a selected live unit; run native MP getters and patch in shadow RAM only.
Never writes process memory. This validates live unit layout, not production UI.
"""
import ctypes as c, struct, sys, json
from pathlib import Path
from unicorn import Uc, UC_ARCH_X86, UC_MODE_32, UC_HOOK_MEM_UNMAPPED
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
u=Uc(UC_ARCH_X86,UC_MODE_32)
def missing(uc,access,address,size,value,data):
 try:
  for a in range(address&~4095,(address+size+4095)&~4095,4096):
   uc.mem_map(a,4096);uc.mem_write(a,read(a,4096))
  return True
 except Exception:return False
u.hook_add(UC_HOOK_MEM_UNMAPPED,missing)
BASE=0xb80000;payload=Path('assets/rally.bin').read_bytes()
u.mem_map(BASE,0x2000);u.mem_write(BASE,payload)
TEMP=0x30000000;STACK=TEMP+0x8000;END=TEMP+0xf000
u.mem_map(TEMP,0x10000)
def call(a,this):
 u.mem_write(STACK,struct.pack('<I',END));u.reg_write(UC_X86_REG_ESP,STACK)
 u.reg_write(UC_X86_REG_ECX,this);u.reg_write(UC_X86_REG_ESI,this)
 u.emu_start(a,END,count=1000000)
 assert u.reg_read(UC_X86_REG_EIP)==END
 return u.reg_read(UC_X86_REG_EAX)
try:
 units=[p for p in struct.unpack('<32I',read(0x8e1ad0,128)) if p]
 assert units,'Select a unit in the game first'
 for p in units:
  table=num(p);getter=num(table+0x224);maximum_getter=num(table+0x234)
  assert getter==0x503c60,'Unexpected live MP layout'
  maximum=call(maximum_getter,p);before=call(getter,p)
  hp=bytes(u.mem_read(p+0xa1,2))
  call(BASE+0x500,p);after=call(getter,p)
  assert after==(maximum*65//100 if maximum>0 else before)
  assert bytes(u.mem_read(p+0xa1,2))==hp
  print(json.dumps(dict(type=hex(struct.unpack('<H',read(p+4,2))[0]),maximum=maximum,live_mp=before,patched_shadow_mp=after,hp_unchanged=True,installed_payload_matches=read(BASE+0x500,0x50)==payload[0x500:0x550])))
finally:k.CloseHandle(h)
