"""Native sampler must not treat sprite heap pointers as simulation fields."""
import json,struct,sys
from pathlib import Path
from unicorn import Uc,UC_ARCH_X86,UC_MODE_32
from unicorn.x86_const import *
p=json.loads(Path(sys.argv[1]).read_text())
def sample(sprite_pointer,hp):
 u=Uc(UC_ARCH_X86,UC_MODE_32)
 for a,size in [(p['code_address'],0x400000),(0x400000,0x300000),(0x800000,0x100000),(0x100000,0x100000)]:u.mem_map(a,size)
 u.mem_write(p['state_code_address'],bytes.fromhex(p['state_code_hex']))
 def put(a,v):u.mem_write(a,struct.pack('<I',v))
 put(0x8a1238,1);put(0x6c3edc,2);put(0x838c98,0x120000)
 put(0x120000,0x121000);put(0x120004,0x122000)
 for obj,vt in [(0x121000,0x680000),(0x122000,0x681000)]:
  put(obj,vt);u.mem_write(obj+4,struct.pack('<Hhhh',1026,10,20,0))
 put(0x680220,0x503c50);put(0x681220,0x56bde0)
 u.mem_write(0x1210a1,struct.pack('<HH',hp,65));put(0x1220a1,sprite_pointer)
 put(0x1220ae,sprite_pointer);put(0x1220b7,sprite_pointer)
 put(p['state_header']+24,0xffffffff);put(p['state_header']+28,0xffffffff)
 put(0x190000,0x180000);u.reg_write(UC_X86_REG_ESP,0x190000)
 u.reg_write(UC_X86_REG_EBX,0);u.emu_start(p['state_targets']['sample'],0x180000,count=100000)
 stride=p['state_storage'];raw=bytes(u.mem_read(stride,112))
 assert struct.unpack_from('<I',raw,48+28)[0]==1
 assert struct.unpack_from('<I',raw,80+28)[0]==0
 assert raw[96:108]==bytes(12)
 return struct.unpack_from('<I',raw,28)[0]
a=sample(0x0512abcd,150);b=sample(0x0678def0,150);c=sample(0x0678def0,149)
assert a==b and a!=c
print('PASS sprite pointer relocation leaves digest unchanged; a real unit HP change alters it; layout flags correct.')
