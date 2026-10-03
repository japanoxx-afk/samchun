"""Native Internet bootstrap preserves the original account/lobby menu path."""
import pefile,struct
from unicorn import Uc,UC_ARCH_X86,UC_MODE_32,UC_HOOK_CODE
from unicorn.x86_const import *
p=pefile.PE('verification/compat-game.exe')
for fail in [None,0x42b710,0x4f6b40,0x42bee0]:
 u=Uc(UC_ARCH_X86,UC_MODE_32);u.mem_map(0x400000,0x800000);u.mem_write(0x400000,p.get_memory_mapped_image());u.reg_write(UC_X86_REG_ESP,0xb00000)
 calls=[];menu=[]
 def hook(uc,a,size,data):
  if a not in [0x42b710,0x4f6b40,0x42bee0,0x465b90]:return
  sp=u.reg_read(UC_X86_REG_ESP);back=struct.unpack('<I',u.mem_read(sp,4))[0]
  calls.append(a)
  if a==0x465b90:menu.append(struct.unpack('<II',u.mem_read(sp+4,8)))
  u.reg_write(UC_X86_REG_EAX,0 if a==fail else 1);u.reg_write(UC_X86_REG_ESP,sp+4);u.reg_write(UC_X86_REG_EIP,back)
 u.hook_add(UC_HOOK_CODE,hook);u.emu_start(0x460ad9,0x460e82,count=120)
 assert menu==([(0x16,0)] if fail is None else [(0x33,1)])
 assert u.reg_read(UC_X86_REG_ESP)==0xb00000
 for a in [0x42bab6,0x42babd,0x42bad2]:
  ptr=struct.unpack('<I',u.mem_read(a,4))[0];assert u.mem_read(ptr,10)==b'127.0.0.1\0'
 assert u.mem_read(0x460a29,5)==bytes.fromhex('68 78 8b 6c 00')
 print('bootstrap',hex(fail) if fail else 'success','passed')
