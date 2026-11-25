"""Record native end transition before cleanup; modes are not yet classified."""
import argparse,hashlib,json,struct
from pathlib import Path
import pefile

def add(executable,profile):
    info=json.loads(profile.read_text());data=bytearray(executable.read_bytes())
    if hashlib.sha256(data).hexdigest()!=info['output_sha256']:raise ValueError('Diagnostic executable mismatch')
    pe=pefile.PE(data=bytes(data));address=info['code_address']+0xc00;header=address+0xe0
    offset=lambda va:pe.get_offset_from_rva(va-0x400000)
    site=0x444921;expected=b'\xe8'+struct.pack('<i',0x45fbb0-site-5)
    if data[offset(site):offset(site)+5]!=expected:raise ValueError('Native end boundary mismatch')
    code=bytearray(b'\x9c\x60')
    if 'sample' in info['state_targets']:
        code+=b'\xc7\x05'+struct.pack('<II',info['state_header']+44,1)+b'\xbb\x01\x00\x00\x00\xe8'
        code+=struct.pack('<i',info['state_targets']['sample']-address-len(code)-4)
    for source,destination in [(0x8a1238,header+4),(0x733d64,header+8),(0x8578cc,header+12)]:code+=b'\xa1'+struct.pack('<I',source)+b'\xa3'+struct.pack('<I',destination)
    code+=b'\xc7\x05'+struct.pack('<II',info['header']+48,1)
    code+=b'\xff\x05'+struct.pack('<I',header)+b'\x61\x9d\xe8'
    code+=struct.pack('<i',0x45fbb0-address-len(code)-4)+b'\xc3'
    if len(code)>0xe0:raise ValueError('End hook overlaps its status header')
    pos=offset(address)
    if any(data[pos:pos+0x100]):raise ValueError('End code cave occupied')
    data[pos:pos+len(code)]=code;pos=offset(site);data[pos:pos+5]=b'\xe8'+struct.pack('<i',address-site-5)
    # Every leave path reaches cleanup, including menu/desktop exit without a
    # victory screen. Seal BEFORE cleanup, without reading a freed object.
    cleanup=info['code_address']+0x300;cleanup_site=0x444310
    expected=b'\xe8'+struct.pack('<i',0x583760-cleanup_site-5)
    if data[offset(cleanup_site):offset(cleanup_site)+5]!=expected:raise ValueError('Cleanup boundary mismatch')
    tail=bytearray(b'\x9c\x60');skips=[]
    for pointer,op in [(info['header']+48,b'\x0f\x85'),(info['state_header'],b'\x0f\x84')]:
        tail+=b'\x83\x3d'+struct.pack('<I',pointer)+b'\x00'+op;skips.append(len(tail));tail+=bytes(4)
    for source,destination in [(0x8a1238,header+4),(0x733d64,header+8),(0x8578cc,header+12)]:tail+=b'\xa1'+struct.pack('<I',source)+b'\xa3'+struct.pack('<I',destination)
    tail+=b'\xc7\x05'+struct.pack('<II',header+16,2)+b'\xc7\x05'+struct.pack('<II',info['header']+48,1)
    tail+=b'\xff\x05'+struct.pack('<I',header)
    for at in skips:struct.pack_into('<i',tail,at,len(tail)-at-4)
    tail+=b'\x61\x9d\xe8'+struct.pack('<i',0x583760-cleanup-len(tail)-3-4)+b'\xc3'
    if len(tail)>0x100:raise ValueError('Cleanup hook too large')
    pos=offset(cleanup)
    if any(data[pos:pos+len(tail)]):raise ValueError('Cleanup hook cave occupied')
    data[pos:pos+len(tail)]=tail;pos=offset(cleanup_site);data[pos:pos+5]=b'\xe8'+struct.pack('<i',cleanup-cleanup_site-5)
    executable.write_bytes(data)
    info.update(output_sha256=hashlib.sha256(data).hexdigest(),end_transition_header=header,end_transition_code_address=address,end_transition_code_hex=code.hex(),cleanup_code_address=cleanup,cleanup_code_hex=tail.hex())
    profile.write_text(json.dumps(info,indent=2))

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('executable',type=Path);p.add_argument('profile',type=Path);a=p.parse_args();add(a.executable,a.profile)
