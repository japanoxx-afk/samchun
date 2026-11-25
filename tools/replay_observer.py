"""Playback-only input sink and display visibility for independently analyzed 1.20g.

Do not modify the fog grid, player ownership, AI visibility or network callbacks.
425510/4256f0 generate outgoing orders; recorded execution enters 44C870 instead.
The visibility facades below are reached by the display/sound/camera paths.
42F870 is shared; only its verified UI call sites are overridden.
"""
import struct


def apply(data,pe,info):
    section=pe.sections[-1];base=0x400000+section.VirtualAddress
    size=section.Misc_VirtualSize;storage=base+size;counter=storage
    stub=storage+16
    code=b'\xf0\xff\x05'+struct.pack('<I',counter)+b'\xb8\x01\0\0\0\xc3'
    # Keep an initialized native base picture when an indirect image is absent.
    # Returning NULL from the factory triggers error 7905 in its outer caller.
    # Base virtual drawing/destruction accepts +9==0 and owns no image resource.
    image_stub=stub+len(code)
    image_code=bytes.fromhex('c706d0e36800 f0ff05')+struct.pack('<I',storage+4)
    image_code+=bytes.fromhex('893d')+struct.pack('<I',storage+8)
    image_code+=bytes.fromhex('a138128a00 a3')+struct.pack('<I',storage+12)
    image_code+=bytes.fromhex('b801000000 5f5e c20800')
    payload=bytes(16)+code+image_code
    def align(v,a):return (v+a-1)//a*a
    total=size+len(payload);raw=align(total,pe.OPTIONAL_HEADER.FileAlignment)
    data.extend(bytes(max(0,section.PointerToRawData+raw-len(data))))
    pos=section.PointerToRawData+size;data[pos:pos+len(payload)]=payload
    struct.pack_into('<I',data,section.get_file_offset()+8,total)
    struct.pack_into('<I',data,section.get_file_offset()+16,raw)
    struct.pack_into('<I',data,pe.OPTIONAL_HEADER.get_field_absolute_offset('SizeOfImage'),align(section.VirtualAddress+total,pe.OPTIONAL_HEADER.SectionAlignment))
    changes=[]
    def edit(site,expected,replacement):
        at=pe.get_offset_from_rva(site-0x400000)
        if data[at:at+len(expected)]!=expected:raise ValueError('Observer boundary mismatch: '+hex(site))
        if len(replacement)!=len(expected):raise ValueError('Observer patch size mismatch')
        data[at:at+len(expected)]=replacement
        changes.append(dict(address=site,expected=expected.hex(),replacement=replacement.hex()))
    for site,expected in [(0x425510,'b800100000'),(0x4256f0,'81ec880f0000')]:
        original=bytes.fromhex(expected)
        edit(site,original,b'\xe9'+struct.pack('<i',stub-site-5)+bytes([0x90])*(len(original)-5))
    edit(0x4ecee5,bytes.fromhex('5f5ec20800'),b'\xe9'+struct.pack('<i',image_stub-0x4ecee5-5))
    # Separate terrain fog, visible-object enumeration, and positional sound/camera tests.
    for site,expected,result in [
        (0x42f2c0,'a1307f830085',1),
        (0x42f340,'a1307f830085',12),
        (0x42f370,'a1307f830085',18),
        (0x42f3a0,'0fbf44240499',12),
        (0x42f3f0,'a1307f830085',1),
        (0x42f420,'568b7424088b',1),
    ]:
        edit(site,bytes.fromhex(expected),b'\xb8'+struct.pack('<I',result)+b'\xc3')
    for site in [0x52d20c,0x52d42e,0x52d825,0x52d89e,0x52ddcb,0x52f92f,0x52fc51,0x52fce0,0x52fd56]:
        edit(site,b'\xe8'+struct.pack('<i',0x42f870-site-5),b'\xb8\x01\0\0\0')
    # 541D10 is the native selection method (vtable +170): it inserts into
    # 52C690, sets the selection flag +2A2 and creates a selection marker.
    # It is not the AI target query; leave the shared 42F870 implementation intact.
    edit(0x541d5f,b'\xe8'+struct.pack('<i',0x42f870-0x541d5f-5),b'\xb8\x01\0\0\0')
    # Objects with +488 enabled also reject non-allied inspection here.
    # Preserve dead/disabled-object checks and normal selection bookkeeping.
    edit(0x541d7b,bytes.fromhex('7460'),bytes.fromhex('eb60'))
    # Native lower HUD: 412760 builds command/progress slots, 414340 dispatches
    # selected-object state to 410E30..4123D5 (production/research/morph panels).
    # Override only their owner-display checks, never the shared alliance query.
    progress_sites=[0x410018,0x410ed9,0x4113c0,0x4115a0,0x41177f,
                    0x411925,0x411abf,0x411c53,0x4123d5,0x412b3c,0x413117]
    for site in progress_sites:
        edit(site,b'\xe8'+struct.pack('<i',0x5319e0-site-5),b'\xb8\x01\0\0\0')
    info.update(observer_native_progress_sites=progress_sites)
    info.update(observer_visibility=True,observer_blocked_counter=counter,observer_input_code_address=stub,
                observer_input_code_hex=code.hex(),observer_patches=changes)
    info.update(observer_empty_image_counter=storage+4,observer_empty_image_descriptor=storage+8,
                observer_empty_image_last_tick=storage+12)

