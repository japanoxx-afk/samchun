"""Read-only diagnostics of selected game entities. Never writes process memory."""
import ctypes as c, struct, sys, json
k=c.WinDLL('kernel32',use_last_error=True)
k.OpenProcess.restype=c.c_void_p
k.ReadProcessMemory.argtypes=[c.c_void_p,c.c_void_p,c.c_void_p,c.c_size_t,c.c_void_p]
k.CloseHandle.argtypes=[c.c_void_p]
h=k.OpenProcess(0x410,False,int(sys.argv[1]))
def read(a,n):
 b=c.create_string_buffer(n)
 if not k.ReadProcessMemory(h,a,b,n,None): raise OSError(c.get_last_error(),hex(a))
 return b.raw
def u(a):return struct.unpack('<I',read(a,4))[0]
def obj(a):
 t=u(a)
 return dict(address=hex(a),vtable=hex(t),type=hex(struct.unpack('<H',read(a+4,2))[0]),position=struct.unpack('<hhh',read(a+6,6)),rally=struct.unpack('<hhh',read(a+0x2bc,6)),command=hex(u(a+0xae)),target=hex(u(a+0xb7)),methods={hex(o):hex(u(t+o)) for o in [0x24,0xb8,0x128,0x1e8,0x1ec,0x1f0,0x36c,0x370]})
try:
 print(json.dumps(dict(selected=[obj(a) for a in struct.unpack('<32I',read(0x8e1ad0,128)) if a],mouse=struct.unpack('<hh',read(0x8e1aa8,4)),pending=read(0x8dfbd0,32).hex()),indent=2))
 for a in sys.argv[2:]:
  if a=='--workers':
   ptrs=struct.unpack('<'+str(u(0x6c3edc))+'I',read(u(0x838c98),u(0x6c3edc)*4))
   for idx,ptr in enumerate(ptrs):
    if ptr and u(u(ptr)+0x1ec)==0x567840:
     o=obj(ptr);print(json.dumps(dict(id=idx,address=o['address'],type=o['type'],position=o['position'],command=o['command'],target=o['target'],queue=read(ptr+0x13a,33).hex())))
  else:print(json.dumps(obj(int(a,0)),indent=2))
finally:k.CloseHandle(h)
