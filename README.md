# samchun

삼국지 천명 2 (3KD2 1.20g) Windows 런처·패치 및 인게임 Internet 호환 서버.
게임 원본과 게임 데이터는 포함하지 않습니다.
지원 원본 SHA256: `A0EE96931B3B74FCE739062D8E58253892510EF863E9127648AC38FD4D515F99`.

## 1.3.0 호환 서버 시험판

게임의 원래 INTERNET → 회원가입/로그인 → 공용 대기실 → 방 생성 화면을 사용합니다.
런처에서 로그인하지 않습니다. 기존 직접 IP 우회 방식과 다른 서버입니다.
계정은 A의 호환 서버에 새로 가입하며 과거 공식 서비스 계정과 연동되지 않습니다.

실제 게임에서 회원가입, 로그인, 대기실 진입, 방 생성까지 확인했습니다.
프로토콜 테스트에서 두 클라이언트의 목록·채팅·방 참가·중계 전송을 확인했습니다.
**서로 다른 두 PC의 실제 게임 시작·전장 동기화는 아직 검증하지 않았습니다.**
길드·랭킹·전적 집계는 구현하지 않았습니다. 인게임에 해당 원본 메뉴가 남아 있습니다.

## A/B 설치 및 실행

Windows 10/11 64비트에서 ZIP 전체를 새 폴더에 풉니다. Python 설치는 필요 없습니다.
양쪽에 같은 버전의 게임 원본과 맵이 있어야 합니다.

1. A: launcher.exe에서 원본 3kd2.exe 경로 지정 → **A: 호환 서버 켜기**.
2. A: 서버 주소 `127.0.0.1` → **INTERNET 게임 실행** → 게임에서 **INTERNET**.
3. A: 게임에서 회원가입/로그인 → 대기실에서 방 생성.
4. B: 서버 주소에 A의 IPv4 입력 → **INTERNET 게임 실행** → 게임에서 **INTERNET**.
5. B: 자기 계정으로 회원가입/로그인 → 방 목록에서 A의 방 선택 → 참가.

B에서는 호환 서버를 별도로 켜지 않습니다. A의 서버 창을 닫으면 접속이 끊깁니다.
같은 LAN 또는 동일한 Radmin VPN/Hamachi 네트워크의 A 주소를 사용하세요.
서버 포트는 TCP **4800**(로그인/대기실), TCP **4901**(게임 중계)입니다.
방화벽을 통째로 끄지 말고 해당 서버 프로그램/포트만 허용합니다.
원본 인증 통신은 TLS가 없으므로 사설 LAN/VPN에서 사용하고 다른 서비스 암호를 재사용하지 마세요.
기존 게임의 짧은 암호 입력 제한도 그대로 유지됩니다.

## 서버 데이터

기본 위치: `%LOCALAPPDATA%\SamchunServer`.
`accounts.sqlite3`에 무작위 salt와 PBKDF2-SHA256(600,000회) 검증값을 저장합니다.
암호 원문과 이메일은 저장하지 않습니다. 로그에는 패킷 종류/길이만 기록하며 암호·채팅 본문을 기록하지 않습니다.
계정 DB는 ZIP/저장소에 포함하지 않습니다. 서버를 옮길 때는 종료 후 DB를 별도로 옮기세요.
방과 접속 상태는 메모리에 보관하며 서버 재시작 시 초기화합니다.

직접 실행: `server/samchun-server.exe --bind 0.0.0.0 --port 4800 --relay-port 4901`.
원본 클라이언트는 기본 포트를 사용하므로 일반 사용자는 포트를 바꾸지 않습니다.

## 기존 패치

- 창모드, 출력 해상도, 16:9 늘림 (전장 시야 범위는 원본과 같음)
- 건물 우클릭 랠리, 기·오어 랠리 자동채집, 랠리 방향 생성
- Enter 입력창 수정, F2 군사 선택, 마침표 대기 일꾼 선택 (최대 32기)
- 원본 EXE 보존, 3kd2-modern.exe를 별도로 생성

마나 65%, 32기 초과 선택, 복수 건물 동시생산, 순차 마법시전은 미구현입니다.
일반 **게임 실행**에는 호환 서버 연결 패치를 적용하지 않습니다.

## 업데이트

런처 업데이트 버튼은 GitHub의 최신 정식 릴리스에서 launcher.exe/SHA256.txt를 내려받아
해시와 어셈블리 버전을 검증하고 백업·교체·재시작합니다. 파일 선택창은 사용하지 않습니다.
시험판은 자동 업데이트에 포함하지 않습니다. 현재 서버가 포함된 시험판은 **전체 ZIP으로 설치**하세요.
이 업데이트 방식은 런처와 내장 게임 패치만 교체합니다. 서버/그래픽 런타임 변경은 전체 ZIP이 필요합니다.
배포: https://github.com/japanoxx-afk/samchun/releases

## 개발 및 검증

- `build.ps1 [-OutputDirectory 경로]`: .NET Framework C# x86 런처 빌드
- `build-server.ps1 -Python python`: Python 3.12 + PyInstaller 6.22.3으로 서버 EXE 빌드
- `python server/compat_server.py --bind 127.0.0.1 --data verification/server-test`: 개발 서버
- `python tools/test_compat_server.py`: 네이티브 요청 기반 소켓 통합 테스트 (pefile/unicorn 필요)
- `python tools/test_compat_native.py`: 원본 로그인·가입 패킷 생성/성공 응답 파서 에뮬레이션
- `python tools/test_compat_room_native.py`: 원본 방 생성 응답의 중계 접속 인자 검증
- `python tools/test_compat_patch.py`: 성공/연결 실패 메뉴 경로와 스택/주소 패치 검증

검증 도구의 게임 경로는 로컬 설치에 맞게 조정하세요. 원본 패킷은 재배포하지 않습니다.
기존 랠리 바이너리 리소스는 assets/rally.bin이며 생성기는 tools/build_game_patch.py입니다.
네트워크 코드: src/CompatPatch.cs 및 server/compat_server.py.

cnc-ddraw (MIT): https://github.com/FunkyFr3sh/cnc-ddraw
Python 및 PyInstaller 배포 고지는 licenses/에 포함합니다.
