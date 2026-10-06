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
from replay_state_probe import generate as generate_state
from replay_stable_ids import generate as generate_ids, EXPECTED as ALLOCATOR_EXPECTED

def build(source, output, profile, stable_ids=False):
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
    rng_header = storage+capacity*record_size
    rng_storage = rng_header+0x1000
    rng_capacity = 65536
    state_header=rng_storage+rng_capacity*32
    state_storage=state_header+0x1000
    state_capacity=512
    state_entity_capacity=512
    state_record_size=48+state_entity_capacity*32
    payload = bytearray(state_storage-base+state_capacity*state_record_size)
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
    # x86 TEB ClientId.UniqueThread, TlsSlots, and expansion array.
    # FS:2C is static loader TLS, NOT the Win32 TlsGetValue slot array.
    emit('64a124000000 894710 31c0 894714 894718 89471c')
    emit('8b15');number(0x72de40)
    emit('81fa40040000');branch('0f83','tls_done')
    emit('83fa40');branch('0f83','extended_tls')
    emit('648b0495100e0000');branch('e9','tls_pointer')
    labels['extended_tls']=len(code)
    emit('83ea40 64a1940f0000')
    labels['tls_array']=len(code)
    emit('85c0');branch('0f84','tls_done')
    emit('8b0490')
    labels['tls_pointer']=len(code)
    emit('85c0');branch('0f84','tls_done')
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
    # Observe the actual CRT rand call, using the TLS pointer returned by its
    # original helper. Do not invoke an additional RNG call or seed operation.
    rng_address=base+0x800
    rng_code=bytearray()
    def re(s): rng_code.extend(bytes.fromhex(s))
    def rn(n): rng_code.extend(struct.pack('<I',n&0xffffffff))
    rlabels,rfix={},[]
    def rb(op,label):
        re(op);rfix.append((len(rng_code),label));rn(0)
    re('e8');rn(0x674743-(rng_address+5))
    re('9c60 b801000000 8705');rn(rng_header+12)
    re('85c0');rb('0f85','busy')
    re('a1');rn(rng_header)
    re('3d');rn(rng_capacity);rb('0f83','full')
    re('89c3 69c0');rn(32);re('05');rn(rng_storage);re('89c7 891f')
    re('a1');rn(0x8a1238);re('894704 64a124000000 894708')
    # pushad saved EAX is the helper result; original return address at ESP+36.
    re('8b44241c 89470c 8b4014 894710 8b442424 894714')
    re('c7471800000000 c7471c00000000 43 891d');rn(rng_header)
    rb('e9','unlock')
    rlabels['full']=len(rng_code);re('f0ff05');rn(rng_header+4)
    rlabels['unlock']=len(rng_code);re('31c0 a3');rn(rng_header+12);rb('e9','resume')
    rlabels['busy']=len(rng_code);re('f0ff05');rn(rng_header+8)
    rlabels['resume']=len(rng_code);re('619d e9');rn(0x671425-(rng_address+len(rng_code)+4))
    for pos,label in rfix:struct.pack_into('<i',rng_code,pos,rlabels[label]-pos-4)
    payload[0x800:0x800+len(rng_code)]=rng_code
    # Reaching 44C91F means decode and batch validation passed. Native dispatch
    # returns 1 even on rejection, so its return value is not acceptance evidence.
    accepted_address=base+0x600
    accepted=bytearray(bytes.fromhex('9c60 f0ff05')+struct.pack('<I',header+20))
    accepted.extend(bytes.fromhex('8b442434 f00105')+struct.pack('<I',header+24))
    accepted.extend(b'\xa1'+struct.pack('<I',0x8a1238)+b'\xa3'+struct.pack('<I',header+28))
    accepted.extend(bytes.fromhex('619d 8b4c2410 33c0 e9'))
    accepted.extend(struct.pack('<i',0x44c925-(accepted_address+len(accepted)+4)))
    payload[0x600:0x600+len(accepted)]=accepted
    accepted_offset=pe.get_offset_from_rva(0x4c91f)
    if data[accepted_offset:accepted_offset+6]!=bytes.fromhex('8b4c241033c0'):
        raise ValueError('Native validated-dispatch bytes do not match.')
    data[accepted_offset:accepted_offset+6]=b'\xe9'+struct.pack('<i',accepted_address-0x44c924)+b'\x90'
    rng_offset=pe.get_offset_from_rva(0x271420)
    if data[rng_offset:rng_offset+5]!=bytes.fromhex('e81e330000'):
        raise ValueError('Native RNG bytes do not match.')
    data[rng_offset:rng_offset+5]=b'\xe9'+struct.pack('<i',rng_address-0x671425)
    state_code,state_targets=generate_state(base+0x1100,state_header,state_storage,state_capacity,
                                           state_record_size,state_entity_capacity)
    if len(state_code)>0x700:raise ValueError('State probe code overlaps allocator stub.')
    payload[0x1100:0x1100+len(state_code)]=state_code
    struct.pack_into('<II',payload,state_header-base+24,0xffffffff,0xffffffff)
    allocator_code=None
    if stable_ids:
        allocator_code=generate_ids(base+0x1800,state_header,header+32)
        if len(allocator_code)>0x800:raise ValueError('Allocator code overlaps command storage.')
        payload[0x1800:0x1800+len(allocator_code)]=allocator_code
        pos=pe.get_offset_from_rva(0x45f4b)
        if data[pos:pos+len(ALLOCATOR_EXPECTED)]!=ALLOCATOR_EXPECTED:
            raise ValueError('Native object allocator bytes do not match.')
        data[pos:pos+len(ALLOCATOR_EXPECTED)]=b'\xe9'+struct.pack('<i',base+0x1800-0x445f50)+b'\x90'*(len(ALLOCATOR_EXPECTED)-5)
    for site,target in [(0x40c6e5,state_targets['before']),(0x40c72f,state_targets['after'])]:
        native_target=0x44c200 if site==0x40c6e5 else 0x502340
        pos=pe.get_offset_from_rva(site-0x400000)
        original=b'\xe8'+struct.pack('<i',native_target-site-5)
        if data[pos:pos+5]!=original:raise ValueError('Main-loop call bytes do not match.')
        data[pos:pos+5]=b'\xe8'+struct.pack('<i',target-site-5)
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
    info={'schema':3,'status':'diagnostic-only-not-replay','game_sha256':SUPPORTED,
          'simulation_patch_version':'replay-stable-ids-experiment-1' if stable_ids else 'original-1.20g-baseline-0',
          'output_sha256':hashlib.sha256(data).hexdigest(),'header':header,
          'storage':storage,'capacity':capacity,'record_size':record_size,
          'command_offset':32,'command_size':111,'hook':0x44c870,'code_address':base,
          'accepted_counter':header+20,'accepted_code_address':accepted_address,
          'accepted_code_hex':accepted.hex(),'accepted_resume':0x44c925,
          'code_hex':code.hex(),'resume':0x44c876,
          'rng_header':rng_header,'rng_storage':rng_storage,'rng_capacity':rng_capacity,
          'rng_code_address':rng_address,'rng_code_hex':rng_code.hex(),'rng_resume':0x671425,
          'state_header':state_header,'state_storage':state_storage,'state_capacity':state_capacity,
          'state_code_address':base+0x1100,'state_code_hex':state_code.hex(),'state_targets':state_targets,
          'state_record_size':state_record_size,'state_entity_capacity':state_entity_capacity,
          'state_checksum_scope':'entities-and-player-resources-not-complete-simulation','state_digest_version':3}
    if allocator_code:
        info.update(allocator_code_address=base+0x1800,allocator_code_hex=allocator_code.hex(),
                    allocator_error_header=header+32,allocator_resume=0x445f62)
    profile.parent.mkdir(parents=True,exist_ok=True)
    profile.write_text(json.dumps(info,indent=2),encoding='utf-8')
    return info

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('source',type=Path);p.add_argument('output',type=Path)
    p.add_argument('profile',type=Path);p.add_argument('--stable-ids',action='store_true');a=p.parse_args()
    info=build(a.source,a.output,a.profile,a.stable_ids)
    print('Diagnostic probe built; original preserved; capacity:',info['capacity'])
