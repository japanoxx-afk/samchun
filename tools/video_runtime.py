"""Presentation-only native renderer selection and explicit fallback report."""
import ctypes as c,hashlib,json,os,struct,threading,time
from pathlib import Path
import pefile
import subprocess
from replay_initial_order import extend

FAILURE_EXIT=0x56494445

def install_input_recovery(data, info):
    """Reacquire a lost/unacquired native DirectInput device, once per poll.

    Never spin while another application owns foreground input. Buffered reads
    that fail expose zero events instead of reusing the preceding event count.
    """
    from replay_initial_order import Code
    pe = pefile.PE(data=bytes(data))
    sites = ((0x590cbc, '3d1e000780750d8b4618508b08ff511c85c07ddb'),
             (0x590d01, '3d1e00078075158b4618508b10ff521c85c07de1'))
    # Verify both boundaries before changing either one.
    for site, expected in sites:
        at = pe.get_offset_from_rva(site - 0x400000)
        if data[at:at+20] != bytes.fromhex(expected):
            raise ValueError('Native input recovery boundary mismatch')
    address, offset = extend(data, pe, 256)
    for index, (site, _) in enumerate(sites):
        stub = address + index * 128
        code = Code(stub)
        code.e('3d1e000780'); code.j('0f84', 'acquire')
        code.e('3d0c000780'); code.j('0f85', 'result')
        code.label('acquire')
        code.e('8b4618 50 8b08 ff511c 85c0'); code.j('0f88', 'result')
        if index == 0:
            code.e('8b4618 8b542414 57 53 8b08 55 52 50 ff5128')
        else:
            code.e('8b4618 57 53 50 8b08 ff5124')
        code.label('result')
        if index == 0:
            code.e('85c0'); code.j('0f89', 'done')
            code.e('c70300000000')
            code.label('done')
        destination = 0x590cd0 if index == 0 else 0x590d1d
        code.e('e9'); code.n(destination - (stub + len(code.b) + 4))
        raw = code.finish()
        if len(raw) > 128: raise ValueError('Input recovery stub overflow')
        data[offset+index*128:offset+index*128+len(raw)] = raw
        at = pe.get_offset_from_rva(site - 0x400000)
        data[at:at+20] = b'\xe9' + struct.pack('<i', stub-site-5) + b'\x90'*15
    info['video_input_recovery'] = 'bounded-native-directinput-v1'

def install_input_wakeup(data, info):
    """Recover event-driven input even when focus loss stops event delivery.

    Native 0x590e70 waits indefinitely before calling GetDeviceData. A lost
    event source cannot reach that function's recovery path. Wake at 100 ms,
    on the existing input thread, and dispatch only while game input is active.
    """
    from replay_initial_order import Code
    pe = pefile.PE(data=bytes(data))
    timeout = pe.get_offset_from_rva(0x590e85-0x400000)
    branch = pe.get_offset_from_rva(0x590e8e-0x400000)
    if data[timeout:timeout+2] != b'\x6a\xff' or data[branch:branch+10] != bytes.fromhex('85c075ee837b080175e8'):
        raise ValueError('Native input wait boundary mismatch')
    address, offset = extend(data, pe, 128)
    q = Code(address)
    q.e('85c0'); q.j('0f84', 'active')
    q.e('3d02010000'); q.j('0f85', 'wait')
    q.label('active')
    q.e('837b0801'); q.j('0f85', 'wait')
    q.e('833d'); q.n(0x838b14); q.e('00'); q.j('0f85', 'wait')
    q.e('e9'); q.n(0x590e98-(address+len(q.b)+4))
    q.label('wait'); q.e('e9'); q.n(0x590e80-(address+len(q.b)+4))
    raw = q.finish(); data[offset:offset+len(raw)] = raw
    data[timeout:timeout+2] = b'\x6a\x64'
    data[branch:branch+10] = b'\xe9'+struct.pack('<i',address-0x590e93)+b'\x90'*5
    info['video_input_wakeup'] = 'native-event-timeout-100ms-v1'

