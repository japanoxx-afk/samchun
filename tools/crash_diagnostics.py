"""Local-only postmortem reports. No game-state writes or network uploads."""
import ctypes as c
import datetime as dt
import json
import os
from pathlib import Path
import platform
import struct
import threading
import traceback
import uuid
import psutil

VERSION='1.3.57'
_lock=threading.RLock()

def write_json(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    temporary=path.with_name(path.name+'.'+uuid.uuid4().hex+'.tmp')
    temporary.write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8')
    os.replace(temporary,path)

def export_error(work,kind,details):
    work=Path(work)
    with _lock:
        marker=work/'error-export.json'
        if marker.exists():folder=Path(json.loads(marker.read_text(encoding='utf-8'))['folder'])
        else:
            stamp=dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).strftime('%Y-%m-%d_%H-%M-%S')
            folder=Path(os.environ.get('LOCALAPPDATA',Path.home()/'AppData/Local'))/'SamchunLauncher'/'ErrorLogs'/(stamp+'_'+uuid.uuid4().hex[:8])
            folder.mkdir(parents=True,exist_ok=True)
            write_json(marker,dict(folder=str(folder)))
        report=dict(time_utc=dt.datetime.now(dt.timezone.utc).isoformat(),kind=kind,details=details,session_folder=str(work))
        write_json(folder/(kind+'.json'),report)
        text='삼국지 천명 2 오류 진단\n종류: '+kind+'\n발생 시각(UTC): '+report['time_utc']+'\n\n'+json.dumps(details,ensure_ascii=False,indent=2)
        if kind!='session-diagnostics' or not (folder/'error.log').exists():
            temp=folder/'error.log.tmp';temp.write_text(text,encoding='utf-8');os.replace(temp,folder/'error.log')
        for source in [work/'game-session.json',work/'crash-native.json',work/'crash-monitor-status.json',work/'error.log']:
            if source.exists() and source.stat().st_size<=2*1024*1024:
                target=folder/('engine-error.log' if source.name=='error.log' else source.name)
                target.write_bytes(source.read_bytes())
        # Stream-only match summaries contain bounded metadata, not the save or
        # the full command journal. Do not bundle accounts, maps or whole memory.
        for source in sorted(work.glob('match-*/record-summary.json'))[-2:]:
            if source.stat().st_size<=2*1024*1024:
                value=json.loads(source.read_text(encoding='utf-8'))
                keys=['end_reason','last_observed_native_tick','process_exit_code','capture_error','allocator_status','observer_empty_images','recent_commands','stream_counts']
                summary={key:value.get(key) for key in keys}
                summary['recent_commands']=[{k:r.get(k) for k in ['sequence','native_frame','slot','command_kind']} for r in (value.get('recent_commands') or [])[-16:]]
                write_json(folder/(source.parent.name+'-summary.json'),summary)
        return folder

class Event(c.Structure):
    _fields_=[('code',c.c_uint32),('pid',c.c_uint32),('tid',c.c_uint32),('pad',c.c_uint32),('data',c.c_ubyte*160)]

class MemoryRegion(c.Structure):
    _fields_=[('base',c.c_void_p),('allocation_base',c.c_void_p),('allocation_protect',c.c_uint32),('size',c.c_size_t),('state',c.c_uint32),('protect',c.c_uint32),('type',c.c_uint32)]

