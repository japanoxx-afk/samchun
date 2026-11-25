# 삼국지천명2 더미 서버(인터넷 호환 서버) NAS 배포 순서

라크무 서버(rakmu-live)·전적 사이트(rtsarena)를 올린 것과 같은 방식이다. 이미지 빌드·SSH 없이 **File Station + Portainer** 만 쓴다.
서버는 Python 표준 라이브러리만 써서 추가 설치가 없다 (`python:3.12-slim` 이 볼륨의 `compat_server.py` 를 그대로 실행).

## 0. 경로와 포트

| File Station | 컨테이너 안 | 내용 |
|---|---|---|
| `game-servers/samchun-live/app/compat_server.py` | `/mnt/game-servers/samchun-live/app/compat_server.py` | 서버 코드 |
| `game-servers/samchun-live/data/` | `/mnt/game-servers/samchun-live/data` | `accounts.sqlite3`(계정·전적), `matches.json`(전적 사이트용), `server.log` |
| `game-servers/samchun-live/backups/` | (서버는 안 씀) | 사람이 백업 보관 |

| 포트 | 용도 | 공유기에서 열기 |
|---|---|---|
| TCP **4800** | 로그인·대기실 | **필요** (외부 4800 → VM 4800) |
| TCP **4901** | 게임 중계 | **필요** (외부 4901 → VM 4901) |
| TCP 4902 | 전적·랭킹 JSON (`/healthz`, `/matches.json`, `/ranking.json`) | 필요 없음 (확인용) |

> **중요**: 게임(3kd2.exe)은 4800/4901 번호를 고정해서 쓴다. 외부 포트와 VM 포트 번호가 **같아야** 한다.
> 지금 공유기는 30000~30999 만 VM 으로 전달한다고 기록돼 있으므로(new-rakum `nas-server/ports.txt`),
> **4800·4901 TCP 전달 규칙을 공유기에 추가**해야 다른 사람이 접속할 수 있다 (서버 관리자에게 요청).
> 게이트웨이 안(같은 공유기)에서만 시험할 때는 전달 규칙 없이 VM 의 내부 IP 로 접속하면 된다.

## 1. 준비 (내 PC, 이 저장소 폴더)

```powershell
.\deploy\Prepare-NasUpload.ps1
```

`deploy\upload\samchun-live\` 에 올릴 파일이 모인다 (`app\compat_server.py`, `app\DEPLOYED_VERSION.txt`, `compose.yaml`, `NAS_DEPLOY.md`).
data 폴더는 들어 있지 않으므로 올려도 NAS 의 계정·전적이 덮어써지지 않는다.

### 기존 계정·전적 옮기기 (선택)

지금까지 PC 에서 런처 **인터넷 서버 구동** 으로 운영한 계정·전적을 그대로 쓰려면:

1. 그 PC 의 런처에서 서버를 끈다 (접속자 없을 때).
2. `%LOCALAPPDATA%\SamchunServer\accounts.sqlite3` 를 복사해 둔다.
3. 아래 2-4 단계에서 `game-servers/samchun-live/data/` 에 그 파일을 올린다 (컨테이너를 켜기 **전에**).

새로 시작하면 이 단계는 건너뛴다. 서버 1.3.58 이상은 예전 DB 에 새 표(matches, match_players)만 더한다 — 기존 계정·전적은 그대로.

## 2. File Station (https://akansas.synology.me:5001/)

1. `game-servers` 를 연다. 다른 프로젝트 폴더(rakmu-live, rtsarena 등)는 건드리지 않는다.
2. 새 폴더 `samchun-live` → 그 안에 `app`, `data`, `backups` 폴더를 만든다.
3. `samchun-live` 에 `compose.yaml`, `NAS_DEPLOY.md` 를 올린다.
4. `samchun-live/app` 에 `compat_server.py`, `DEPLOYED_VERSION.txt` 를 올린다. (기존 DB 를 옮기면 `data` 에 `accounts.sqlite3`)
   최종 모양:
   ```
   game-servers/samchun-live/compose.yaml
   game-servers/samchun-live/app/compat_server.py   ← 이 위치여야 함
   game-servers/samchun-live/data/                   (비어 있거나 accounts.sqlite3)
   ```

## 3. Portainer (https://akansas.synology.me:9443/)

1. 게임 서버 Docker 환경(rakmu-server, rtsarena-web 이 보이는 곳)을 고른다.
2. Containers 의 Published Ports 와 다른 스택에서 **4800, 4901, 4902** 를 쓰는 것이 없는지 확인한다.
   (이 스택은 `network_mode: host` 라 VM 포트를 직접 쓴다 — 겹치면 서버가 `Address already in use` 로 꺼진다.)
3. Stacks → **+ Add stack** → Name: `samchun` → Build method: **Web editor** → `compose.yaml` 내용 전체 붙여 넣기.
   (환경변수는 필요 없다. `game_servers_data` 볼륨은 rtsarena 스택이 쓰는 그 외부 볼륨이다.)
4. **Deploy the stack**.
5. Containers → `samchun-server` 가 running, 1분 뒤 **healthy** 인지 확인.
   Logs 에 아래가 보이면 정상:
   ```
   Status/ranking JSON on http://0.0.0.0:4902/ (healthz, matches.json, ranking.json)
   3KD2 compatibility server listening on 0.0.0.0:4800
   Native game relay listening on TCP 4901
   Server 1.3.59: in-game personal ranking, match history export (/mnt/game-servers/samchun-live/data/matches.json), relay nodelay=True
   ```
6. File Station 에서 `samchun-live/data` 에 `accounts.sqlite3`, `matches.json`, `server.log` 가 생겼는지 확인.

## 4. 접속 확인

- (VM 안 / 같은 망) 브라우저 `http://<VM 내부 IP>:4902/healthz` → `{"ok": true, "version": "1.3.59", ...}`
- 게임 PC 런처: **서버 주소 = `112.159.73.235`** (런처는 IPv4 숫자만 받는다. `akansas.synology.me` 는 안 됨)
  → **입력한 서버로 게임 접속** → 게임에서 **INTERNET** → 회원가입/로그인.
  NAS 서버를 쓸 때는 런처의 **인터넷 서버 구동** 버튼을 누르지 않는다 (그건 내 PC 에 서버를 켜는 버튼).
