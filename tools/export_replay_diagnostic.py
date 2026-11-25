"""Package a verified diagnostic trace; never classify it as a completed match."""
import argparse,json
from pathlib import Path
from replay_journal import Writer
from replay_archive import create
from replay_engine import data_hashes

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ['trace','checkpoint','directory']:p.add_argument(name,type=Path)
    a=p.parse_args();trace=json.loads(a.trace.read_text(encoding='utf-8'))
    a.directory.mkdir(parents=True,exist_ok=True);journal=a.directory/'converted-diagnostic.scpartial'
    writer=Writer(journal,{'format':'converted-diagnostic-not-live-journal'})
    writer.append('checkpoint',trace['initial_checkpoint'])
    for kind,key in [('command','records'),('rng','rng_records'),('state','states')]:
        for row in trace[key]:writer.append(kind,row)
    writer.close({k:v for k,v in trace.items() if k not in ['records','rng_records','states']})
    print(create(journal,a.checkpoint,a.directory,diagnostic=True,data_hashes=data_hashes(a.checkpoint.parent.parent)))
