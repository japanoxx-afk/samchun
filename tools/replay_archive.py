"""Experimental normalized SINGLE archive. Data only; no embedded executable."""
import hashlib,json,struct,zipfile,time
from datetime import datetime,timezone,timedelta
from pathlib import Path
from replay_journal import read,Writer
from verify_replay_trace import verify
from replay_constants import SUPPORTED

SIMULATION='modern-1.3.22-replay-stable-ids-experiment-1'
LIMIT=128*1024*1024
MEMBERS={'metadata.json','checkpoint.sav','record.journal'}

def sha(data):return hashlib.sha256(data).hexdigest()

def trace_from_journal(path):
    records=[];rng=[];states=[];summary=None;checkpoint=None
    for entry in read(path):
        kind=entry['kind'];payload=entry['payload']
        if kind=='command':records.append(payload)
        elif kind=='rng':rng.append(payload)
        elif kind=='state':states.append(payload)
        elif kind=='checkpoint':
            if checkpoint is not None:raise ValueError('Duplicate checkpoint metadata')
            checkpoint=payload
        elif kind=='seal':summary=payload
        elif kind!='metadata':raise ValueError('Unsupported journal entry kind')
    if not isinstance(summary,dict) or summary.get('format')!='samchun-diagnostic-trace':
        raise ValueError('Missing complete recording summary')
    trace=dict(summary,records=records,rng_records=rng,states=states,
               initial_checkpoint=checkpoint,retained_in_memory=True)
    expected=trace.get('stream_counts')
    if expected!={'commands':len(records),'rng_calls':len(rng),'state_samples':len(states)}:
        raise ValueError('Journal counts do not match the sealed summary')
    if verify(trace)['issues']:raise ValueError('Recording has missing, rejected or discontinuous data')
    if trace.get('game_sha256')!=SUPPORTED or trace.get('simulation_patch_version')!=SIMULATION:
        raise ValueError('Unsupported game/simulation version')
    if not checkpoint or checkpoint.get('context_mode') not in [2,3] or not checkpoint.get('native_save_succeeded') or not checkpoint.get('rng_valid'):
        raise ValueError('Invalid SINGLE/network initial checkpoint')
    if trace.get('accepted_status',{}).get('validated_dispatches')!=len(records):
        raise ValueError('Recording contains unvalidated command attempts')
    if not states or not states[0]['valid'] or states[0]['phase']!=0 or states[0]['native_frame']!=checkpoint['native_frame']:
        raise ValueError('Initial checkpoint boundary is missing')
    if 'player_unit_order' in checkpoint:
        from replay_initial_order import validate
        validate(checkpoint['player_unit_order'])
    allowed=checkpoint.get('slot_ids',[0] if checkpoint['context_mode']==3 else [])
    rate=checkpoint.get('tick_rate',30)
    if type(rate) is not int or not 1<=rate<=240:raise ValueError('Invalid simulation tick rate')
    names=checkpoint.get('participants',[])
    if (not isinstance(names,list) or len(names)>9 or
        any(not isinstance(x,dict) or type(x.get('slot')) is not int or
            not isinstance(x.get('id'),str) or len(x['id'])>40 or
            any(ord(c)<32 for c in x['id']) for x in names) or
        len({x['slot'] for x in names})!=len(names) or
        any(x['slot'] not in allowed for x in names)):
        raise ValueError('Invalid participant identity metadata')

    if (not isinstance(allowed,list) or not allowed or len(allowed)>9 or
        any(type(slot) is not int or not 0<=slot<9 for slot in allowed) or len(set(allowed))!=len(allowed)):
        raise ValueError('Invalid participant slot list')
    if any(row['slot'] not in allowed for row in records):raise ValueError('Command refers to an absent participant slot')
    return trace

