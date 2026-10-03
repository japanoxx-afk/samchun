"""Execute original selection/control-group/command loops and new dispatch hooks."""
from pathlib import Path
import struct,pefile
from unicorn import Uc,UC_ARCH_X86,UC_MODE_32,UC_HOOK_CODE
from unicorn.x86_const import *
P=pefile.PE(r'C:\Users\seo\Downloads\DGGL\Games\3KD2120g_Win\3kd2.exe')
def patched_image():
 data=bytearray(P.get_memory_mapped_image());m=Path('assets/selection.bin').read_bytes();off=4
 for _ in range(struct.unpack_from('<I',m)[0]):
  pos,length=struct.unpack_from('<II',m,off);off+=8
  assert data[pos:pos+length]==m[off:off+length]
  data[pos:pos+length]=m[off+length:off+2*length];off+=2*length
 return bytes(data)
IMAGE=patched_image();PAYLOAD=Path('assets/rally.bin').read_bytes()
S,C,G,D=0xb84000,0xb85000,0xb86000,0xb88000
STACK,END=0x1108000,0x110f000
n=lambda v:struct.pack('<I',v&0xffffffff)
class Case:
 def __init__(self,count=64):
  self.u=u=Uc(UC_ARCH_X86,UC_MODE_32);u.mem_map(0x400000,0x800000);u.mem_write(0x400000,IMAGE);u.mem_write(0xb80000,PAYLOAD);u.mem_map(0x1000000,0x200000)
  self.units=[0x1000000+i*0x1000 for i in range(count)];self.callbacks={};self.stub=0x1111000
  self.put(0x8dfbcc,count)
  for i,obj in enumerate(self.units):
   self.put(S+i*4,obj);table=obj+0x400;self.put(obj,table);self.put(obj+4,i+1)
   for off,value,pop in [(0x24,0x410,0),(0x214,0,0),(0x6e0,0,0),(0x1e8,3000,12),(0x2e0,0,8),(0x2f0,1,0),(0x620,1,4),(0x624,1,4),(0x128,0,0)]:self.method(table,off,b'\xb8'+n(value)+(b'\xc2'+struct.pack('<H',pop) if pop else b'\xc3'))
   self.method(table,0x1f0,bytes.fromhex('8b 41 04 c3'))
   a=self.stub;self.method(table,0x170,b'\x51\xe8'+struct.pack('<i',0x52c690-a-6)+bytes.fromhex('83 c4 04 c3'))
   a=self.stub;self.method(table,0x174,b'\x51\xe8'+struct.pack('<i',0x52c610-a-6)+bytes.fromhex('83 c4 04 c3'))
  u.hook_add(UC_HOOK_CODE,self.hook)
  for a in (0x40d270,0x40f2a0,0x43b7d0,0x5319e0,0x573670,0x4e2970,0x500fb0,0x515a80):self.callbacks[a]=lambda: self.ret(1)
 def method(self,table,off,code):self.put(table+off,self.stub);self.u.mem_write(self.stub,code);self.stub+=64
 def put(self,a,v):self.u.mem_write(a,n(v))
 def get(self,a):return struct.unpack('<I',self.u.mem_read(a,4))[0]
 def ret(self,v=1,pop=0):
  u=self.u;sp=u.reg_read(UC_X86_REG_ESP);u.reg_write(UC_X86_REG_EAX,v);u.reg_write(UC_X86_REG_EIP,self.get(sp));u.reg_write(UC_X86_REG_ESP,sp+4+pop)
 def hook(self,u,a,size,data):
  if a in self.callbacks:self.callbacks[a]()
 def run(self,a,args=()):
  self.put(STACK,END)
  for i,arg in enumerate(args):self.put(STACK+4+i*4,arg)
  self.u.reg_write(UC_X86_REG_ESP,STACK);self.u.emu_start(a,END,count=200000)
  assert self.u.reg_read(UC_X86_REG_EIP)==END,hex(self.u.reg_read(UC_X86_REG_EIP))
  assert self.u.reg_read(UC_X86_REG_ESP)==STACK+4
 def command_ids(self):return [self.get(C+i*32+10) for i in range(64) if self.get(C+i*32+5)]

