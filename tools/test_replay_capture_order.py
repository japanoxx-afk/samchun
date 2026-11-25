"""Initial order hook shadow test; source live-game snapshots are separate."""
import json,struct,sys
from unicorn import Uc,UC_ARCH_X86,UC_MODE_32
from unicorn.x86_const import *
p=json.load(open(sys.argv[1]));u=Uc(UC_ARCH_X86,UC_MODE_32)
for a,n in [(p['code_address'],0x4000000),(0x400000,0x400000),(0x800000,0x100000),(0x100000,0x100000)]:u.mem_map(a,n)
def put(a,v):u.mem_write(a,struct.pack('<I',v))
def get(a):return struct.unpack('<I',u.mem_read(a,4))[0]
u.mem_write(p['order_capture_code_address'],bytes.fromhex(p['order_capture_code_hex']))
u.mem_write(p['state_targets']['before'],b'\xff\x05'+struct.pack('<I',0x180000)+b'\xc3')
put(0x837dcc,0x180200);put(p['initial_save_header'],4)
for slot,ids in [(0,[12289,4]),(4,[10])]:
 player=0x181000+slot*0x100;put(0x18020c+slot*4,player);put(player+8,len(ids));put(player+4,player+0x20)
 for i,id in enumerate(ids):
  node=player+0x20+i*16;unit=0x185000+slot*0x1000+i*0x100
  u.mem_write(node,struct.pack('<III',0,unit,node+16 if i+1<len(ids) else 0));u.mem_write(unit+0x5c,struct.pack('<H',id))
for _ in range(2):
 u.reg_write(UC_X86_REG_ESP,0x190000);put(0x190000,0x180100)
 u.emu_start(p['order_capture_code_address'],0x180100,count=10000)
assert get(p['initial_order_ready'])==1 and get(p['initial_order_error'])==0 and get(0x180000)==2
counts=struct.unpack('<9I',u.mem_read(p['initial_order_address'],36));assert counts==(2,0,0,0,1,0,0,0,0)
assert struct.unpack('<2H',u.mem_read(p['initial_order_address']+36,4))==(12289,4)
assert struct.unpack('<H',u.mem_read(p['initial_order_address']+36+4*32768,2))==(10,)
print('PASS one exact initial owner-list order snapshot, then native dispatch unchanged')