def recover_stopped(journal,destination):
    """Seal only an intact prefix. Never claim a stopped match was a victory."""
    trace=trace_from_journal(journal)
    cleanup=trace.get('end_reason')=='native-cleanup-transition'
    other_end=trace.get('end_reason')=='native-end-transition' and (trace.get('end_transition') or {}).get('mode') in [8,9,10]
    if not cleanup and not other_end and (trace.get('end_reason')!='process-unreadable-or-exited' or trace.get('process_exit_code')!=0):
        raise ValueError('Only a clean process exit can be recovered automatically')
    final=max((s for s in trace['states'] if s['phase']==1 and s['valid']),key=lambda s:s['native_frame'],default=None)
    if final is None:raise ValueError('No completed simulation tick to recover')
    tick=final['native_frame']
    streams={'command':[r for r in trace['records'] if r['native_frame']<=tick],
             'rng':[r for r in trace['rng_records'] if r['native_frame']<=tick],
             'state':[r for r in trace['states'] if r['sequence']<=final['sequence']]}
    summary={k:v for k,v in trace.items() if k not in ['records','rng_records','states']}
    summary.update(end_reason='recording-stopped-at-verified-tick',
                   stop_info={'original_reason':trace['end_reason'],'process_exit_code':trace.get('process_exit_code'),'native_end_mode':(trace.get('end_transition') or {}).get('mode'),'last_complete_tick':tick},
                   stream_counts={'commands':len(streams['command']),'rng_calls':len(streams['rng']),'state_samples':len(streams['state'])})
    summary['accepted_status']=dict(trace['accepted_status'],validated_dispatches=len(streams['command']))
    with_writer=Writer(destination,{'format':'samchun-recovered-prefix','source_sha256':sha(Path(journal).read_bytes())})
    try:
        with_writer.append('checkpoint',trace['initial_checkpoint'])
        for kind,rows in streams.items():
            for row in rows:
                deadline=time.monotonic()+30
                while True:
                    try:with_writer.append(kind,row);break
                    except BufferError:
                        if time.monotonic()>=deadline:raise
                        time.sleep(.005) # offline conversion; never blocks the game loop
        with_writer.close(summary)
    finally:with_writer.close()
    return Path(destination)

def stopped_trace(trace):
    stop=trace.get('stop_info') or {}
    return (trace.get('end_reason')=='recording-stopped-at-verified-tick' and
            (stop.get('original_reason')=='native-cleanup-transition' or stop.get('process_exit_code')==0 or
             (stop.get('original_reason')=='native-end-transition' and stop.get('native_end_mode') in [8,9,10]))
            and trace['states'][-1]['phase']==1 and stop.get('last_complete_tick')==trace['states'][-1]['native_frame'])

def create(journal,checkpoint,folder,diagnostic=False,data_hashes=None,game_directory=None):
    trace=trace_from_journal(journal)
    ending=trace.get('end_transition') or {}
    completed=trace['end_reason']=='native-end-transition' and ending.get('mode') in [6,7]
    if not diagnostic and not completed and not stopped_trace(trace):
        raise ValueError('A completed native match end was not observed; partial record retained')
    save=Path(checkpoint).read_bytes()
    if len(save)<8 or len(save)>16*1024*1024 or struct.unpack_from('<II',save)!=(0x253,0x253):
        raise ValueError('Unsupported native checkpoint')
    recorded=Path(journal).read_bytes()
    if len(recorded)>LIMIT:raise ValueError('Experimental recording size limit exceeded')
    initialization=trace['initial_checkpoint'].get('initialization','normalized-native-loader-v1')
    metadata=dict(format=2,kind='samchun-replay',auto_saved=not diagnostic,initialization=initialization,game_sha256=SUPPORTED,
                  simulation_patch_version=SIMULATION,checkpoint_sha256=sha(save),journal_sha256=sha(recorded),
                  first_tick=trace['initial_checkpoint']['native_frame'],last_tick=trace['states'][-1]['native_frame'],
                  command_count=len(trace['records']),diagnostic_only=diagnostic,
                  completion='completed' if completed else 'stopped' if stopped_trace(trace) else 'diagnostic',
                  state_scope=trace['state_checksum_scope'],observer=False,multiplayer=trace['initial_checkpoint']['context_mode']==2,
                  slot_ids=trace['initial_checkpoint'].get('slot_ids',[0]),
                  map_snapshot='embedded-native-save',participants=trace['initial_checkpoint'].get('participants',[]),tick_rate=trace['initial_checkpoint'].get('tick_rate',30),participant_metadata='native-player-name-v1',data_hashes=data_hashes or {})
    maps={}
    if game_directory is not None:
        from replay_map_dependency import package_maps
        manifest,maps=package_maps(checkpoint,game_directory)
        metadata.update(format=3,maps=manifest,map_snapshot='embedded-native-save-and-map-v1')
    folder=Path(folder);folder.mkdir(parents=True,exist_ok=True)
    name=datetime.now(timezone(timedelta(hours=9))).strftime('%Y-%m-%d_%H-%M-%S')
    stem=name+('_diagnostic' if diagnostic else '_auto'+('_stopped' if not completed else ''))
    destination=folder/(stem+'.screplay');suffix=1
    while destination.exists():
        destination=folder/(stem+'_'+str(suffix)+'.screplay');suffix+=1
    temporary=destination.with_suffix('.writing')
    with temporary.open('xb') as stream:
        with zipfile.ZipFile(stream,'w',compression=zipfile.ZIP_STORED) as archive:
            archive.writestr('metadata.json',json.dumps(metadata,ensure_ascii=False))
            archive.writestr('checkpoint.sav',save)
            archive.writestr('record.journal',recorded)
            for member,data in maps.items():archive.writestr(member,data)
    temporary.rename(destination)
    # Diagnostic files are never confused with completed auto-saved matches.
    if diagnostic:destination.with_suffix(destination.suffix+'.keep').write_text('diagnostic')
    else:prune(folder)
    return destination

