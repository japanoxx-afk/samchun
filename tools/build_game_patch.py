"""Build position-specific x86 hooks for the exact supported 3KD2 1.20g binary.
No game file is modified by this script; it emits launcher payload assets.
"""
from pathlib import Path
import struct, json, hashlib, pefile

GAME=Path(r'C:\Users\seo\Downloads\DGGL\Games\3KD2120g_Win\3kd2.exe')
b=GAME.read_bytes(); p=pefile.PE(data=b)
assert hashlib.sha256(b).hexdigest()=='a0ee96931b3b74fce739062d8e58253892510ef863e9127648ac38fd4d515f99'
align=lambda n,a:(n+a-1)//a*a
rva=align(max(s.VirtualAddress+max(s.Misc_VirtualSize,s.SizeOfRawData) for s in p.sections),p.OPTIONAL_HEADER.SectionAlignment)
BASE=p.OPTIONAL_HEADER.ImageBase+rva

class Code:
 def __init__(self,base): self.base=base; self.b=bytearray(); self.labels={}; self.fix=[]
 def emit(self,s): self.b.extend(bytes.fromhex(s))
 def n(self,n): self.b.extend(struct.pack('<I',n&0xffffffff))
 def label(self,s): self.labels[s]=len(self.b)
 def j(self,op,label): self.emit(op); self.fix.append((len(self.b),label)); self.n(0)
 def call(self,target): self.emit('e8'); self.n(target-self.base-len(self.b)-4)
 def finish(self):
  for o,l in self.fix: struct.pack_into('<i',self.b,o,self.labels[l]-o-4)
  return bytes(self.b)

# Replace only the per-entity right-click command decision. The original network
# batching and rally receiver remain intact. Preserve thiscall's 12-byte cleanup.
right=Code(BASE)
right.emit('9c 60 89 ce') # save flags/registers; esi = selected entity
right.emit('8b 06 ff 90 28 01 00 00 85 c0') # native IsBuilding
right.j('0f 84','original')
# The native base rally setter/getter pair is required; exclude scenery objects.
right.emit('8b 06 81 b8 6c 03 00 00');right.n(0x503f40)
right.j('0f 85','original')
right.emit('81 b8 70 03 00 00');right.n(0x54e330)
right.j('0f 85','original')
# All native building entities accept rally positions; units retain native decisions.
right.emit('61 9d b8 c0 0b 00 00 c2 0c 00')
right.label('original');right.emit('61 9d ff a0 e8 01 00 00')
right_bytes=right.finish()

