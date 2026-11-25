"""Restore recorded frame and CRT seed once, before the first command drain.

This is an experiment. A SAV is not assumed to include every transient state.
"""
import argparse, hashlib, json, struct
from pathlib import Path
import pefile


def add(executable, profile, checkpoint):
    if not checkpoint.get('native_save_succeeded') or not checkpoint.get('rng_valid'):
        raise ValueError('Missing successful initial save or observed CRT seed')
    if checkpoint.get('context_mode') not in [2,3]:raise ValueError('Unsupported checkpoint context')
    info=json.loads(profile.read_text());data=bytearray(executable.read_bytes())
    if hashlib.sha256(data).hexdigest()!=info['output_sha256']:
        raise ValueError('Runtime hash mismatch')
    pe=pefile.PE(data=bytes(data));address=info['code_address']+0xa00
    offset=lambda va:pe.get_offset_from_rva(va-0x400000)
    site=0x40c6e5;previous=info['state_targets']['before'];flag=address+0x180
    expected=b'\xe8'+struct.pack('<i',previous-site-5)
    if data[offset(site):offset(site)+5]!=expected:
        raise ValueError('First drain boundary mismatch')
    code=bytearray(b'\x9c\x60\x83\x3d'+struct.pack('<I',flag)+b'\x00\x0f\x85')
    skip=len(code);code+=bytes(4)
    if 'player_unit_order' in checkpoint:
        from replay_initial_order import restore_order
        target=restore_order(data,pe,info,checkpoint['player_unit_order'])
        code+=b'\xe8'+struct.pack('<i',target-address-len(code)-5)+bytes.fromhex('83f801740d')
        code+=b'\xc7\x05'+struct.pack('<II',flag,2)+bytes.fromhex('619dc3')
    code+=b'\x68'+struct.pack('<I',checkpoint['rng_state'])+b'\xe8'
    code+=struct.pack('<i',0x671413-address-len(code)-4)+b'\x83\xc4\x04'
    for pointer,value in [(0x8a1238,checkpoint['native_frame']),
                          (0x837f24,0),
                          (0x6a455c,0xffffffff),
                          (info['header'],0),(info['accepted_counter'],0),
                          (info['accepted_counter']+4,0),(info['rng_header'],0),
                          (info['state_header'],0),(info['state_header']+24,0xffffffff),
                          (info['state_header']+28,0xffffffff),(flag,1)]:
        code+=b'\xc7\x05'+struct.pack('<II',pointer,value)
    struct.pack_into('<i',code,skip,len(code)-skip-4)
    code+=b'\x61\x9d\xe8'+struct.pack('<i',previous-address-len(code)-5-4)+b'\xc3'
    # Relative CALL starts after POPAD/POPFD (two bytes), then its opcode.
    call_at=len(code)-6
    struct.pack_into('<i',code,call_at+1,previous-(address+call_at+5))
    if len(code)>0x180:raise ValueError('Restore stub overlaps status header')
    pos=offset(address)
    if any(data[pos:pos+0x200]):raise ValueError('Restore cave occupied')
    data[pos:pos+len(code)]=code
    pos=offset(site);data[pos:pos+5]=b'\xe8'+struct.pack('<i',address-site-5)
    executable.write_bytes(data)
    info.update(output_sha256=hashlib.sha256(data).hexdigest(),restore_code_address=address,
                restore_code_hex=code.hex(),restore_header=flag,restored_checkpoint=checkpoint)
    profile.write_text(json.dumps(info,indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ['executable','profile','checkpoint_metadata']:p.add_argument(name,type=Path)
    a=p.parse_args();add(a.executable,a.profile,json.loads(a.checkpoint_metadata.read_text()))
