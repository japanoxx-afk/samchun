"""Supplement native SAV with each player's unit-list iteration order.

Analyzed in 3KD2: player head +4/count +8, list node unit +4/next +8,
unit ID WORD +0x5c (native getter 0x4229e0). The neutral-order updater
0x554560 walks this list; changing its order changes RNG consumption.
"""
import hashlib,json,struct
import pefile

class Code:
 def __init__(self,address):self.address=address;self.b=bytearray();self.labels={};self.fix=[]
 def e(self,s):self.b.extend(bytes.fromhex(s))
 def n(self,v):self.b.extend(struct.pack('<I',v&0xffffffff))
 def label(self,s):self.labels[s]=len(self.b)
 def j(self,op,label):self.e(op);self.fix.append((len(self.b),label));self.n(0)
 def call(self,address):self.e('e8');self.n(address-self.address-len(self.b)-4)
 def finish(self):
  for at,label in self.fix:struct.pack_into('<i',self.b,at,self.labels[label]-at-4)
  return self.b

def extend(data,pe,size):
 section=pe.sections[-1];base=0x400000+section.VirtualAddress
 used=(section.Misc_VirtualSize+3)&~3;address=base+used
 total=used+size;align=lambda v,a:(v+a-1)//a*a
 raw=align(total,pe.OPTIONAL_HEADER.FileAlignment)
 data.extend(bytes(max(0,section.PointerToRawData+raw-len(data))))
 struct.pack_into('<I',data,section.get_file_offset()+8,total)
 struct.pack_into('<I',data,section.get_file_offset()+16,raw)
 struct.pack_into('<I',data,pe.OPTIONAL_HEADER.get_field_absolute_offset('SizeOfImage'),align(section.VirtualAddress+total,pe.OPTIONAL_HEADER.SectionAlignment))
 return address,section.PointerToRawData+used

def validate(order):
 if not isinstance(order,list) or len(order)!=9:raise ValueError('Invalid initial player-list snapshot')
 flat=[]
 for row in order:
  if not isinstance(row,list) or len(row)>16384 or any(type(i) is not int or not 0<=i<16384 for i in row):raise ValueError('Invalid unit-list identity')
  flat.extend(row)
 if len(flat)>16384 or len(set(flat))!=len(flat):raise ValueError('Duplicate initial unit-list identity')

def capture_order(executable,profile):
 p=json.loads(profile.read_text());data=bytearray(executable.read_bytes())
 if hashlib.sha256(data).hexdigest()!=p['output_sha256']:raise ValueError('Order recorder runtime mismatch')
 pe=pefile.PE(data=bytes(data));off=lambda a:pe.get_offset_from_rva(a-0x400000)
 if pe.get_data(0x4229e0-0x400000,5)!=bytes.fromhex('0fbf415cc3'):raise ValueError('Native unit ID getter mismatch')
 order,position=extend(data,pe,36+9*32768)
 address=p['code_address']+0x400;flag=p['initial_save_header'];c=Code(address)
 c.e('9c60 833d');c.n(flag);c.e('04');c.j('0f85','done')
 c.e('833d');c.n(flag+32);c.e('00');c.j('0f85','done')
 c.e('8b0d');c.n(0x837dcc);c.e('31f6')
 c.label('player');c.e('8b44b10c 31db 85c0');c.j('0f84','count')
 c.e('8b5808 81fb00400000');c.j('0f87','error');c.e('8b5004')
 c.label('count');c.e('891cb5');c.n(order);c.e('89f7 c1e70f 81c7');c.n(order+36);c.e('31ed 85db');c.j('0f84','next')
 c.label('node');c.e('85d2');c.j('0f84','error');c.e('8b4204 85c0');c.j('0f84','error')
 c.e('0fb7405c 3d00400000');c.j('0f83','error');c.e('6689046f 8b5208 45 39dd');c.j('0f82','node')
 c.e('85d2');c.j('0f85','error')
 c.label('next');c.e('46 83fe09');c.j('0f82','player');c.j('e9','ready')
 c.label('error');c.e('c705');c.n(flag+36);c.n(1)
 c.label('ready');c.e('c705');c.n(flag+32);c.n(1)
 c.label('done');c.e('619d');c.call(p['state_targets']['before']);c.e('c3');code=c.finish()
 if len(code)>0x200 or any(data[off(address):off(address)+len(code)]):raise ValueError('Order capture cave unavailable')
 data[off(address):off(address)+len(code)]=code
 start=p['initial_save_code_address'];saved=bytearray.fromhex(p['initial_save_code_hex']);at=len(saved)-6
 expected=b'\xe8'+struct.pack('<i',p['state_targets']['before']-(start+at+5))
 if saved[at:at+5]!=expected:raise ValueError('Initial order boundary mismatch')
 saved[at:at+5]=b'\xe8'+struct.pack('<i',address-(start+at+5));data[off(start):off(start)+len(saved)]=saved
 executable.write_bytes(data)
 p.update(output_sha256=hashlib.sha256(data).hexdigest(),initial_save_code_hex=saved.hex(),initial_order_address=order,initial_order_ready=flag+32,initial_order_error=flag+36,order_capture_code_address=address,order_capture_code_hex=code.hex())
 profile.write_text(json.dumps(p,indent=2))

