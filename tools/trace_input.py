"""Temporary CPU hardware breakpoint tracing. No game code/data bytes are changed."""
import ctypes as c,struct,sys,time,json
from pathlib import Path
k=c.WinDLL('kernel32',use_last_error=True)
class E(c.Structure):_fields_=[('code',c.c_uint32),('pid',c.c_uint32),('tid',c.c_uint32),('pad',c.c_uint32),('data',c.c_ubyte*160)]
k.OpenProcess.restype=k.OpenThread.restype=c.c_void_p
for f in ['Wow64GetThreadContext','Wow64SetThreadContext']:getattr(k,f).argtypes=[c.c_void_p,c.c_void_p]
k.ReadProcessMemory.argtypes=[c.c_void_p,c.c_void_p,c.c_void_p,c.c_size_t,c.c_void_p];k.CloseHandle.argtypes=[c.c_void_p]
k.SuspendThread.argtypes=k.ResumeThread.argtypes=[c.c_void_p]
pid=int(sys.argv[1]);addr=int(sys.argv[2],16);h=k.OpenProcess(0x410,False,pid);threads=set();reports=[]
def read(a,n):
 b=c.create_string_buffer(n);return b.raw if k.ReadProcessMemory(h,a,b,n,None) else bytes(n)
def context(tid,configure=False):
 th=k.OpenThread(0x1a,False,tid);ctx=(c.c_uint32*179)();ctx[0]=0x10017;k.Wow64GetThreadContext(th,c.byref(ctx))
 if configure:ctx[1]=addr;ctx[6]=1;k.Wow64SetThreadContext(th,c.byref(ctx))
 k.CloseHandle(th);return ctx
assert k.DebugActiveProcess(pid);k.DebugSetProcessKillOnExit(False);print('Tracing',pid,hex(addr),flush=True)
try:
 end=time.monotonic()+120
 while time.monotonic()<end and not Path('verification/trace-stop').exists():
  e=E()
  if not k.WaitForDebugEvent(c.byref(e),250):continue
  status=0x10002
  if e.code in [2,3]:threads.add(e.tid);context(e.tid,True)
  if e.code==1:
   code=struct.unpack_from('<I',e.data)[0]
   if code in (0x80000004,0x4000001e): # WOW64 reports STATUS_WX86_SINGLE_STEP
    ctx=context(e.tid);sp=ctx[49];r={'eip':hex(ctx[46]),'ecx':hex(ctx[43]),'eax':hex(ctx[44]),'esi':hex(ctx[40]),'edi':hex(ctx[39]),'ebp':hex(ctx[45]),'input_result':hex(struct.unpack('<I',read(0x6c4b80,4))[0]),'stack':[hex(x) for x in struct.unpack('<64I',read(sp,256))]};reports.append(r);print(json.dumps(r),flush=True)
    th=k.OpenThread(0x18,False,e.tid);ctx[5]=0;ctx[48]|=0x10000;k.Wow64SetThreadContext(th,c.byref(ctx));k.CloseHandle(th)
   elif code not in (0x80000003,0x4000001f):status=0x80010001
  k.ContinueDebugEvent(e.pid,e.tid,status)
  if e.code==5:break
finally:
 for tid in threads:
  th=k.OpenThread(0x1a,False,tid)
  if th:
   k.SuspendThread(th);ctx=(c.c_uint32*179)();ctx[0]=0x10010;k.Wow64GetThreadContext(th,c.byref(ctx));ctx[1]=ctx[5]=ctx[6]=0;k.Wow64SetThreadContext(th,c.byref(ctx));k.ResumeThread(th);k.CloseHandle(th)
 k.DebugActiveProcessStop(pid);k.CloseHandle(h);Path('verification/input-trace.json').write_text(json.dumps(reports,indent=2))