- 두 PC 로 방 만들기 → 입장 → 게임 1판 → 끝난 뒤 대기실 **랭킹** 메뉴에 두 계정이 보이면 완료.
- 안 되면: 로그인 화면에서 멈춤 = 4800 전달 문제, 방에는 들어가는데 게임이 시작 안 됨 = 4901 전달 문제.

## 5. 전적 사이트(RTS ARENA)와 연결

rtsarena 저장소 main(2026-11-26 이후)이 삼국지천명2 를 지원한다. NAS 에 반영하는 순서:

1. rtsarena 폴더에서 `.\deploy\Prepare-NasUpload.ps1` → File Station `rtsarena/app/arena` 덮어쓰기.
2. Portainer → Stacks → `rtsarena` → **Editor** 에 rtsarena 의 새 `deploy/compose.yaml` 붙여 넣기 → **Update the stack**.
   새 compose 에는 `SAMCHUN_MATCHES_FILE=/mnt/game-servers/samchun-live/data/matches.json` 이 들어 있다
   (같은 `game_servers_data` 볼륨이라 파일을 바로 읽는다, 1분마다 동기화). 기존 `ARENA_UPLOAD_TOKEN` 환경변수는 그대로 둔다.
3. `http://akansas.synology.me:30013/healthz` 의 `sync.samchun.error` 가 비어 있으면 연결됨.

사이트 상단 드롭박스에서 **삼국지천명2** 를 고르면 리더보드·전적기록·게임통계·맵통계 메뉴와 전적이 이 서버 기록으로 바뀐다.
리더보드 = 게임 안 랭킹 (같은 점수 규칙·순서). 리플레이 업로드는 아직 없다 (경기 카드에 "리플레이 미지원").

## 6. 운영

- **코드 업데이트**: `samchun-live/app` 을 `backups/app-YYYYMMDD` 로 복사 → `Prepare-NasUpload.ps1` → `app/compat_server.py` 덮어쓰기
  → Portainer Containers → samchun-server → **Restart**. 접속자가 없을 때 한다 (재시작하면 방·접속이 끊긴다. 계정·전적은 유지).
- **백업**: 서버를 잠깐 멈추거나(Stop) 접속자 없을 때 `samchun-live/data/accounts.sqlite3` 를 `backups/data-YYYYMMDD/` 로 복사.
- **로그**: Portainer Logs 또는 `samchun-live/data/server.log` (접속 IP 가 있으니 공개하지 않는다. 암호는 기록하지 않음).
- **보안**: 게임 원래 프로토콜이라 암호화(TLS)가 없다. 다른 사이트와 같은 암호를 쓰지 말라고 안내한다.
- NAS 공유 폴더에서 SQLite 파일 잠금이 안 되면 서버가 스스로 "process lock only" 로 바꿔 계속 돈다 (로그에 경고 1줄).
  처음부터 그렇게 하려면 compose 의 environment 에 `SAMCHUN_SQLITE_NOLOCK: "1"`.
