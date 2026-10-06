"""Verify experimental tick injection boundaries in shadow RAM only."""
import json,struct,sys
from unicorn import Uc,UC_ARCH_X86,UC_MODE_32
from unicorn.x86_const import *
p=json.load(open(sys.argv[1],encoding='utf-8'))
for mode in ['due','future','late','wrong-initial','rejected']:
 u=Uc(UC_ARCH_X86,UC_MODE_32)
 probe_size=(p['playback_storage']+p['playback_count']*128-p['code_address']+4095)//4096*4096
 for a,s in [(p['code_address'],probe_size),(0x400000,0x300000),
             (0x800000,0x100000),(0x100000,0x100000)]:u.mem_map(a,s)
 u.mem_write(p['playback_code_address'],bytes.fromhex(p['playback_code_hex']))
 u.mem_write(0x43a7d0,b'\xb8'+struct.pack('<I',0x120000)+b'\xc3')
 u.mem_write(0x120030,struct.pack('<II',1,0x121000))
 stub=b'\xff\x05'+struct.pack('<I',0x180100)
 if mode!='rejected':stub+=b'\xff\x05'+struct.pack('<I',p['accepted_counter'])
 u.mem_write(0x44c870,stub+b'\xc2\x04\x00')
 frame=p['playback_initial_frame']
 u.mem_write(0x8a1238,struct.pack('<I',frame+(mode=='wrong-initial')))
 scheduled=frame+int(mode=='future')-int(mode=='late')
 u.mem_write(p['playback_storage'],struct.pack('<II',scheduled,0)+bytes(120))
 # Keep the second command in the future to test a single dispatch.
 u.mem_write(p['playback_storage']+128,struct.pack('<II',frame+100,0)+bytes(120))
 regs=[UC_X86_REG_EAX,UC_X86_REG_EBX,UC_X86_REG_ECX,UC_X86_REG_EDX,
       UC_X86_REG_ESI,UC_X86_REG_EDI,UC_X86_REG_EBP]
 values=[111,222,333,444,555,666,777]
 for r,v in zip(regs,values):u.reg_write(r,v)
 u.reg_write(UC_X86_REG_ESP,0x190000);u.mem_write(0x190000,struct.pack('<I',0x180000))
 u.emu_start(p['playback_code_address'],0x180000,count=10000)
 assert [u.reg_read(r) for r in regs]==values
 assert u.reg_read(UC_X86_REG_ESP)==0x190004
 cursor,status=struct.unpack('<II',u.mem_read(p['playback_header'],8))
 if mode=='due':assert (cursor,status)==(1,1)
 elif mode=='future':assert (cursor,status)==(0,1)
 elif mode=='late':assert (cursor,status)==(0,3)
 elif mode=='rejected':assert (cursor,status)==(0,6)
 else:assert (cursor,status)==(0,2)
 assert struct.unpack('<I',u.mem_read(0x180100,4))[0]==int(mode in ['due','rejected'])
print('PASS: exact-tick injection, future wait, late/initial rejection, native stack and registers.')
print('Actual restored-game state equality has NOT been tested by this script.')
