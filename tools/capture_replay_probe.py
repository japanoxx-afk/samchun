"""Read a finite native diagnostic buffer without modifying game memory.

This diagnostic JSON cannot be played. It must never be advertised or accepted
as a finished replay file. Wall-clock polling is not simulation timing; only the
native frame stored by the hook is attached to command attempts.
"""
import argparse,ctypes as c,hashlib,json,struct,time
from collections import deque
from pathlib import Path

def capture(pid,profile,output,seconds,recover_state_tail=False,journal_path=None,retain=True,on_checkpoint=None):
 k=c.WinDLL('kernel32',use_last_error=True)
 k.OpenProcess.argtypes=[c.c_uint32,c.c_int,c.c_uint32];k.OpenProcess.restype=c.c_void_p
 k.CloseHandle.argtypes=[c.c_void_p]
 k.ReadProcessMemory.argtypes=[c.c_void_p,c.c_void_p,c.c_void_p,c.c_size_t,c.POINTER(c.c_size_t)]
 k.QueryFullProcessImageNameW.argtypes=[c.c_void_p,c.c_uint32,c.c_wchar_p,c.POINTER(c.c_uint32)]
 k.GetExitCodeProcess.argtypes=[c.c_void_p,c.POINTER(c.c_uint32)]
 p=json.loads(profile.read_text(encoding='utf-8'))
 h=k.OpenProcess(0x1010,False,pid)
 if not h:raise OSError(c.get_last_error(),'OpenProcess')
 records=[];rng_records=[];rng_last=0;rng_lost=[0,0]
 states=[];state_last=0;state_lost=[0,0]
 playback_status=None;autoload_status=None;observer_blocked_commands=0;observer_empty_images={}
 accepted_status=None
 allocator_status=None
 reason='time-limit';metrics=[];lost=[0,0];last=0;error=None
 end_transition=None;end_seen=False;playback_end_seen=False
 initial_checkpoint=None;state_history_omitted=0
 journal=None;metric_count=0;metric_sum=0.;metric_max=0.
 last_native_tick=None;recent_commands=deque(maxlen=16)
 def emit(kind,row):
  if journal:journal.append(kind,row)
 def read(address,size):
  buf=c.create_string_buffer(size);done=c.c_size_t()
  if not k.ReadProcessMemory(h,address,buf,size,c.byref(done)) or done.value!=size:
   raise OSError(c.get_last_error(),'ReadProcessMemory')
  return buf.raw
 def entries(address,stride,capacity,first,count):
  if count<first or (not p.get('ring_buffers') and count>capacity) or count-first>capacity:
   raise ValueError('Native buffer lost unread entries; record is incomplete.')
  if not p.get('ring_buffers'):return read(address+first*stride,(count-first)*stride)
  result=bytearray();remaining=count-first;index=first%capacity
  while remaining:
   length=min(remaining,capacity-index);result.extend(read(address+index*stride,length*stride));remaining-=length;index=0
  return bytes(result)
 try:
  image=c.create_unicode_buffer(32768);length=c.c_uint32(len(image))
  if not k.QueryFullProcessImageNameW(h,0,image,c.byref(length)):raise OSError(c.get_last_error())
  if hashlib.sha256(Path(image.value).read_bytes()).hexdigest()!=p['output_sha256']:
   raise ValueError('Process executable does not match diagnostic profile.')
  if struct.unpack('<I',read(p['header']+16,4))[0]!=0x31505253:raise ValueError('Diagnostic marker mismatch.')
  if journal_path:
   from replay_journal import Writer
   journal=Writer(journal_path,dict(format='samchun-diagnostic-journal',not_a_replay=True,
                  game_sha256=p['game_sha256'],simulation_patch_version=p['simulation_patch_version'],
                  runtime_sha256=p['output_sha256']))
  until=time.monotonic()+seconds
  while time.monotonic()<until:
   start=time.perf_counter()
   try:
    if p.get('observer_blocked_counter'):
     observer_blocked_commands=struct.unpack('<I',read(p['observer_blocked_counter'],4))[0]
    if p.get('observer_empty_image_counter'):
     count,descriptor,tick=struct.unpack('<III',read(p['observer_empty_image_counter'],12))
     observer_empty_images=dict(count=count,last_descriptor=descriptor,last_tick=tick)
    if p.get('autoload_status_address'):
     autoload_status=struct.unpack('<I',read(p['autoload_status_address'],4))[0]
    if p.get('session_failure_address') and struct.unpack('<I',read(p['session_failure_address'],4))[0]:
     raise ValueError('Next match initialized before the reader acknowledged the previous recording')
    if p.get('session_generation_address'):
     generation=struct.unpack('<I',read(p['session_generation_address'],4))[0]
     expected=p.get('expected_generation',0)
     if generation<expected:time.sleep(.05);continue
     if generation>expected:raise ValueError('A match started before its recording session was attached')
    if p.get('restore_order_status') and struct.unpack('<I',read(p['restore_order_status'],4))[0]==2:
     raise ValueError('Initial player unit-list restoration failed')
    if p.get('restore_header') and initial_checkpoint is None:
     if not struct.unpack('<I',read(p['restore_header'],4))[0]:
      time.sleep(0.05);continue
     initial_checkpoint=p['restored_checkpoint'];emit('checkpoint',initial_checkpoint)
    if p.get('initial_save_header') and initial_checkpoint is None:
     stage,saved,frame,seed,valid,mode=struct.unpack('<IIIIII',read(p['initial_save_header'],24))
     if stage==0xffffffff:
      reason='unsupported-mode-or-initial-checkpoint-failed';break
     if stage>=(4 if p.get('initial_save_normalize') else 2):
      if p.get('initial_order_ready') and not struct.unpack('<I',read(p['initial_order_ready'],4))[0]:time.sleep(.01);continue
      if p.get('initial_order_error') and struct.unpack('<I',read(p['initial_order_error'],4))[0]:raise ValueError('Initial player unit-list snapshot failed')
      initial_checkpoint=dict(save_name=p['initial_save_name'],native_frame=frame,
                              rng_state=seed,rng_valid=bool(valid),context_mode=mode,
                              native_save_succeeded=saved==1)
      context=struct.unpack('<I',read(0x837dcc,4))[0]
      slots=struct.unpack('<I',read(context+0x30,4))[0]
      if not 1<=slots<=9:raise ValueError('Invalid native participant slot count')
      queues=struct.unpack('<9I',read(context+0x34,36))
      initial_checkpoint['slot_ids']=[i for i in range(slots) if queues[i]]
      # Native 519EB8 copies the network roster ID into player+165A;
      # 51A561 serializes the same bounded 41-byte name field.
      participants=[]
      for slot in initial_checkpoint['slot_ids']:
       player=struct.unpack('<I',read(context+12+slot*4,4))[0]
       raw=read(player+0x165a,41).split(b'\0',1)[0] if player else b''
       name=raw.decode('cp949','replace')
       if any(ord(x)<32 for x in name):name=''
       participants.append(dict(slot=slot,id=name))
      initial_checkpoint['participants']=participants
      initial_checkpoint['tick_rate']=struct.unpack('<I',read(0x72a6f0,4))[0]
      if not 1<=initial_checkpoint['tick_rate']<=240:raise ValueError('Invalid native simulation tick rate')
      initial_checkpoint['initialization']='native-network-save-v1' if mode==2 else 'normalized-native-loader-v1'
      if p.get('initial_order_address'):
       address=p['initial_order_address'];counts=struct.unpack('<9I',read(address,36))
       if any(n>16384 for n in counts):raise ValueError('Invalid initial unit-list count')
       order=[list(struct.unpack('<'+'H'*n,read(address+36+i*32768,n*2))) if n else [] for i,n in enumerate(counts)]
       from replay_initial_order import validate
       validate(order);initial_checkpoint['player_unit_order']=order
      emit('checkpoint',initial_checkpoint)
      if on_checkpoint:on_checkpoint(initial_checkpoint)
     else:
      # Initial loading uses RNG too. Its counters are reset by the native
      # checkpoint hook; never treat that reset as lost match commands.
      time.sleep(0.05)
      continue
    if p.get('allocator_error_header'):
     errors,reserved,last_frame,policy=struct.unpack('<IIII',read(p['allocator_error_header'],16))
     allocator_status=dict(errors=errors,last_error_frame=last_frame,policy=policy)
    if p.get('accepted_counter'):
     accepted,batch_components,frame=struct.unpack('<III',read(p['accepted_counter'],12))
     accepted_status=dict(validated_dispatches=accepted,decoded_components=batch_components,last_frame=frame)
    if p.get('playback_header'):
     cursor,status=struct.unpack('<II',read(p['playback_header'],8))
     playback_status=dict(cursor=cursor,status=status,
                         meanings={0:'not-started',1:'injecting',2:'wrong-initial-frame',
                                   3:'late-command',4:'invalid-slot',5:'commands-exhausted',
                                   6:'native-command-validation-rejected'}.get(status,'unknown'))
    count,overflow,busy,lock=struct.unpack('<IIII',read(p['header'],16))
    if count<last or (not p.get('ring_buffers') and count>p['capacity']):raise ValueError('Invalid native record count.')
    lost=[overflow,busy]
    if count>last:
     stride=p['record_size'];prefix=p.get('command_offset',16)
     raw=entries(p['storage'],stride,p['capacity'],last,count)
     for i in range(count-last):
      entry=raw[i*stride:(i+1)*stride];seq,frame,slot,size=struct.unpack_from('<IIII',entry)
      if seq!=last+i or size!=111:raise ValueError('Uncommitted/corrupt diagnostic entry.')
      cmd=entry[prefix:prefix+111]
      record={'sequence':seq,'native_frame':frame,'slot':slot,
                      'scheduled_frame':struct.unpack_from('<I',cmd,2)[0],
                      'command_kind':struct.unpack_from('<I',cmd,7)[0],
                      'raw':cmd.hex(),'status':'dispatch-attempt-before-validation'}
      if p['schema']>=2:
       thread,rng,valid=struct.unpack_from('<III',entry,16)
       record.update(native_thread=thread,rng_state=rng if valid else None)
      emit('command',record)
      recent_commands.append(record);last_native_tick=frame
      if retain:records.append(record)
     last=count
    if p.get('rng_header'):
     count,overflow,busy,lock=struct.unpack('<IIII',read(p['rng_header'],16))
     if count<rng_last or (not p.get('ring_buffers') and count>p['rng_capacity']):raise ValueError('Invalid RNG count.')
     rng_lost=[overflow,busy]
     if count>rng_last:
      raw=entries(p['rng_storage'],32,p['rng_capacity'],rng_last,count)
      for i in range(count-rng_last):
       seq,frame,thread,pointer,state,caller=struct.unpack_from('<IIIIII',raw,i*32)
       if seq!=rng_last+i:raise ValueError('Invalid RNG sequence.')
       rng_record=dict(sequence=seq,native_frame=frame,native_thread=thread,
                       tls_pointer=pointer,state_before=state,caller=caller)
       emit('rng',rng_record)
       if retain:rng_records.append(rng_record)
      rng_last=count
    if p.get('state_header'):
     count,overflow,busy,lock=struct.unpack('<IIII',read(p['state_header'],16))
     if count<state_last or (not p.get('ring_buffers') and count>p['state_capacity']):raise ValueError('Invalid state count.')
     state_lost=[overflow,busy]
     if recover_state_tail and state_last==0 and p.get('ring_buffers') and count>p['state_capacity']:
      state_last=count-p['state_capacity'];state_history_omitted=state_last
     if count>state_last:
      state_stride=p.get('state_record_size',32)
      raw=entries(p['state_storage'],state_stride,p['state_capacity'],state_last,count)
      for i in range(count-state_last):
       entry=raw[i*state_stride:(i+1)*state_stride]
       seq,frame,phase,checksum,objects,valid,capacity=struct.unpack_from('<IIIIIII',entry)
       if seq!=state_last+i:raise ValueError('Invalid state sequence.')
       state=dict(sequence=seq,native_frame=frame,phase=phase,checksum=checksum,
                          objects=objects,valid=bool(valid),table_capacity=capacity,
                          unit_resource_checksum=struct.unpack_from('<I',entry,28)[0]
                          if p.get('state_digest_version',0)>=2 else None)
       if p.get('state_digest_version',0)>=3:
        entities,resources,players,flags=struct.unpack_from('<IIII',entry,32)
        if entities>p['state_entity_capacity']:raise ValueError('Invalid entity snapshot length.')
        rows=[]
        for j in range(entities):
         offset=48+j*32
         entity_id,kind=struct.unpack_from('<II',entry,offset)
         position=struct.unpack_from('<hhh',entry,offset+8)
         hp,mana,command,target=struct.unpack_from('<HHII',entry,offset+16)
         rows.append(dict(id=entity_id,type=kind,position=list(position),owner=entry[offset+14],
                          hp=hp,mana=mana,command=command,target=target))
         if p.get('state_digest_version',0)>=4:
          rows[-1]['extended_fields_valid']=bool(struct.unpack_from('<I',entry,offset+28)[0])
        state.update(entities=rows,player_resource_checksum=resources,player_slots=players,snapshot_flags=flags)
       emit('state',state)
       last_native_tick=frame
       if retain:states.append(state)
      state_last=count
    if p.get('end_transition_header'):
     ends,frame,mode,result=struct.unpack('<IIII',read(p['end_transition_header'],16))
     if ends:
      end_transition=dict(count=ends,native_frame=frame,mode=mode,result=result)
      if end_seen:
       kind=struct.unpack('<I',read(p['end_transition_header']+16,4))[0]
       reason='native-cleanup-transition' if kind==2 else 'native-end-transition'
       break
      end_seen=True
    if p.get('playback_end_flag') and struct.unpack('<I',read(p['playback_end_flag'],4))[0]:
     if playback_end_seen:reason='diagnostic-end-frame-reached';break
     playback_end_seen=True
    if playback_status and playback_status['status'] in [2,3,4,6]:
     reason='diagnostic-command-playback-error';break
   except OSError:
    reason='process-unreadable-or-exited';break
   elapsed=(time.perf_counter()-start)*1000
   metric_count+=1;metric_sum+=elapsed;metric_max=max(metric_max,elapsed)
   time.sleep(0.05)
 except Exception as exc:
  reason='capture-error';error=dict(type=type(exc).__name__,message=str(exc))
  raise
 finally:
  exit_code=c.c_uint32();exit_known=bool(k.GetExitCodeProcess(h,c.byref(exit_code)))
  k.CloseHandle(h)
  report={'format':'samchun-diagnostic-trace','format_version':1,
          'not_a_replay':True,'game_sha256':p['game_sha256'],
          'simulation_patch_version':p.get('simulation_patch_version','original-1.20g-baseline-0'),
          'probe_sha256':p['output_sha256'],'end_reason':reason,
          'overflow_count':lost[0],'concurrent_drop_count':lost[1],
          'records':records,'reader_ms':{'samples':metric_count,
          'mean':metric_sum/max(1,metric_count),'max':metric_max},
          'limitations':['Checkpoint is external; complete state/RNG restoration is not verified.','No complete state equality verified.',
                        'Reader timing is not game loop or network performance.',
                        'Process exit alone does not prove normal match end.']}
  report.update(rng_records=rng_records,rng_overflow_count=rng_lost[0],
                rng_concurrent_drop_count=rng_lost[1])
  report.update(states=states,state_overflow_count=state_lost[0],state_concurrent_drop_count=state_lost[1],
                state_checksum_scope=p.get('state_checksum_scope','none'))
  report['playback_status']=playback_status
  report['autoload_status']=autoload_status
  report['observer_blocked_commands']=observer_blocked_commands
  report['observer_empty_images']=observer_empty_images
  report['capture_error']=error
  report['accepted_status']=accepted_status
  report['allocator_status']=allocator_status
  report['end_transition']=end_transition
  report['initial_checkpoint']=initial_checkpoint
  report['state_history_omitted']=state_history_omitted
  report['last_observed_native_tick']=last_native_tick
  report['recent_commands']=list(recent_commands)
  report['process_exit_code']=exit_code.value if exit_known and exit_code.value!=259 else None
  report['retained_in_memory']=retain
  report['stream_counts']=dict(commands=last,rng_calls=rng_last,state_samples=state_last-state_history_omitted)
  if journal:
   try:
    journal.close({key:value for key,value in report.items()
                   if key not in ['records','rng_records','states']})
   except Exception as exc:
    report['capture_error']=dict(type=type(exc).__name__,message=str(exc))
    report['end_reason']='journal-write-error'
  output.parent.mkdir(parents=True,exist_ok=True)
  output.write_text(json.dumps(report,indent=2),encoding='utf-8')
 print('Diagnostic records:',last,'overflow/concurrent drops:',lost)

if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__)
 p.add_argument('pid',type=int);p.add_argument('profile',type=Path);p.add_argument('output',type=Path)
 p.add_argument('--seconds',type=float,default=60)
 p.add_argument('--recover-state-tail',action='store_true',help='Diagnostic comparison only: explicitly report missing earlier state samples')
 p.add_argument('--journal',type=Path)
 p.add_argument('--stream-only',action='store_true',help='Bounded-memory recording to journal; omit arrays from summary JSON')
 a=p.parse_args()
 if not 0<a.seconds<=3600:raise ValueError('Diagnostic duration must be 0..3600 seconds.')
 if a.stream_only and not a.journal:p.error('--stream-only requires --journal')
 capture(a.pid,a.profile,a.output,a.seconds,a.recover_state_tail,a.journal,not a.stream_only)
