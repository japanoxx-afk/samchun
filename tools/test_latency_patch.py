"""Execute the native relay socket hook, including error and datagram paths."""
import struct,pefile
from unicorn import Uc,UC_ARCH_X86,UC_MODE_32,UC_HOOK_CODE
from unicorn.x86_const import *
p=pefile.PE('verification/compat-game.exe')
for sock,kind,result in [(73,1,0),(73,1,0xffffffff),(0xffffffff,1,0),(73,2,0)]:
 u=Uc(UC_ARCH_X86,UC_MODE_32);u.mem_map(0x400000,0x800000);u.mem_write(0x400000,p.get_memory_mapped_image())
 sp=0xb00000;u.reg_write(UC_X86_REG_ESP,sp);u.mem_write(sp+0x2898,struct.pack('<I',kind));u.mem_write(0x682328,struct.pack('<I',0xb70000))
 regs={UC_X86_REG_EAX:sock,UC_X86_REG_EBX:12,UC_X86_REG_ECX:23,UC_X86_REG_EDX:34,UC_X86_REG_ESI:45,UC_X86_REG_EDI:56}
 for r,v in regs.items():u.reg_write(r,v)
 calls=[]
 def hook(uc,a,size,data):
  if a!=0xb70000:return
  s=u.reg_read(UC_X86_REG_ESP);back,handle,level,option,ptr,length=struct.unpack('<6I',u.mem_read(s,24))
  calls.append((handle,level,option,length,struct.unpack('<I',u.mem_read(ptr,4))[0]))
  u.reg_write(UC_X86_REG_EAX,result);u.reg_write(UC_X86_REG_ECX,0xcccc);u.reg_write(UC_X86_REG_EDX,0xdddd)
  u.reg_write(UC_X86_REG_ESP,s+24);u.reg_write(UC_X86_REG_EIP,back)
 u.hook_add(UC_HOOK_CODE,hook);u.emu_start(0x4f923c,0x4f9241,count=100)
 assert calls==([(73,6,1,4,1)] if sock==73 and kind==1 else [])
 assert u.reg_read(UC_X86_REG_ESP)==sp
 assert u.reg_read(UC_X86_REG_EBP)==sock
 for r,v in regs.items():assert u.reg_read(r)==v
 assert bool(u.reg_read(UC_X86_REG_EFLAGS)&64)==(sock==0xffffffff)
 print('TCP_NODELAY hook passed:',sock,kind,result)