# The production-with-rally path issues a Move command to a newly created unit.
# Resolve the world target and call Worker's native contextual command resolver.
# Accept ONLY the two native resource gather commands (4001/4002).
gather=Code(BASE+0x200)
gather.emit('9c 60 89 ce 8b 7c 24 28') # esi=unit, edi=command (return + pushfd/pushad)
gather.emit('81 7f 05 b8 0b 00 00');gather.j('0f 85','dispatch')
gather.emit('8b 06 81 b8 ec 01 00 00');gather.n(0x567840)
gather.j('0f 85','dispatch') # only Worker contextual handler
gather.emit('0f bf 47 1c 50 0f bf 47 1a 50 8b 0d');gather.n(0x838c78)
gather.call(0x453c80) # native map hit test, callee pops x/y
gather.emit('85 c0');gather.j('0f 84','dispatch')
gather.emit('89 c3 8b 10 89 d9 ff 92 50 02 00 00 83 f8 01')
gather.j('0f 84','dispatch') # dead/inactive target
gather.emit('8b 06 6a 00 53 89 f1 ff 90 ec 01 00 00')
gather.emit('3d a1 0f 00 00');gather.j('0f 84','accept')
gather.emit('3d a2 0f 00 00');gather.j('0f 85','dispatch')
gather.label('accept');gather.emit('89 47 05 8b 03 89 d9 ff 90 f0 01 00 00 89 47 0e')
gather.emit('61 9d ff 60 38') # issue only a resolved gather command
gather.label('dispatch');gather.emit('61 9d c2 04 00') # keep native adjusted Move on rejection
gather_bytes=gather.finish()
# Target right-click uses a distinct native route. Preserve its target ID while
# supplying the target's world position for the rally receiver.
target=Code(BASE+0x100)
target.emit('9c 60 89 cf 8b 5c 24 28 8b 6c 24 04')
target.emit('8b 07 ff 90 28 01 00 00 85 c0');target.j('0f 84','original')
target.emit('8b 07 81 b8 6c 03 00 00');target.n(0x503f40);target.j('0f 85','original')
target.emit('81 b8 70 03 00 00');target.n(0x54e330);target.j('0f 85','original')
target.emit('85 db');target.j('0f 84','original')
target.emit('83 ec 08 89 e0 50 89 d9 8b 13 ff 92 b8 00 00 00')
target.emit('8b 14 24 89 55 0c 66 8b 54 24 04 66 89 55 10 83 c4 08')
target.emit('61 9d b8 c0 0b 00 00 c2 08 00')
target.label('original');target.emit('61 9d ff a2 ec 01 00 00')
target_bytes=target.finish()
assert len(target_bytes)<0xf0
# Wrap BOTH producer calls, after normal construction/initialization finishes.
# EDI is the producing component; its +49 points to the owning building.
# Read its original rally, never the pathfinding-adjusted Move destination.
produce=Code(BASE+0x400)
for _ in range(6):produce.emit('ff 74 24 18') # copy cdecl arguments, right to left
produce.call(0x54fef0);produce.emit('83 c4 18 9c 60 89 c6 85 c0')
produce.j('0f 84','done')
produce.emit('83 ec 20 31 c0')
for o in range(0,32,4):produce.emit('89 44 24 '+format(o,'02x'))
produce.emit('8b 4f 49 8b 01 8d 54 24 1a 52 ff 90 70 03 00 00 85 c0')
produce.j('0f 84','free')
produce.emit('89 e7 8b 06 89 f1 ff 90 14 02 00 00 88 47 09')
produce.emit('8b 06 89 f1 ff 90 f0 01 00 00 89 47 0a c7 47 05 b8 0b 00 00')
produce.emit('8b 06 89 f1 57');produce.call(BASE+0x200)
produce.label('free');produce.emit('83 c4 20')
produce.label('done');produce.emit('61 9d c3')
produce_bytes=produce.finish()
# The original loader serializes the input queue including a process-local
# CRITICAL_SECTION. Read into scratch space, then copy only serializable bytes
# under the CURRENT lock. Never expose the stale saved lock to the input thread.
saved=Code(BASE+0x600)
saved.emit('83 79 24 01');saved.j('0f 85','original')
saved.emit('56 57 53 55 89 ce 81 ec 98 09 00 00 85 04 24 81 ec 98 09 00 00 85 04 24')
saved.emit('89 e7 68 30 13 00 00 57 89 f1');saved.call(0x500380)
saved.emit('89 c5 85 c0');saved.j('0f 84','done')
saved.emit('68 3c c1 8c 00 ff 15 78 21 68 00')
saved.emit('89 e6 bf 28 c1 8c 00 b9 05 00 00 00 fc f3 a5 83 c6 18 83 c7 18 b9 c1 04 00 00 f3 a5')
saved.emit('68 3c c1 8c 00 ff 15 7c 21 68 00')
saved.label('done');saved.emit('89 e8 81 c4 30 13 00 00 5d 5b 5f 5e c2 08 00')
saved.label('original');saved.emit('b8 80 03 50 00 ff e0')
saved_bytes=saved.finish()
# Recover the exact 1.1.0 malformed command layout on an existing worker:
# target==0, auxiliary field holds a live resource ID, and native contextual
# resolution matches its current gather command. All other commands untouched.
recover=Code(BASE+0x700)
recover.emit('9c 60 89 ce 8b 86 ae 00 00 00 3d a1 0f 00 00');recover.j('0f 84','check')
recover.emit('3d a2 0f 00 00');recover.j('0f 85','original')
recover.label('check');recover.emit('83 be b7 00 00 00 00');recover.j('0f 85','original')
recover.emit('8b 9e bb 00 00 00 85 db');recover.j('0f 8e','original')
recover.emit('3b 1d dc 3e 6c 00');recover.j('0f 8d','original')
recover.emit('a1 98 8c 83 00 8b 04 98 85 c0');recover.j('0f 84','original')
recover.emit('6a 00 50 89 f1');recover.call(0x567840)
recover.emit('3b 86 ae 00 00 00');recover.j('0f 85','original')
recover.emit('89 9e b7 00 00 00 c7 86 bb 00 00 00 00 00 00 00')
recover.label('original');recover.emit('61 9d 56 8b f1 8b 06 e9');recover.n(0x5664d5-(recover.base+len(recover.b)+4))
recover_bytes=recover.finish()
assert len(saved_bytes)<=0x100 and len(recover_bytes)<=0x100
# Select the search seed on the rally-facing perimeter BEFORE unit creation.
# Keep the native occupancy/terrain/unit-size search and original fallback.
spawn=Code(BASE+0x800)
spawn.emit('55 89 e5 53 56 57 83 ec 28 8b 77 49')
spawn.emit('8d 45 ec 50 89 f1 8b 06 ff 90 70 03 00 00 85 c0');spawn.j('0f 84','fallback')
spawn.emit('8d 45 dc 50 8d 45 e4 50 89 f1 8b 06 ff 90 fc 01 00 00 85 c0');spawn.j('0f 84','fallback')
# A rally inside the building rectangle keeps the normal exit.
for off,lo,hi in [('ec','e4','dc'),('ee','e6','de')]:
 spawn.emit('0f bf 45 '+off+' 0f bf 4d '+lo+' 39 c8');spawn.j('0f 8c','outside')
 spawn.emit('0f bf 4d '+hi+' 39 c8');spawn.j('0f 8f','outside')
