from pathlib import Path
import struct
from unicorn import Uc,UC_ARCH_X86,UC_MODE_32
from unicorn.x86_const import *
payload=Path('dist/runtime/patches/rally.bin').read_bytes()
n=lambda v:struct.pack('<I',v)
cases=0
for dialog in [60,34]:
 for result in [0,1,13,97]:
  for event,scan in [(117,30),(117,28),(117,156),(4,0),(117,14)]:
   u=Uc(UC_ARCH_X86,UC_MODE_32);u.mem_map(0x400000,0x800000);u.mem_map(0x1000000,0x10000)
   u.mem_write(0xb80000,payload);u.mem_write(0x446b00,b'\xb8'+n(result)+b'\xc3')
   u.mem_write(0x851860,n(dialog));sp=0x1008000;ev=0x1001000;end=0x100f000
   u.mem_write(sp,n(end));u.mem_write(sp+0x38,n(ev));u.mem_write(ev,n(event));u.mem_write(ev+11,struct.pack('<H',scan));u.reg_write(UC_X86_REG_ESP,sp)
   u.emu_start(0xb80c00,end,count=100)
   expected=1 if dialog==60 and result==13 and (event!=117 or scan not in (28,156)) else result
   assert u.reg_read(UC_X86_REG_EAX)==expected
   assert u.reg_read(UC_X86_REG_ESP)==sp+4
   cases+=1
print(f'{cases} prompt cases passed: stale Enter, Return, keypad Return, backspace, cancel, other dialogs')
