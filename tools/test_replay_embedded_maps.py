"""Portable replay/map integrity and recovery tests; not actual game verification."""
import json,sys,tempfile,zipfile,hashlib
from pathlib import Path
from replay_archive import unpack,include_maps,prune
from replay_map_dependency import MapLease,recover_maps,map_path
file=Path(sys.argv[1])
with tempfile.TemporaryDirectory() as temp:
 root=Path(temp);meta,trace,save=unpack(file,root/'extracted')
 assert meta['format']==3 and meta['maps']
 row=meta['maps'][0];game=root/'other-pc';game.mkdir();target=map_path(game,row['path'])
 lease=MapLease(game);lease.install(meta['maps'],root/'extracted')
 assert target.is_file() and hashlib.sha256(target.read_bytes()).hexdigest()==row['sha256']
 lease.close();assert not target.exists()
 target.write_bytes(b'original-map')
 lease=MapLease(game);lease.install(meta['maps'],root/'extracted')
 assert target.read_bytes()!=b'original-map'
 recover_maps(game);assert target.read_bytes()==b'original-map'
 lease.close() # completed recovery is idempotent
 interrupted=game/'launcher-backup'/'replay-maps'/('0'*32);interrupted.mkdir()
 (interrupted/'restore.pending').write_text('{partial')
 recover_maps(game);assert target.read_bytes()==b'original-map'
 lease=MapLease(game);lease.install(meta['maps'],root/'extracted');target.write_bytes(b'user-edit')
 try:lease.close()
 except ValueError:pass
 else:raise AssertionError('User map edit overwritten on restore')
 assert target.read_bytes()==b'user-edit' and (lease.directory/'0.original').read_bytes()==b'original-map'
 target.write_bytes((root/'extracted'/row['member']).read_bytes());lease.close();assert target.read_bytes()==b'original-map'
 copy=include_maps(file,root/'no-local-map',root/'copied.screplay')
 other,_,_=unpack(copy,root/'copy-work');assert other['maps']==meta['maps']
 def broken(name,mutate):
  path=root/name
  with zipfile.ZipFile(file) as source,zipfile.ZipFile(path,'w') as out:
   for member in source.namelist():
    data=source.read(member)
    if member=='metadata.json':
     m=json.loads(data);mutate(m);data=json.dumps(m).encode()
    if name=='bad-map.screplay' and member==row['member']:data=data[:-1]+bytes([data[-1]^1])
    out.writestr(member,data)
  try:unpack(path,root/(name+'-work'))
  except (ValueError,KeyError):pass
  else:raise AssertionError('Corrupt/unsafe embedded map accepted')
 broken('bad-map.screplay',lambda m:None)
 broken('bad-path.screplay',lambda m:m['maps'][0].update(path='MAP/../outside.map'))
 broken('bad-member.screplay',lambda m:m['maps'][0].update(member='../outside.map'))
 broken('bad-size.screplay',lambda m:m['maps'][0].update(size=0))
 keep=root/'retention';keep.mkdir()
 for i in range(8):
  with zipfile.ZipFile(keep/('%02d_auto.screplay'%i),'w') as z:z.writestr('metadata.json',json.dumps(dict(format=3,kind='samchun-replay',auto_saved=True,diagnostic_only=False)))
 permanent=keep/'old_permanent.screplay';permanent.write_bytes(b'preserved')
 prune(keep);assert len(list(keep.glob('*.screplay')))==6 and permanent.exists()
print('PASS embedded map integrity, no-map import, original restore, crash recovery, unsafe member/path/size rejection, format-3 retention.')
