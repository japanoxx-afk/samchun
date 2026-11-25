"""Archive checks against a real trace; retention uses synthetic file headers."""
import json,sys,tempfile,zipfile
from pathlib import Path
from replay_journal import Writer
from replay_archive import create,unpack,prune

trace=json.loads(Path(sys.argv[1]).read_text(encoding='utf-8'));save=Path(sys.argv[2])
with tempfile.TemporaryDirectory() as directory:
    root=Path(directory);journal=root/'record.scpartial'
    writer=Writer(journal,{'format':'diagnostic-conversion-not-live-recording'})
    writer.append('checkpoint',trace['initial_checkpoint'])
    for kind,key in [('command','records'),('rng','rng_records'),('state','states')]:
        for row in trace[key]:writer.append(kind,row)
    writer.close({k:v for k,v in trace.items() if k not in ['records','rng_records','states']})
    archive=create(journal,save,root,diagnostic=True)
    metadata,restored,checkpoint=unpack(archive,root/'loaded')
    assert restored['records']==trace['records'] and restored['states']==trace['states']
    assert restored['rng_records']==trace['rng_records'] and checkpoint.read_bytes()==save.read_bytes()
    try:create(journal,save,root/'normal')
    except ValueError:pass
    else:raise AssertionError('Diagnostic pause/stop was accepted as normal match end')
    corrupted=root/'corrupt.screplay'
    with zipfile.ZipFile(archive) as source,zipfile.ZipFile(corrupted,'w') as dest:
        for member in source.namelist():
            data=source.read(member)
            if member=='checkpoint.sav':data=data[:-1]+bytes([data[-1]^1])
            dest.writestr(member,data)
    try:unpack(corrupted,root/'bad')
    except ValueError:pass
    else:raise AssertionError('Corrupt checkpoint accepted')
    retention=root/'retention';retention.mkdir()
    meta={'format':2,'kind':'samchun-replay','auto_saved':True,'diagnostic_only':False}
    for i in range(8):
        file=retention/('2026-10-07_12-00-%02d.screplay'%i)
        with zipfile.ZipFile(file,'w') as out:out.writestr('metadata.json',json.dumps(meta))
    preserved=retention/'2026-10-07_12-00-00.screplay';preserved.with_suffix('.screplay.keep').write_text('permanent')
    unrelated=retention/'user-file.screplay';unrelated.write_bytes(b'not ours')
    prune(retention)
    assert preserved.exists() and unrelated.exists()
    assert len(list(retention.glob('*.screplay')))==7 # five auto + permanent + unrelated
    assert not (retention/'2026-10-07_12-00-01.screplay').exists()
    assert not (retention/'2026-10-07_12-00-02.screplay').exists()
print('PASS actual-trace roundtrip, corrupt file and unfinished match rejection, latest-five/permanent retention')
