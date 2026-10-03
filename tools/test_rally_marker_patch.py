"""Execute native manual-rally marker creation and exact placement arguments."""
from test_selection_patch import *
cases=0
for network in (0,2):
 for created in (0,1):
  c=Case(0);c.u.mem_map(0,4096);c.put(0,123);world=0x1103000;obj=0x1104000;table=0x1105000
  c.put(world,network);c.put(obj,table);c.put(table+8,0x1107000);c.put(0x6c3fb0,1);c.put(0x8e1aa8,0x00c80064)
  calls=[]
  c.callbacks[0x43a7d0]=lambda:c.ret(world)
  def allocate():
   sp=c.u.reg_read(UC_X86_REG_ESP);assert c.get(sp+4)==0x11c;c.ret(obj)
  def construct():
   sp=c.u.reg_read(UC_X86_REG_ESP);assert c.u.reg_read(UC_X86_REG_ECX)==obj
   assert c.get(sp+4)==0x36f6 and c.get(sp+8)==int(network!=2);c.ret(obj,8)
  def position():
   sp=c.u.reg_read(UC_X86_REG_ESP);assert c.get(sp+8)==0x00c80064
   out=c.get(sp+4);c.u.mem_write(out,struct.pack('<hhh',320,640,48));c.ret(out,8)
  def display():
   sp=c.u.reg_read(UC_X86_REG_ESP);assert c.u.reg_read(UC_X86_REG_ECX)==obj
   assert struct.unpack('<hhh',c.u.mem_read(sp+4,6))==(320,640,48)
   assert [c.get(sp+i) for i in (12,16,20,24,28)]==[1,0,1,0,1]
   calls.append('marker');c.ret(created,28)
  def release():
   sp=c.u.reg_read(UC_X86_REG_ESP);assert c.get(sp+4)==1;calls.append('release');c.ret(0,4)
  c.callbacks.update({0x56d4c0:allocate,0x42fea0:construct,0x453800:position,0x4303e0:display,0x1107000:release})
  c.run(0x5283f0);assert c.get(0)==123 and calls==(['marker'] if created else ['marker','release']);cases+=1
c=Case(0);c.u.mem_map(0,4096);c.put(0x6c3fb0,3)
c.callbacks[0x43a7d0]=lambda:(_ for _ in ()).throw(AssertionError('Unexpected allocation'))
c.run(0x5283f0);cases+=1
print(f'{cases} native green marker cases passed: asset, screen-to-world position, network mode, arguments, creation cleanup, SEH/stack preservation')
