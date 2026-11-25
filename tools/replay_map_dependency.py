"""Inspect length-prefixed native MAP references before starting the game.

Native SAV strings use a DWORD byte length followed by CP949 text. Only
relative MAP paths with that framing are accepted; arbitrary binary matches
and paths outside the game directory are never used as file operations.
"""
import struct
from pathlib import Path, PureWindowsPath


def required_maps(checkpoint):
    data = Path(checkpoint).read_bytes()
    found = set()
    upper = data.upper()
    start = 0
    while True:
        at = upper.find(b'.\\MAP\\', start)
        if at < 0:
            break
        start = at + 6
        if at < 4:
            continue
        length = struct.unpack_from('<I', data, at - 4)[0]
        if not 6 < length <= 260 or at + length > len(data):
            continue
        raw = data[at:at + length]
        if not raw.upper().endswith(b'.MAP') or b'\0' in raw:
            continue
        try:
            name = raw.decode('cp949', 'strict')
        except UnicodeDecodeError:
            continue
        path = PureWindowsPath(name)
        if (path.is_absolute() or path.drive or len(path.parts) < 2 or
                path.parts[0].upper() != 'MAP' or
                any(part in ('..', '.') or ':' in part or
                    any(ord(c) < 32 for c in part) for part in path.parts)):
            raise ValueError('리플레이의 지도 경로가 올바르지 않습니다.')
        found.add(path.as_posix())
    return sorted(found)


def check_maps(checkpoint, game_directory):
    root = Path(game_directory).resolve()
    missing = []
    for name in required_maps(checkpoint):
        target = (root / name).resolve()
        if not target.is_relative_to(root):
            raise ValueError('리플레이의 지도 경로가 게임 폴더 밖을 가리킵니다.')
        if not target.is_file():
            missing.append(name)
    if missing:
        raise ValueError('이 리플레이에 필요한 지도 파일이 없습니다: ' +
                         ', '.join(missing) +
                         '\n경기를 기록한 PC의 같은 지도 파일을 게임 폴더에 복사해 주세요.')
    return required_maps(checkpoint)


MAP_LIMIT = 16 * 1024 * 1024
MAP_TOTAL_LIMIT = 32 * 1024 * 1024

def map_path(root, name):
    if not isinstance(name,str):raise ValueError('Invalid embedded map path')
    path = PureWindowsPath(name)
    if (path.is_absolute() or path.drive or
        len(path.parts)<2 or path.parts[0].upper()!='MAP' or
        any(part in ('.','..') or ':' in part or any(ord(c)<32 for c in part) for part in path.parts)
        or path.suffix.upper()!='.MAP'):
        raise ValueError('Invalid embedded map path')
    root=Path(root).resolve();target=(root/Path(*path.parts)).resolve()
    if not target.is_relative_to(root):raise ValueError('Map path escapes game folder')
    return target


def package_maps(checkpoint, game_directory):
    import hashlib
    manifest=[];payloads={}
    for i,name in enumerate(check_maps(checkpoint,game_directory)):
        target=map_path(game_directory,name)
        if not 0<target.stat().st_size<=MAP_LIMIT:raise ValueError('Map size exceeds replay limit')
        data=target.read_bytes();member='maps/%d.map'%i
        manifest.append(dict(path=name,member=member,sha256=hashlib.sha256(data).hexdigest(),size=len(data)))
        payloads[member]=data
    if len(manifest)>16 or sum(len(x) for x in payloads.values())>MAP_TOTAL_LIMIT:raise ValueError('Embedded map total exceeds replay limit')
    return manifest,payloads


