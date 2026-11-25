"""One-time native initial save experiment. Does not provide a released replay."""
import argparse,hashlib,json,struct
from pathlib import Path
import pefile

def add(executable,profile,game_directory,name,normalize=False,multiplayer=False):
    if not name.startswith('RPLA') or len(name)>8 or not name.isalnum():raise ValueError('Diagnostic save name must be RPLA plus ASCII letters/digits')
    destination=game_directory/'SAVE'/(name+'.SAV')
    if destination.exists():raise ValueError('Never overwrite an existing checkpoint')
    destination.parent.mkdir(exist_ok=True)
    info=json.loads(profile.read_text());data=bytearray(executable.read_bytes())
    if hashlib.sha256(data).hexdigest()!=info['output_sha256']:raise ValueError('Diagnostic executable hash mismatch')
    pe=pefile.PE(data=bytes(data));base=info['code_address'];address=base+(0xd00 if normalize else 0xa00)
    offset=lambda va:pe.get_offset_from_rva(va-0x400000)
    hook=0x40c6e5;previous=info['state_targets']['before']
    expected=b'\xe8'+struct.pack('<i',previous-hook-5)
    if data[offset(hook):offset(hook)+5]!=expected:raise ValueError('Initial frame hook mismatch')
    flag=base+0xb80;path=base+0xbc0
    code=bytearray();fix=[];labels={}
    def e(s):code.extend(bytes.fromhex(s))
    def n(v):code.extend(struct.pack('<I',v&0xffffffff))
    def call(v):e('e8');n(v-address-len(code)-4)
    def j(op,label):e(op);fix.append((len(code),label));n(0)
    e('9c60 833d');n(flag);e('00');j('0f85','next_stage' if normalize else 'done')
    e('c705');n(flag);n(1)
    if normalize:
        call(0x43a7d0);e('833803')
        if multiplayer:
            j('0f84','supported');e('833802');j('0f85','unsupported');labels['supported']=len(code)
        else:j('0f85','unsupported')
    if multiplayer:
        imports={item.address:item.name for library in pe.DIRECTORY_ENTRY_IMPORT for item in library.imports}
        if imports.get(0x682178)!=b'EnterCriticalSection' or imports.get(0x68217c)!=b'LeaveCriticalSection':raise ValueError('Native queue lock imports mismatch')
        e('68');n(0x839de4);e('ff15');n(0x682178)
    e('68');n(path);call(0x4ff390);e('83c404')
    if multiplayer:
        e('50 68');n(0x839de4);e('ff15');n(0x68217c);e('58')
    e('a3');n(flag+4)
    if normalize:e('83f801');j('0f85','unsupported')
    e('a1');n(0x8a1238);e('a3');n(flag+8)
    call(0x43a7d0);e('8b00 a3');n(flag+20)
    # Win32 dynamic TLS, observed without allocating CRT storage or drawing RNG.
    e('8b15');n(0x72de40);e('83fa40');j('0f83','tls_expanded')
    e('648b0495100e0000');j('e9','tls_pointer')
    labels['tls_expanded']=len(code);e('83ea40 64a1940f0000 85c0');j('0f84','tls_done');e('8b0490')
    labels['tls_pointer']=len(code);e('85c0');j('0f84','tls_done');e('8b4014 a3');n(flag+12)
    e('c705');n(flag+16);n(1)
    labels['tls_done']=len(code)
    if normalize:e('833d');n(flag+16);e('01');j('0f85','unsupported')
    if normalize and multiplayer:
        # Network matches retain their live transport and synchronized clock.
        # Save only; never request LOAD, reseed or modify the live frame.
        e('833d');n(flag+20);e('02');j('0f84','arm')
    if not normalize:
        # Constructor RNG and loading activity belong to initialization, not
        # the recorded post-checkpoint command/tick stream.
        for pointer,value in [(info['header'],0),(info['header']+20,0),(info['header']+24,0),
                              (info['rng_header'],0),(info['state_header'],0),
                              (info['state_header']+24,0xffffffff),(info['state_header']+28,0xffffffff)]:
            e('c705');n(pointer);n(value)
    e('c705');n(flag);n(2)
    if normalize:
        # Request the same native full reload used by the game's LOAD path.
        # The first initialization is discarded; recording starts after reload.
        raw=('.\\SAVE\\'+name+'.SAV\0').encode('ascii')
        e('be');n(path);e('bf');n(0x8b7750);e('b9');n(len(raw));e('fc f3a4')
        e('c705');n(0x733d64);n(1)
        e('619d c3')
        labels['next_stage']=len(code);e('833d');n(flag);e('02');j('0f84','wait')
        e('833d');n(flag);e('03');j('0f85','done')
        # Reload constructors may draw RNG; restore the checkpoint boundary
        # after those constructors, before any commands or scheduler update.
        e('ff35');n(flag+12);call(0x671413);e('83c404')
        e('a1');n(flag+8);e('a3');n(0x8a1238)
        e('c705');n(0x837f24);n(0)
        # Main-loop last-updated frame survives a same-process LOAD. Mark the
        # restored first frame pending, so it is simulated exactly once.
        e('c705');n(0x6a455c);n(0xffffffff)
        labels['arm']=len(code)
        for pointer,value in [(info['header'],0),(info['header']+20,0),(info['header']+24,0),
                              (info['rng_header'],0),(info['state_header'],0),
                              (info['state_header']+24,0xffffffff),(info['state_header']+28,0xffffffff),
                              (info['header']+32,0),(info['header']+44,0),
                              (info['header']+4,0),(info['header']+8,0),
                              (info['rng_header']+4,0),(info['rng_header']+8,0),
                              (info['state_header']+4,0),(info['state_header']+8,0),(flag,4)]:
            e('c705');n(pointer);n(value)
        j('e9','done');labels['wait']=len(code);e('619d c3')
        labels['unsupported']=len(code);e('c705');n(flag);n(0xffffffff)
        e('c705');n(info['header']+48);n(1)
    labels['done']=len(code);e('619d');call(previous);e('c3')
    for at,label in fix:struct.pack_into('<i',code,at,labels[label]-at-4)
    if len(code)>(0x280 if normalize else 0x180):raise ValueError('Initial save code overlaps reserved memory')
    pos=offset(address)
    if any(data[pos:pos+(0x280 if normalize else 0x200)]):raise ValueError('Code cave occupied')
    data[pos:pos+len(code)]=code
    raw=('.\\SAVE\\'+name+'.SAV\0').encode('ascii');pos=offset(path);data[pos:pos+len(raw)]=raw
    pos=offset(hook);data[pos:pos+5]=b'\xe8'+struct.pack('<i',address-hook-5)
    if normalize:
        # A request to LOAD is handled at the next main-loop iteration. The
        # current iteration MUST NOT update/sample the discarded old world.
        # The earlier experiment omitted this and compared that stale sample.
        after_site=0x40c72f;after=info['state_targets']['after'];guard=base+0xf80
        pos=offset(after_site)
        if data[pos:pos+5]!=b'\xe8'+struct.pack('<i',after-after_site-5):raise ValueError('After-update hook mismatch')
        skip=bytearray(b'\x83\x3d'+struct.pack('<I',flag)+b'\x04\x72\x05\xe9')
        skip+=struct.pack('<i',after-guard-len(skip)-4)+b'\x31\xc0\xc3'
        guard_pos=offset(guard)
        if any(data[guard_pos:guard_pos+len(skip)]):raise ValueError('Normalization guard cave occupied')
        data[guard_pos:guard_pos+len(skip)]=skip
        data[pos:pos+5]=b'\xe8'+struct.pack('<i',guard-after_site-5)
        info.update(normalize_after_guard=guard,normalize_after_code_hex=skip.hex())
        # More than one drain can run before the outer loop processes LOAD.
        # Only the native full-loader return may mark the new world ready.
        loader_site=0x4ff875;loader=base+0xfa0;pos=offset(loader_site)
        if data[pos:pos+5]!=b'\xe8'+struct.pack('<i',0x4ff6b0-loader_site-5):raise ValueError('Full loader boundary mismatch')
        completed=bytearray(b'\xff\x74\x24\x04\xe8')
        completed+=struct.pack('<i',0x4ff6b0-loader-len(completed)-4)+b'\x83\xc4\x04\x9c\x83\x3d'
        completed+=struct.pack('<I',flag)+b'\x02\x75\x0a\xc7\x05'+struct.pack('<II',flag,3)+b'\x9d\xc3'
        loader_pos=offset(loader)
        if any(data[loader_pos:loader_pos+len(completed)]):raise ValueError('Load completion cave occupied')
        data[loader_pos:loader_pos+len(completed)]=completed
        data[pos:pos+5]=b'\xe8'+struct.pack('<i',loader-loader_site-5)
        info.update(normalize_load_complete=loader,normalize_load_code_hex=completed.hex())
    executable.write_bytes(data)
    info.update(output_sha256=hashlib.sha256(data).hexdigest(),initial_save_header=flag,initial_save_name=name+'.SAV',initial_save_code_address=address,initial_save_code_hex=code.hex(),initial_save_normalize=normalize,initial_save_multiplayer=multiplayer)
    profile.write_text(json.dumps(info,indent=2))

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ['executable','profile','game_directory']:p.add_argument(name,type=Path)
    p.add_argument('name');p.add_argument('--normalize',action='store_true');a=p.parse_args();add(a.executable,a.profile,a.game_directory,a.name,a.normalize)
