"""Standalone experimental match recorder/player, packaged with PyInstaller.

No address/structure/patch from another game is used. Runtime builders accept
only independently verified Samchun binaries. Imported files contain data only.
"""
import argparse,json,os,shutil,subprocess,sys,tempfile,time,traceback,uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import psutil
from build_replay_probe import build,SUPPORTED,MODERN_SUPPORTED,MODERN_BASELINES
from build_replay_playback_probe import playback
from add_replay_initial_save_probe import add as add_save
from add_replay_autoload_probe import add as add_load
from add_replay_restore_probe import add as add_restore
from add_replay_end_probe import add as add_end
from add_replay_session_probe import add as add_session
from replay_mailbox import arm
from replay_initial_order import capture_order
from capture_replay_probe import capture
from compare_replay_traces import compare
from replay_archive import create,unpack,sha,recover_stopped
NO_DIALOG=False
ACTIVE_CONTROLS=None
ACTIVE_PLAYBACK=None
ACTIVE_MAPS=None
ACTIVE_LIVE_OBSERVER=None
ACTIVE_DIAGNOSTICS=[]

class SessionBusy(ValueError):pass

def stop_helper(process,work,label):
    """Cleanup must not replace the original result or skip map/mutex recovery."""
    if process is None:return
    try:
        if process.poll() is None:
            process.terminate()
            try:process.wait(5)
            except subprocess.TimeoutExpired:process.kill();process.wait(5)
    except Exception:
        try:
            with (Path(work)/'cleanup-error.log').open('a',encoding='utf-8') as log:
                log.write(label+'\n'+traceback.format_exc()+'\n')
        except OSError:pass

def start_diagnostics(process,profile,work,mode):
    from crash_diagnostics import CrashMonitor,write_json
    try:ACTIVE_DIAGNOSTICS.append(CrashMonitor(process,profile,work,mode))
    except Exception:write_json(work/'crash-monitor-status.json',dict(error=traceback.format_exc()))

class GameSessionLock:
    def __init__(self,directory):
        import ctypes as c
        self.k=c.WinDLL('kernel32',use_last_error=True)
        self.k.CreateMutexW.argtypes=[c.c_void_p,c.c_int,c.c_wchar_p];self.k.CreateMutexW.restype=c.c_void_p
        self.k.WaitForSingleObject.argtypes=[c.c_void_p,c.c_uint32]
        self.k.ReleaseMutex.argtypes=[c.c_void_p];self.k.CloseHandle.argtypes=[c.c_void_p]
        name='Local\\SamchunReplay-'+sha(str(directory.resolve()).lower().encode('utf-8'))[:24]
        self.handle=self.k.CreateMutexW(None,False,name)
        if not self.handle:raise OSError(c.get_last_error(),'Replay session mutex')
        if self.k.WaitForSingleObject(self.handle,0) not in [0,0x80]:
            self.k.CloseHandle(self.handle);self.handle=None
            raise SessionBusy('게임 실행 또는 리플레이 작업이 이미 진행 중입니다. 실행 중인 게임이나 리플레이를 종료한 뒤 다시 실행해 주세요.')
    def close(self):
        if self.handle:self.k.ReleaseMutex(self.handle);self.k.CloseHandle(self.handle);self.handle=None


def notice(text,error=False):
    if NO_DIALOG:return
    import ctypes
    ctypes.windll.user32.MessageBoxW(None,text,'삼국지 천명2 리플레이',0x10 if error else 0x40)


def idle(directory):
    for process in psutil.process_iter(['name','exe']):
        try:
            name=(process.info['name'] or '').lower();exe=process.info['exe']
            if name.startswith('3kd2') and 'edit' not in name and exe and Path(exe).parent.resolve()==directory.resolve():
                raise ValueError('게임을 종료한 뒤 리플레이 기록/재생을 시작해 주세요.')
        except (psutil.AccessDenied,psutil.NoSuchProcess):continue


def prepare(game,baseline):
    game=game.resolve();baseline=baseline.resolve()
    if sha(game.read_bytes())!=SUPPORTED:raise ValueError('지원하는 원본 1.20g 실행 파일이 아닙니다.')
    if sha(baseline.read_bytes()) not in MODERN_BASELINES:raise ValueError('시뮬레이션 패치가 이 시험 버전과 호환되지 않습니다.')
    idle(baseline.parent)
    from replay_map_dependency import recover_maps
    recover_maps(baseline.parent)
    return baseline.parent


def unique_save(directory,prefix):
    for _ in range(100):
        name=prefix+uuid.uuid4().hex[:4].upper()
        if not (directory/'SAVE'/(name+'.SAV')).exists():return name
    raise ValueError('새 시작 저장 파일 이름을 만들 수 없습니다. 기존 파일은 보존됩니다.')