def install_failure_guard(data, info):
    pe=pefile.PE(data=bytes(data))
    exit_iat=next(i.address for e in pe.DIRECTORY_ENTRY_IMPORT for i in e.imports if i.name==b"ExitProcess")
    address,offset=extend(data,pe,272)
    ready=address+256
    from replay_initial_order import Code
    for index,(site,target,args) in enumerate(((0x56feeb,0x5710c0,1),(0x56fefd,0x571200,3),(0x56fed7,0x5864e0,3),(0x44211b,0x5701b0,5))):
        at=pe.get_offset_from_rva(site-0x400000)
        expected=b"\xe8"+struct.pack("<i",target-site-5)
        if data[at:at+5]!=expected:raise ValueError("Video initialization boundary mismatch")
        stub=address+index*64;code=Code(stub)
        for _ in range(args):code.e("ff7424"+bytes([args*4]).hex())
        code.call(target);code.e("83c4"+bytes([args*4]).hex()+"85c0");code.j("0f85","ok")
        code.e("68");code.n(FAILURE_EXIT);code.e("ff15");code.n(exit_iat)
        code.label("ok")
        if site==0x44211b:code.e("c705");code.n(ready);code.n(1)
        code.e("c3");raw=code.finish()
        if len(raw)>64:raise ValueError("Video guard exceeds allocated space")
        data[offset+index*64:offset+index*64+len(raw)]=raw
        data[at:at+5]=b"\xe8"+struct.pack("<i",stub-site-5)
    info["video_failure_guard"]=True
    info["video_ready_address"]=ready

def configure(executable,profile,directory,requested_mode=None):
    info=json.loads(profile.read_text(encoding='utf-8'));data=bytearray(executable.read_bytes())
    if hashlib.sha256(data).hexdigest()!=info['output_sha256']:raise ValueError('Video runtime hash mismatch')
    from sell_hotkey import install as install_sell_hotkey
    install_sell_hotkey(data, info)
    try:mode=int((directory/'option.ini').read_text(encoding='utf-8-sig').strip())
    except (OSError,ValueError):mode=0
    if requested_mode is not None:mode=requested_mode
    if mode not in (0,1,2,3):mode=0
    names={0:'Auto Detect',1:'Direct3D',2:'Software',3:'Voodoo'}
    info.update(video_requested=names[mode],video_requested_option=mode,video_backend='cnc-ddraw')
    if mode in (1,3):
        # Static DDRAW import otherwise loads the software-only compatibility
        # DLL beside the EXE before native Direct3D initialization even starts.
        pe=pefile.PE(data=bytes(data));entry=next(e for e in pe.DIRECTORY_ENTRY_IMPORT if e.dll.lower()==b'ddraw.dll')
        from hardware_video import prepare
        relative,fullscreen=prepare(directory, mode)
        dll=str(relative/'DDraw.dll').replace('/','\\').encode('ascii')+b'\0'
        glide=str(relative/'Glide2x.dll').replace('/','\\').encode('ascii')+b'\0'
        address,offset=extend(data,pe,len(dll)+len(glide))
        data[offset:offset+len(dll)+len(glide)]=dll+glide
        struct.pack_into('<I',data,entry.struct.get_field_absolute_offset('Name'),address-0x400000)
        glide_site=pe.get_offset_from_rva(0x587021-0x400000)
        if data[glide_site:glide_site+5]!=bytes.fromhex('687cb17200'):
            raise ValueError('Native Glide loader boundary mismatch')
        struct.pack_into('<I',data,glide_site+1,address+len(dll))
        info.update(video_backend='dgVoodoo 2.87.6 / Direct3D 11',video_import=str(relative/'DDraw.dll'),video_fullscreen=fullscreen)
        # Preload the matching D3DImm companion for DDraw's basename lookup.
        pe=pefile.PE(data=bytes(data))
        descriptors=b''.join(e.struct.__pack__() for e in pe.DIRECTORY_ENTRY_IMPORT)
        companion=str(relative/'D3DImm.dll').replace('/','\\').encode('ascii')+b'\0'
        function=b'\0\0GetD3DVersion\0'
        table_size=len(descriptors)+40
        block,raw=extend(data,pe,table_size+16+len(companion)+len(function))
        name=block+table_size+16;symbol=name+len(companion)
        lookup=block+table_size;thunk=lookup+8
        descriptor=struct.pack('<5I',lookup-0x400000,0,0,name-0x400000,thunk-0x400000)
        payload=descriptor+descriptors+bytes(20)+struct.pack('<4I',symbol-0x400000,0,symbol-0x400000,0)+companion+function
        data[raw:raw+len(payload)]=payload
        import_directory=pe.OPTIONAL_HEADER.DATA_DIRECTORY[1]
        struct.pack_into('<II',data,import_directory.get_file_offset(),block-0x400000,table_size)
        install_failure_guard(data,info)
    # Keyboard recovery for EVERY renderer (1.3.62). The native DirectInput reader
    # (0x590cbc/0x590d01) re-acquires only after DIERR_INPUTLOST; a keyboard that is
    # DIERR_NOTACQUIRED (game started or returned while another window had focus:
    # chat, Discord, launcher...) stayed dead for the rest of the session. This was
    # first fixed for Voodoo only (1.3.55/1.3.56); the code path is renderer-independent.
    install_input_recovery(data, info)
    install_input_wakeup(data, info)
    executable.write_bytes(data);info['output_sha256']=hashlib.sha256(data).hexdigest();profile.write_text(json.dumps(info,indent=2))
    env=os.environ.copy();env.pop('RENDER3D',None)
    if mode:env['RENDER3D']={1:'DIRECT3D',2:'SOFTWARE',3:'VOODOO'}[mode]
    if mode == 3:
        env['__COMPAT_LAYER'] = (env.get('__COMPAT_LAYER', '') + ' HIGHDPIAWARE').strip()
    return env

