import struct,sys
from pathlib import Path
import pefile
from unicorn import Uc,UC_ARCH_X86,UC_MODE_32,UC_HOOK_CODE
from unicorn.x86_const import *
from sell_hotkey import install

data=bytearray(Path(sys.argv[1]).read_bytes());info={};install(data,info)
p=pefile.PE(data=bytes(data))
assert p.get_data(0x51867b-0x400000,1)==b'\x0b'
assert p.get_data(0x518097-0x400000,2)==b'\xff\x36'
for event,button,enabled,owned,selected,expected in [
 (14,21,1,1,1,False),(16,21,1,1,1,True),
 (14,19,1,1,1,True),(16,19,1,1,1,False),
 (16,21,3,1,1,False),(16,21,1,0,1,False),
 (16,21,1,1,0,False),(16,0,1,1,1,False),
 (17,21,1,1,1,True)]:
 u=Uc(UC_ARCH_X86,UC_MODE_32);u.mem_map(0x400000,(p.OPTIONAL_HEADER.SizeOfImage+4095)&~4095)
 for s in p.sections:u.mem_write(0x400000+s.VirtualAddress,bytes(data[s.PointerToRawData:s.PointerToRawData+s.SizeOfRawData]))
 u.mem_map(0x20000000,0x10000)
 obj,vt,panel,pvt,btn,bvt,sp,stop=[0x20000000+x for x in (0x1000,0x2000,0x3000,0x4000,0x5000,0x6000,0x8000,0x100)]
 put=lambda a,v:u.mem_write(a,struct.pack('<I',v))
 put(0x6c3edc,10);put(obj,vt);put(panel,pvt);put(btn,bvt);put(0x73f3c0,panel)
 u.mem_write(btn+4,struct.pack('<H',button));u.mem_write(btn+7,bytes([enabled]))
 for field,addr in [(0x214,0x20000110),(0x24,0x20000120),(0x2e0,0x20000130)]:put(vt+field,addr)
 put(pvt+0x7c,0x20000140);put(bvt+0xc,0x20000150)
 u.mem_write(sp,struct.pack('<III',stop,0x20000900,event));u.reg_write(UC_X86_REG_ESP,sp);called=[];trace=[]
 def hook(uc,address,size,unused):
  trace.append(hex(address))
  if address==stop:uc.emu_stop();return
  if address==0x20000150:called.append(button);uc.emu_stop();return
  mocks={0x5308d0:(1 if selected else 0xffffffff,0),0x446200:(obj,0),0x5319e0:(owned,0),0x40eeb0:(1,0),0x515a80:(0,0),0x20000110:(0,0),0x20000120:(2001,0),0x20000130:(0,8),0x20000140:(btn if button else 0,16)}
  if address not in mocks:return
  value,pop=mocks[address];esp=uc.reg_read(UC_X86_REG_ESP)
  ret=struct.unpack('<I',uc.mem_read(esp,4))[0];uc.reg_write(UC_X86_REG_EAX,value);uc.reg_write(UC_X86_REG_ESP,esp+4+pop);uc.reg_write(UC_X86_REG_EIP,ret)
 u.hook_add(UC_HOOK_CODE,hook);u.emu_start(0x414910,0,count=500)
 assert bool(called)==expected,(event,button,enabled,owned,selected,called,trace[-25:])
print('PASS: native command-panel C sell, A blocked for sell, other A commands retained; ownership, disabled and missing selection guarded')
