"""Attach read-only exception diagnostics; never patches or injects game code."""
import ctypes as c, struct, sys, json, time
from pathlib import Path
k=c.WinDLL('kernel32',use_last_error=True)
class Event(c.Structure):
 _fields_=[('code',c.c_uint32),('pid',c.c_uint32),('tid',c.c_uint32),('pad',c.c_uint32),('data',c.c_ubyte*160)]
k.OpenProcess.restype=c.c_void_p;k.OpenThread.restype=c.c_void_p
k.ReadProcessMemory.argtypes=[c.c_void_p,c.c_void_p,c.c_void_p,c.c_size_t,c.c_void_p]
k.Wow64GetThreadContext.argtypes=[c.c_void_p,c.c_void_p];k.CloseHandle.argtypes=[c.c_void_p]
k.GetFinalPathNameByHandleW.argtypes=[c.c_void_p,c.c_wchar_p,c.c_uint32,c.c_uint32]
modules=[]
pid=int(sys.argv[1]);h=k.OpenProcess(0x410,False,pid)
def read(a,n):
 b=c.create_string_buffer(n)
 return b.raw if k.ReadProcessMemory(h,a,b,n,None) else b''
if not k.DebugActiveProcess(pid):raise OSError(c.get_last_error())
k.DebugSetProcessKillOnExit(False)
print('Debugger attached to game',pid,flush=True)
try:
 deadline=time.monotonic()+(float(sys.argv[2]) if len(sys.argv)>2 else 900)
 while time.monotonic()<deadline:
  ev=Event()
  if not k.WaitForDebugEvent(c.byref(ev),1000):continue
  status=0x10002;d=bytes(ev.data)
  if ev.code==1:
   code,flags=struct.unpack_from('<II',d);address=struct.unpack_from('<Q',d,16)[0];first=struct.unpack_from('<I',d,152)[0]
   if code!=0x80000003:
    status=0x80010001
    if code in (0xc0000005,0xc0000374,0xc0000409) or not first:
     th=k.OpenThread(0x8,False,ev.tid);ctx=(c.c_uint32*179)();ctx[0]=0x10007
     k.Wow64GetThreadContext(th,c.byref(ctx));k.CloseHandle(th)
     names={'edi':39,'esi':40,'ebx':41,'edx':42,'ecx':43,'eax':44,'ebp':45,'eip':46,'esp':49}
     report={'code':hex(code),'address':hex(address),'first_chance':first,'registers':{n:hex(ctx[i]) for n,i in names.items()},'info':[hex(x) for x in struct.unpack_from('<15Q',d,32)],'stack':read(ctx[49],512).hex(),'instructions':read(ctx[46]-32,96).hex(),'modules':modules,'critical_section':read(0x8cc13c,24).hex()}
     print(json.dumps(report,indent=2),flush=True)
     report.update(pid=pid,captured_at=time.strftime('%Y-%m-%dT%H:%M:%S'))
     Path('verification/game-exception.json').write_text(json.dumps(report,indent=2))
     Path('verification/game-exception-'+str(pid)+'.json').write_text(json.dumps(report,indent=2))
  elif ev.code==5:
   print('Game exited',hex(struct.unpack_from('<I',d)[0]),flush=True)
   k.ContinueDebugEvent(ev.pid,ev.tid,status);break
  elif ev.code in (3,6):
   fh=struct.unpack_from('<Q',d)[0]
   if fh:
    path=c.create_unicode_buffer(1024);k.GetFinalPathNameByHandleW(fh,path,1024,0)
    modules.append({'base':hex(struct.unpack_from('<Q',d,24 if ev.code==3 else 8)[0]),'path':path.value})
    k.CloseHandle(fh)
  k.ContinueDebugEvent(ev.pid,ev.tid,status)
finally:
 k.DebugActiveProcessStop(pid);k.CloseHandle(h)
