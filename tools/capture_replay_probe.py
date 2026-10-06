"""Read a finite native diagnostic buffer without modifying game memory.

This diagnostic JSON cannot be played. It must never be advertised or accepted
as a finished replay file. Wall-clock polling is not simulation timing; only the
native frame stored by the hook is attached to command attempts.
"""
import argparse,ctypes as c,hashlib,json,struct,time
from pathlib import Path

def capture(pid,profile,output,seconds):
 k=c.WinDLL('kernel32',use_last_error=True)
 k.OpenProcess.argtypes=[c.c_uint32,c.c_int,c.c_uint32];k.OpenProcess.restype=c.c_void_p
 k.CloseHandle.argtypes=[c.c_void_p]
 k.ReadProcessMemory.argtypes=[c.c_void_p,c.c_void_p,c.c_void_p,c.c_size_t,c.POINTER(c.c_size_t)]
 k.QueryFullProcessImageNameW.argtypes=[c.c_void_p,c.c_uint32,c.c_wchar_p,c.POINTER(c.c_uint32)]
 p=json.loads(profile.read_text(encoding='utf-8'))
 h=k.OpenProcess(0x1010,False,pid)
 if not h:raise OSError(c.get_last_error(),'OpenProcess')
 records=[];rng_records=[];rng_last=0;rng_lost=[0,0]
 states=[];state_last=0;state_lost=[0,0]
 playback_status=None
 accepted_status=None
 allocator_status=None
 reason='time-limit';metrics=[];lost=[0,0];last=0;error=None
 def read(address,size):
  buf=c.create_string_buffer(size);done=c.c_size_t()
  if not k.ReadProcessMemory(h,address,buf,size,c.byref(done)) or done.value!=size:
   raise OSError(c.get_last_error(),'ReadProcessMemory')
  return buf.raw
 try:
  image=c.create_unicode_buffer(32768);length=c.c_uint32(len(image))
  if not k.QueryFullProcessImageNameW(h,0,image,c.byref(length)):raise OSError(c.get_last_error())
  if hashlib.sha256(Path(image.value).read_bytes()).hexdigest()!=p['output_sha256']:
   raise ValueError('Process executable does not match diagnostic profile.')
  if struct.unpack('<I',read(p['header']+16,4))[0]!=0x31505253:raise ValueError('Diagnostic marker mismatch.')
  until=time.monotonic()+seconds
  while time.monotonic()<until:
   start=time.perf_counter()
   try:
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
    if count<last or count>p['capacity']:raise ValueError('Invalid native record count.')
    lost=[overflow,busy]
    if count>last:
     stride=p['record_size'];prefix=p.get('command_offset',16)
     raw=read(p['storage']+last*stride,(count-last)*stride)
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
      records.append(record)
     last=count
    if p.get('rng_header'):
     count,overflow,busy,lock=struct.unpack('<IIII',read(p['rng_header'],16))
     if count<rng_last or count>p['rng_capacity']:raise ValueError('Invalid RNG count.')
     rng_lost=[overflow,busy]
     if count>rng_last:
      raw=read(p['rng_storage']+rng_last*32,(count-rng_last)*32)
      for i in range(count-rng_last):
       seq,frame,thread,pointer,state,caller=struct.unpack_from('<IIIIII',raw,i*32)
       if seq!=rng_last+i:raise ValueError('Invalid RNG sequence.')
       rng_records.append(dict(sequence=seq,native_frame=frame,native_thread=thread,
                               tls_pointer=pointer,state_before=state,caller=caller))
      rng_last=count
    if p.get('state_header'):
     count,overflow,busy,lock=struct.unpack('<IIII',read(p['state_header'],16))
     if count<state_last or count>p['state_capacity']:raise ValueError('Invalid state count.')
     state_lost=[overflow,busy]
     if count>state_last:
      state_stride=p.get('state_record_size',32)
      raw=read(p['state_storage']+state_last*state_stride,(count-state_last)*state_stride)
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
        state.update(entities=rows,player_resource_checksum=resources,player_slots=players,snapshot_flags=flags)
       states.append(state)
      state_last=count
    if p.get('playback_end_flag') and struct.unpack('<I',read(p['playback_end_flag'],4))[0]:
     reason='diagnostic-end-frame-reached';break
    if playback_status and playback_status['status'] in [2,3,4,6]:
     reason='diagnostic-command-playback-error';break
   except OSError:
    reason='process-unreadable-or-exited';break
   metrics.append((time.perf_counter()-start)*1000)
   time.sleep(0.05)
 except Exception as exc:
  reason='capture-error';error=dict(type=type(exc).__name__,message=str(exc))
  raise
 finally:
  k.CloseHandle(h)
  report={'format':'samchun-diagnostic-trace','format_version':1,
          'not_a_replay':True,'game_sha256':p['game_sha256'],
          'simulation_patch_version':p.get('simulation_patch_version','original-1.20g-baseline-0'),
          'probe_sha256':p['output_sha256'],'end_reason':reason,
          'overflow_count':lost[0],'concurrent_drop_count':lost[1],
          'records':records,'reader_ms':{'samples':len(metrics),
          'mean':sum(metrics)/max(1,len(metrics)),'max':max(metrics,default=0)},
          'limitations':['Checkpoint is external; complete state/RNG restoration is not verified.','No complete state equality verified.',
                        'Reader timing is not game loop or network performance.',
                        'Process exit alone does not prove normal match end.']}
  report.update(rng_records=rng_records,rng_overflow_count=rng_lost[0],
                rng_concurrent_drop_count=rng_lost[1])
  report.update(states=states,state_overflow_count=state_lost[0],state_concurrent_drop_count=state_lost[1],
                state_checksum_scope=p.get('state_checksum_scope','none'))
  report['playback_status']=playback_status
  report['capture_error']=error
  report['accepted_status']=accepted_status
  report['allocator_status']=allocator_status
  output.parent.mkdir(parents=True,exist_ok=True)
  output.write_text(json.dumps(report,indent=2),encoding='utf-8')
 print('Diagnostic records:',len(records),'overflow/concurrent drops:',lost)

if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__)
 p.add_argument('pid',type=int);p.add_argument('profile',type=Path);p.add_argument('output',type=Path)
 p.add_argument('--seconds',type=float,default=60);a=p.parse_args()
 if not 0<a.seconds<=3600:raise ValueError('Diagnostic duration must be 0..3600 seconds.')
 capture(a.pid,a.profile,a.output,a.seconds)
