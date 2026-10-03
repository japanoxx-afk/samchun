from pathlib import Path
import pefile, struct, re, capstone
game = Path(r'C:\Users\seo\Downloads\DGGL\Games\3KD2120g_Win\3kd2.exe')
p = pefile.PE(str(game)); b = game.read_bytes()
md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32)
def va(off): return p.OPTIONAL_HEADER.ImageBase + p.get_rva_from_offset(off)
def refs(v):
    needle = struct.pack('<I', v); start = 0
    while (off := b.find(needle, start)) >= 0:
        yield off; start = off + 1
print('ImageBase', hex(p.OPTIONAL_HEADER.ImageBase), 'Entry', hex(p.OPTIONAL_HEADER.AddressOfEntryPoint))
for s in p.sections: print(s.Name, hex(s.VirtualAddress), hex(s.PointerToRawData), hex(s.SizeOfRawData))
for match in re.finditer(rb'[ -~]{6,}', b):
    value=match.group().decode('ascii')
    if any(k in value.lower() for k in ['rally', 'gather', 'worker', 'command', 'cursor', '.?av']):
        print('STRING', hex(va(match.start())), value)
        if 'rally' in value.lower():
            for off in refs(va(match.start())):
                print('REF',hex(va(off)))
                for i in md.disasm(b[max(0,off-24):off+80],va(max(0,off-24))): print(hex(i.address),i.mnemonic,i.op_str)
