"""Original game result emitter and lobby statistics parser interoperability."""
import struct,sys
from pathlib import Path
from test_compat_native import *
def result_packet(outcome=1, name='a'):
 pe=pefile.PE('verification/compat-game.exe');u=Uc(UC_ARCH_X86,UC_MODE_32)
 u.mem_map(0x400000,0x800000);u.mem_write(0x400000,pe.get_memory_mapped_image())
 u.mem_write(0x8b0320,name.encode()+b'\0')
 args=[outcome,10,20,30,0xb10000,0xb11000,0xb12000]
 u.mem_write(0xb00000,struct.pack('<8I',0xb70000,*args));u.reg_write(UC_X86_REG_ESP,0xb00000);captured=[]
 def hook(uc,a,size,data):
  if a==0x42c050:
   sp=u.reg_read(UC_X86_REG_ESP);back,ptr,n=struct.unpack('<3I',u.mem_read(sp,12));captured.append(bytes(u.mem_read(ptr,n)))
   u.reg_write(UC_X86_REG_EAX,1);u.reg_write(UC_X86_REG_ESP,sp+4);u.reg_write(UC_X86_REG_EIP,back)
 u.hook_add(UC_HOOK_CODE,hook);u.emu_start(0x4f7a90,0xb70000,count=3000)
 assert len(captured)==1 and len(captured[0])==690 and captured[0][4]==1
 assert captured[0][7]==outcome and captured[0][8:24].split(b'\0')[0]==name.encode()
 return captured[0]
def parse_statistics(body):
 pe=pefile.PE(str(GAME));u=Uc(UC_ARCH_X86,UC_MODE_32);u.mem_map(0x400000,0x800000);u.mem_write(0x400000,pe.get_memory_mapped_image())
 u.mem_write(0xb10000,b'a\0');u.mem_write(0x8b0320,b'a\0');u.mem_write(0xb00000,struct.pack('<3I',0xb70000,0,0xb10000));u.reg_write(UC_X86_REG_ESP,0xb00000)
 def hook(uc,a,size,data):
  if a not in (0x42c100,0x42c050,0x42c140,0x42dca0):return
  if a==0x42c140:u.mem_write(0x8aff20,packet(0x7a,body))
  sp=u.reg_read(UC_X86_REG_ESP);back=struct.unpack('<I',u.mem_read(sp,4))[0]
  u.reg_write(UC_X86_REG_EAX,1);u.reg_write(UC_X86_REG_ESP,sp+4);u.reg_write(UC_X86_REG_EIP,back)
 u.hook_add(UC_HOOK_CODE,hook);u.emu_start(0x4f7c40,0xb70000,count=3000)
 return struct.unpack('<4H',u.mem_read(0x8b0359,8))
if __name__=='__main__':
 for outcome in (1,2,3,4):result_packet(outcome)
 body=bytearray(80);struct.pack_into('<4H',body,57,12,3,2,17)
 assert parse_statistics(body)==(12,3,2,17)
 print('Native result packets for all outcome codes and native statistics display counters passed')
