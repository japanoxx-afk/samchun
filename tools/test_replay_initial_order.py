"""Neutral enumeration shadow tests; live two-match checks are separate."""
import json,struct,sys
from pathlib import Path
from unicorn import Uc,UC_ARCH_X86,UC_MODE_32
from unicorn.x86_const import *
import pefile
p=json.loads(Path(sys.argv[1]).read_text());exe=Path(sys.argv[2]);pe=pefile.PE(str(exe));section=pe.sections[-1]
u=Uc(UC_ARCH_X86,UC_MODE_32)
for a,size in [(p['code_address'],0x4000000),(0x400000,0x400000),(0x800000,0x100000),(0x100000,0x100000)]:u.mem_map(a,size)
u.mem_write(p['code_address'],pe.get_data(section.VirtualAddress,section.Misc_VirtualSize))
def put(a,v):u.mem_write(a,struct.pack('<I',v))
def get(a):return struct.unpack('<I',u.mem_read(a,4))[0]
player=0x180200;ids=[12,12288,10,14];put(player+4,0x181000);put(player+8,len(ids))
for i,id in enumerate(ids):
 node=0x181000+i*16;unit=0x182000+i*0x100
 u.mem_write(node,struct.pack('<III',0,unit,node+16 if i+1<len(ids) else 0));u.mem_write(unit+0x5c,struct.pack('<H',id))
original=bytes(u.mem_read(0x181000,64));head=get(player+4)
u.reg_write(UC_X86_REG_ESP,0x190000);put(0x190000,0x180100)
u.reg_write(UC_X86_REG_EAX,player);u.reg_write(UC_X86_REG_ESI,4);u.reg_write(UC_X86_REG_EDI,0x1234);u.reg_write(UC_X86_REG_EBX,99)
u.emu_start(p['neutral_order_code_address'],0x180100,count=200000)
assert get(p['restore_order_status'])==1
expected_order=json.loads(Path(sys.argv[3]).read_text())['initial_checkpoint']['player_unit_order'][4]
expected=[12288]+[id for id in expected_order if id in ids]
node=u.reg_read(UC_X86_REG_EDI);actual=[]
while node:
 actual.append(struct.unpack('<H',u.mem_read(get(node+4)+0x5c,2))[0]);node=get(node+8)
assert actual==expected,(actual,expected)
assert bytes(u.mem_read(0x181000,64))==original and get(player+4)==head
assert u.reg_read(UC_X86_REG_EBX)==99 and u.reg_read(UC_X86_REG_ESP)==0x190004
assert get(0x190014)==u.reg_read(UC_X86_REG_EDI)
print('PASS source-order neutral enumeration including new units, without changing world nodes or native iterators')