class CrashMonitor:
    def __init__(self,process,profile,work,mode):
        self.process=process;self.work=Path(work);self.profile=json.loads(Path(profile).read_text(encoding='utf-8'))
        self.stop=threading.Event();self.ready=threading.Event();self.modules=[];self.last_exception=None
        session=dict(launcher_version=VERSION,mode=mode,pid=process.pid,started_utc=dt.datetime.now(dt.timezone.utc).isoformat(),windows=platform.platform(),machine=platform.machine())
        session.update({k:self.profile.get(k) for k in ['game_sha256','baseline_sha256','output_sha256','simulation_patch_version']})
        write_json(self.work/'game-session.json',session)
        self.thread=threading.Thread(target=self.run,name='Samchun crash diagnostics',daemon=True);self.thread.start()
        self.ready.wait(2)

    def finish(self):
        self.stop.set();self.thread.join(2)

    def run(self):
        k=c.WinDLL('kernel32',use_last_error=True)
        k.OpenProcess.restype=c.c_void_p;k.OpenThread.restype=c.c_void_p
        k.ReadProcessMemory.argtypes=[c.c_void_p,c.c_void_p,c.c_void_p,c.c_size_t,c.c_void_p]
        k.Wow64GetThreadContext.argtypes=[c.c_void_p,c.c_void_p];k.CloseHandle.argtypes=[c.c_void_p]
        k.GetFinalPathNameByHandleW.argtypes=[c.c_void_p,c.c_wchar_p,c.c_uint32,c.c_uint32]
        k.VirtualQueryEx.argtypes=[c.c_void_p,c.c_void_p,c.c_void_p,c.c_size_t];k.VirtualQueryEx.restype=c.c_size_t
        handle=k.OpenProcess(0x410,False,self.process.pid);attached=False
        def read(address,size):
            b=c.create_string_buffer(size)
            return b.raw if address and k.ReadProcessMemory(handle,address,b,size,None) else b''
        def uint(address):
            b=read(address,4);return struct.unpack('<I',b)[0] if len(b)==4 else None
        def snapshot():
            value=dict(last_tick=uint(0x8a1238))
            try:value['process_memory']=psutil.Process(self.process.pid).memory_info()._asdict()
            except psutil.Error:pass
            count=uint(0x6c3edc);table=uint(0x838c98)
            if count and table and 0<count<=65536:
                raw=read(table,count*4)
                if len(raw)==count*4:value['objects']=dict(capacity=count,occupied=sum(x!=0 for x in struct.unpack('<'+'I'*count,raw)))
            a=self.profile.get('allocator_error_header')
            if a:
                raw=read(a,16)
                if len(raw)==16:value['allocator_counters']=list(struct.unpack('<4I',raw))
            return value
        try:
            if not handle or not k.DebugActiveProcess(self.process.pid):raise OSError(c.get_last_error(),'Crash monitor attach')
            attached=True
            if not k.DebugSetProcessKillOnExit(False):raise OSError(c.get_last_error(),'Keep game alive if monitor stops')
            write_json(self.work/'crash-monitor-status.json',dict(attached=True,pid=self.process.pid))
            self.ready.set();initial_breaks=set()
            while not self.stop.is_set():
                event=Event()
                if not k.WaitForDebugEvent(c.byref(event),500):continue
                status=0x10002;data=bytes(event.data);exited=False
                try:
                    if event.code==1:
                        code=struct.unpack_from('<I',data)[0];address=struct.unpack_from('<Q',data,16)[0];first=struct.unpack_from('<I',data,152)[0]
                        if first and code in (0x80000003,0x4000001f) and code not in initial_breaks:initial_breaks.add(code)
                        else:
                            status=0x80010001 # Preserve native exception handling.
                            if not first or code in (0xc0000005,0xc0000374,0xc0000409):
                                th=k.OpenThread(0x8,False,event.tid);context=(c.c_uint32*179)();context[0]=0x10007
                                valid=bool(th and k.Wow64GetThreadContext(th,c.byref(context)))
                                if th:k.CloseHandle(th)
                                region=MemoryRegion();found=k.VirtualQueryEx(handle,address,c.byref(region),c.sizeof(region))
                                module=next((m for m in self.modules if found and m['base']==region.allocation_base),None)
                                report=dict(exception_code=hex(code),exception_address=hex(address),first_chance=bool(first),thread_id=event.tid,modules=self.modules,module=module,module_offset=hex(address-module['base']) if module else None)
                                if valid:
                                    report['registers']={n:hex(context[i]) for n,i in dict(edi=39,esi=40,ebx=41,edx=42,ecx=43,eax=44,ebp=45,eip=46,esp=49).items()}
                                    raw=read(context[49],128);report['stack_words']=[hex(x) for x in struct.unpack('<'+'I'*(len(raw)//4),raw)] if raw else []
                                report.update(snapshot());self.last_exception=report
                                if not first:
                                    write_json(self.work/'crash-native.json',report);export_error(self.work,'native-crash',report)
                    elif event.code in (3,6):
                        file=struct.unpack_from('<Q',data)[0];base=struct.unpack_from('<Q',data,24 if event.code==3 else 8)[0]
                        path=c.create_unicode_buffer(32768)
                        if file:k.GetFinalPathNameByHandleW(file,path,len(path),0);k.CloseHandle(file)
                        self.modules.append(dict(base=base,path=path.value or 'unknown'))
                        # Debug-event hProcess/hThread are owned by Windows:
                        # ContinueDebugEvent closes them on process/thread exit.
                        # Closing early lets their numeric values be reused by
                        # Popen/mutex handles, which Windows then closes later.
                        # Only hFile above is explicitly debugger-owned.
                    elif event.code==7:
                        base=struct.unpack_from('<Q',data)[0];self.modules=[m for m in self.modules if m['base']!=base]
                    elif event.code==5:
                        exit_code=struct.unpack_from('<I',data)[0];exited=True
                        intentional=(self.work/'game-exit-intent.json').exists() or (self.work/'user-stop.json').exists()
                        write_json(self.work/'game-exit.json',dict(exit_code=hex(exit_code),normal=exit_code==0 or intentional,intentional=intentional))
                        if exit_code and not intentional:export_error(self.work,'abnormal-exit',dict(exit_code=hex(exit_code),last_exception=self.last_exception))
                finally:k.ContinueDebugEvent(event.pid,event.tid,status)
                if exited:break
        except Exception:
            write_json(self.work/'crash-monitor-status.json',dict(attached=False,error=traceback.format_exc()))
        finally:
            self.ready.set()
            if attached:k.DebugActiveProcessStop(self.process.pid)
            if handle:k.CloseHandle(handle)
