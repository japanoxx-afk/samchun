"""Generate bounded diagnostic state sampling at native main-loop boundaries.

This checksum deliberately covers only independently identified common entity
fields. It is NOT a complete simulation checksum: resources, queues and AI are
still being analyzed. No pointer values or selection/camera data are hashed.
"""
import struct

def generate(base,header,storage,capacity,record_size=32,entity_capacity=0):
    code=bytearray();labels={};fix=[]
    def e(s):code.extend(bytes.fromhex(s))
    def n(v):code.extend(struct.pack('<I',v&0xffffffff))
    def label(s):labels[s]=len(code)
    def jump(op,s):e(op);fix.append((len(code),s));n(0)
    def call(address):e('e8');n(address-(base+len(code)+4))
    # Original main-loop call targets, not entire prologue replacement.
    label('before');e('9c60 31db');jump('e8','sample');e('619d');call(0x44c200);e('c3')
    label('after');call(0x502340);e('9c60 bb01000000');jump('e8','sample')
    # Diagnostic playback stops only AFTER the reference final update/sample.
    # Recording leaves this disabled. This is not the finished replay end UI.
    e('833d');n(header+36);e('00');jump('0f84','after_return')
    e('a1');n(0x8a1238);e('3b05');n(header+32);jump('0f82','after_return')
    e('c705');n(0x837f24);n(1)
    e('c705');n(header+40);n(1)
    label('after_return');e('619d c3')
    label('sample')
    e('a1');n(0x8a1238)
    # Each phase has its own last frame. Sampling at frame boundaries avoids
    # inconsistent external ReadProcessMemory snapshots during object updates.
    e('8b149d');n(header+24);e('83faff');jump('0f84','due')
    e('89c1 29d1 83f91e');jump('0f82','return')
    label('due');e('89049d');n(header+24)
    e('b801000000 8705');n(header+12);e('85c0');jump('0f85','busy')
    e('a1');n(header);e('3d');n(capacity);jump('0f83','full')
    e('69c0');n(record_size);e('05');n(storage);e('89c7')
    e('a1');n(header);e('8907 a1');n(0x8a1238);e('894704 895f08')
    e('a1');n(0x6c3edc);e('894718 31c9 894f10')
    if entity_capacity:e('894f20 894f24 894f28 894f2c')
    e('81f800000100');jump('0f87','invalid')
    e('85c0');jump('0f84','invalid')
    e('8b35');n(0x838c98);e('85f6');jump('0f84','invalid')
    e('bdc59d1c81 31db') # FNV-1a; index is part of identity.
    label('object');e('3b1d');n(0x6c3edc);jump('0f83','done')
    e('8b149e 85d2');jump('0f84','next')
    e('ff4710 31dd 69ed93010001')
    # Common entity identity/type and x/y/z: eight bytes starting at +4.
    e('8b4204 31c5 69ed93010001 8b4208 31c5 69ed93010001')
    # Only unit/building type range uses validated extended fields.
    e('0fb74204 3d00040000');jump('0f82','next')
    e('3d14060000');jump('0f83','next')
    for encoded in ['0fb6425e','8b82a1000000','8b82ae000000','8b82b7000000']:
        e(encoded+' 31c5 69ed93010001')
    label('next');e('43');jump('e9','object')
    label('done');e('896f0c c7471401000000 b9c59d1c81 31db 31ed')
    # A separate digest for the game's independently established unit/building
    # and resource definition ranges. Keep the all-object digest as evidence;
    # never hide visual/object-table divergence by replacing it silently.
    label('simulation_object');e('3b1d');n(0x6c3edc);jump('0f83','simulation_done')
    e('8b149e 85d2');jump('0f84','simulation_next')
    e('0fb74204 3de8030000');jump('0f82','simulation_next')
    e('3d40060000');jump('0f83','simulation_next')
    e('31d9 69c993010001')
    for encoded in ['8b4204','8b4208']:
        e(encoded+' 31c1 69c993010001')
    e('0fb74204 3d14060000');jump('0f83','capture_entity' if entity_capacity else 'simulation_next')
    for encoded in ['0fb6425e','8b82a1000000','8b82ae000000','8b82b7000000']:
        e(encoded+' 31c1 69c993010001')
    if entity_capacity:
        label('capture_entity');e('81fd');n(entity_capacity);jump('0f83','entity_full')
        # Preserve the semantic hash and object pointer while copying fields.
        e('51 52 89e8 c1e005 01f8 83c030 8918')
        e('0fb74a04 894804 8b4a06 894808 0fb74a0a 89480c')
        e('c7401000000000 c7401400000000 c7401800000000 c7401c00000000')
        e('0fb74a04 81f914060000');jump('0f83','entity_copied')
        e('8a4a5e 88480e 8b8aa1000000 894810 8b8aae000000 894814 8b8ab7000000 894818')
        label('entity_copied');e('5a 59 45');jump('e9','simulation_next')
        label('entity_full');e('ff472c')
    label('simulation_next');e('43');jump('e9','simulation_object')
    label('simulation_done');e('894f1c')
    if entity_capacity:
        e('896f20 8b35');n(0x837dcc);e('85f6');jump('0f84','players_invalid')
        e('8b4608 894728 83f80c');jump('0f87','players_invalid')
        e('b9c59d1c81 31db')
        label('player');e('3b5e08');jump('0f83','players_done')
        e('8b549e0c 85d2');jump('0f84','player_next')
        e('31d9 69c993010001')
        for offset in [0x18,0x28,0x2c,0x30]:
            e('8b42'+format(offset,'02x'))
            if offset!=0x18:e('3520806236')
            e('31c1 69c993010001')
        label('player_next');e('43');jump('e9','player')
        label('players_done');e('894f24');jump('e9','publish')
        label('players_invalid');e('814f2c00000080')
    jump('e9','publish')
    label('invalid');e('c7471400000000 c7470c00000000 c7471c00000000')
    label('publish');e('ff05');n(header);jump('e9','unlock')
    label('full');e('f0ff05');n(header+4)
    label('unlock');e('31c0 a3');n(header+12);jump('e9','return')
    label('busy');e('f0ff05');n(header+8)
    label('return');e('c3')
    for position,name in fix:struct.pack_into('<i',code,position,labels[name]-position-4)
    return bytes(code),{name:base+labels[name] for name in ['before','after']}
