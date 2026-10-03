"""Homogeneous production-building menus and native per-building training."""
import struct

def build(Code,b,payload):
 edits={}
 # Native multi-selection accepts only six special mobile buildings through
 # virtual +0x4a4. Remove that restriction at selection call sites only;
 # ownership and native per-entity visibility/death checks remain intact.
 for a,size in ((0x52ce29,2),(0x52ce5c,2),(0x52d0c6,6),(0x52d101,6),
                (0x529b27,6),(0x529c93,6),(0x529874,2)):
  o=a-0x400000
  assert b[o:o+1]==(b'\x74' if size==2 else b'\x0f')
  edits[o]=(b[o:o+size],b'\x90'*size)

 def patch(a,code):
  o=a-0x400000;edits[o]=(b[o:o+len(code)],code)
 def block(off,c):
  code=c.finish();assert len(code)<0x200;payload[off:off+len(code)]=code
 # Select the original full building menu when every selected entity is a live,
 # owned building of the same type. Mixed or enemy selections retain native UI.
 c=Code(0xb82800);c.emit('60 31 ff 31 db be 00 40 b8 00')
 c.label('loop');c.emit('8b 2e 85 ed');c.j('0f 84','next')
 def method(off):c.emit('8b 45 00 89 e9 ff 90');c.n(off)
 method(0x128);c.emit('85 c0');c.j('0f 84','original')
 method(0x250);c.emit('83 f8 01');c.j('0f 84','original')
 method(0x214);c.emit('50');c.call(0x5319e0);c.emit('83 c4 04 85 c0');c.j('0f 84','original')
 method(0x24);c.emit('85 db');c.j('0f 85','compare');c.emit('89 c3')
 c.label('compare');c.emit('39 d8');c.j('0f 85','original');c.emit('47')
 c.label('next');c.emit('83 c6 04 81 fe 00 41 b8 00');c.j('0f 8c','loop')
 c.emit('83 ff 02');c.j('0f 8c','original');c.emit('c7 44 24 1c 01 00 00 00')
 c.label('original');c.emit('61 39 f0');c.j('0f 8e','single');c.emit('e9');c.n(0x4127fb-(c.base+len(c.b)+4))
 c.label('single');c.emit('e9');c.n(0x4130dd-(c.base+len(c.b)+4));block(0x2800,c)
 assert b[0x127f3:0x127fb]==bytes.fromhex('3bc60f8ee2080000')
 patch(0x4127f3,b'\xe9'+struct.pack('<i',0xb82800-0x4127f8)+b'\x90'*3)
 # Only the production-button call site is hooked. Cancellation, upgrades and
 # building placement keep their native one-building behavior.
 c=Code(0xb82a00);c.emit('53 55 56 57 8b 5c 24 18 81 fb e8 03 00 00');c.j('0f 8c','native');c.emit('81 fb dc 05 00 00');c.j('0f 8d','native')
 c.emit('83 3d cc fb 8d 00 01');c.j('0f 8e','native')
 c.emit('ff 74 24 14');c.call(0x446200);c.emit('83 c4 04 85 c0');c.j('0f 84','native');c.emit('89 c1 8b 00 ff 90 28 01 00 00 85 c0');c.j('0f 84','native')
 c.emit('ff 74 24 14');c.call(0x446200);c.emit('83 c4 04 89 c1 8b 00 ff 50 24 89 c5 31 ff be 00 40 b8 00')
 c.label('loop');c.emit('8b 0e 85 c9');c.j('0f 84','next');c.emit('8b 01 ff 50 24 39 e8');c.j('0f 85','next')
 c.emit('8b 0e 8b 01 ff 90 28 01 00 00 85 c0');c.j('0f 84','next')
 c.emit('8b 0e 8b 01 ff 90 50 02 00 00 83 f8 01');c.j('0f 84','next')
 c.emit('8b 0e 8b 01 ff 90 14 02 00 00 50');c.call(0x5319e0);c.emit('83 c4 04 85 c0');c.j('0f 84','next')
 c.emit('8b 0e 8b 01 ff 90 f0 01 00 00 53 50');c.call(0x45b870);c.emit('83 c4 08 09 c7')
 c.label('next');c.emit('83 c6 04 81 fe 00 41 b8 00');c.j('0f 8c','loop');c.emit('89 f8 5f 5e 5d 5b c3')
 c.label('native');c.emit('5f 5e 5d 5b e9');c.n(0x45b870-(c.base+len(c.b)+4));block(0x2a00,c)
 assert b[0xdba7:0xdbac]==b'\xe8'+struct.pack('<i',0x45b870-0x40dbac)
 patch(0x40dba7,b'\xe8'+struct.pack('<i',0xb82a00-0x40dbac))
 return edits
