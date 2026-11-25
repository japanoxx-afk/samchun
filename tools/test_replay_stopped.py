"""Use a real clean-exit journal; synthetic variants must be rejected."""
import sys,tempfile,copy
from pathlib import Path
from unittest.mock import patch
import replay_archive as archive
source=Path(sys.argv[1]);save=Path(sys.argv[2])
trace=archive.trace_from_journal(source)
with tempfile.TemporaryDirectory() as directory:
    work=Path(directory)
    recovered=archive.recover_stopped(source,work/'stopped.journal')
    file=archive.create(recovered,save,work/'files')
    metadata,actual,_=archive.unpack(file,work/'loaded')
    assert metadata['completion']=='stopped' and metadata['auto_saved'] and not metadata['diagnostic_only']
    assert '_auto_stopped' in file.name
    assert actual['states'][-1]['phase']==1
    assert all(r['native_frame']<=metadata['last_tick'] for r in actual['records']+actual['rng_records'])
    for key,value in [('process_exit_code',0xc0000005),('process_exit_code',None),('end_reason','capture-error')]:
        invalid=copy.deepcopy(trace);invalid[key]=value
        with patch.object(archive,'trace_from_journal',return_value=invalid):
            try:archive.recover_stopped(source,work/'must-not-write')
            except ValueError:pass
            else:raise AssertionError('Crash/incomplete exit was accepted')
print('PASS real clean-exit recovery/roundtrip, last-complete-tick clipping, crash and unknown exit rejection')
