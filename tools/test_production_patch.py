"""Original training callback, queue/cost checks, per-building native command."""
from test_selection_patch import *

def setup(specs,budget=10000):
 c=Case(len(specs));sent=[];messages=[];remaining=[budget];definition=0x1103000;table=0x1104000;world=0x1105000;player=0x1106000
 c.put(definition,table);c.put(world+8,2);c.put(world+12,player);c.put(world+16,player)
 for off,value in ((0xa0,25),(0xa4,0),(0xa8,1)):
  c.method(table,off,b'\xb8'+n(value)+b'\xc3')
 for i,(obj,spec) in enumerate(zip(c.units,specs)):
  for field,key,default in ((0x80,'queue',0),(0x84,'type',1501),(0x88,'dead',0),(0x8c,'owner',0),(0x90,'building',1)):
   c.put(obj+field,spec.get(key,default))
  for off,field in ((0x384,0x80),(0x24,0x84),(0x250,0x88),(0x214,0x8c),(0x128,0x90)):
   c.method(obj+0x400,off,b'\x8b\x81'+n(field)+(bytes.fromhex('c2 04 00') if off==0x384 else b'\xc3'))
 c.put(0x6c3edc,len(specs)+1)
 c.callbacks[0x43a7d0]=lambda:c.ret(world)
 c.callbacks[0x5308d0]=lambda:c.ret(1)
 c.callbacks[0x573670]=lambda:c.ret(0)
 c.callbacks[0x446200]=lambda:c.ret(c.units[c.get(c.u.reg_read(UC_X86_REG_ESP)+4)-1])
 c.callbacks[0x4fba40]=lambda:c.ret(definition)
 c.callbacks[0x5319e0]=lambda:c.ret(int(c.get(c.u.reg_read(UC_X86_REG_ESP)+4)==0))
 c.callbacks[0x51d870]=lambda:c.ret(1,4)
 c.callbacks[0x51d6a0]=lambda:c.ret(int(remaining[0]>=25),12)
 def sender():
  sp=c.u.reg_read(UC_X86_REG_ESP);ptr=c.get(sp+4);assert c.get(sp+8)==1
  data=bytes(c.u.mem_read(ptr,32));command=struct.unpack_from('<I',data,5)[0];unit=struct.unpack_from('<I',data,10)[0];kind=struct.unpack_from('<I',data,14)[0]
  assert command==5008 and kind==1040 and remaining[0]>=25
  sent.append(unit);remaining[0]-=25;c.ret()
 c.callbacks[0x425510]=sender
 c.callbacks[0x521320]=lambda:(messages.append(c.get(c.u.reg_read(UC_X86_REG_ESP)+4)),c.ret())[-1]
 return c,sent,remaining,messages
cases=0
for count in (1,2,3,32,64):
 c,sent,budget,msg=setup([{}]*count)
 event=0x1107000;button=event+0x100;c.put(event,0);c.put(button+0x2d,1040)
 c.run(0x40db20,(event,button,6));assert sent==list(range(1,count+1));cases+=1
 # Repeated click queues one more item per selected building.
 c.run(0x40db20,(event,button,6));assert sent==list(range(1,count+1))*2;cases+=1
for specs,budget,expected in [([{}, {'queue':5},{}],100,[1,3]),([{},{}],25,[1]),([{},{}],0,[]),([{}, {'dead':1},{}],100,[1,3]),([{}, {'owner':1},{}],100,[1,3]),([{}, {'type':1502},{}],100,[1,3]),([{}, {'building':0},{}],100,[1,3])]:
 c,sent,remaining,msg=setup(specs,budget);c.run(0xb82a00,(1,1040));assert sent==expected,(specs,sent);assert remaining[0]>=0;cases+=1
# In-game menu redirect requires homogeneous owned buildings only.
for specs,expected in [([{},{}],'building'),([{}]*64,'building'),([{}, {'type':1502}],'native'),([{}, {'owner':1}],'native'),([{}, {'dead':1}],'native'),([{}, {'building':0}],'native'),([{}],'building')]:
 c,_,_,_=setup(specs);seen=[]
 def path(name):
  seen.append(name);c.ret()
 c.callbacks[0x4130dd]=lambda:path('building');c.callbacks[0x4127fb]=lambda:path('native')
 c.u.reg_write(UC_X86_REG_EAX,len(specs));c.u.reg_write(UC_X86_REG_ESI,1);c.run(0x4127f3);assert seen==[expected],(specs,seen);cases+=1
# Producer outside the selected buildings retains the original single command path.
c,sent,_,_=setup([{'building':0},{}]);c.run(0xb82a00,(1,1040));assert sent==[1];cases+=1
print(f'{cases} production cases passed: actual button callback, 1..64 native training commands, repeat, queue capacity, costs, ownership, dead/mixed buildings and menu routing')

