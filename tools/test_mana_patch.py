"""Execute production hooks as x86, including the native MP getter layout."""
import runpy, struct
from unicorn import UC_HOOK_CODE
from unicorn.x86_const import *

ctx=runpy.run_path('tools/test_game_patch.py')
Case,BASE,UNIT,TABLE,STACK,END,n=[ctx[k] for k in ('Case','BASE','UNIT','TABLE','STACK','END','n')]
cases=0
for entry,factory,argc in [(0x400,0x54fef0,6),(0x550,0x54f5a0,5)]:
 for maximum in [0,1,99,100,150,200,300,32767,-1]:
  for success in [True,False]:
   c=Case();u=c.u
   c.method(TABLE,0x234,native=c.ret(maximum))
   u.mem_write(UNIT+0xa1,struct.pack('<HH',4321,17))
   producer=UNIT+0x4000;building=UNIT+0x5000
   c.put(producer+0x49,building);c.put(building,TABLE)
   u.mem_write(building+0x2bc,struct.pack('<hhh',32767,0,0))
   u.mem_write(factory,b'\xb8'+n(UNIT if success else 0)+b'\xc3')
   args=list(range(101,101+argc));seen=[]
   def trace(uc,a,size,data):
    if a==factory:
     sp=uc.reg_read(UC_X86_REG_ESP)
     seen.append(list(struct.unpack('<'+'I'*argc,uc.mem_read(sp+4,argc*4))))
   u.hook_add(UC_HOOK_CODE,trace)
   c.put(STACK,END)
   for i,arg in enumerate(args):c.put(STACK+4+4*i,arg)
   regs={UC_X86_REG_EDI:producer,UC_X86_REG_ESI:0x12345678,UC_X86_REG_EBX:0x87654321,UC_X86_REG_EBP:0x13579bdf}
   for r,v in regs.items():u.reg_write(r,v)
   u.reg_write(UC_X86_REG_ESP,STACK);u.emu_start(BASE+entry,END,count=2000)
   assert seen==[args]
   assert u.reg_read(UC_X86_REG_EAX)==(UNIT if success else 0)
   assert u.reg_read(UC_X86_REG_ESP)==STACK+4
   for r,v in regs.items():assert u.reg_read(r)==v
   hp,mp=struct.unpack('<HH',u.mem_read(UNIT+0xa1,4))
   assert hp==4321
   assert mp==(maximum*65//100 if success and maximum>0 else 17)
   cases+=1
print(f'{cases} mana production cases passed (both factories, upgraded maximum, HP preservation, null return, zero MP, rounding).')
