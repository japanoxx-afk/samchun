"""Build a diagnostic command-dispatch trace, NOT a playable replay.

Only the independently analyzed, hash-verified original EXE is accepted. The
finite buffer never wraps; overflow and concurrent calls are explicitly counted.
It performs no I/O or allocation inside the native dispatcher. Records include
attempted commands before native validation, not claims of successful execution.
"""
import argparse
import hashlib
import json
import shutil
import struct
from pathlib import Path
import pefile
from analyze_replay import SUPPORTED

def build(source, output, profile):
    if source.resolve() == output.resolve():
        raise ValueError('Original executable cannot be overwritten.')
    data = bytearray(source.read_bytes())
    if hashlib.sha256(data).hexdigest() != SUPPORTED:
        raise ValueError('Unsupported original SHA-256.')
    pe = pefile.PE(data=bytes(data))
    expected = bytes.fromhex('81ec18090000')
    offset = pe.get_offset_from_rva(0x4c870)
    if data[offset:offset+6] != expected:
        raise ValueError('Native dispatcher bytes do not match.')
    def align(n,a): return (n+a-1)//a*a
    rva = align(max(s.VirtualAddress+max(s.Misc_VirtualSize,s.SizeOfRawData)
                    for s in pe.sections), pe.OPTIONAL_HEADER.SectionAlignment)
    base = pe.OPTIONAL_HEADER.ImageBase+rva
    header = base+0x1000
    storage = header+0x1000
    capacity = 4096
    record_size=160
    payload = bytearray(0x2000+capacity*record_size)
    code = bytearray()
    def emit(s): code.extend(bytes.fromhex(s))
    def number(n): code.extend(struct.pack('<I',n&0xffffffff))
    labels,fixups = {},[]
    def branch(op,label):
        emit(op);fixups.append((len(code),label));number(0)
    # Save all GPRs/flags. Original argument is at saved ESP+40.
    emit('9c60 b801000000 87 05');number(header+12)
    emit('85c0');branch('0f85','busy')
    emit('a1');number(header)
    emit('3d');number(capacity);branch('0f83','full')
    emit('89c3 69c0');number(record_size);emit('05');number(storage);emit('89c7')
    # Sequence, native synchronized frame, slot ID; byte length is 111.
    emit('891f a1');number(0x8a1238);emit('894704 8b01 894708')
    emit('c7470c6f000000')
    # Read existing CRT TLS only; calling its allocator would change game state.
    # x86 TEB ClientId.UniqueThread, TLS array, and expansion array.
    emit('64a124000000 894710 31c0 894714 894718 89471c')
    emit('8b15');number(0x72de40)
    emit('81fa40040000');branch('0f83','tls_done')
    emit('83fa40');branch('0f83','extended_tls')
    emit('64a12c000000');branch('e9','tls_array')
    labels['extended_tls']=len(code)
    emit('83ea40 64a1940f0000')
    labels['tls_array']=len(code)
    emit('85c0');branch('0f84','tls_done')
    emit('8b0490 85c0');branch('0f84','tls_done')
    emit('8b4014 894714 c7471801000000')
    labels['tls_done']=len(code)
    emit('83c720 8b742428 b96f000000 fc f3a4')
    # Publish count only after copying. x86 aligned store ordering; lock is released last.
    emit('43 891d');number(header);branch('e9','unlock')
    labels['full']=len(code);emit('f0ff05');number(header+4)
    labels['unlock']=len(code);emit('31c0 a3');number(header+12);branch('e9','resume')
    labels['busy']=len(code);emit('f0ff05');number(header+8)
    labels['resume']=len(code);emit('619d');code.extend(expected)
    emit('e9');number(0x44c876-(base+len(code)+4))
    for pos,label in fixups:struct.pack_into('<i',code,pos,labels[label]-pos-4)
    payload[:len(code)]=code
    struct.pack_into('<I',payload,0x1010,0x31505253) # SRP1 diagnostic marker
    raw = align(len(data),pe.OPTIONAL_HEADER.FileAlignment)
    raw_size = align(len(payload),pe.OPTIONAL_HEADER.FileAlignment)
    section_table=pe.sections[-1].get_file_offset()+40
    if section_table+40>pe.OPTIONAL_HEADER.SizeOfHeaders:
        raise ValueError('No section header space.')
    data.extend(bytes(raw+raw_size-len(data)));data[raw:raw+len(payload)]=payload
    name=b'.rprobe\0'
    data[section_table:section_table+40]=struct.pack('<8sIIIIIIHHI',name,len(payload),rva,raw_size,raw,0,0,0,0,0xe0000020)
    struct.pack_into('<H',data,pe.FILE_HEADER.get_field_absolute_offset('NumberOfSections'),len(pe.sections)+1)
    struct.pack_into('<I',data,pe.OPTIONAL_HEADER.get_field_absolute_offset('SizeOfImage'),align(rva+len(payload),pe.OPTIONAL_HEADER.SectionAlignment))
    struct.pack_into('<I',data,pe.OPTIONAL_HEADER.get_field_absolute_offset('CheckSum'),0)
    data[offset:offset+6]=b'\xe9'+struct.pack('<i',base-0x44c875)+b'\x90'
    backup=source.parent/'launcher-backup'/'replay-original-1.20g.exe'
    backup.parent.mkdir(exist_ok=True)
    if backup.exists():
        if hashlib.sha256(backup.read_bytes()).hexdigest()!=SUPPORTED:
            raise ValueError('Existing replay backup hash mismatch.')
    else:shutil.copyfile(source,backup)
    output.parent.mkdir(parents=True,exist_ok=True);output.write_bytes(data)
    info={'schema':2,'status':'diagnostic-only-not-replay','game_sha256':SUPPORTED,
          'output_sha256':hashlib.sha256(data).hexdigest(),'header':header,
          'storage':storage,'capacity':capacity,'record_size':record_size,
          'command_offset':32,'command_size':111,'hook':0x44c870,'code_address':base,
          'code_hex':code.hex(),'resume':0x44c876}
    profile.parent.mkdir(parents=True,exist_ok=True)
    profile.write_text(json.dumps(info,indent=2),encoding='utf-8')
    return info

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('source',type=Path);p.add_argument('output',type=Path)
    p.add_argument('profile',type=Path);a=p.parse_args()
    info=build(a.source,a.output,a.profile)
    print('Diagnostic probe built; original preserved; capacity:',info['capacity'])
