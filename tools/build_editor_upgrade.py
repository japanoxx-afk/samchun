"""Build a source-locked XOR delta for upgrading the legacy mission editor."""
import argparse,gzip,hashlib,struct
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('source');p.add_argument('target');p.add_argument('output');a=p.parse_args()
s=Path(a.source).read_bytes();t=Path(a.target).read_bytes()
assert hashlib.sha256(s).hexdigest()=='faa9bf7f9ee7be3cb79fc92515233a279dd1dea14f469c9ec5f8e5cf0e46f342'
assert hashlib.sha256(t).hexdigest()=='58d8d5399ab47bfb4d42b30c16642ed6e415cbc359025c75fd164e6131a5417d'
d=bytes(x^y for x,y in zip(s,t));assert len(d)==len(t)
Path(a.output).write_bytes(gzip.compress(b'EDUP1'+struct.pack('<I',len(t))+d,compresslevel=9,mtime=0))
print('Editor upgrade delta:',Path(a.output).stat().st_size,'bytes')
