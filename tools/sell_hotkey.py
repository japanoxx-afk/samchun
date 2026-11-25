"""3KD2 native command-panel Sell button (ID 21): C instead of A.

Preserves native selection, ownership, disabled-button and queued command checks.
Only local input routing changes; recorded command formats remain unchanged.
"""
import struct
import pefile
from replay_initial_order import Code, extend

def install(data, info):
    pe=pefile.PE(data=bytes(data))
    off=lambda a:pe.get_offset_from_rva(a-0x400000)
    edits=[(0x51867b,b'\x3d',b'\x0b'), # C event -> native command-panel route
           (0x518097,b'\x6a\x0e',b'\xff\x36'), # pass actual A/C event
           (0x414a9e,b'\x08',b'\x00')] # C -> same candidate slot as A
    expected=bytes.fromhex('8bf085f6746e')
    for a,old,new in edits:
        if data[off(a):off(a)+len(old)]!=old:raise ValueError('Sell hotkey dispatch mismatch')
    if data[off(0x4149ff):off(0x4149ff)+6]!=expected:
        raise ValueError('Sell button eligibility boundary mismatch')
    # Button definitions and constructor independently identify ID 21 as Sell.
    if pe.get_data(0x6ac5e8-0x400000,4)!=struct.pack('<I',21) or pe.get_data(0x6ac5f1-0x400000,4)!=struct.pack('<I',0x40d7e0):
        raise ValueError('Native Sell command definition mismatch')
    address,offset=extend(data,pe,128);q=Code(address)
    q.e('8bf0 85f6');q.j('0f84','skip')
    q.e('837c240c10');q.j('0f85','other')
    q.e('66837e0415');q.j('0f85','skip');q.j('e9','allow')
    q.label('other');q.e('837c240c0e');q.j('0f85','allow')
    q.e('66837e0415');q.j('0f84','skip')
    q.label('allow');q.e('e9');q.n(0x414a05-(address+len(q.b)+4))
    q.label('skip');q.e('e9');q.n(0x414a73-(address+len(q.b)+4))
    raw=q.finish();data[offset:offset+len(raw)]=raw
    for a,old,new in edits:data[off(a):off(a)+len(old)]=new
    data[off(0x4149ff):off(0x4149ff)+6]=b'\xe9'+struct.pack('<i',address-0x414a04)+b'\x90'
    info['sell_hotkey']='C';info['sell_hotkey_guard']=address