def observe(process,profile,work):
    info=json.loads(profile.read_text(encoding='utf-8'))
    def run():
        k=c.WinDLL('kernel32');k.OpenProcess.restype=c.c_void_p;k.ReadProcessMemory.argtypes=[c.c_void_p,c.c_void_p,c.c_void_p,c.c_size_t,c.c_void_p];k.CloseHandle.argtypes=[c.c_void_p]
        h=k.OpenProcess(0x410,False,process.pid)
        try:
            deadline=time.monotonic()+45;actual=0
            while h and time.monotonic()<deadline:
                value=c.c_uint32()
                if not k.ReadProcessMemory(h,0xafdf08,c.byref(value),4,None):break
                if value.value in (1,2,3):actual=value.value;break
                time.sleep(.2)
            report=dict(requested=info.get('video_requested'),backend=info.get('video_backend'),actual={0:'Initialization not observed',1:'Voodoo',2:'Direct3D',3:'Software'}[actual])
            report['fallback']=actual!=0 and report['requested']!='Auto Detect' and report['requested']!=report['actual']
            if info.get('video_recovery_reason'):report['explanation']=info['video_recovery_reason']
            elif report['fallback']:report['explanation']='Native game rejected the requested graphics device and selected Software. Direct3D requires a compatible legacy device; Voodoo requires Glide 2.x hardware or a separately installed compatible runtime.'
            from crash_diagnostics import write_json
            write_json(work/'video-mode.json',report)
            folder=Path(os.environ.get('LOCALAPPDATA','.'))/'SamchunLauncher'/'ErrorLogs';folder.mkdir(parents=True,exist_ok=True)
            write_json(folder/'video-last.json',report)
        finally:
            if h:k.CloseHandle(h)
    threading.Thread(target=run,name='Video initialization report',daemon=True).start()


def launch(executable,profile,directory,work):
    env=configure(executable,profile,directory)
    process=subprocess.Popen([str(executable)],cwd=str(directory),env=env)
    info=json.loads(profile.read_text(encoding='utf-8'))
    if info.get('video_failure_guard'):
        k=c.WinDLL('kernel32');k.OpenProcess.restype=c.c_void_p
        k.ReadProcessMemory.argtypes=[c.c_void_p,c.c_void_p,c.c_void_p,c.c_size_t,c.c_void_p]
        k.CloseHandle.argtypes=[c.c_void_p]
        h=k.OpenProcess(0x410,False,process.pid)
        ready=False;actual=0
        try:
            deadline=time.monotonic()+45
            while process.poll() is None and time.monotonic()<deadline:
                value=c.c_uint32()
                if h and k.ReadProcessMemory(h,info['video_ready_address'],c.byref(value),4,None) and value.value==1:
                    renderer=c.c_uint32()
                    if k.ReadProcessMemory(h,0xafdf08,c.byref(renderer),4,None):actual=renderer.value
                    ready=True;break
                time.sleep(.02)
        finally:
            if h:k.CloseHandle(h)
        expected={1:2,3:1}[info['video_requested_option']]
        if not ready or actual!=expected:
            if process.poll() is None:process.terminate();process.wait(10)
            from crash_diagnostics import write_json
            report=dict(requested=info['video_requested'],actual={0:'Initialization failed',1:'Voodoo',2:'Direct3D',3:'Software'}.get(actual,'Unknown'),backend=info['video_backend'],ready=ready,exit_code=process.returncode,fallback=False,failed=True)
            write_json(work/'video-mode.json',report)
            write_json(Path(os.environ.get('LOCALAPPDATA','.'))/'SamchunLauncher'/'ErrorLogs'/'video-last.json',report)
            raise ValueError(info['video_requested']+' 비디오 모드를 초기화하지 못했습니다. 설정은 유지했습니다. 오류 리포트 ZIP을 저장해 주세요. Software로 실행하려면 런처에서 직접 선택해 주세요.')
    observe(process,profile,work)
    return process
