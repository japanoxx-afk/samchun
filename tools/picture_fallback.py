"""Handle only native indirect pictures with neither a file nor a loaded image.

The native initializer otherwise returns success with its derived vtable still
installed, and drawing that empty object raises picType=12 / error7901.
Keep the already initialized, resource-free base picture instead. Do not alter
valid pictures, image lookup, game commands, fog or player ownership.
"""
import hashlib
import json
import struct
import pefile


def apply(data, pe, info):
    site=0x4ecee5
    offset=pe.get_offset_from_rva(site-0x400000)
    expected=bytes.fromhex('5f5ec20800')
    if data[offset:offset+5]!=expected:
        raise ValueError('Empty-picture initializer boundary mismatch')
    section=pe.sections[-1]
    used=(section.Misc_VirtualSize+15)&~15
    storage=0x400000+section.VirtualAddress+used
    stub=storage+16
    code=bytes.fromhex('c706d0e36800 f0ff05')+struct.pack('<I',storage)
    code+=bytes.fromhex('893d')+struct.pack('<I',storage+4)
    code+=bytes.fromhex('a138128a00 a3')+struct.pack('<I',storage+8)
    code+=bytes.fromhex('b801000000 5f5e c20800')
    payload=bytes(16)+code
    total=used+len(payload)
    align=lambda n,a:(n+a-1)//a*a
    raw=align(total,pe.OPTIONAL_HEADER.FileAlignment)
    data.extend(bytes(max(0,section.PointerToRawData+raw-len(data))))
    at=section.PointerToRawData+used
    data[at:at+len(payload)]=payload
    data[offset:offset+5]=b'\xe9'+struct.pack('<i',stub-site-5)
    struct.pack_into('<I',data,section.get_file_offset()+8,total)
    struct.pack_into('<I',data,section.get_file_offset()+16,raw)
    struct.pack_into('<I',data,pe.OPTIONAL_HEADER.get_field_absolute_offset('SizeOfImage'),align(section.VirtualAddress+total,pe.OPTIONAL_HEADER.SectionAlignment))
    info.update(observer_empty_image_counter=storage,observer_empty_image_descriptor=storage+4,
                observer_empty_image_last_tick=storage+8,picture_fallback_site=site,
                picture_fallback_code=stub,picture_fallback_code_hex=code.hex())


def install(executable,profile):
    info=json.loads(profile.read_text(encoding='utf-8'))
    data=bytearray(executable.read_bytes())
    if hashlib.sha256(data).hexdigest()!=info['output_sha256']:
        raise ValueError('Empty-picture runtime hash mismatch')
    apply(data,pefile.PE(data=bytes(data)),info)
    executable.write_bytes(data)
    info['output_sha256']=hashlib.sha256(data).hexdigest()
    profile.write_text(json.dumps(info,indent=2),encoding='utf-8')