def unpack(file,work):
    file=Path(file)
    if file.stat().st_size>LIMIT+48*1024*1024:raise ValueError('Replay file is too large')
    with zipfile.ZipFile(file) as archive:
        entries=archive.infolist()
        if len(entries)>19 or len({x.filename for x in entries})!=len(entries) or not MEMBERS.issubset({x.filename for x in entries}):
            raise ValueError('Invalid replay members')
        if any(x.file_size>LIMIT or x.flag_bits&1 for x in entries):raise ValueError('Invalid/encrypted replay payload')
        if sum(x.file_size for x in entries)>LIMIT+48*1024*1024:raise ValueError('Replay expands beyond size limit')
        meta_entry=next(x for x in entries if x.filename=='metadata.json')
        if meta_entry.file_size>16384:raise ValueError('Oversized replay metadata')
        metadata=json.loads(archive.read('metadata.json'))
        if (metadata.get('format') not in [2,3] or metadata.get('kind')!='samchun-replay' or metadata.get('game_sha256')!=SUPPORTED or
            metadata.get('simulation_patch_version')!=SIMULATION or
            metadata.get('initialization') not in ['normalized-native-loader-v1','native-network-save-v1']):
            raise ValueError('Unsupported game, recording format or simulation patches')
        maps={}
        manifest=metadata.get('maps',[]) if metadata['format']==3 else []
        if not isinstance(manifest,list) or len(manifest)>16:raise ValueError('Invalid embedded maps')
        from replay_map_dependency import map_path,MAP_LIMIT,MAP_TOTAL_LIMIT
        expected_members=set(MEMBERS)
        for i,row in enumerate(manifest):
            if not isinstance(row,dict) or row.get('member')!='maps/%d.map'%i or not isinstance(row.get('path'),str):raise ValueError('Invalid map manifest')
            map_path(Path.cwd(),row['path'])
            entry=archive.getinfo(row['member'])
            if type(row.get('size')) is not int or not 0<entry.file_size<=MAP_LIMIT or row['size']!=entry.file_size:raise ValueError('Invalid embedded map size')
            data=archive.read(row['member'])
            if sha(data)!=row.get('sha256'):raise ValueError('Embedded map checksum mismatch')
            maps[row['member']]=data;expected_members.add(row['member'])
        if {x.filename for x in entries}!=expected_members or sum(len(x) for x in maps.values())>MAP_TOTAL_LIMIT:raise ValueError('Invalid embedded map payloads')
        save=archive.read('checkpoint.sav');journal=archive.read('record.journal')
    if sha(save)!=metadata.get('checkpoint_sha256') or sha(journal)!=metadata.get('journal_sha256'):
        raise ValueError('Replay payload checksum mismatch')
    if len(save)<8 or len(save)>16*1024*1024 or struct.unpack_from('<II',save)!=(0x253,0x253):
        raise ValueError('Invalid native checkpoint')
    work=Path(work);work.mkdir(parents=True,exist_ok=True)
    saved=work/'checkpoint.sav';recorded=work/'record.journal'
    saved.write_bytes(save);recorded.write_bytes(journal)
    if metadata['format']==3:
        from replay_map_dependency import required_maps
        if sorted(x['path'] for x in manifest)!=required_maps(saved):raise ValueError('Embedded maps differ from checkpoint dependencies')
        (work/'maps').mkdir(exist_ok=True)
        for member,data in maps.items():(work/member).write_bytes(data)
    trace=trace_from_journal(recorded)
    if metadata.get('participants',[])!=trace['initial_checkpoint'].get('participants',[]) or metadata.get('tick_rate',30)!=trace['initial_checkpoint'].get('tick_rate',30):
        raise ValueError('Participant identities or simulation clock metadata mismatch')
    if metadata.get('multiplayer')!=(trace['initial_checkpoint']['context_mode']==2) or metadata.get('slot_ids',[0])!=trace['initial_checkpoint'].get('slot_ids',[0]):
        raise ValueError('Participant metadata does not match the recording')
    if metadata.get('initialization')!=trace['initial_checkpoint'].get('initialization','normalized-native-loader-v1'):
        raise ValueError('Initialization method differs from the checkpoint')
    if not metadata.get('diagnostic_only') and (trace.get('end_reason')!='native-end-transition' or
        (trace.get('end_transition') or {}).get('mode') not in [6,7]) and not stopped_trace(trace):raise ValueError('Completed match end is missing')
    if metadata.get('completion')=='stopped' and not stopped_trace(trace):raise ValueError('Invalid stopped-match boundary')
    if (metadata.get('first_tick')!=trace['initial_checkpoint']['native_frame'] or
        metadata.get('last_tick')!=trace['states'][-1]['native_frame'] or
        metadata.get('command_count')!=len(trace['records'])):raise ValueError('Replay metadata/tick mismatch')
    return metadata,trace,saved

