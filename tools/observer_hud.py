"""1.20g presentation-only HUD gates; never alter the simulation or commands."""
import hashlib,json,struct
import pefile

ENTRIES={0x43ae40:'83ec348b442438',0x4147e0:'83ec14a1b0788c00',
         0x4147b0:'a1e4f37300',0x45f8c0:'8b0d44878400',0x520e20:'a10cdfaf00',
         0x461720:'a154188500',0x502e20:'83ec245533ed'}

def apply(data,pe,info,playback=False):
    section=pe.sections[-1];size=(section.Misc_VirtualSize+15)&~15
    base=0x400000+section.VirtualAddress+size
    payload=bytearray(b'HUD1'+struct.pack('<III',0,int(playback),0));patches=[]
    for site,expected in ENTRIES.items():
        original=bytes.fromhex(expected);at=pe.get_offset_from_rva(site-0x400000)
        if data[at:at+len(original)]!=original:raise ValueError('Observer HUD boundary mismatch: '+hex(site))
        stub=base+len(payload);code=bytearray(bytes.fromhex('9c60 833d')+struct.pack('<I',base+4)+b'\x01');fix=[];labels={}
        def branch(op,label):
            code.extend(bytes.fromhex(op));fix.append((len(code),label));code.extend(bytes(4))
        branch('0f85','normal')
        if not playback:
            code+=bytes.fromhex('a1cc7d8300 85c0');branch('0f84','normal')
            code+=bytes.fromhex('833802');branch('0f85','normal')
            code+=bytes.fromhex('8b4058 85c0');branch('0f84','normal')
            code+=bytes.fromhex('83783503');branch('0f85','normal')
        if site==0x502e20:
            # Fill the native back surface (surface 1) before the world draw, and
            # include the HUD band in the software renderer's dirty region.
            # LockSurface(1, &pitch), clear the locked surface using its pitch,
            # then unlock. af dba4 is a COPY-from-pointer operation, not fill.
            code+=bytes.fromhex('83ec04 54 6a01 ff15acdbaf00 83c408 85c0')
            branch('0f84','clear_done')
            code+=bytes.fromhex('a178dbaf00 8b7804 8b0c24 0faf0d70dbaf00 31c0 fc f3aa 6a01 ff15b0dbaf00 83c404')
            labels['clear_done']=len(code);code+=bytes.fromhex('83c404')
            code+=bytes.fromhex('a170dbaf00 48 c1e010 8b0d6cdbaf00 49 09c8 50 6a00 e8')
            code+=struct.pack('<i',0x502a20-(stub+len(code)+4))
            code+=bytes.fromhex('83c408')
        if site!=0x502e20:code+=bytes.fromhex('619d 31c0 c3')
        labels['normal']=len(code);code+=bytes.fromhex('619d')+original
        code+=b'\xe9'+struct.pack('<i',site+len(original)-(stub+len(code)+5))
        for pos,label in fix:struct.pack_into('<i',code,pos,labels[label]-pos-4)
        payload+=code;data[at:at+len(original)]=b'\xe9'+struct.pack('<i',stub-site-5)+b'\x90'*(len(original)-5)
        patches.append(dict(site=site,original=original.hex(),stub=stub,code=code.hex(),normal=stub+labels['normal']+2))
    # Replace the original shared-battle upper-left resource block for observers.
    # Gate the player-resource draw, not its parent: the latter also draws clock.
    # 51CF20 is thiscall with four callee-cleaned arguments (ret 10h).
    site=0x51cf20;original=bytes.fromhex('81ecf0000000');at=pe.get_offset_from_rva(site-0x400000)
    if data[at:at+len(original)]!=original:raise ValueError('Observer resource draw boundary mismatch')
    stub=base+len(payload);code=bytearray(bytes.fromhex('9c60'));fix=[]
    def normal_branch(op):
        code.extend(bytes.fromhex(op));fix.append(len(code));code.extend(bytes(4))
    if not playback:
        code+=bytes.fromhex('a1cc7d8300 85c0');normal_branch('0f84')
        code+=bytes.fromhex('833802');normal_branch('0f85')
        code+=bytes.fromhex('8b4058 85c0');normal_branch('0f84')
        code+=bytes.fromhex('83783503');normal_branch('0f85')
    code+=bytes.fromhex('619d 31c0 c21000');normal=len(code)
    code+=bytes.fromhex('619d')+original+b'\xe9'
    code+=struct.pack('<i',site+len(original)-(stub+len(code)+4))
    for pos in fix:struct.pack_into('<i',code,pos,normal-pos-4)
    payload+=code;data[at:at+len(original)]=b'\xe9'+struct.pack('<i',stub-site-5)+b'\x90'
    info['observer_resource_patch']=dict(site=site,stub=stub,original=original.hex(),code=code.hex(),normal=stub+normal+2)
    total=size+len(payload);align=lambda n,a:(n+a-1)//a*a
    raw=align(total,pe.OPTIONAL_HEADER.FileAlignment);end=section.PointerToRawData+raw
    data.extend(bytes(max(0,end-len(data))));start=section.PointerToRawData+size;data[start:start+len(payload)]=payload
    struct.pack_into('<I',data,section.get_file_offset()+8,total);struct.pack_into('<I',data,section.get_file_offset()+16,raw)
    struct.pack_into('<I',data,pe.OPTIONAL_HEADER.get_field_absolute_offset('SizeOfImage'),align(section.VirtualAddress+total,pe.OPTIONAL_HEADER.SectionAlignment))
    info.update(observer_hud_flag=base+4,observer_hud_magic=base,observer_hud_patches=patches)

def install(executable,profile,playback=False):
    info=json.loads(profile.read_text());data=bytearray(executable.read_bytes())
    if hashlib.sha256(data).hexdigest()!=info['output_sha256']:raise ValueError('Observer HUD runtime hash mismatch')
    apply(data,pefile.PE(data=bytes(data)),info,playback)
    executable.write_bytes(data);info['output_sha256']=hashlib.sha256(data).hexdigest();profile.write_text(json.dumps(info,indent=2))
