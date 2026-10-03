"""Native click dispatch feedback; original manual-rally sound remains singular."""
from test_selection_patch import *
original=P.get_memory_mapped_image()
assert IMAGE[0x12e260:0x12e26a]==original[0x12e260:0x12e26a]
assert IMAGE[0x12f965:0x12f96a]==original[0x12f965:0x12f96a]
cases=0
for count,commands,expected in [(1,[3008],1),(1,[3000],0),(1,[2000],0),(0,[],0),(64,[3008]*64,1),(64,[3000]*63+[3008],1),(64,[3000]*64,0)]:
 c=Case(count);sounds=[];dispatch=[];markers=[]
 c.callbacks[0x5283f0]=lambda:(markers.append(1),c.ret())[-1]
 for i,command in enumerate(commands):c.put(C+i*32+5,command)
 before=bytes(c.u.mem_read(C,2048))
 c.callbacks[0x515a80]=lambda:(sounds.append(c.get(c.u.reg_read(UC_X86_REG_ESP)+4)),c.ret(123))[-1]
 c.callbacks[0x52c080]=lambda:(dispatch.append(1),c.ret(77))[-1]
 c.callbacks[0x530072]=lambda:c.ret(77);c.run(0x53006d)
 assert sounds==[461]*expected and dispatch==[1] and markers==[1]*expected
 assert c.u.reg_read(UC_X86_REG_EAX)==77
 assert bytes(c.u.mem_read(C,2048))==before;cases+=1
# Ignore stale commands for empty selected slots.
c=Case(0);c.put(C+5,3008);sounds=[]
c.callbacks[0x5283f0]=lambda:(_ for _ in ()).throw(AssertionError("Unexpected marker"))
c.callbacks[0x515a80]=lambda:(sounds.append(1),c.ret())[-1];c.callbacks[0x52c080]=lambda:c.ret()
c.callbacks[0x530072]=lambda:c.ret(77);c.run(0x53006d);assert not sounds;cases+=1
# Original manual command builder emits native rally and plays 461 once.
c=Case(1);sounds=[];dispatch=[]
c.callbacks[0x515a80]=lambda:(sounds.append(c.get(c.u.reg_read(UC_X86_REG_ESP)+4)),c.ret())[-1]
c.callbacks[0x52c080]=lambda:(dispatch.append(1),c.ret())[-1]
def position():
 sp=c.u.reg_read(UC_X86_REG_ESP);out=c.get(sp+4);c.u.mem_write(out,struct.pack('<hhh',100,200,0));c.ret(out,8)
c.callbacks[0x453800]=position;c.run(0x52e1f0,(0,))
assert sounds==[461] and dispatch==[1] and c.get(C+5)==3008;cases+=1
print(f'{cases} rally sound cases passed: click-only, once, ground/resource command, unrelated commands, empty slots, native manual sound and unchanged cursor preview')