class MapLease:
    """Use recorded map bytes during playback, then restore the user's files.

    A durable restore manifest allows recovery after an engine/process crash.
    All stored paths are relative, bounded MAP paths checked again on restore.
    """
    def __init__(self,root):
        self.root=Path(root).resolve();self.directory=None

    def install(self,manifest,work):
        import hashlib,json,uuid
        if not manifest:return
        self.directory=self.root/'launcher-backup'/'replay-maps'/uuid.uuid4().hex
        self.directory.mkdir(parents=True)
        entries=[]
        for i,row in enumerate(manifest):
            target=map_path(self.root,row['path']);source=Path(work)/'maps'/('%d.map'%i)
            data=source.read_bytes()
            if hashlib.sha256(data).hexdigest()!=row['sha256']:raise ValueError('Extracted map checksum mismatch')
            if target.is_file() and hashlib.sha256(target.read_bytes()).hexdigest()==row['sha256']:continue
            existed=target.exists()
            if existed and not target.is_file():raise ValueError('Map target is not a file')
            original=target.read_bytes() if existed else None
            if original is not None:
                with (self.directory/('%d.original'%i)).open('xb') as stream:
                    stream.write(original);stream.flush();__import__('os').fsync(stream.fileno())
            entries.append(dict(path=row['path'],index=i,existed=existed,original_sha256=hashlib.sha256(original).hexdigest() if existed else None,installed_sha256=row['sha256']))
        # Persist the full recovery description before touching any game map.
        with (self.directory/'restore.pending').open('x',encoding='utf-8') as stream:
            json.dump(entries,stream);stream.flush();__import__('os').fsync(stream.fileno())
        (self.directory/'restore.pending').replace(self.directory/'restore.json')
        for row in entries:
            target=map_path(self.root,row['path']);target.parent.mkdir(parents=True,exist_ok=True)
            data=(Path(work)/'maps'/('%d.map'%row['index'])).read_bytes()
            if hashlib.sha256(data).hexdigest()!=row['installed_sha256']:raise ValueError('Staged map changed before installation')
            temporary=target.with_name(target.name+'.replay-'+self.directory.name)
            with temporary.open('xb') as stream:
                stream.write(data);stream.flush();__import__('os').fsync(stream.fileno())
            temporary.replace(target)

    def close(self):
        if self.directory:restore_maps(self.root,self.directory);self.directory=None


def restore_maps(root,directory):
    import hashlib,json
    root=Path(root).resolve();directory=Path(directory).resolve()
    area=(root/'launcher-backup'/'replay-maps').resolve()
    if directory.parent!=area or len(directory.name)!=32 or any(c not in '0123456789abcdef' for c in directory.name):raise ValueError('Invalid map recovery directory')
    file=directory/'restore.json'
    if not file.exists():return
    if file.stat().st_size>16384:raise ValueError('Invalid map recovery manifest')
    entries=json.loads(file.read_text(encoding='utf-8'))
    if not isinstance(entries,list) or len(entries)>16:raise ValueError('Invalid map recovery entries')
    for row in entries:
        index=row['index']
        if type(index) is not int or not 0<=index<16 or type(row['existed']) is not bool:raise ValueError('Invalid map recovery entry')
        target=map_path(root,row['path'])
        current=hashlib.sha256(target.read_bytes()).hexdigest() if target.is_file() else None
        original=row['original_sha256']
        pending=target.with_name(target.name+'.replay-'+directory.name)
        if pending.is_file():pending.unlink()
        if current==original:continue
        if current is not None and current!=row['installed_sha256']:
            raise ValueError('지도 파일이 재생 중 변경돼 원본 백업을 보존했습니다: '+str(directory))
        if row['existed']:
            data=(directory/('%d.original'%index)).read_bytes()
            if hashlib.sha256(data).hexdigest()!=original:raise ValueError('Map backup checksum mismatch')
            target.parent.mkdir(parents=True,exist_ok=True)
            temporary=target.with_name(target.name+'.restore-'+directory.name)
            with temporary.open('wb') as stream:
                stream.write(data);stream.flush();__import__('os').fsync(stream.fileno())
            temporary.replace(target)
        elif target.exists():target.unlink()
        temporary=target.with_name(target.name+'.replay-'+directory.name)
        if temporary.is_file():temporary.unlink()
    file.rename(directory/'restored.json')


def recover_maps(root):
    area=Path(root)/'launcher-backup'/'replay-maps'
    if area.is_dir():
        for directory in area.iterdir():
            if directory.is_dir() and (directory/'restore.json').is_file():restore_maps(root,directory)
