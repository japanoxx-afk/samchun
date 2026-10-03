from test_compat_native import *

def room_call(frame):
 pe=pefile.PE(str(GAME));u=Uc(UC_ARCH_X86,UC_MODE_32);u.mem_map(0x400000,0x800000);u.mem_write(0x400000,pe.get_memory_mapped_image())
 u.mem_write(0xb10100,b'TesterA\0');u.mem_write(0xb00000,struct.pack('<IIII',0xb70000,0xb10000,8,0xb10100));u.reg_write(UC_X86_REG_ESP,0xb00000)
 captures=[]
 def ret(value=1,extra=0):
  sp=u.reg_read(UC_X86_REG_ESP);a=struct.unpack('<I',u.mem_read(sp,4))[0];u.reg_write(UC_X86_REG_EAX,value);u.reg_write(UC_X86_REG_ESP,sp+4+extra);u.reg_write(UC_X86_REG_EIP,a)
 def hook(uc,a,n,user):
  sp=u.reg_read(UC_X86_REG_ESP)
  if a in [0x42c050,0x42b420]:ret()
  elif a==0x42c1a0:
   ptr=struct.unpack('<I',u.mem_read(sp+4,4))[0];u.mem_write(ptr,frame);ret()
  elif a==0x670f14:ret(0,4)
  elif a==0x670eae:
   ptr=struct.unpack('<I',u.mem_read(sp+8,4))[0];u.mem_write(ptr,bytes.fromhex('020000007f000001')+bytes(8));ret(0,12)
  elif a==0x670ee4:ret(0x2513,4)
  elif a==0x4f91d0:
   captures.append(struct.unpack('<9I',u.mem_read(sp+4,36)));ret(1,36)
 u.hook_add(UC_HOOK_CODE,hook);u.emu_start(0x42cb90,0xb70000,count=5000)
 return captures,u.reg_read(UC_X86_REG_EAX)
if __name__=='__main__':
 body=bytearray(360);body[0]=1;struct.pack_into('<I',body,1,100);struct.pack_into('<I',body,15,100);struct.pack_into('<I',body,15+195,100);struct.pack_into('<I',body,15+203,1);struct.pack_into('<I',body,222,1)
 result,success=room_call(packet(0x7e,body));print(result,success)
 assert success==1 and result[0][5:7]==(100,1) and result[0][8]==1
 print('native room response -> relay group/user/host identifiers passed')