def restore_order(data,pe,p,order):
    validate(order);address=p['code_address']+0xd00;helper=address+0x20
    storage,position=extend(data,pe,36+9*32768+65536+16384*12+16+9*16384)
    nodes=storage+36+9*32768;clones=nodes+65536;status=clones+16384*12;head=status+4;produced=status+8;unit_temp=status+12
    relocated=status+16
    for slot,row in enumerate(order):
        struct.pack_into('<I',data,position+slot*4,len(row))
        if row:struct.pack_into('<'+'H'*len(row),data,position+36+slot*32768,*row)
    # Preserve world list links and all cached native iterators. Only this
    # neutral-unit enumeration receives a temporary ordered view.
    c=Code(helper);c.e('9c60 89c3 31c0 bf');c.n(nodes);c.e('b900400000 fc f3ab')
    c.e('8b0cb5');c.n(storage);c.e('89f7 c1e70f 81c7');c.n(storage+36)
    c.e('85c9');c.j('0f84','marked')
    c.label('mark');c.e('0fb707 89f2 c1e20e 01c2 80ba');c.n(relocated);c.e('00');c.j('0f85','mark_next')
    c.e('c70485');c.n(nodes);c.n(1)
    c.label('mark_next');c.e('83c702 49');c.j('0f85','mark')
    c.label('marked');c.e('8b4b08 81f900400000');c.j('0f87','error')
    c.e('8b5304 bf');c.n(clones);c.e('31ed c705');c.n(head);c.n(0);c.e('c705');c.n(produced);c.n(0)
    c.e('85c9');c.j('0f84','old')
    def append(prefix):
        c.e('c70700000000 894704 c7470800000000 85ed');c.j('0f84',prefix+'first')
        c.e('897d08');c.j('e9',prefix+'end')
        c.label(prefix+'first');c.e('893d');c.n(head)
        c.label(prefix+'end');c.e('89fd 83c70c ff05');c.n(produced)
    c.label('scan');c.e('85d2');c.j('0f84','error');c.e('8b4204 85c0');c.j('0f84','error')
    c.e('a3');c.n(unit_temp);c.e('0fb7405c 3d00400000');c.j('0f83','error')
    c.e('833c85');c.n(nodes);c.e('01');c.j('0f84','existing')
    c.e('833c85');c.n(nodes);c.e('00');c.j('0f85','error')
    c.e('c70485');c.n(nodes);c.n(2);c.e('a1');c.n(unit_temp);append('new');c.j('e9','scan_next')
    c.label('existing');c.e('891485');c.n(nodes)
    c.label('scan_next');c.e('8b5208 49');c.j('0f85','scan');c.e('85d2');c.j('0f85','error')
    c.label('old');c.e('8b0cb5');c.n(storage);c.e('c1e60f 81c6');c.n(storage+36);c.e('85c9');c.j('0f84','complete')
    c.label('ordered');c.e('0fb706 8b0485');c.n(nodes);c.e('83f802');c.j('0f86','ordered_next');c.e('8b4004');append('prior')
    c.label('ordered_next');c.e('83c602 49');c.j('0f85','ordered')
    c.label('complete');c.e('a1');c.n(produced);c.e('3b4308');c.j('0f85','error')
    c.e('a1');c.n(head);c.e('890424 c705');c.n(status);c.n(1);c.j('e9','done')
    c.label('error');c.e('c705');c.n(status);c.n(2);c.e('c705');c.n(0x837f24);c.n(1);c.e('8b4304 890424')
    c.label('done');c.e('619d 897c2414 c3');code=c.finish()
    off=pe.get_offset_from_rva(address-0x400000)
    if len(code)+0x20>0x300 or any(data[off:off+len(code)+0x20]):raise ValueError('Ordered observer enumeration cave unavailable')
    initialize=b'\xc7\x05'+struct.pack('<II',status,1)+b'\xb8\x01\0\0\0\xc3'
    data[off:off+len(initialize)]=initialize;data[off+0x20:off+0x20+len(code)]=code
    site=0x5545bb;position=pe.get_offset_from_rva(site-0x400000)
    if data[position:position+7]!=bytes.fromhex('8b7804897c2410'):raise ValueError('Neutral enumeration boundary mismatch')
    data[position:position+7]=b'\xe8'+struct.pack('<i',helper-site-5)+b'\x90\x90'
    p.update(restore_order_code_address=address,restore_order_code_hex=initialize.hex(),restore_order_status=status,
             neutral_order_code_address=helper,neutral_order_code_hex=code.hex(),neutral_order_storage=storage,
             neutral_order_nodes=nodes,neutral_order_clones=clones)
    # Native ownership/create notifications add a unit to the FRONT of its
    # new owner's list. An initial ID returning to the neutral slot must
    # join the native new/reinserted prefix, rather than its old snapshot rank.
    event_pe=pefile.PE(data=bytes(data))
    event,event_position=extend(data,event_pe,256)
    hook=Code(event);hook.e('9c60 833d');hook.n(status);hook.e('01');hook.j('0f85','done')
    hook.e('8b442428 833802');hook.j('0f85','done')
    hook.e('8b5004 83fa09');hook.j('0f83','done')
    hook.e('8b4808 81f900400000');hook.j('0f83','done')
    hook.e('c1e20e 01ca c682');hook.n(relocated);hook.e('01')
    hook.label('done');hook.e('619d 538b5c2408');hook.j('e9','resume')
    hook.labels['resume']=0x43a715-event
    event_code=hook.finish();data[event_position:event_position+len(event_code)]=event_code
    site=0x43a710;event_site=pe.get_offset_from_rva(site-0x400000)
    if data[event_site:event_site+5]!=bytes.fromhex('538b5c2408'):raise ValueError('Native owner notification boundary mismatch')
    data[event_site:event_site+5]=b'\xe9'+struct.pack('<i',event-site-5)
    p.update(neutral_relocated_address=relocated,neutral_owner_event_address=event,neutral_owner_event_code_hex=event_code.hex())
    return address

