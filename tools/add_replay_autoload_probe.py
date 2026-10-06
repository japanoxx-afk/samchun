"""Experimental native checkpoint load at initialized main-loop boundary."""
import argparse,hashlib,json,struct
from pathlib import Path
import pefile

def add(executable,profile,checkpoint):
    info=json.loads(profile.read_text(encoding='utf-8'))
    data=bytearray(executable.read_bytes())
    if hashlib.sha256(data).hexdigest()!=info['output_sha256']:raise ValueError('Probe hash mismatch')
    expected='db015576f7af34cc913b2485f17b083d0adcd d96ff8f0467cb733ea5f30d3cf4'.replace(' ','')
    if hashlib.sha256(checkpoint.read_bytes()).hexdigest()!=expected:raise ValueError('Checkpoint mismatch')
    pe=pefile.PE(data=bytes(data));base=info['code_address'];address=base+0x700
    offset=lambda va:pe.get_offset_from_rva(va-0x400000)
    stolen=bytes.fromhex('a1643d730083f804');hook=0x40c21e
    if data[offset(hook):offset(hook)+8]!=stolen:raise ValueError('Load boundary mismatch')
    code=bytearray();fix=[];labels={}
    def emit(s):code.extend(bytes.fromhex(s))
    def word(n):code.extend(struct.pack('<I',n&0xffffffff))
    def call(n):emit('e8');word(n-address-len(code)-4)
    def branch(s):emit('0f85');fix.append((len(code),s));word(0)
    flag=address+0xe0;path=address+0xe8
    emit('9c60 833d');word(flag);emit('00');branch('done')
    emit('c705');word(flag);word(1)
    emit('6a00 68');word(path);call(0x4ff4d0);emit('83c408 83f801');branch('failed')
    emit('c705');word(0x733d64);word(1)
    emit('c705');word(flag);word(2)
    emit('e9');fix.append((len(code),'done'));word(0)
    labels['failed']=len(code);emit('c705');word(flag);word(3)
    labels['done']=len(code);emit('619d');code.extend(stolen)
    emit('e9');word(hook+8-address-len(code)-4)
    for at,label in fix:struct.pack_into('<i',code,at,labels[label]-at-4)
    if len(code)>0xe0:raise ValueError('Cave overflow')
    pos=offset(address)
    if any(data[pos:pos+0x100]):raise ValueError('Cave occupied')
    data[pos:pos+len(code)]=code
    pathname=b'.\\SAVE\\RPLTEST.SAV\0'
    data[offset(path):offset(path)+len(pathname)]=pathname
    data[offset(hook):offset(hook)+8]=b'\xe9'+struct.pack('<i',address-hook-5)+b'\x90'*3
    executable.write_bytes(data)
    info.update(output_sha256=hashlib.sha256(data).hexdigest(),autoload_status_address=flag,
                autoload_code_address=address,autoload_code_hex=code.hex(),autoload_checkpoint_sha256=expected)
    profile.write_text(json.dumps(info,indent=2),encoding='utf-8')

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ['executable','profile','checkpoint']:p.add_argument(name,type=Path)
    a=p.parse_args();add(a.executable,a.profile,a.checkpoint)
