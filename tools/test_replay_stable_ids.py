"""Check free-stack integrity and native instruction preservation in shadow RAM."""
import json,struct,sys
from unicorn import Uc,UC_ARCH_X86,UC_MODE_32
from unicorn.x86_const import *
p=json.load(open(sys.argv[1],encoding='utf-8'))
for mode in ['physical','visual','loading','unsupported','occupied','exhausted']:
 u=Uc(UC_ARCH_X86,UC_MODE_32)
 for a,s in [(p['code_address'],0x400000),(0x400000,0x300000),
             (0x800000,0x100000),(0x100000,0x100000)]:u.mem_map(a,s)
 u.mem_write(p['allocator_code_address'],bytes.fromhex(p['allocator_code_hex']))
 regs=[UC_X86_REG_EAX,UC_X86_REG_EBX,UC_X86_REG_ECX,UC_X86_REG_EDX,
       UC_X86_REG_ESI,UC_X86_REG_EDI,UC_X86_REG_EBP]
 values=[111,222,333,444,555,0x120000,777]
 for r,v in zip(regs,values):u.reg_write(r,v)
 u.reg_write(UC_X86_REG_ESP,0x190000)
 u.mem_write(0x120004,struct.pack('<H',0x7533 if mode=='visual' else 0x402))
 u.mem_write(0x6c3edc,struct.pack('<I',8192 if mode=='unsupported' else 16384))
 u.mem_write(0x6c47f8,struct.pack('<I',5))
 u.mem_write(0x838c9c,struct.pack('<I',0x130000))
 u.mem_write(0x838c98,struct.pack('<I',0x140000))
 ids=[13000,4,12288,5,13001,12289] if mode!='exhausted' else [10,4,8,5,1,9]
 u.mem_write(0x130000,struct.pack('<6H',*ids))
 if mode=='occupied':u.mem_write(0x140000+12288*4,struct.pack('<I',0x122000))
 u.mem_write(p['state_header'],struct.pack('<I',0 if mode=='loading' else 1))
 u.mem_write(0x8a1238,struct.pack('<I',77))
 u.emu_start(p['allocator_code_address'],p['allocator_resume'],count=200000)
 chosen=12288 if mode=='physical' else 5 if mode=='visual' else ids[-1]
 assert u.reg_read(UC_X86_REG_ESI)==chosen,(mode,u.reg_read(UC_X86_REG_ESI))
 assert u.reg_read(UC_X86_REG_EAX)==4
 assert u.reg_read(UC_X86_REG_ECX)==0x130000
 for r,v in zip(regs,values):
  if r not in [UC_X86_REG_EAX,UC_X86_REG_ECX,UC_X86_REG_ESI]:assert u.reg_read(r)==v
 assert u.reg_read(UC_X86_REG_ESP)==0x190000
 assert struct.unpack('<I',u.mem_read(0x6c47f8,4))[0]==4
 remaining=list(struct.unpack('<5H',u.mem_read(0x130000,10)))
 assert sorted(remaining)==sorted(v for v in ids if v!=chosen)
 errors=struct.unpack('<I',u.mem_read(p['allocator_error_header'],4))[0]
 assert errors==int(mode in ['unsupported','occupied','exhausted'])
print('PASS: stable physical ID, lower visual ID, original load behavior, free-stack integrity, explicit failures.')
print('Actual game determinism and multiplayer/performance are NOT verified by this script.')
