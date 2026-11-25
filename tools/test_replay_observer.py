"""Executable input-sink ABI and non-mutating display facade checks."""
import json,struct,sys
from pathlib import Path
import pefile
from unicorn import Uc,UC_ARCH_X86,UC_MODE_32
from unicorn.x86_const import *
p=json.loads(Path(sys.argv[1]).read_text());pe=pefile.PE(sys.argv[2]);u=Uc(UC_ARCH_X86,UC_MODE_32)
u.mem_map(0x400000,0x4000000);u.mem_map(0x100000,0x100000)
for section in pe.sections:u.mem_write(0x400000+section.VirtualAddress,section.get_data())
regs=[UC_X86_REG_EBX,UC_X86_REG_ECX,UC_X86_REG_EDX,UC_X86_REG_ESI,UC_X86_REG_EDI,UC_X86_REG_EBP]
for number,site in enumerate([0x425510,0x4256f0]):
 for reg,value in zip(regs,[11,22,33,44,55,66]):u.reg_write(reg,value)
 u.reg_write(UC_X86_REG_ESP,0x190000);u.mem_write(0x190000,struct.pack('<IIII',0x180000,0,0,0))
 u.emu_start(site,0x180000,count=20)
 assert u.reg_read(UC_X86_REG_EAX)==1 and u.reg_read(UC_X86_REG_ESP)==0x190004
 assert [u.reg_read(r) for r in regs]==[11,22,33,44,55,66]
 assert struct.unpack('<I',u.mem_read(p['observer_blocked_counter'],4))[0]==number+1
for site,result in [(0x42f2c0,1),(0x42f340,12),(0x42f370,18),(0x42f3a0,12),(0x42f3f0,1),(0x42f420,1)]:
 u.reg_write(UC_X86_REG_ESP,0x190000);u.mem_write(0x190000,struct.pack('<I',0x180000))
 u.emu_start(site,0x180000,count=5);assert u.reg_read(UC_X86_REG_EAX)==result
# Shared AI/target visibility and the fog-grid implementation remain original.
original=pefile.PE(r'C:\Users\seo\Downloads\DGGL\Games\3KD2120g_Win\3kd2.exe')
for address in [0x42f870,0x42f010,0x42f0c0]:
 assert pe.get_data(address-0x400000,12)==original.get_data(address-0x400000,12)
assert pe.get_data(0x141d5f,5)==bytes.fromhex('b801000000')
assert pe.get_data(0x141d7b,2)==bytes.fromhex('eb60')
for typ in [12,13]:
 u.mem_write(0x160000,bytes(64));u.mem_write(0x160004,bytes([typ]))
 u.reg_write(UC_X86_REG_ESI,0x160000);u.reg_write(UC_X86_REG_EDI,0x170000)
 u.reg_write(UC_X86_REG_ESP,0x190000);u.mem_write(0x190000,struct.pack('<5I',55,44,0x180000,17,18))
 u.emu_start(0x4ecee5,0x180000,count=40)
 assert u.reg_read(UC_X86_REG_EAX)==1 and u.reg_read(UC_X86_REG_ESP)==0x190014
 assert u.reg_read(UC_X86_REG_ESI)==44 and u.reg_read(UC_X86_REG_EDI)==55
 assert struct.unpack('<I',u.mem_read(0x160000,4))[0]==0x68e3d0
 assert u.mem_read(0x160004,1)==bytes([typ])
assert struct.unpack('<I',u.mem_read(p['observer_empty_image_counter'],4))[0]==2
print('PASS outgoing input consumed without network calls; cdecl stack/registers intact; display visibility separate from native AI/grid')

# Enemy progress is a display-only override; preserve the shared alliance function.
for address in [0x5319e0]:
 assert pe.get_data(address-0x400000,32)==original.get_data(address-0x400000,32)
assert len(p['observer_native_progress_sites'])==11
for address in p['observer_native_progress_sites']:
 assert original.get_data(address-0x400000,5)==b'\xe8'+struct.pack('<i',0x5319e0-address-5)
 assert pe.get_data(address-0x400000,5)==bytes.fromhex('b801000000')
 u.reg_write(UC_X86_REG_ESP,0x190000)
 u.mem_write(0x190000,struct.pack('<I',7))
 u.emu_start(address,address+5,count=1)
 assert u.reg_read(UC_X86_REG_EAX)==1 and u.reg_read(UC_X86_REG_ESP)==0x190000
print('PASS all 11 native HUD progress guards; shared alliance query and caller stack preserved')
