"""Emulate initial neutral order and native ownership re-insertion notifications."""
import json,struct,sys
from pathlib import Path
from unicorn import Uc,UC_ARCH_X86,UC_MODE_32
from unicorn.x86_const import *
import pefile
p=json.loads(Path(sys.argv[1]).read_text());pe=pefile.PE(sys.argv[2]);section=pe.sections[-1]
u=Uc(UC_ARCH_X86,UC_MODE_32)
for a,size in [(p['code_address'],0x4000000),(0x400000,0x400000),(0x800000,0x100000),(0x100000,0x100000)]:u.mem_map(a,size)
u.mem_write(p['code_address'],pe.get_data(section.VirtualAddress,section.Misc_VirtualSize))
def put(a,v):u.mem_write(a,struct.pack('<I',v))
def get(a):return struct.unpack('<I',u.mem_read(a,4))[0]
player=0x180200;ids=[555,559,560];put(player+4,0x181000);put(player+8,len(ids))
for i,id in enumerate(ids):
 node=0x181000+i*16;unit=0x182000+i*0x100
 u.mem_write(node,struct.pack('<III',0,unit,node+16 if i+1<len(ids) else 0));u.mem_write(unit+0x5c,struct.pack('<H',id))
original=bytes(u.mem_read(0x181000,48))
def enumerate_ids():
 u.reg_write(UC_X86_REG_ESP,0x190000);put(0x190000,0x180100)
 u.reg_write(UC_X86_REG_EAX,player);u.reg_write(UC_X86_REG_ESI,2)
 u.emu_start(p['neutral_order_code_address'],0x180100,count=200000)
 node=u.reg_read(UC_X86_REG_EDI);actual=[]
 while node:
  actual.append(struct.unpack('<H',u.mem_read(get(node+4)+0x5c,2))[0]);node=get(node+8)
 assert get(p['restore_order_status'])==1
 assert bytes(u.mem_read(0x181000,48))==original
 return actual
assert enumerate_ids()==[560,559,555]
def notify(kind,slot,id):
 u.reg_write(UC_X86_REG_ESP,0x190000);put(0x190000,0x180100);put(0x190004,0x183000)
 u.mem_write(0x183000,struct.pack('<III',kind,slot,id))
 u.emu_start(p['neutral_owner_event_address'],0x43a715,count=1000)
 assert u.reg_read(UC_X86_REG_ESP)==0x18fffc
 assert u.reg_read(UC_X86_REG_EBX)==0x183000
notify(18,2,555)
assert enumerate_ids()==[560,559,555]
notify(2,2,555)
assert enumerate_ids()==[555,560,559]
notify(2,9,555);notify(2,2,16384)
assert enumerate_ids()==[555,560,559]
print('PASS ownership return moves an initial ID into the native prefix; invalid messages ignored; world nodes preserved.')
