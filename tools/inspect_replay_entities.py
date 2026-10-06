"""Read-only object class reconnaissance; no calls into the live game."""
import ctypes as c,struct,collections,sys
k=c.WinDLL('kernel32',use_last_error=True);k.OpenProcess.restype=c.c_void_p
k.ReadProcessMemory.argtypes=[c.c_void_p,c.c_void_p,c.c_void_p,c.c_size_t,c.c_void_p]
k.CloseHandle.argtypes=[c.c_void_p]
h=k.OpenProcess(0x410,False,int(sys.argv[1]))
def read(a,n):
 b=c.create_string_buffer(n)
 if not k.ReadProcessMemory(h,a,b,n,None):raise OSError(c.get_last_error(),hex(a))
 return b.raw
def num(a):return struct.unpack('<I',read(a,4))[0]
try:
 capacity=num(0x6c3edc)
 if not 0<capacity<=65536:raise ValueError('Bad capacity')
 pointers=struct.unpack('<'+str(capacity)+'I',read(num(0x838c98),capacity*4))
 hist=collections.Counter()
 for pointer in pointers:
  if not pointer:continue
  raw=read(pointer,6);vtable,kind=struct.unpack('<IH',raw)
  getter=num(vtable+0x24)
  hist[(kind,getter,read(getter,12).hex())]+=1
 for (kind,getter,code),count in hist.most_common(60):
  print(hex(kind),count,hex(getter),code)
finally:k.CloseHandle(h)
