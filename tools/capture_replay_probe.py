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
 records=[];reason='time-limit';metrics=[];lost=[0,0];last=0
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
   except OSError:
    reason='process-unreadable-or-exited';break
   metrics.append((time.perf_counter()-start)*1000)
   time.sleep(0.05)
 finally:
  k.CloseHandle(h)
  report={'format':'samchun-diagnostic-trace','format_version':1,
          'not_a_replay':True,'game_sha256':p['game_sha256'],
          'probe_sha256':p['output_sha256'],'end_reason':reason,
          'overflow_count':lost[0],'concurrent_drop_count':lost[1],
          'records':records,'reader_ms':{'samples':len(metrics),
          'mean':sum(metrics)/max(1,len(metrics)),'max':max(metrics,default=0)},
          'limitations':['No restorable initial state/RNG captured.','No state equality verified.',
                        'Reader timing is not game loop or network performance.',
                        'Process exit alone does not prove normal match end.']}
  output.parent.mkdir(parents=True,exist_ok=True)
  output.write_text(json.dumps(report,indent=2),encoding='utf-8')
 print('Diagnostic records:',len(records),'overflow/concurrent drops:',lost)

if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__)
 p.add_argument('pid',type=int);p.add_argument('profile',type=Path);p.add_argument('output',type=Path)
 p.add_argument('--seconds',type=float,default=60);a=p.parse_args()
 if not 0<a.seconds<=3600:raise ValueError('Diagnostic duration must be 0..3600 seconds.')
 capture(a.pid,a.profile,a.output,a.seconds)