def prune(folder):
    autos=[]
    for file in Path(folder).glob('*.screplay'):
        if file.with_suffix(file.suffix+'.keep').exists() or '_permanent' in file.stem:continue
        # Only our completed version-2 auto-saves can be removed.
        try:
            with zipfile.ZipFile(file) as archive:
                if archive.getinfo('metadata.json').file_size>16384:continue
                meta=json.loads(archive.read('metadata.json'))
            if meta.get('format') in [2,3] and meta.get('kind')=='samchun-replay' and meta.get('auto_saved') is True and meta.get('diagnostic_only') is False:autos.append(file)
        except (OSError,ValueError,KeyError,zipfile.BadZipFile):continue
    for file in sorted(autos,key=lambda f:f.name,reverse=True)[5:]:file.unlink()


def include_maps(file,game_directory,destination):
    """Make a portable copy of a validated older replay; preserve its journal."""
    import tempfile
    destination=Path(destination)
    with tempfile.TemporaryDirectory() as temp:
        metadata,trace,saved=unpack(file,Path(temp))
        if metadata['format']==3:
            manifest=metadata['maps'];maps={r['member']:(Path(temp)/r['member']).read_bytes() for r in manifest}
        else:
            from replay_map_dependency import package_maps
            manifest,maps=package_maps(saved,game_directory)
        metadata.update(format=3,maps=manifest,map_snapshot='embedded-native-save-and-map-v1')
        with zipfile.ZipFile(file) as original:
            saved_bytes=original.read('checkpoint.sav');journal=original.read('record.journal')
        with destination.open('xb') as stream:
            with zipfile.ZipFile(stream,'w',compression=zipfile.ZIP_STORED) as archive:
                archive.writestr('metadata.json',json.dumps(metadata,ensure_ascii=False))
                archive.writestr('checkpoint.sav',saved_bytes);archive.writestr('record.journal',journal)
                for member,data in maps.items():archive.writestr(member,data)
    return destination