def tests():
 cases=0
 # True native insertion rejects the 65th and selection clear removes all 64.
 c=Case(0)
 for i in range(70):c.run(0x52c690,(0x1000000+i*0x1000,))
 assert c.get(0x8dfbcc)==64 and c.get(S+252)==0x1000000+63*0x1000;cases+=1
 c=Case();c.run(0x52c6f0);assert c.get(0x8dfbcc)==0 and bytes(c.u.mem_read(S,256))==bytes(256);cases+=1
 # Native control-group save and recall, including units 33..64.
 c=Case();c.run(0x529480,(3,));assert c.get(G+3*0x108)==64
 assert [c.get(G+3*0x108+4+i*4) for i in range(64)]==c.units
 c.run(0x529670,(3,));assert c.get(0x8dfbcc)==64;cases+=1
 c.run(0x529300,(3,c.units[-1]));assert c.get(G+3*0x108)==63;cases+=1
 # Actual native ground command builder emits all IDs, correct 32-byte records.
 c=Case()
 def position():
  sp=c.u.reg_read(UC_X86_REG_ESP);out=c.get(sp+4);c.u.mem_write(out,struct.pack('<hhh',100,200,0));c.ret(out,8)
 c.callbacks[0x453800]=position;c.run(0x52f1a0,(0,0,0));assert c.command_ids()==list(range(1,65));cases+=1
 # Actual native dispatcher groups 64 commands; wrapper calls unchanged sender twice.
 sent=[]
 def sender():
  sp=c.u.reg_read(UC_X86_REG_ESP);ptr=c.get(sp+4);amount=c.get(c.get(sp+8));assert c.get(sp+12)==1 and 0<amount<=32
  sent.extend(c.get(ptr+i*32+10) for i in range(amount));c.ret()
 c.callbacks[0x4256f0]=sender
 def finish():c.u.reg_write(UC_X86_REG_EIP,END);c.u.reg_write(UC_X86_REG_ESP,STACK+4)
 c.callbacks[0x52c2cb]=finish;c.run(0x52c080);assert sent==list(range(1,65));cases+=1
 # Wrapper boundaries with multiple different command groups.
 for counts in ([0],[1],[31],[32],[33],[64],[64,17,33,0,64]):
  c=Case(0);seen=[]
  for j,amount in enumerate(counts):
   c.put(0x1100000+j*4,amount)
   for i in range(amount):c.put(D+j*0x800+i*32+10,100*j+i+1)
  def sender():
   sp=c.u.reg_read(UC_X86_REG_ESP);ptr=c.get(sp+4);amount=c.get(c.get(sp+8));assert 1<=amount<=32 and c.get(sp+12)==1
   seen.extend(c.get(ptr+i*32+10) for i in range(amount));c.ret()
  c.callbacks[0x4256f0]=sender;c.run(0xb82000,(D,0x1100000,len(counts)))
  assert seen==[100*j+i+1 for j,amount in enumerate(counts) for i in range(amount)];cases+=1
 # Native packet encoder receives ordinary <=32-unit packets; bounded wire writes.
 for command in (2000,2001,3000,12000):
  for amount in (1,32):
   c=Case(0);out=0x1102000;c.u.mem_write(out,b'\xcc'*200)
   for i in range(amount):c.put(C+i*32+5,command);c.put(C+i*32+10,i+1)
   c.run(0x426330,(C,out,amount));packet=bytes(c.u.mem_read(out,111))
   assert packet[0]==amount and [struct.unpack_from('<H',packet,11+i*2)[0] for i in range(amount)]==list(range(1,amount+1))
   assert bytes(c.u.mem_read(out+111,89))==b'\xcc'*89;cases+=1
 # One valid caster per click, wraparound, insufficient-MP/unsupported zero commands.
 for eligible in ([0,1,2], [32,63], [63], [], list(range(64))):
  c=Case();observed=[]
  def filtered():
   observed.append([i for i in range(64) if c.get(C+i*32+5)])
   c.ret()
  c.callbacks[0x52c080]=filtered
  for click in range(max(3,len(eligible)+1)):
   for i in range(64):c.put(C+i*32+5,12000 if i in eligible else 0)
   c.run(0xb82200)
  expected=[[eligible[i%len(eligible)]] for i in range(len(observed))] if eligible else [[]]*len(observed)
  assert observed==expected,(eligible,observed);cases+=1
 # Save compatibility wrapper caps serialized counts, restores live selections.
 for load in (False,True):
  c=Case();file=0x1100000;c.put(file+0x24,int(load))
  for j in range(12):c.put(G+j*0x108,64)
  def serialize():
   if load:
    c.put(0x8dfbcc,32)
    for j in range(12):c.put(G+j*0x108,32)
   else:
    assert c.get(0x8dfbcc)==32 and all(c.get(G+j*0x108)==32 for j in range(12))
   c.ret()
  c.callbacks[0xb82400]=serialize;c.run(0xb82600,(file,))
  assert c.get(0x8dfbcc)==(32 if load else 64)
  assert all(c.get(G+j*0x108)==(32 if load else 64) for j in range(12))
  if load:assert bytes(c.u.mem_read(S+128,132))==bytes(132)
  cases+=1
 # Execute original serializer through wrapper, then replay its legacy stream.
 c=Case();file=0x1100000;stream=[]
 for j in range(12):
  c.put(G+j*0x108,64)
  for i,obj in enumerate(c.units):c.put(G+j*0x108+4+i*4,obj)
 def scalar():
  sp=c.u.reg_read(UC_X86_REG_ESP);ptr=c.get(sp+4);stream.append(bytes(c.u.mem_read(ptr,4)));c.ret(1,4)
 def buffer():
  sp=c.u.reg_read(UC_X86_REG_ESP);ptr=c.get(sp+4);size=c.get(sp+8);stream.append(bytes(c.u.mem_read(ptr,size)));c.ret(1,8)
 c.callbacks[0x500400]=scalar;c.callbacks[0x500380]=buffer;c.callbacks[0x556cb0]=lambda:c.ret()
 c.run(0x5282b0,(file,));assert struct.unpack('<I',stream[1])[0]==32
 assert all(c.get(G+j*0x108)==64 and c.get(G+j*0x108+0x84)==c.units[32] for j in range(12))
 # Group records start after position/count/32 IDs/buffer/other native fields.
 group_start=38
 assert len(stream)>=group_start+12*34,(len(stream),group_start)
 for j in range(12):
  assert struct.unpack('<I',stream[group_start+j*34])[0]==32
  assert stream[group_start+j*34+33]==n(0xffffffff)
 saved=list(stream);c.put(file+0x24,1)
 def scalar_load():
  sp=c.u.reg_read(UC_X86_REG_ESP);ptr=c.get(sp+4);c.u.mem_write(ptr,saved.pop(0));c.ret(1,4)
 def buffer_load():
  sp=c.u.reg_read(UC_X86_REG_ESP);ptr=c.get(sp+4);size=c.get(sp+8);data=saved.pop(0);assert len(data)==size;c.u.mem_write(ptr,data);c.ret(1,8)
 c.callbacks[0x500400]=scalar_load;c.callbacks[0x500380]=buffer_load
 c.callbacks[0x446200]=lambda:c.ret(c.units[c.get(c.u.reg_read(UC_X86_REG_ESP)+4)-1])
 c.run(0x5282b0,(file,));assert not saved and c.get(0x8dfbcc)==32
 assert all(c.get(G+j*0x108)==32 and c.get(G+j*0x108+0x84)==0 for j in range(12));cases+=1
 # Real native spell construction checks MP and ability support before filter.
 for eligible in ([1,2],[32,63],[],[63]):
  c=Case();definition=0x1103000;table=0x1104000;c.put(definition,table)
  c.method(table,0,b'\xb8'+n(2300)+b'\xc3')
  c.method(table,0xe4,b'\xb8'+n(0x40)+b'\xc3')
  c.method(table,0x78,b'\xb8'+n(50)+b'\xc3')
  for i,obj in enumerate(c.units):
   c.put(obj+0x80,100 if i in eligible else 49)
   c.put(obj+0x84,int(i%2==0 or i in eligible))
   c.method(obj+0x400,0x224,bytes.fromhex('8b 81 80 00 00 00 c3'))
   c.method(obj+0x400,0x84,bytes.fromhex('8b 81 84 00 00 00 c2 04 00'))
   c.method(obj+0x400,0x428,bytes.fromhex('31 c0 c2 04 00'))
  c.put(0x8dffe4,2300);c.put(0x6c3edc,64)
  c.callbacks[0x42f870]=lambda:c.ret(0)
  c.callbacks[0x5308d0]=lambda:c.ret(1)
  c.callbacks[0x446200]=lambda:c.ret(c.units[0])
  c.callbacks[0x4fba40]=lambda:c.ret(definition)
  def position():
   sp=c.u.reg_read(UC_X86_REG_ESP);out=c.get(sp+4);c.u.mem_write(out,struct.pack('<hhh',100,200,0));c.ret(out,8)
  c.callbacks[0x453800]=position;c.callbacks[0x521320]=lambda:c.ret()
  observed=[]
  def filtered():
   observed.append([i for i in range(64) if c.get(C+i*32+5)])
   c.ret()
  c.callbacks[0x52c080]=filtered
  for click in range(3):
   c.u.mem_write(C,bytes(0x800));c.run(0x52d400,(100,200))
  assert observed==([[eligible[i%len(eligible)]] for i in range(3)] if eligible else [[],[],[]]),observed
  cases+=1
 print(f'{cases} selection/spell cases passed: native 64 insertion, clear, groups, ground commands, dispatch, bounded wire packets, round robin, compatible save wrapper')
if __name__=='__main__':tests()

