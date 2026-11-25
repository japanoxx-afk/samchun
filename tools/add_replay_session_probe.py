"""Re-arm at native new-match initialization, after the previous cleanup.

The external recorder publishes the next unused checkpoint name before READY.
No live unit/network state is written by the external process.
"""
import hashlib,json,struct
import pefile

def add(executable,profile):
    info=json.loads(profile.read_text());data=bytearray(executable.read_bytes())
    if hashlib.sha256(data).hexdigest()!=info['output_sha256']:raise ValueError('Session runtime mismatch')
    pe=pefile.PE(data=bytes(data));offset=lambda a:pe.get_offset_from_rva(a-0x400000)
    base=info['code_address'];address=base+0x200;ending=info['end_transition_header'];flag=info['initial_save_header']
    imports={item.address:item.name for library in pe.DIRECTORY_ENTRY_IMPORT for item in library.imports}
    if imports.get(0x682180)!=b'Sleep' or imports.get(0x6822e0)!=b'timeGetTime':raise ValueError('Native startup wait import mismatch')
    code=bytearray(b'\x9c\x60');fix=[];labels={}
    def branch(op,label):
        code.extend(bytes.fromhex(op));fix.append((len(code),label));code.extend(bytes(4))
    for pointer in [ending+20,ending+24]:
        code+=b'\x83\x3d'+struct.pack('<I',pointer)+b'\x01';branch('0f85','done')
    # This runs once between worlds, before initialization; never during a tick.
    # Do not overwrite old rings until the external reader has sealed them.
    code+=b'\xff\x15'+struct.pack('<I',0x6822e0)+b'\x89\xc7'
    labels['wait']=len(code)
    code+=b'\x83\x3d'+struct.pack('<I',flag+24)+b'\x01';branch('0f84','reset')
    code+=b'\x6a\x01\xff\x15'+struct.pack('<I',0x682180)
    code+=b'\xff\x15'+struct.pack('<I',0x6822e0)+b'\x29\xf8\x3d'+struct.pack('<I',2000);branch('0f82','wait')
    code+=b'\xc7\x05'+struct.pack('<II',flag+28,1);branch('e9','done')
    labels['reset']=len(code);code+=b'\x31\xc0'
    for pointer in [flag,flag+4,flag+8,flag+12,flag+16,flag+20,flag+24,flag+32,flag+36,
                    info['state_header'],ending,ending+16,ending+20,ending+24,info['header']+48]:
        code+=b'\xa3'+struct.pack('<I',pointer)
    code+=b'\xff\x05'+struct.pack('<I',ending+28)
    labels['done']=len(code)
    for at,label in fix:struct.pack_into('<i',code,at,labels[label]-at-4)
    code+=b'\xc7\x05'+struct.pack('<II',ending+20,0)
    code+=b'\x61\x9d\xff\x74\x24\x04\xe8'+struct.pack('<i',0x444250-address-len(code)-7-4)+b'\x83\xc4\x04\xc3'
    site=0x40c28d;expected=b'\xe8'+struct.pack('<i',0x444250-site-5)
    if data[offset(site):offset(site)+5]!=expected:raise ValueError('New-match boundary mismatch')
    if len(code)>0x100 or any(data[offset(address):offset(address)+len(code)]):raise ValueError('Session cave unavailable')
    data[offset(address):offset(address)+len(code)]=code
    data[offset(site):offset(site)+5]=b'\xe8'+struct.pack('<i',address-site-5)
    # This is the final instruction of the independently inspected, no-argument
    # cleanup routine; it executes after units, terrain and context were freed.
    complete=base+0x380;site=0x4443b8
    if data[offset(site):offset(site)+6]!=bytes.fromhex('b801000000c3'):raise ValueError('Cleanup completion mismatch')
    tail=b'\xc7\x05'+struct.pack('<II',ending+20,1)+bytes.fromhex('b801000000c3')
    if any(data[offset(complete):offset(complete)+len(tail)]):raise ValueError('Cleanup completion cave unavailable')
    data[offset(complete):offset(complete)+len(tail)]=tail
    data[offset(site):offset(site)+5]=b'\xe8'+struct.pack('<i',complete-site-5)
    executable.write_bytes(data)
    info.update(output_sha256=hashlib.sha256(data).hexdigest(),session_code_address=address,session_code_hex=code.hex(),
                session_ready_address=ending+24,session_ack_address=flag+24,session_failure_address=flag+28,session_generation_address=ending+28,session_cleanup_complete_address=ending+20,
                session_path_address=flag+0x40,session_complete_address=complete,session_complete_code_hex=tail.hex())
    profile.write_text(json.dumps(info,indent=2))
