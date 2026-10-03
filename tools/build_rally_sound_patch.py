"""Play native manual-rally feedback only at the actual right-click dispatch."""
import struct

def build(Code,original,payload):
 c=Code(0xb82c00);c.emit('9c 60 31 c9')
 c.label('loop');c.emit('83 3c 8d 00 40 b8 00 00');c.j('0f 84','next')
 c.emit('89 ca c1 e2 05 81 ba 05 50 b8 00 c0 0b 00 00');c.j('0f 84','sound')
 c.label('next');c.emit('41 83 f9 40');c.j('0f 8c','loop');c.j('e9','done')
 # Reuse manual rally's native green click marker (53014a -> 5283f0).
 c.label('sound');c.call(0x5283f0);c.emit('68 cd 01 00 00');c.call(0x515a80);c.emit('83 c4 04')
 c.label('done');c.emit('61 9d e9');c.n(0x52c080-(c.base+len(c.b)+4))
 code=c.finish();assert len(code)<0x200;payload[0x2c00:0x2c00+len(code)]=code
 a=0x53006d;o=a-0x400000;old=b'\xe8'+struct.pack('<i',0x52c080-a-5)
 assert original[o:o+5]==old
 return {o:(old,b'\xe8'+struct.pack('<i',0xb82c00-a-5))}