def data_hashes(directory):
    return {file.name.lower():sha(file.read_bytes()) for file in sorted(directory.iterdir())
            if file.is_file() and (file.suffix.lower()=='.pak' or file.name.lower() in ['3kd2data.dbx','aidll.dll'])}


def record(game,baseline,work,network_helper=None,server_ip=None):
    global ACTIVE_LIVE_OBSERVER
    directory=prepare(game,baseline);work.mkdir(parents=True,exist_ok=False)
    runtime=directory/'3kd2-record.exe';profile=work/'runtime.json'
    name=unique_save(directory,'RPLA')
    build(baseline,runtime,profile,stable_ids=True,original=game,ring=True)
    add_save(runtime,profile,directory,name,normalize=True,multiplayer=True)
    capture_order(runtime,profile)
    add_end(runtime,profile)
    add_session(runtime,profile)
    if network_helper:
        subprocess.run([str(network_helper),'--patch-replay-network',str(runtime),server_ip],check=True)
        info=json.loads(profile.read_text());info['output_sha256']=sha(runtime.read_bytes());profile.write_text(json.dumps(info,indent=2))
    from observer_hud import install as install_hud
    install_hud(runtime,profile)
    # Normal single/multiplayer recording needs the same empty-picture safety
    # as playback. This changes only the failed presentation initializer.
    from picture_fallback import install as install_pictures
    install_pictures(runtime,profile)
    hashes=data_hashes(directory)
    configure_replay_display(directory,'3kd2-record')
    from video_runtime import launch as launch_video
    process=launch_video(runtime,profile,directory,work)
    start_diagnostics(process,profile,work,'game-record')
    helper=Path(getattr(sys,'_MEIPASS',Path(__file__).parent.parent/'dist'/'replay'))/'samchun-replay-controls.exe'
    if helper.exists():
        try:ACTIVE_LIVE_OBSERVER=subprocess.Popen([str(helper),'--live',str(process.pid),str(work)])
        except OSError:(work/'live-observer-error.log').write_text(traceback.format_exc(),encoding='utf-8')
    base_profile=json.loads(profile.read_text());pending=[]
    def save_match(journal,checkpoint,match_work,result):
        stopped=(result['end_reason']=='native-cleanup-transition' or
                 (result['end_reason']=='native-end-transition' and (result.get('end_transition') or {}).get('mode') in [8,9,10]) or
                 (result['end_reason']=='process-unreadable-or-exited' and result.get('process_exit_code')==0))
        if stopped:journal=recover_stopped(journal,match_work/'recovered.journal')
        destination=create(journal,checkpoint,directory/'Replays',data_hashes=hashes,game_directory=directory)
        (match_work/'saved.json').write_text(json.dumps({'file':str(destination)},ensure_ascii=False))
        return str(destination)
    with ThreadPoolExecutor(max_workers=1) as writer:
        generation=0
        while True:
            match_work=work/('match-%04d'%generation);match_work.mkdir()
            active=dict(base_profile,expected_generation=generation,initial_save_name=name+'.SAV')
            active_profile=match_work/'runtime.json';active_profile.write_text(json.dumps(active,indent=2))
            journal=match_work/'record.scpartial';report=match_work/'record-summary.json'
            next_name=unique_save(directory,'RPLA')
            while next_name==name:next_name=unique_save(directory,'RPLA')
            def checkpoint_ready(checkpoint_info):
                # Publish during the current match, after its path was consumed.
                # The next initializer never waits for archive compression.
                shutil.copyfile(directory/'SAVE'/(name+'.SAV'),match_work/'checkpoint.sav')
                arm(process.pid,profile,next_name)
            try:
                capture(process.pid,active_profile,report,24*3600,journal_path=journal,retain=False,on_checkpoint=checkpoint_ready)
            except OSError:
                if process.poll() is not None:break
                raise
            result=json.loads(report.read_text(encoding='utf-8'))
            code=process.poll()
            if code not in (None,0) and not (work/'error-export.json').exists():
                from crash_diagnostics import export_error
                export_error(work,'abnormal-exit',dict(exit_code=hex(code&0xffffffff),last_tick=result.get('last_observed_native_tick'),exception_details='See crash-native.json if crash monitoring was available.'))
            if result['capture_error']:raise ValueError('Recording capture failed: '+str(result['capture_error']))
            if process.poll() is None and result.get('end_transition'):
                arm(process.pid,profile,acknowledge=True)
            if result.get('initial_checkpoint') is not None:
                checkpoint=match_work/'checkpoint.sav'
                if not checkpoint.exists():shutil.copyfile(directory/'SAVE'/(name+'.SAV'),checkpoint)
                pending.append(writer.submit(save_match,journal,checkpoint,match_work,result))
            if process.poll() is not None:break
            if result['end_reason']=='unsupported-mode-or-initial-checkpoint-failed':
                raise ValueError('Initial checkpoint is unsupported or failed; native game continues.')
            name=next_name
            generation+=1
        saved=[future.result() for future in pending]
    (work/'saved.json').write_text(json.dumps({'files':saved},ensure_ascii=False))



