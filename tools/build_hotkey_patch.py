"""Native input-queue hotkeys, executed on the game thread, not the input thread."""
def build(Code, BASE):
 blocks={}
 def gate(c,label):
  for addr in (0x838ca8,0x851854):
   c.emit('83 3d');c.n(addr);c.emit('00');c.j('0f 85',label)
  c.emit('80 3d');c.n(0x8cd7f8);c.emit('00');c.j('0f 85',label)
 # Register comma and period after existing bindings (DirectInput scan codes).
 c=Code(BASE+0xd00)
 for _ in range(3):c.emit('ff 74 24 0c')
 c.call(0x5737a0);c.emit('83 c4 0c 68');c.n(BASE+0xe80)
 c.emit('6a 34 6a 00');c.call(0x5737a0);c.emit('83 c4 0c 68');c.n(BASE+0xd80)
 c.emit('6a 33 6a 00');c.call(0x5737a0);c.emit('83 c4 0c c3');blocks[0xd00]=c.finish()
 for offset,mode in [(0xe00,0),(0xe80,1),(0xd80,2)]:
  c=Code(BASE+offset);gate(c,'done')
  c.emit('8b 0d');c.n(0x71f864);c.emit('85 c9');c.j('0f 84','done')
  c.emit('6a '+format(mode,'02x')+' 68');c.n(0x100);c.call(0x518990)
  c.label('done');c.emit('c3');blocks[offset]=c.finish()
 # An unused event ID avoids changing existing worker/camera shortcut behavior.
 c=Code(BASE+0xf00);c.emit('8b 44 24 04 81 38');c.n(0x100);c.j('0f 85','native')
 c.emit('8b 40 0f 83 f8 02');c.j('0f 87','done');c.emit('50');c.call(BASE+0x1000);c.emit('83 c4 04')
 c.label('done');c.emit('b8 01 00 00 00 c3')
 c.label('native');c.emit('a0 f8 d7 8c 00 e9');c.n(0x517ac5-(c.base+len(c.b)+4));blocks[0xf00]=c.finish()
 c=Code(BASE+0x1000)
 # Keep the historical entry address stable; larger implementation is isolated
 # from the Internet bootstrap at +1400..1500 and 64-selection code at +2000.
 c.emit('e9');c.n(BASE+0x1800-(BASE+0x1000+5));blocks[0x1000]=c.finish()
 c=Code(BASE+0x1800);gate(c,'return')
 # Locals: first object/index, next object/index, double flag; all pointers
 # are collected fresh on this input event, never retained across world cleanup.
 c.emit('53 55 56 57 83 ec 14 8b 5c 24 28 31 ed 31 ff 31 c0')
 for offset in (0,4,8,12,16):c.emit('89 44 24 '+format(offset,'02x'))
 c.emit('85 db');c.j('0f 84','begin')
 c.emit('ff 15 8c 21 68 00 89 d9 c1 e1 04 81 c1');c.n(BASE+0x2f00)
 c.emit('89 c2 2b 11 89 01 81 fa 90 01 00 00');c.j('0f 87','arm')
 c.emit('83 79 04 01');c.j('0f 85','arm')
 c.emit('c7 44 24 10 01 00 00 00 c7 41 04 00 00 00 00');c.j('e9','begin')
 c.label('arm');c.emit('c7 41 04 01 00 00 00')
 c.label('begin')
 c.emit('a1 98 8c 83 00 85 c0');c.j('0f 84','finish')
 c.label('loop');c.emit('3b 2d dc 3e 6c 00');c.j('0f 8d','finish')
 c.emit('a1 98 8c 83 00 8b 34 a8 85 f6');c.j('0f 84','next')
 # Same ownership eligibility used by native selection.
 def method(off):
  c.emit('8b 06 89 f1 ff 90');c.n(off)
 method(0x214);c.emit('50');c.call(0x5319e0);c.emit('83 c4 04 85 c0');c.j('0f 84','next')
 method(0x128);c.emit('85 c0');c.j('0f 85','next')
 method(0x250);c.emit('83 f8 01');c.j('0f 84','next')
 method(0x69c);c.emit('85 c0');c.j('0f 85','next')
 method(0x678);c.emit('85 c0');c.j('0f 84','classify')
 method(0x5b8);c.emit('85 c0');c.j('0f 84','next')
 c.label('classify');method(0x24)
 for typ in (0x402,0x438,0x464):
  c.emit('3d');c.n(typ);c.j('0f 84','worker')
 c.emit('85 db');c.j('0f 85','next')
 # Military entity IDs occupy 1000..1499. Definition category 0x20
 # covers only one movement class and omitted air/mechanical units.
 # Workers are handled above; 0x468 is excluded by the native click selector.
 c.emit('3d');c.n(1000);c.j('0f 8c','next')
 c.emit('3d');c.n(1500);c.j('0f 8d','next')
 c.emit('3d');c.n(0x468);c.j('0f 84','next');c.j('e9','select')
 c.label('worker');c.emit('85 db');c.j('0f 84','next')
 # Native idle (6000) and hold/stop (3002) both use vtable+0x744.
 # Active gather/build/repair/move commands must not be selected.
 c.emit('8b 86 ae 00 00 00 85 c0');c.j('0f 84','idle_queue')
 c.emit('3d 70 17 00 00');c.j('0f 84','idle_queue')
 c.emit('3d ba 0b 00 00');c.j('0f 85','next')
 c.label('idle_queue')
 c.emit('80 be 3a 01 00 00 00');c.j('0f 85','next')
 c.emit('83 fb 02');c.j('0f 85','candidate')
 c.emit('56');c.call(BASE+0x2a00);c.emit('83 c4 04 85 c0');c.j('0f 84','next')
 c.label('candidate');c.emit('83 3c 24 00');c.j('0f 85','after_first')
 c.emit('89 34 24 89 6c 24 04')
 c.label('after_first');c.emit('83 7c 24 08 00');c.j('0f 85','select')
 c.emit('89 d8 c1 e0 04 81 c0');c.n(BASE+0x2f00)
 c.emit('3b 68 08');c.j('0f 8e','select')
 c.emit('89 74 24 08 89 6c 24 0c')
 c.label('select');c.emit('85 ff');c.j('0f 85','add')
 c.call(0x52c6f0);c.emit('bf 01 00 00 00 c6 05 c8 1a 8e 00 00')
 c.label('add');c.emit('83 3d cc fb 8d 00 40');c.j('0f 8d','next');method(0x170)
 # Selection and command buffers are relocated by the accompanying 64-unit patch.
 # Worker cycling considers every eligible worker even past selection capacity.
 c.emit('85 db');c.j('0f 85','next')
 c.emit('83 3d cc fb 8d 00 40');c.j('0f 8d','finish')
 c.label('next');c.emit('45');c.j('e9','loop')
 c.label('finish');c.emit('83 7c 24 10 00');c.j('0f 84','selection_refresh')
 c.emit('8b 44 24 08 8b 54 24 0c 85 c0');c.j('0f 85','center')
 c.emit('8b 04 24 8b 54 24 04 85 c0');c.j('0f 84','selection_refresh')
 c.label('center');c.emit('89 d9 c1 e1 04 89 91');c.n(BASE+0x2f08)
 c.emit('50');c.call(BASE+0x2b00);c.emit('83 c4 04')
 c.label('selection_refresh');c.emit('85 ff');c.j('0f 84','restore')
 c.call(0x40d270);c.emit('6a 00 6a 01');c.call(0x40f2a0);c.emit('83 c4 08')
 c.label('restore');c.emit('83 c4 14 5f 5e 5d 5b')
 c.label('return');c.emit('c3');blocks[0x1800]=c.finish()
 # Native world coordinate accessor +B8 uses a caller-supplied 6-byte value.
 c=Code(BASE+0x2a00);c.emit('83 ec 08 8b 4c 24 0c 8b 01 54 ff 90 b8 00 00 00 8b 15 78 8c 83 00 85 d2');c.j('0f 84','no')
 c.emit('0f bf 08 0f bf 52 24 29 d1');c.j('0f 88','no')
 c.emit('0f bf 15 90 78 8c 00 39 d1');c.j('0f 8d','no')
 c.emit('8b 15 78 8c 83 00 0f bf 48 02 0f bf 52 26 29 d1');c.j('0f 88','no')
 c.emit('0f bf 15 b0 78 8c 00 39 d1');c.j('0f 8d','no')
 c.emit('b8 01 00 00 00');c.j('e9','done');c.label('no');c.emit('31 c0');c.label('done');c.emit('83 c4 08 c3');blocks[0x2a00]=c.finish()
 # Match native control-group centering (529771..5297CA), including map clamp.
 c=Code(BASE+0x2b00);c.emit('83 ec 08 8b 4c 24 0c 8b 01 54 ff 90 b8 00 00 00 8b 15 78 8c 83 00 85 d2');c.j('0f 84','done')
 c.emit('0f b7 4a 34 c1 e1 05 66 8b 10 66 29 ca 66 89 14 24 8b 15 78 8c 83 00 0f b7 4a 36 c1 e1 05 66 8b 50 02 66 29 ca 66 89 54 24 02 ff 34 24');c.call(0x44ec40);c.emit('83 c4 04')
 c.label('done');c.emit('83 c4 08 c3');blocks[0x2b00]=c.finish()
 # Independent double-press timers/cursors; start before index zero for wrapping.
 import struct
 blocks[0x2f00]=b''.join(struct.pack('<IIII',0,0,0xffffffff,0) for _ in range(3))
 for off,data in blocks.items():assert len(data)<=(0x800 if off==0x1800 else 0x100 if off in (0x2a00,0x2b00) else 0x80), (hex(off),len(data))
 return blocks