spawn.j('e9','fallback')
spawn.label('outside')
for axis,off,lo,hi,out in [('x','ec','e4','dc','d4'),('y','ee','e6','de','d6')]:
 spawn.emit('0f bf 45 '+off+' 0f bf 4d '+lo+' 83 e9 20 39 c8');spawn.j('0f 8d',axis+'lower')
 spawn.emit('89 c8');spawn.label(axis+'lower')
 spawn.emit('0f bf 4d '+hi+' 83 c1 20 39 c8');spawn.j('0f 8e',axis+'upper')
 spawn.emit('89 c8');spawn.label(axis+'upper')
 spawn.emit('85 c0');spawn.j('0f 89',axis+'positive');spawn.emit('31 c0');spawn.label(axis+'positive')
 spawn.emit('3d ff 7f 00 00');spawn.j('0f 8f','fallback')
 spawn.emit('66 89 45 '+out)
spawn.emit('0f bf 45 d6 50 0f bf 45 d4 50');spawn.call(0x44eba0)
spawn.emit('83 c4 08 03 45 00 66 89 45 d8') # preserve original air altitude
spawn.emit('ff 75 18 ff 75 14 ff 75 10 ff 75 d8 ff 75 d4');spawn.call(0x44f720)
spawn.emit('83 c4 14 85 c0');spawn.j('0f 84','fallback')
spawn.emit('83 c4 28 5f 5e 5b 5d c3')
spawn.label('fallback');spawn.emit('83 c4 28 5f 5e 5b 5d b8 20 f7 44 00 ff e0')
spawn_bytes=spawn.finish();assert len(spawn_bytes)<=0x400
# The opening Enter WM_CHAR can remain in the editor result until the next
# DirectInput event. Only the actual Return scan-code event may submit chat.
prompt=Code(BASE+0xc00)
prompt.call(0x446b00)
prompt.emit('83 f8 0d');prompt.j('0f 85','done')
prompt.emit('83 3d 60 18 85 00 3c');prompt.j('0f 85','done')
prompt.emit('8b 4c 24 38 85 c9');prompt.j('0f 84','neutral')
prompt.emit('83 39 75');prompt.j('0f 85','neutral')
prompt.emit('66 83 79 0b 1c');prompt.j('0f 84','done')
prompt.emit('66 81 79 0b 9c 00');prompt.j('0f 84','done')
prompt.label('neutral');prompt.emit('b8 01 00 00 00')
prompt.label('done');prompt.emit('c3')
prompt_bytes=prompt.finish();assert len(prompt_bytes)<=0x100
from build_hotkey_patch import build as build_hotkeys
hotkeys=build_hotkeys(Code,BASE)
payload=bytearray(0x1400);payload[:len(right_bytes)]=right_bytes;payload[0x100:0x100+len(target_bytes)]=target_bytes;payload[0x200:0x200+len(gather_bytes)]=gather_bytes;payload[0x400:0x400+len(produce_bytes)]=produce_bytes
payload[0x800:0x800+len(spawn_bytes)]=spawn_bytes
payload[0x600:0x600+len(saved_bytes)]=saved_bytes;payload[0x700:0x700+len(recover_bytes)]=recover_bytes
payload[0xc00:0xc00+len(prompt_bytes)]=prompt_bytes
for offset,code in hotkeys.items():payload[offset:offset+len(code)]=code
out=Path('dist/runtime/patches');out.mkdir(parents=True,exist_ok=True)
(out/'rally.bin').write_bytes(payload)
metadata={'source_sha256':hashlib.sha256(b).hexdigest(),'section_rva':rva,'base':BASE,'right_size':len(right_bytes),'target_size':len(target_bytes),'gather_size':len(gather_bytes),'hooks':[]}
for offset,target,expected in [(0x130bb0,BASE,bytes.fromhex('ff 90 e8 01 00 00')),(0x12f3f0,BASE,bytes.fromhex('ff 90 e8 01 00 00')),(0x12f1f5,BASE+0x100,bytes.fromhex('ff 92 ec 01 00 00'))]+[(o,BASE+0x400,b'\xe8'+struct.pack('<i',0x54fef0-(0x400000+o+5))) for o in [0xf5843,0xf5887]]:
 assert b[offset:offset+len(expected)]==expected
 metadata['hooks'].append({'offset':offset,'target':target,'expected':expected.hex()})
for offset,target,expected,kind in [(0x12c000,BASE+0xd00,'e89b770400','call'),(0x117ac0,BASE+0xf00,'a0f8d78c00','jump'),(0x659ba,BASE+0xc00,'e84111feff','call'),(0xf5793,BASE+0x800,'e8889ff5ff','call'),(0x118731,BASE+0x600,'e84a7cfeff','call'),(0x1664d0,BASE+0x700,'568bf18b06','jump')]:
 assert b[offset:offset+5].hex()==expected
 metadata['hooks'].append({'offset':offset,'target':target,'expected':expected,'kind':kind})
(out/'rally.bin').write_bytes(payload)
metadata['edits']=[{'offset':o,'expected':b[o:o+4].hex(),'value':struct.pack('<I',BASE+0xe00).hex()} for o in (0x12b5ae,0x12b632)]
(out/'metadata.json').write_text(json.dumps(metadata,indent=2))
print(json.dumps(metadata,indent=2))
