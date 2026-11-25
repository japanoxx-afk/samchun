"""Synthetic nine-slot playback dispatch test; does not replace a network match."""
import json,struct,sys,tempfile
from pathlib import Path
from unicorn import Uc,UC_ARCH_X86,UC_MODE_32,UC_HOOK_CODE
from unicorn.x86_const import *
from build_replay_playback_probe import playback
root=Path('verification/replay/multi-dispatch');root.mkdir(exist_ok=True)
trace=json.loads(Path('verification/replay/standalone-play-final/reference.json').read_text())
frame=trace['initial_checkpoint']['native_frame']
trace['initial_checkpoint'].update(context_mode=2,slot_ids=[0,2,8],initialization='native-network-save-v1')
commands=[]
for i,slot in enumerate([8,0,2]):
 row=dict(trace['records'][0],sequence=i,slot=slot,native_frame=frame,scheduled_frame=frame)
 raw=bytearray.fromhex(row['raw']);struct.pack_into('<I',raw,2,frame);row['raw']=raw.hex();commands.append(row)
trace['records']=commands;trace['accepted_status']['validated_dispatches']=3
trace_path=root/'fixture.json';trace_path.write_text(json.dumps(trace))
game=Path(r'C:\Users\seo\Downloads\DGGL\Games\3KD2120g_Win')
profile=root/'runtime.json'
playback(game/'3kd2-replay-base.exe',trace_path,root/'play.exe',profile,original=game/'3kd2.exe',checkpoint=Path('verification/replay/standalone-play-final/checkpoint.sav'),ring=True)
p=json.loads(profile.read_text());assert p['offline_multiplayer_clock']
import pefile
patched=pefile.PE(str(root/'play.exe'))
assert patched.get_data(0x40c57b-0x400000,5)==bytes.fromhex('83c4089090'), 'Loaded queues must bypass the live clock handshake and pop both arguments'
u=Uc(UC_ARCH_X86,UC_MODE_32)
for a,size in [(p['code_address'],0x4000000),(0x400000,0x400000),(0x800000,0x100000),(0x100000,0x100000)]:u.mem_map(a,size)
import pefile
pe=pefile.PE(str(root/'play.exe'));section=pe.sections[-1];u.mem_write(p['code_address'],pe.get_data(section.VirtualAddress,section.Misc_VirtualSize))
u.mem_write(0x43a7d0,b'\xb8'+struct.pack('<I',0x180200)+b'\xc3')
u.mem_write(0x180230,struct.pack('<I',9))
for slot in [0,2,8]:u.mem_write(0x180234+slot*4,struct.pack('<I',0x181000+slot*4))
u.mem_write(0x44c870,b'\xff\x05'+struct.pack('<I',p['accepted_counter'])+b'\xc2\x04\x00')
u.mem_write(0x8a1238,struct.pack('<I',frame));u.reg_write(UC_X86_REG_ESP,0x190000);u.mem_write(0x190000,struct.pack('<I',0x180100))
seen=[]
def hook(u,address,size,user):
 if address==0x44c870:seen.append((u.reg_read(UC_X86_REG_ECX)-0x181000)//4)
u.hook_add(UC_HOOK_CODE,hook)
u.emu_start(p['playback_code_address'],0x180100,count=3000)
assert seen==[8,0,2],seen
assert struct.unpack('<II',u.mem_read(p['playback_header'],8))==(3,5)
assert u.reg_read(UC_X86_REG_ESP)==0x190004
print('PASS all participant slots dispatch in recorded order, native stack balanced; network waiting replaced only in playback')

