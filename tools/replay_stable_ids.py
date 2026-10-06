"""Experimental allocator policy for the independently analyzed 1.20g table.

The loaded checkpoint is left intact. After its first main-loop sample, known
unit/building/resource definitions use IDs 12288..16383; other objects use the
lower range. This is a NEW simulation patch, requiring both recording and
playback to use it. Exhaustion/unsupported initial state is explicitly counted.
No object is destroyed, moved in memory, or silently overwritten.
"""
import struct
EXPECTED=bytes.fromhex('a1f8476c008b0d9c8c830033f6668b344148a3f8476c00')
def generate(base,state_header,error_header):
    code=bytearray();labels={};fix=[]
    def e(s):code.extend(bytes.fromhex(s))
    def n(v):code.extend(struct.pack('<I',v&0xffffffff))
    def label(s):labels[s]=len(code)
    def branch(op,s):e(op);fix.append((len(code),s));n(0)
    e('9c60 833d');n(state_header);e('00');branch('0f84','native')
    e('813d');n(0x6c3edc);n(16384);branch('0f85','unsupported')
    # Once armed, verify that the checkpoint did not occupy the reserved range.
    e('833d');n(error_header+12);e('00');branch('0f85','ready')
    e('8b35');n(0x838c98);e('b900300000')
    label('check_initial');e('833c8e00');branch('0f85','unsupported')
    e('41 81f900400000');branch('0f82','check_initial')
    e('c705');n(error_header+12);n(1)
    label('ready');e('833d');n(error_header+12);e('01');branch('0f85','native')
    e('8b1d');n(0x6c47f8);e('85db');branch('0f88','exhausted')
    e('81fb00400000');branch('0f83','unsupported')
    e('8b35');n(0x838c9c);e('0fb74704 3de8030000');branch('0f82','visual')
    e('3d40060000');branch('0f83','visual')
    # Select the smallest free physical ID, independent of visual LIFO churn.
    e('ba00400000 31c9 bfffffffff')
    label('physical');e('0fb7044e 3d00300000');branch('0f82','physical_next')
    e('39d0');branch('0f83','physical_next');e('89c2 89cf')
    label('physical_next');e('41 39d9');branch('0f86','physical')
    e('83ffff');branch('0f84','exhausted');branch('e9','swap')
    label('visual');e('89d9')
    label('visual_loop');e('0fb7044e 3d00300000');branch('0f82','visual_found')
    e('49');branch('0f89','visual_loop');branch('e9','exhausted')
    label('visual_found');e('89cf')
    label('swap')
    # Swap the selected entry with the top, then execute the original pop bytes.
    # Use the selected index EDI for both reads and writes.
    e('668b047e 668b145e 6689147e 6689045e');branch('e9','native')
    label('unsupported');e('c705');n(error_header+12);n(2)
    label('exhausted');e('f0ff05');n(error_header)
    e('a1');n(0x8a1238);e('a3');n(error_header+8)
    label('native');e('619d');code.extend(EXPECTED)
    e('e9');n(0x445f62-(base+len(code)+4))
    for position,name in fix:struct.pack_into('<i',code,position,labels[name]-position-4)
    return bytes(code)
