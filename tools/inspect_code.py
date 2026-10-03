from pathlib import Path
import struct, capstone, sys
b=Path(r'C:\Users\seo\Downloads\DGGL\Games\3KD2120g_Win\3kd2.exe').read_bytes()
c=capstone.Cs(capstone.CS_ARCH_X86,capstone.CS_MODE_32)
if sys.argv[1]=='refs':
 for value in sys.argv[2:]:
  v=int(value,16); needle=struct.pack('<I',v); start=0
  while (off:=b.find(needle,start))>=0:
   start=off+1
   print(hex(v),'REF',hex(off+0x400000))
else:
 for value in sys.argv[1:]:
  address,size=(int(x,16) for x in value.split(':')); off=address-0x400000
  print('\nDISASM',hex(address))
  for i in c.disasm(b[off:off+size],address):print(hex(i.address),i.mnemonic,i.op_str)
