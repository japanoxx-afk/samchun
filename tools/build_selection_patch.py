"""Exact native selection relocation and spell dispatch for supported 1.20g."""
import struct
from capstone import Cs, CS_ARCH_X86, CS_MODE_32
S=0xb84000; C=0xb85000; G=0xb86000; D=0xb88000

def build(Code, original, payload):
 md=Cs(CS_ARCH_X86,CS_MODE_32);md.detail=True;md.skipdata=True
 edits={}
 def edit(addr,new):
  o=addr-0x400000; old=original[o:o+len(new)]
  if old!=new: edits[o]=(old,new)
 def imm(addr,value):
  i=next(md.disasm(original[addr-0x400000:addr-0x400000+15],addr))
  assert i.imm_size
  edit(addr+i.imm_offset,int(value).to_bytes(i.imm_size,'little'))
 # Absolute addresses are audited by operand type, avoiding adjacent globals.
 import pefile
 pe=pefile.PE(data=original)
 for sec in pe.sections:
  if not sec.Characteristics&0x20000000:continue
  for i in md.disasm(sec.get_data(),0x400000+sec.VirtualAddress):
   if not i.id:continue
   for op in i.operands:
    kind=op.type; value=op.imm if kind==2 else op.mem.disp if kind==3 else 0
    new=None
    if value in (0x8e1ad0,0x8e1ad4,0x8e1b50):
     new=S+(0x100 if value==0x8e1b50 else value-0x8e1ad0)
     if i.address in (0x528321,0x52835a):new=S+0x80 # original save layout
    elif 0x8dfbd0<=value<0x8dffd0:new=C+value-0x8dfbd0
    elif kind==2 and i.mnemonic=='cmp' and 0x8dffd0<=value<=0x8dffef:new=C+0x800+value-0x8dffd0
    elif value in (0x8e0388,0x8e03a6):new=D+value-0x8e0388
    elif 0x8df568<=value<0x8dfb40 and (value-0x8df568)%0x88 in (0,4):new=G+((value-0x8df568)//0x88)*0x108+(value-0x8df568)%0x88
    elif kind==2 and i.mnemonic=='cmp' and value in (0x8dfb40,0x8dfbc8):new=G+(11 if value==0x8dfb40 else 12)*0x108
    if new is not None:
     off=i.imm_offset if kind==2 else i.disp_offset
     size=i.imm_size if kind==2 else i.disp_size
     assert size==4,(hex(i.address),i.op_str)
     edit(i.address+off,struct.pack('<I',new))
 caps=[0x529277,0x529327,0x529332,0x529427,0x529436,0x5294a5,0x5296d3,0x529835,0x529886,0x52c278,0x52c5ee,0x52c6ab,0x412ed9,0x412ede,0x45bbb2,0x45bbb7]
 for a in caps:imm(a,64)
 for i in md.disasm(original[0x128730:0x1289a0],0x528730):
  if i.imm_size and any(o.type==2 and o.imm==32 for o in i.operands):imm(i.address,64)
 for a in (0x529acb,0x529c28,0x529e1b,0x52a05b,0x52a1eb,0x52a35b):imm(a,65)
 for a in (0x529313,0x5293cf,0x529411,0x529541,0x52954b,0x52957c,0x5296ce,0x529840):imm(a,5)
 for a in (0x52932a,0x52942a):
  i=next(md.disasm(original[a-0x400000:a-0x400000+15],a));edit(a+i.disp_offset,struct.pack('<I',0x100))
 for a in (0x52857a,0x5283ca):imm(a,0x108)
 imm(0x528580,65);imm(0x528591,65);imm(0x52859d,0x200)
 imm(0x52c039,320);imm(0x52c0bd,0xa00)
 imm(0x52c1e6,6);imm(0x52c233,6)
 def block(off,c):
  code=c.finish();assert len(code)<0x200;payload[off:off+len(code)]=code
 def hook(a,target):edit(a,b'\xe8'+struct.pack('<i',target-a-5))
 # Native wire encoder supports 32 commands. Send each 64-entry group in two
 # ordinary packets, with untouched timestamps, owner IDs and game protocol.
 c=Code(0xb82000)
 c.emit('55 53 56 57 83 ec 04 8b 74 24 18 8b 5c 24 1c 8b 6c 24 20 31 ff')
 c.label('group');c.emit('85 ed');c.j('0f 8e','done')
 c.emit('8b 03 83 f8 40');c.j('0f 86','bounded');c.emit('b8 40 00 00 00');c.label('bounded')
 c.emit('89 04 24 85 c0');c.j('0f 8e','next')
 c.emit('83 f8 20');c.j('0f 8e','first');c.emit('c7 04 24 20 00 00 00')
 c.label('first');c.emit('6a 01 8d 44 24 04 50 56');c.call(0x4256f0);c.emit('83 c4 0c 09 c7')
 c.emit('8b 03 83 f8 20');c.j('0f 8e','next');c.emit('83 e8 20 83 f8 20');c.j('0f 86','second');c.emit('b8 20 00 00 00')
 c.label('second');c.emit('89 04 24 6a 01 8d 44 24 04 50 8d 86 00 04 00 00 50');c.call(0x4256f0);c.emit('83 c4 0c 09 c7')
 c.label('next');c.emit('81 c6 00 08 00 00 83 c3 04 4d');c.j('e9','group')
 c.label('done');c.emit('89 f8 83 c4 04 5f 5e 5b 5d c3');block(0x2000,c);hook(0x52c2c3,0xb82000)
 # Builders already validate spell support and actual MP; retain one valid
 # command, starting after the caster used by the preceding click.
 c=Code(0xb82200);c.emit('60 8b 1d 00 42 b8 00 83 e3 3f 31 c9 bf ff ff ff ff')
 c.label('find');c.emit('8d 04 0b 83 e0 3f 89 c2 c1 e2 05 81 c2');c.n(C)
 c.emit('83 3c 85');c.n(S);c.emit('00');c.j('0f 84','skip');c.emit('81 7a 05 d0 07 00 00');c.j('0f 84','eligible');c.emit('81 7a 05 d1 07 00 00');c.j('0f 84','eligible');c.emit('81 7a 05 e0 2e 00 00');c.j('0f 85','skip');c.label('eligible');c.emit('89 c7 40 83 e0 3f a3 00 42 b8 00');c.j('e9','clear')
 c.label('skip');c.emit('41 83 f9 40');c.j('0f 8c','find')
 c.label('clear');c.emit('31 c9 ba');c.n(C)
 c.label('zero');c.emit('39 f9');c.j('0f 84','keep');c.emit('c7 42 05 00 00 00 00')
 c.label('keep');c.emit('83 c2 20 41 83 f9 40');c.j('0f 8c','zero');c.emit('61 e9');c.n(0x52c080-(c.base+len(c.b)+4));block(0x2200,c)
 for a in (0x52d3c4,0x52d6ab,0x52d7b4):
  assert original[a-0x400000:a-0x400000+5]==b'\xe8'+struct.pack('<i',0x52c080-a-5)
  hook(a,0xb82200)
 # Saving remains byte-compatible: temporary counts are capped to the 32 slots
 # serialized by the original game. Live 64 selections/groups are restored.
 c=Code(0xb82400);c.emit('56 57 8b 7c 24 0c e9');c.n(0x5282b6-(c.base+len(c.b)+4));block(0x2400,c)
 c=Code(0xb82600);c.emit('53 55 56 57 83 ec 64 8b 6c 24 78 8b 45 24 85 c0');c.j('0f 85','load')
 c.emit('a1 cc fb 8d 00 89 04 24 83 f8 20');c.j('0f 8e','groups');c.emit('c7 05 cc fb 8d 00 20 00 00 00')
 c.label('groups');c.emit('31 db be');c.n(G)
 c.label('savegroup');c.emit('8b 06 89 44 dc 04 8b 96 84 00 00 00 89 54 dc 08 c7 86 84 00 00 00 00 00 00 00 83 f8 20');c.j('0f 8e','saved');c.emit('c7 06 20 00 00 00')
 c.label('saved');c.emit('81 c6 08 01 00 00 43 83 fb 0c');c.j('0f 8c','savegroup');c.j('e9','call')
 c.label('load');c.emit('31 c0 bf');c.n(S+0x80);c.emit('b9 21 00 00 00 f3 ab bf');c.n(C+0x400);c.emit('b9 00 01 00 00 f3 ab 31 db be');c.n(G)
 c.label('loadgroup');c.emit('8d be 84 00 00 00 b9 21 00 00 00 f3 ab 81 c6 08 01 00 00 43 83 fb 0c');c.j('0f 8c','loadgroup')
 c.label('call');c.emit('55');c.call(0xb82400);c.emit('83 c4 04 89 c7 83 7d 24 00');c.j('0f 85','loaded')
 c.emit('8b 04 24 a3 cc fb 8d 00 31 db be');c.n(G)
 c.label('restore');c.emit('8b 44 dc 04 89 06 8b 54 dc 08 89 96 84 00 00 00 81 c6 08 01 00 00 43 83 fb 0c');c.j('0f 8c','restore')
 c.j('e9','done');c.label('loaded');c.emit('31 c0 31 db be');c.n(G)
 c.label('discard');c.emit('8d be 84 00 00 00 b9 21 00 00 00 f3 ab 81 c6 08 01 00 00 43 83 fb 0c');c.j('0f 8c','discard')
 c.label('done');c.emit('89 f8 83 c4 64 5f 5e 5d 5b c3');block(0x2600,c)
 edit(0x5282b0,b'\xe9'+struct.pack('<i',0xb82600-0x5282b5)+b'\x90')
 from build_rally_sound_patch import build as build_rally_sound
 edits.update(build_rally_sound(Code,original,payload))
 out=bytearray(struct.pack('<I',len(edits)))
 for o,(old,new) in sorted(edits.items()):out+=struct.pack('<II',o,len(old))+old+new
 return bytes(out),edits
