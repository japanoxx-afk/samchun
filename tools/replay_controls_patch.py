"""Playback pacing only: preserve one command drain/update per simulation tick."""
import struct
def apply(data,pe,info):
 s=pe.sections[-1];size=s.Misc_VirtualSize;base=0x400000+s.VirtualAddress+size
 code=bytes.fromhex('a1f0a67200 0faf05')+struct.pack('<I',base)+b'\xc3'
 # Observe native DirectInput left-button transitions without changing simulation.
 mouse=base+16+len(code);m=bytearray(bytes.fromhex('9c60 0fb64609 83e001 3b05')+struct.pack('<I',base+4))
 m+=b'\x74';same=len(m);m+=b'\0';m+=b'\xa3'+struct.pack('<I',base+4)+bytes.fromhex('85c0 74');up=len(m);m+=b'\0'
 m+=bytes.fromhex('a1207f8300 a3')+struct.pack('<I',base+12)+bytes.fromhex('ff05')+struct.pack('<I',base+8)
 end=len(m);m[same]=end-same-1;m[up]=end-up-1;m+=bytes.fromhex('619d e9')+struct.pack('<i',0x43c5f0-mouse-len(m)-5-2)
 # Relative jump starts after POPAD/POPFD.
 jump=len(m)-5;struct.pack_into('<i',m,jump+1,0x43c5f0-(mouse+jump+5))
 payload=struct.pack('<IIII',1,0,0,0)+code+m
 total=size+len(payload);raw=(total+pe.OPTIONAL_HEADER.FileAlignment-1)//pe.OPTIONAL_HEADER.FileAlignment*pe.OPTIONAL_HEADER.FileAlignment
 data.extend(bytes(max(0,s.PointerToRawData+raw-len(data))))
 data[s.PointerToRawData+size:s.PointerToRawData+size+len(payload)]=payload
 struct.pack_into('<I',data,s.get_file_offset()+8,total);struct.pack_into('<I',data,s.get_file_offset()+16,raw)
 struct.pack_into('<I',data,pe.OPTIONAL_HEADER.get_field_absolute_offset('SizeOfImage'),(s.VirtualAddress+total+4095)&~4095)
 site=0x4e2fd2;at=pe.get_offset_from_rva(site-0x400000)
 expected=b'\xe8'+struct.pack('<i',0x56f600-site-5)
 if data[at:at+5]!=expected:raise ValueError('Replay clock call mismatch')
 data[at:at+5]=b'\xe8'+struct.pack('<i',base+16-site-5)
 at=pe.get_offset_from_rva(0x52ad10-0x400000)
 if data[at:at+6]!=bytes.fromhex('8b0d64f87100'):raise ValueError('Replay native Esc menu mismatch')
 data[at]=0xc3
 at=pe.get_offset_from_rva(0x52ad20-0x400000)
 if data[at:at+5]!=bytes.fromhex('a1a88c8300'):raise ValueError('Replay native auto-menu mismatch')
 data[at]=0xc3
 site=0x517b31;at=pe.get_offset_from_rva(site-0x400000)
 expected=b'\xe8'+struct.pack('<i',0x43c5f0-site-5)
 if data[at:at+5]!=expected:raise ValueError('Replay native mouse-event boundary mismatch')
 data[at:at+5]=b'\xe8'+struct.pack('<i',mouse-site-5)
 info.update(observer_speed_address=base,observer_speed_values=[1,2,4],observer_native_mouse_counter=base+8,observer_native_mouse_point=base+12)
