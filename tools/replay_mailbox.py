"""Write only the verified recorder module's next-path/READY mailbox."""
import ctypes as c,hashlib,json
from pathlib import Path

def arm(pid,profile,name=None,acknowledge=False):
    if not acknowledge and (len(name)!=8 or not name.isascii() or not name.isalnum() or not name.startswith('RPLA')):raise ValueError('Invalid checkpoint name')
    p=json.loads(Path(profile).read_text())
    k=c.WinDLL('kernel32',use_last_error=True)
    k.OpenProcess.argtypes=[c.c_uint32,c.c_int,c.c_uint32];k.OpenProcess.restype=c.c_void_p
    k.QueryFullProcessImageNameW.argtypes=[c.c_void_p,c.c_uint32,c.c_wchar_p,c.POINTER(c.c_uint32)]
    k.ReadProcessMemory.argtypes=[c.c_void_p,c.c_void_p,c.c_void_p,c.c_size_t,c.c_void_p]
    k.WriteProcessMemory.argtypes=[c.c_void_p,c.c_void_p,c.c_void_p,c.c_size_t,c.POINTER(c.c_size_t)]
    k.CloseHandle.argtypes=[c.c_void_p]
    handle=k.OpenProcess(0x1038,False,pid)
    if not handle:raise OSError(c.get_last_error(),'Open recorder mailbox')
    try:
        image=c.create_unicode_buffer(32768);length=c.c_uint32(len(image))
        if not k.QueryFullProcessImageNameW(handle,0,image,c.byref(length)):raise OSError(c.get_last_error())
        if hashlib.sha256(Path(image.value).read_bytes()).hexdigest()!=p['output_sha256']:raise ValueError('Wrong recorder process')
        for key in ['session_ready_address','session_generation_address','session_path_address','session_ack_address']:
            if not p['code_address']<=p[key]<p['code_address']+0x1000:raise ValueError('Mailbox is outside verified module')
        ended=c.c_uint32()
        complete=c.c_uint32()
        if not k.ReadProcessMemory(handle,p['end_transition_header'],c.byref(ended),4,None):raise OSError(c.get_last_error())
        if not k.ReadProcessMemory(handle,p['session_cleanup_complete_address'],c.byref(complete),4,None):raise OSError(c.get_last_error())
        stage=c.c_uint32()
        if not k.ReadProcessMemory(handle,p['initial_save_header'],c.byref(stage),4,None):raise OSError(c.get_last_error())
        if not ended.value and not complete.value and stage.value!=4:raise ValueError('Checkpoint has not been consumed')
        def write(address,data):
            buffer=c.create_string_buffer(data);done=c.c_size_t()
            if not k.WriteProcessMemory(handle,address,buffer,len(data),c.byref(done)) or done.value!=len(data):raise OSError(c.get_last_error(),'Recorder mailbox write')
        if acknowledge:
            if not ended.value:raise ValueError('Cannot release an unsealed native match')
            write(p['session_ack_address'],b'\1\0\0\0')
            return
        write(p['session_path_address'],('.\\SAVE\\'+name+'.SAV\0').encode('ascii').ljust(24,b'\0'))
        write(p['session_ready_address'],b'\1\0\0\0') # publish last
    finally:k.CloseHandle(handle)
