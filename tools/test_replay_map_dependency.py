"""Native framed map references must be checked before starting a game."""
import struct,tempfile
from pathlib import Path
from replay_map_dependency import required_maps,check_maps
with tempfile.TemporaryDirectory() as tmp:
 root=Path(tmp);save=root/'test.sav'
 def framed(s):
  raw=s.encode('cp949');return struct.pack('<I',len(raw))+raw
 save.write_bytes(framed('.\\MAP\\test.map'))
 assert required_maps(save)==['MAP/test.map']
 try:check_maps(save,root)
 except ValueError as e:assert 'MAP/test.map' in str(e)
 else:raise AssertionError('Missing map accepted')
 (root/'MAP').mkdir();(root/'MAP/test.map').write_bytes(b'map')
 assert check_maps(save,root)==['MAP/test.map']
 save.write_bytes(framed('.\\MAP\\..\\outside.map'))
 try:required_maps(save)
 except ValueError:pass
 else:raise AssertionError('Traversal accepted')
 save.write_bytes(b'noise .\\MAP\\fake.map')
 assert required_maps(save)==[]
print('PASS framed relative MAP, missing dependency, existing map, traversal and unframed noise.')