def progress(work,text,percent,game_pid=None):
    work.mkdir(parents=True,exist_ok=True)
    temporary=work/'loading.tmp'
    temporary.write_text(json.dumps(dict(text=text,percent=percent,game_pid=game_pid),ensure_ascii=False),encoding='utf-8')
    os.replace(temporary,work/'loading.json')

def configure_replay_display(directory,runtime_name='3kd2-playback'):
    import ctypes as c
    ini=directory/'ddraw.ini'
    if not ini.exists():return
    backup=directory/'launcher-backup'/('replay-display-original.ini' if runtime_name=='3kd2-playback' else 'observer-display-original.ini')
    backup.parent.mkdir(exist_ok=True)
    if not backup.exists():shutil.copyfile(ini,backup)
    k=c.WinDLL('kernel32',use_last_error=True)
    k.GetPrivateProfileStringW.argtypes=[c.c_wchar_p,c.c_wchar_p,c.c_wchar_p,c.c_wchar_p,c.c_uint,c.c_wchar_p]
    k.WritePrivateProfileStringW.argtypes=[c.c_wchar_p,c.c_wchar_p,c.c_wchar_p,c.c_wchar_p]
    value=c.create_unicode_buffer(32)
    k.GetPrivateProfileStringW('ddraw','windowed','false',value,len(value),str(ini))
    fullscreen=value.value.lower()!='true'
    k.GetPrivateProfileStringW('ddraw','fullscreen','false',value,len(value),str(ini))
    fullscreen=fullscreen or value.value.lower()=='true'
    for section in [runtime_name,runtime_name+'.exe']:
        for key,val in dict(windowed='true',fullscreen='true' if fullscreen else 'false',border='false' if fullscreen else 'true',savesettings='0').items():
            if not k.WritePrivateProfileStringW(section,key,val,str(ini)):raise OSError(c.get_last_error(),'리플레이 화면 설정 저장 실패')


