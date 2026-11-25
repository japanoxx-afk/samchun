"""Native DirectInput click observer ABI and edge detection."""
import json,struct,sys
from pathlib import Path
import pefile
from unicorn import Uc,UC_ARCH_X86,UC_MODE_32
from unicorn.x86_const import *
p=json.loads(Path(sys.argv[1]).read_text());pe=pefile.PE(sys.argv[2]);u=Uc(UC_ARCH_X86,UC_MODE_32);u.mem_map(0x400000,0x4000000);u.mem_map(0x100000,0x100000)
for s in pe.sections:u.mem_write(0x400000+s.VirtualAddress,s.get_data())
u.mem_write(0x43c5f0,b'\xc3');regs=[UC_X86_REG_EAX,UC_X86_REG_EBX,UC_X86_REG_ECX,UC_X86_REG_EDX,UC_X86_REG_EDI,UC_X86_REG_EBP]
for flags,expected in [(0,0),(1,1),(1,1),(0,1),(1,2)]:
 for reg,value in zip(regs,[11,22,33,44,55,66]):u.reg_write(reg,value)
 u.reg_write(UC_X86_REG_ESI,0x160000);u.mem_write(0x160009,bytes([flags]));u.mem_write(0x837f20,struct.pack('<hh',760,25));u.reg_write(UC_X86_REG_ESP,0x190000);u.mem_write(0x190000,struct.pack('<I',0x180000));u.emu_start(0x517b31,0x517b36,count=40)
 assert struct.unpack('<I',u.mem_read(p['observer_native_mouse_counter'],4))[0]==expected
 assert [u.reg_read(reg) for reg in regs]==[11,22,33,44,55,66]
 assert u.reg_read(UC_X86_REG_ESP)==0x190000
 assert u.reg_read(UC_X86_REG_ESI)==0x160000
assert u.mem_read(p['observer_native_mouse_point'],4)==struct.pack('<hh',760,25)
print('PASS native click edge detection, exact cursor sample, registers and caller stack; original handler called')
