"""Execute original x86 account builders/response parsers against local server frames."""
from pathlib import Path
import struct, sys
import pefile
from unicorn import Uc, UC_ARCH_X86, UC_MODE_32, UC_HOOK_CODE
from unicorn.x86_const import *
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'server'))
from compat_server import packet
GAME=Path(r'C:\Users\seo\Downloads\DGGL\Games\3KD2120g_Win\3kd2.exe')

def account_call(register=False,response=None):
    pe=pefile.PE(str(GAME));u=Uc(UC_ARCH_X86,UC_MODE_32)
    u.mem_map(0x400000,0x800000);u.mem_write(0x400000,pe.get_memory_mapped_image())
    u.mem_write(0xb10000,b'TesterA\0');u.mem_write(0xb10100,b'Test123\0');u.mem_write(0xb10200,b'TesterA\0')
    args=[0xb10000,0xb10100,0xb10200,0] if register else [0xb10000,0xb10100,0xb10200]
    u.mem_write(0xb00000,struct.pack('<'+'I'*(1+len(args)),0xb70000,*args));u.reg_write(UC_X86_REG_ESP,0xb00000)
    captured=[]
    def ret(value=1):
        esp=u.reg_read(UC_X86_REG_ESP);addr=struct.unpack('<I',u.mem_read(esp,4))[0]
        u.reg_write(UC_X86_REG_ESP,esp+4);u.reg_write(UC_X86_REG_EAX,value);u.reg_write(UC_X86_REG_EIP,addr)
    def hook(uc,a,size,user):
        if a in [0x42c100,0x573290,0x43bbe0]:ret()
        elif a==0x42c050:
            esp=u.reg_read(UC_X86_REG_ESP);ptr,n=struct.unpack('<II',u.mem_read(esp+4,8));captured.append(bytes(u.mem_read(ptr,n)))
            if response is None:u.emu_stop()
            else:ret()
        elif a==0x42c140:
            u.mem_write(0x8aff20,response);ret()
    u.hook_add(UC_HOOK_CODE,hook)
    u.emu_start(0x4f6f80 if register else 0x4f6b60,0xb70000,count=5000)
    return captured[0],u.reg_read(UC_X86_REG_EAX),u

if __name__=='__main__':
    for register in [False,True]:
        req,_,_=account_call(register)
        assert len(req)==152 and req[4]==(0x30 if register else 0xc)
        assert req[7:23].split(b'\0')[0]==b'TesterA'
        assert req[23:34].split(b'\0')[0]==b'Test123'
        rec=bytearray(485);struct.pack_into('<I',rec,0,123)
        _,result,u=account_call(register,packet(0x94,b'\x02'+rec))
        assert result==0 and struct.unpack('<I',u.mem_read(0x837ca8,4))[0]==123
        print(('register' if register else 'login')+': native request and success parser passed')