def play(game,baseline,file,work):
    global ACTIVE_CONTROLS,ACTIVE_PLAYBACK,ACTIVE_MAPS
    progress(work,"리플레이 파일과 실행 파일 검사 중",15)
    directory=prepare(game,baseline)
    metadata,reference,saved=unpack(file,work)
    progress(work,"지도·게임 데이터 호환성 확인 중",30)
    from replay_map_dependency import check_maps
    if metadata.get('format')==3:
        from replay_map_dependency import MapLease
        ACTIVE_MAPS=MapLease(directory);ACTIVE_MAPS.install(metadata['maps'],work)
    check_maps(saved,directory)
    expected=metadata.get('data_hashes',{})
    if expected and expected!=data_hashes(directory):raise ValueError('지도/게임 데이터 또는 AI DLL이 기록한 PC와 다릅니다. 같은 게임 데이터가 필요합니다.')
    name=unique_save(directory,'RPLB');checkpoint=directory/'SAVE'/(name+'.SAV')
    checkpoint.parent.mkdir(exist_ok=True)
    with checkpoint.open('xb') as stream:stream.write(saved.read_bytes())
    trace=work/'reference.json';trace.write_text(json.dumps(reference))
    runtime=directory/'3kd2-playback.exe';profile=work/'runtime.json'
    progress(work,'재생 명령과 초기 상태 준비 중',50)
    playback(baseline,trace,runtime,profile,original=game,checkpoint=checkpoint,ring=True)
    add_restore(runtime,profile,reference['initial_checkpoint'])
    add_load(runtime,profile,checkpoint,native_checkpoint=True)
    from observer_hud import install as install_hud
    install_hud(runtime,profile,playback=True)
    configure_replay_display(directory)
    progress(work,'게임 시작 중',70)
    from video_runtime import launch as launch_video
    process=launch_video(runtime,profile,directory,work)
    ACTIVE_PLAYBACK=process
    start_diagnostics(process,profile,work,'replay')
    progress(work,'지도 로딩 및 초기 상태 복원 중',85,process.pid)
    report=work/'playback.json'
    controls=None
    if not NO_DIALOG:
        types={e['id']:e['type'] for s in reference.get('states',[])[:2] for e in s.get('entities',[])}
        order=reference['initial_checkpoint'].get('player_unit_order',[])
        slots=metadata.get('slot_ids') or [i for i,ids in enumerate(order) if any(1000<=types.get(x,0)<1556 and types.get(x) not in [1131,1137] for x in ids)]
        if not slots:raise ValueError('참가자 슬롯을 확인할 수 없습니다.')
        (work/'controls.json').write_text(json.dumps(dict(slots=slots,participants=metadata.get('participants',[]),first_tick=metadata['first_tick'],last_tick=metadata['last_tick'],tick_rate=metadata.get('tick_rate',30))),encoding='utf-8')
        helper=Path(getattr(sys,'_MEIPASS',Path(__file__).resolve().parent.parent/'dist/replay'))/'samchun-replay-controls.exe'
        if not helper.exists():process.terminate();raise ValueError('리플레이 관전 제어 파일이 없습니다.')
        controls=subprocess.Popen([str(helper),str(process.pid),str(work.resolve())])
        ACTIVE_CONTROLS=controls
        deadline=time.monotonic()+10
        while not (work/'controls-ready').exists():
            if controls.poll() is not None or time.monotonic()>deadline:
                process.terminate();raise ValueError('리플레이 Esc 및 관전 제어 초기화 실패. '+str(work/'controls-error.log'))
            time.sleep(.05)
    try:capture(process.pid,profile,report,24*3600)
    except Exception:
        stop_helper(controls,work,'controls after capture failure')
        raise
    actual=json.loads(report.read_text(encoding='utf-8'))
    if (work/'user-stop.json').exists():
        actual['end_reason']='user-stopped';report.write_text(json.dumps(actual),encoding='utf-8')
        return
    comparison=compare(reference,actual)
    (work/'comparison.json').write_text(json.dumps(comparison,indent=2))
    # Persist a small, useful diagnosis before a generic incomplete-end error.
    # Keep raw sampled-object differences separate from RNG/resources evidence.
    rejected=(actual.get('playback_status') or {})
    cursor=rejected.get('cursor')
    command=reference['records'][cursor] if isinstance(cursor,int) and 0<=cursor<len(reference['records']) else None
    failure=dict(last_tick=actual.get('last_observed_native_tick'),
                 end_reason=actual.get('end_reason'),playback_status=rejected,
                 rejected_command=command if rejected.get('status')==6 else None,
                 first_sample_difference=comparison.get('first_unit_resource_mismatch'),
                 first_rng_difference=comparison.get('first_rng_mismatch'),
                 first_resource_difference=comparison.get('first_player_resource_mismatch'))
    if rejected.get('status') in [2,3,4,6] or any(failure[k] for k in ['first_sample_difference','first_rng_difference','first_resource_difference']):
        (work/'failure.json').write_text(json.dumps(failure,ensure_ascii=False,indent=2),encoding='utf-8')
    if not actual.get('states'):
        raise ValueError('리플레이 초기 전장 복원에 실패했습니다. 로드 단계: '+str(actual.get('autoload_status'))+'; 종료 코드: '+str(actual.get('process_exit_code'))+'; 로그: '+str(work))
    differences=[x for x in [comparison['first_unit_resource_mismatch'],comparison['first_player_resource_mismatch'],comparison['first_rng_mismatch']] if x]
    if differences:
        first_tick=min(x.get('native_frame',x.get('expected',{}).get('native_frame',0)) for x in differences)
        raise ValueError('기록과 재생의 상태가 처음 달라진 틱: '+str(first_tick)+'. 명령·객체·난수 진단: '+str(work/'failure.json'))
    if actual['capture_error'] or actual['end_reason']!='diagnostic-end-frame-reached':
        detail=' 마지막 틱: '+str(actual.get('last_observed_native_tick'))+'. 종료 사유: '+str(actual['end_reason'])
        raise ValueError('재생이 기록 끝에 도달하지 못했습니다.'+detail+'; 로그: '+str(work))
    if not comparison['command_attempts_match'] or not comparison['rng_calls_match'] or comparison['missing_reference_samples']:
        raise ValueError('명령 또는 상태 검사 지점이 누락됐습니다. 로그: '+str(work))
    if controls:
        (work/'control-result.json').write_text(json.dumps(dict(result='complete')),encoding='utf-8')
        controls.wait()
        if process.poll() is None:
            (work/'game-exit-intent.json').write_text(json.dumps(dict(reason='replay-complete')),encoding='utf-8')
            process.terminate();process.wait(5)
    else:
        notice('리플레이가 종료되었습니다.')
        if process.poll() is None:
            (work/'game-exit-intent.json').write_text(json.dumps(dict(reason='replay-complete')),encoding='utf-8')
            process.terminate();process.wait(5)


