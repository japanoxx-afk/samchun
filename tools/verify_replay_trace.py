"""Check diagnostic ordering/RNG continuity, not replay state equality."""
import argparse,json
from pathlib import Path

def verify(trace):
    if trace.get('format')!='samchun-diagnostic-trace' or not trace.get('not_a_replay'):
        raise ValueError('Expected a diagnostic trace, not a replay file.')
    issues=[]
    if trace.get('allocator_status') and trace['allocator_status']['errors']:
        issues.append({'kind':'allocator-policy-failed','details':trace['allocator_status']})
    for key in ['overflow_count','concurrent_drop_count','rng_overflow_count','rng_concurrent_drop_count',
                'state_overflow_count','state_concurrent_drop_count']:
        if trace.get(key,0):issues.append({'kind':key,'count':trace[key]})
    commands=trace['records']
    for row in trace.get('states',[]):
        if row.get('snapshot_flags',0):
            issues.append({'kind':'invalid-or-truncated-state','frame':row['native_frame'],'flags':row['snapshot_flags']})
    for i,row in enumerate(commands):
        if row['sequence']!=i:issues.append({'kind':'command-sequence','sequence':i})
        if row['scheduled_frame']!=row['native_frame']:
            issues.append({'kind':'command-frame','sequence':i,'frame':row['native_frame']})
    previous={}
    rng=trace.get('rng_records',[])
    for i,row in enumerate(rng):
        if row['sequence']!=i:issues.append({'kind':'rng-sequence','sequence':i})
        key=(row['native_thread'],row['tls_pointer'])
        prior=previous.get(key)
        if prior is not None:
            expected=(prior['state_before']*214013+2531011)&0xffffffff
            if row['state_before']!=expected:
                issues.append({'kind':'rng-discontinuity-or-reseed','sequence':i,
                               'frame':row['native_frame'],'caller':hex(row['caller']),
                               'expected':expected,'actual':row['state_before']})
        previous[key]=row
    return {'commands':len(commands),'rng_calls':len(rng),'rng_streams':len(previous),
            'issues':issues,'first_issue':issues[0] if issues else None,
            'replay_state_equality_verified':False}

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('trace',type=Path)
    a=p.parse_args();report=verify(json.loads(a.trace.read_text(encoding='utf-8')))
    print(json.dumps(report,indent=2))
    raise SystemExit(bool(report['issues']))
