"""Build a single-save command-injection experiment, NOT a released replay.

Requires a state diagnostic from a single loaded checkpoint. Original command
drain is bypassed during the experiment. Observer UI, full initial-state and
simulation compatibility, multiplayer and normal ending are not implemented.
"""
import argparse,hashlib,json,struct
from pathlib import Path
import pefile
from build_replay_probe import build
from verify_replay_trace import verify
from analyze_replay import SUPPORTED

def playback(source,trace_path,output,profile):
    trace=json.loads(trace_path.read_text(encoding='utf-8'))
    if trace.get('game_sha256')!=SUPPORTED:raise ValueError('Trace game hash is unsupported.')
    result=verify(trace)
    if result['issues']:raise ValueError('Diagnostic has missing/discontinuous data.')
    states=trace.get('states',[])
    if not states or not states[0]['valid'] or states[0]['phase']!=0:
        raise ValueError('Missing initial pre-dispatch entity checkpoint.')
    commands=trace['records']
    if not commands:raise ValueError('No commands to test.')
    if any(x['slot']!=0 for x in commands):raise ValueError('Only verified single-slot experiment supported.')
    if trace.get('accepted_status') and trace['accepted_status']['validated_dispatches']!=len(commands):
        raise ValueError('Experiment contains unvalidated command attempts.')
    if any(x['native_frame']<states[0]['native_frame'] for x in commands):
        raise ValueError('Commands precede initial checkpoint.')
    final=max((r for r in states if r['valid'] and r['phase']==1),key=lambda r:r['native_frame'],default=None)
    if final is None or final['native_frame']<commands[-1]['native_frame']:
        raise ValueError('Missing final post-update checkpoint.')
    version=trace.get('simulation_patch_version','original-1.20g-baseline-0')
    if version not in ['original-1.20g-baseline-0','replay-stable-ids-experiment-1']:
        raise ValueError('Unsupported simulation patch version.')
    info=build(source,output,profile,stable_ids=version=='replay-stable-ids-experiment-1')
    data=bytearray(output.read_bytes());pe=pefile.PE(data=bytes(data));section=pe.sections[-1]
    end_pos=section.PointerToRawData+info['state_header']-info['code_address']+32
    struct.pack_into('<II',data,end_pos,final['native_frame'],1)
    base=info['code_address'];address=base+0x400
    header=base+section.Misc_VirtualSize
    # Dedicated appended data, never overlaps diagnostic command/RNG/state buffers.
    storage=header+0x100
    payload=bytearray(0x100+len(commands)*128)
    for i,row in enumerate(commands):
        struct.pack_into('<II',payload,0x100+i*128,row['native_frame'],row['slot'])
        raw=bytes.fromhex(row['raw'])
        if len(raw)!=111:raise ValueError('Bad command size.')
        if struct.unpack_from('<I',raw,2)[0]!=row['native_frame']:
            raise ValueError('Raw command scheduled frame mismatch.')
        payload[0x108+i*128:0x108+i*128+111]=raw
    code=bytearray();labels={};fix=[]
    def e(s):code.extend(bytes.fromhex(s))
    def n(v):code.extend(struct.pack('<I',v&0xffffffff))
    def label(s):labels[s]=len(code)
    def branch(op,s):e(op);fix.append((len(code),s));n(0)
    def call(target):e('e8');n(target-(address+len(code)+4))
    e('9c60')
    # Validate restored frame at first native drain. Mismatched loading fails closed.
    e('a1');n(header+4);e('85c0');branch('0f85','loop')
    e('a1');n(0x8a1238);e('3d');n(states[0]['native_frame']);branch('0f85','bad_initial')
    e('c705');n(header+4);n(1)
    label('loop');e('a1');n(header+4);e('83f801');branch('0f85','return')
    e('8b1d');n(header);e('81fb');n(len(commands));branch('0f83','finished')
    e('89de c1e607 81c6');n(storage)
    e('a1');n(0x8a1238);e('3b06');branch('0f82','return');branch('0f87','late')
    call(0x43a7d0)
    e('8b5604 3b5030');branch('0f83','bad_slot')
    e('8b4c9034 85c9');branch('0f84','bad_slot')
    e('8b3d');n(info['accepted_counter'])
    e('8d4608 50');call(0x44c870)
    e('47 3b3d');n(info['accepted_counter']);branch('0f85','rejected')
    e('ff05');n(header);branch('e9','loop')
    label('bad_initial');e('c705');n(header+4);n(2);branch('e9','return')
    label('late');e('c705');n(header+4);n(3);branch('e9','return')
    label('bad_slot');e('c705');n(header+4);n(4);branch('e9','return')
    label('rejected');e('c705');n(header+4);n(6);branch('e9','return')
    label('finished');e('c705');n(header+4);n(5)
    label('return');e('619d c3')
    for pos,name in fix:struct.pack_into('<i',code,pos,labels[name]-pos-4)
    if len(code)>0x200:raise ValueError('Playback stub overlaps validation stub.')
    pos=section.PointerToRawData+0x400;data[pos:pos+len(code)]=code
    pos=pe.get_offset_from_rva(0x4c200)
    if data[pos:pos+8]!=bytes.fromhex('535657e8c8e5feff'):
        raise ValueError('Native drain prologue mismatch.')
    data[pos:pos+8]=b'\xe9'+struct.pack('<i',address-0x44c205)+b'\x90'*3
    def align(v,a):return (v+a-1)//a*a
    end=section.PointerToRawData+section.Misc_VirtualSize
    size=section.Misc_VirtualSize+len(payload)
    raw_size=align(size,pe.OPTIONAL_HEADER.FileAlignment)
    data.extend(bytes(max(0,section.PointerToRawData+raw_size-len(data))))
    data[end:end+len(payload)]=payload
    struct.pack_into('<I',data,section.get_file_offset()+8,size)
    struct.pack_into('<I',data,section.get_file_offset()+16,raw_size)
    struct.pack_into('<I',data,pe.OPTIONAL_HEADER.get_field_absolute_offset('SizeOfImage'),
                     align(section.VirtualAddress+size,pe.OPTIONAL_HEADER.SectionAlignment))
    output.write_bytes(data)
    info.update(status='single-checkpoint-playback-experiment-not-released',
                output_sha256=hashlib.sha256(data).hexdigest(),playback_header=header,
                playback_storage=storage,playback_count=len(commands),playback_initial_frame=states[0]['native_frame'],
                playback_end_frame=final['native_frame'],playback_end_flag=info['state_header']+40,
                playback_code_address=address,playback_code_hex=code.hex(),
                required_checkpoint_sha256='db015576f7af34cc913b2485f17b083d0adcd d96ff8f0467cb733ea5f30d3cf4'.replace(' ',''))
    profile.write_text(json.dumps(info,indent=2),encoding='utf-8')
    print('Experimental command playback built:',len(commands),'commands; not a finished replay.')

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ['source','trace','output','profile']:p.add_argument(name,type=Path)
    a=p.parse_args();playback(a.source,a.trace,a.output,a.profile)
