"""Verify the editor's relocated draw-list frame against a large viewport."""
import argparse, struct
import pefile
from unicorn import Uc, UC_ARCH_X86, UC_MODE_32
from unicorn.x86_const import UC_X86_REG_EBP
parser=argparse.ArgumentParser()
parser.add_argument('original');parser.add_argument('patched');args=parser.parse_args()
old=pefile.PE(args.original);new=pefile.PE(args.patched)
assert new.get_data(0x1bd9f,5)==bytes.fromhex('e94f000000')
assert new.get_data(0x1c80f,2)==bytes.fromhex('eb20')
assert new.get_data(0x3f9d8,2)==bytes.fromhex('9090')
assert struct.unpack('<I',new.get_data(0x2277a,4))[0]==0x4004c
for count in [1024,4095,16383,65535]:
 u=Uc(UC_ARCH_X86,UC_MODE_32);u.mem_map(0x400000,0x30000);u.mem_map(0x100000,0x100000)
 u.mem_write(0x42293c,new.get_data(0x2293c,0x24));frame=0x180000;u.reg_write(UC_X86_REG_EBP,frame)
 u.mem_write(frame,struct.pack('<I',0x12345678));u.mem_write(frame-0x40004,struct.pack('<I',count));u.mem_write(frame-0x40030,struct.pack('<I',0x76543210))
 u.emu_start(0x42293c,0x42295e)
 assert struct.unpack('<I',u.mem_read(frame-0x40000+count*4,4))[0]==0x76543210
 assert struct.unpack('<I',u.mem_read(frame,4))[0]==0x12345678
 assert struct.unpack('<I',u.mem_read(frame-0x40004,4))[0]==count+1
print('Large viewport draw-list writes retain the frame at 1024, 4095, 16383 and 65535 objects.')

