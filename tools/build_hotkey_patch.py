"""Native input-queue hotkeys, executed on the game thread, not the input thread."""
def build(Code, BASE):
 blocks={}
 def gate(c,label):
  for addr in (0x838ca8,0x851854):
   c.emit('83 3d');c.n(addr);c.emit('00');c.j('0f 85',label)
  c.emit('80 3d');c.n(0x8cd7f8);c.emit('00');c.j('0f 85',label)
 # Register period after the existing bindings. The original cdecl call is retained.
 c=Code(BASE+0xd00)
 for _ in range(3):c.emit('ff 74 24 0c')
 c.call(0x5737a0);c.emit('83 c4 0c 68');c.n(BASE+0xe80)
 c.emit('6a 34 6a 00');c.call(0x5737a0);c.emit('83 c4 0c c3');blocks[0xd00]=c.finish()
 for offset,mode in [(0xe00,0),(0xe80,1)]:
  c=Code(BASE+offset);gate(c,'done')
  c.emit('8b 0d');c.n(0x71f864);c.emit('85 c9');c.j('0f 84','done')
  c.emit('6a '+format(mode,'02x')+' 68');c.n(0x100);c.call(0x518990)
  c.label('done');c.emit('c3');blocks[offset]=c.finish()
 # An unused event ID avoids changing existing worker/camera shortcut behavior.
 c=Code(BASE+0xf00);c.emit('8b 44 24 04 81 38');c.n(0x100);c.j('0f 85','native')
 c.emit('8b 40 0f 83 f8 01');c.j('0f 87','done');c.emit('50');c.call(BASE+0x1000);c.emit('83 c4 04')
 c.label('done');c.emit('b8 01 00 00 00 c3')
 c.label('native');c.emit('a0 f8 d7 8c 00 e9');c.n(0x517ac5-(c.base+len(c.b)+4));blocks[0xf00]=c.finish()
 c=Code(BASE+0x1000);gate(c,'return')
 c.emit('53 55 56 57 8b 5c 24 14 31 ed 31 ff') # mode, index, cleared flag
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
 # Native military selector's unit category (includes mobile military types).
 method(0x28);c.emit('85 c0');c.j('0f 84','next')
 c.emit('89 c1 8b 00 ff 90 d4 00 00 00 83 f8 20');c.j('0f 85','next');c.j('e9','select')
 c.label('worker');c.emit('83 fb 01');c.j('0f 85','next')
 # Native idle (6000) and hold/stop (3002) both use vtable+0x744.
 # Active gather/build/repair/move commands must not be selected.
 c.emit('8b 86 ae 00 00 00 85 c0');c.j('0f 84','idle_queue')
 c.emit('3d 70 17 00 00');c.j('0f 84','idle_queue')
 c.emit('3d ba 0b 00 00');c.j('0f 85','next')
 c.label('idle_queue')
 c.emit('80 be 3a 01 00 00 00');c.j('0f 85','next')
 c.label('select');c.emit('85 ff');c.j('0f 85','add')
 c.call(0x52c6f0);c.emit('bf 01 00 00 00 c6 05 c8 1a 8e 00 00')
 c.label('add');method(0x170)
 # Respect native buffer capacity. Expanding this requires a separate command/save patch.
 c.emit('83 3d cc fb 8d 00 20');c.j('0f 8d','finish')
 c.label('next');c.emit('45');c.j('e9','loop')
 c.label('finish');c.emit('85 ff');c.j('0f 84','restore')
 c.call(0x40d270);c.emit('6a 00 6a 01');c.call(0x40f2a0);c.emit('83 c4 08')
 c.label('restore');c.emit('5f 5e 5d 5b')
 c.label('return');c.emit('c3');blocks[0x1000]=c.finish()
 for off,data in blocks.items():assert len(data)<=(0x400 if off==0x1000 else 0x80), (hex(off),len(data))
 return blocks