def main():
    global NO_DIALOG
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode',choices=['record','play','validate','bundle'])
    parser.add_argument('--game',type=Path);parser.add_argument('--baseline',type=Path)
    parser.add_argument('--file',type=Path);parser.add_argument('--destination',type=Path);parser.add_argument('--work',type=Path,required=True)
    parser.add_argument('--network-helper',type=Path);parser.add_argument('--server-ip')
    parser.add_argument('--no-dialog',action='store_true',help='Internal automated verification; write logs without a modal dialog')
    args=parser.parse_args()
    NO_DIALOG=args.no_dialog
    lock=None
    try:
        if args.mode not in ['validate','bundle']:lock=GameSessionLock(args.baseline.parent)
        if args.mode=='validate':unpack(args.file,args.work)
        elif args.mode=='bundle':
            from replay_archive import include_maps
            args.work.mkdir(parents=True,exist_ok=True)
            # An already portable file needs no local map or write operation.
            import zipfile
            with zipfile.ZipFile(args.file) as archive:version=json.loads(archive.read('metadata.json')).get('format')
            if args.destination:include_maps(args.file,args.game.parent,args.destination)
            elif version!=3:
                backup=args.work/'original.screplay';shutil.copyfile(args.file,backup)
                temporary=args.file.with_name(args.file.name+'.maps-'+uuid.uuid4().hex)
                try:
                    include_maps(args.file,args.game.parent,temporary);temporary.replace(args.file)
                finally:
                    if temporary.exists():temporary.unlink()
        elif args.mode=='record':record(args.game,args.baseline,args.work,args.network_helper,args.server_ip)
        else:play(args.game,args.baseline,args.file,args.work)
        return 0
    except SessionBusy as error:
        notice(str(error))
        return 2
    except Exception:
        args.work.mkdir(parents=True,exist_ok=True)
        log=args.work/'error.log';details=traceback.format_exc()
        for name in ['record-summary.json','failure.json','comparison.json']+ [str(path.relative_to(args.work)) for path in sorted(args.work.glob('match-*/record-summary.json'))[-2:]]:
            if (args.work/name).exists():details+='\n'+name+'\n'+(args.work/name).read_text(encoding='utf-8')
        playback_log=args.work/'playback.json'
        if playback_log.exists():
            diagnostic=json.loads(playback_log.read_text(encoding='utf-8'))
            details+='\nplayback summary\n'+json.dumps({key:diagnostic.get(key) for key in ['end_reason','autoload_status','process_exit_code','last_observed_native_tick','playback_status','capture_error','recent_commands']},ensure_ascii=False,indent=2)
        log.write_text(details,encoding='utf-8')
        from crash_diagnostics import export_error
        try:export_error(args.work,'engine-error',dict(message=str(sys.exc_info()[1]),traceback=details))
        except Exception:pass
        # A rejected replay command pauses the native game. Do not leave that
        # unusable process behind after reporting failure to the launcher.
        stop_helper(ACTIVE_CONTROLS,args.work,'controls after error')
        stop_helper(ACTIVE_PLAYBACK,args.work,'playback after error')
        if args.mode not in ['validate','bundle']:notice('리플레이 작업 실패\n'+str(sys.exc_info()[1])+'\n로그: '+str(log),True)
        return 1
    finally:
        for monitor in ACTIVE_DIAGNOSTICS:
            try:monitor.finish()
            except Exception:
                try:(args.work/'monitor-cleanup-error.log').write_text(traceback.format_exc(),encoding='utf-8')
                except OSError:pass
        # Capture summaries are completed after the native exception event;
        # refresh an existing error bundle with the final match/tick/commands.
        if (args.work/'error-export.json').exists():
            try:
                from crash_diagnostics import export_error
                export_error(args.work,'session-diagnostics',dict(mode=args.mode))
            except Exception:pass
        stop_helper(ACTIVE_LIVE_OBSERVER,args.work,'live observer')
        stop_helper(ACTIVE_CONTROLS,args.work,'controls')
        try:
            if ACTIVE_MAPS:ACTIVE_MAPS.close()
        except Exception:
            cleanup=args.work/'map-restore-error.log';cleanup.write_text(traceback.format_exc(),encoding='utf-8')
            notice('지도 원본 복원에 실패했습니다. 백업은 보존했습니다. 로그: '+str(cleanup),True)
            return 1
        finally:
            if lock:lock.close()


if __name__=='__main__':raise SystemExit(main())
