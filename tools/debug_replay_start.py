"""One-shot native milestones in an owned diagnostic process, never a user's game."""
import ctypes as c,struct,subprocess,time,json,sys
from pathlib import Path
k=c.WinDLL('kernel32',use_last_error=True)
class Event(c.Structure):
 _fields_=[('code',c.c_uint32),('pid',c.c_uint32),('tid',c.c_uint32),('pad',c.c_uint32),('data',c.c_ubyte*160)]
k.OpenProcess.restype=c.c_void_p;k.OpenThread.restype=c.c_void_p
for name in ['ReadProcessMemory','WriteProcessMemory']:
 getattr(k,name).argtypes=[c.c_void_p,c.c_void_p,c.c_void_p,c.c_size_t,c.c_void_p]
k.Wow64GetThreadContext.argtypes=[c.c_void_p,c.c_void_p]
k.Wow64SetThreadContext.argtypes=[c.c_void_p,c.c_void_p]
k.CloseHandle.argtypes=[c.c_void_p]
exe=Path(sys.argv[1]).resolve();out=Path(sys.argv[2]);assert exe.name=='3kd2-multi-debug.exe'
p=subprocess.Popen([str(exe)],cwd=exe.parent,creationflags=2)
h=k.OpenProcess(0x1f0fff,False,p.pid);original={};rows=[]
sites=[0x4ff4d0,0x40c28d,0x40c302,0x4ff870,0x4ff720,0x4ff73a,0x4ff790,0x4ff7a7,0x4ff7be,0x40c333,0x40c388,0x40c4fc,0x40c564,0x40c6e0,0x40c8d9,0x43b8b0,0x44e550]
def read(a,n):
 b=c.create_string_buffer(n);return b.raw if k.ReadProcessMemory(h,a,b,n,None) else bytes(n)
def write(a,b):
 if not k.WriteProcessMemory(h,a,b,len(b),None):raise OSError(c.get_last_error())
deadline=time.monotonic()+45
try:
 while time.monotonic()<deadline:
  ev=Event()
  if not k.WaitForDebugEvent(c.byref(ev),500):continue
  d=bytes(ev.data);status=0x10002
  if ev.code==3:
   for a in sites:original[a]=read(a,1);write(a,b'\xcc')
  elif ev.code==1:
   code=struct.unpack_from('<I',d)[0];a=struct.unpack_from('<Q',d,16)[0]
   if code in [0x80000003,0x4000001f] and a in original:
    th=k.OpenThread(0x1f03ff,False,ev.tid);ctx=(c.c_uint32*179)();ctx[0]=0x10007
    assert k.Wow64GetThreadContext(th,c.byref(ctx))
    cp=struct.unpack('<I',read(0x837dcc,4))[0]
    row={'address':hex(a),'eax':hex(ctx[44]),'ecx':hex(ctx[43]),'esp':hex(ctx[49]),'stack':read(ctx[49],32).hex(),'frame':struct.unpack('<I',read(0x8a1238,4))[0],'context':read(cp,104).hex(),'message':read(0x837e50,200).split(b'\0')[0].decode('cp949',errors='replace')}
    rows.append(row);print(json.dumps(row),flush=True);out.write_text(json.dumps(rows,indent=2),encoding='utf-8')
    write(a,original.pop(a));ctx[46]=a;assert k.Wow64SetThreadContext(th,c.byref(ctx));k.CloseHandle(th)
   elif code not in [0x80000003,0x4000001f]:
    print('EXCEPTION',hex(code),hex(a),flush=True);status=0x80010001
  elif ev.code==5:
   print('EXIT',struct.unpack_from('<I',d)[0],flush=True);k.ContinueDebugEvent(ev.pid,ev.tid,status);break
  k.ContinueDebugEvent(ev.pid,ev.tid,status)
finally:
 for a,b in original.items():
  try:write(a,b)
  except OSError:pass
 k.DebugActiveProcessStop(p.pid);k.CloseHandle(h)
 if p.poll() is None:p.terminate();p.wait(5)

