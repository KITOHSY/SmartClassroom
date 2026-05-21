# SmartClassroom — Moonlight Qt 패치 빌드 & 검증 (T13)

이 문서는 T13 패치 시리즈가 적용된 moonlight-qt fork(`smartclassroom/t13-url-handler` 브랜치, 업스트림 태그 `v6.1.0` 기준)를 **Windows에서 MSVC 2022 + Qt online installer**로 빌드해 `moonlight://connect?...` URL 핸들러를 끝까지 검증하는 절차다.

macOS·Linux 빌드는 v1.1 후속 — T13 v1 시점에는 **세 OS 모두에 대한 패치는 머지하되 검증은 Windows만** 한다 (KPI 측정 환경이 Windows).

## 1. 전제

- Windows 10/11, 관리자 권한
- Visual Studio 2022 **또는** VS BuildTools (Workload **"C++을 사용한 데스크톱 개발"** + MSVC v143/v144 + Windows 10/11 SDK). e2e(2026-05-21)는 VS 2026 BuildTools의 **MSVC v144**로 빌드 성공 — Qt 6.7 binary가 `msvc2019_64` flavor지만 v143/v144와 C++ ABI가 호환(Microsoft 보장).
- [Qt online installer](https://www.qt.io/download-open-source) — 컴포넌트:
  - **Qt 6.7.x** + **MSVC 2019 64-bit** flavor — 업스트림 v6.1.0 CI 매트릭스(`appveyor.yml:7-8` `Visual Studio 2022` + `QTDIR: C:\Qt\6.7`, `build_script`의 `%QTDIR%\msvc2019_64\bin`)와 정확히 일치. 6.7은 non-LTS라 MaintenanceTool에서 **"Archive" 아카이브 옵션을 체크**해야 목록에 나온다.
  - **Qt Quick Controls 2**, **Qt SVG**, **Qt Multimedia**
  - **Tools** → **jom** (멀티코어 빌드)
- [WiX Toolset v4](https://wixtoolset.org/) (MSI 빌드)
- `git submodule update --init --recursive` 완료된 체크아웃

> v6.1.0 업스트림 CI는 정확히 Qt **6.7** + `msvc2019_64`를 쓴다 (`appveyor.yml`). 다른 Qt major/minor를 쓰면 패치 보정이 필요할 수 있으므로 6.7.x 고정 권장.

## 2. 패치 적용

```cmd
cd /d D:\Hongsun\moonlight-qt
git fetch upstream --tags
git checkout -b smartclassroom\t13-url-handler v6.1.0
git submodule update --init --recursive
git am D:\Hongsun\SmartClassroom\client-patches\moonlight-qt\*.patch
```

`git am`이 실패하면 업스트림 태그가 v6.1.0이 맞는지 / submodule이 모두 init 되어
있는지 / 패치 파일들이 0001~0008 순서대로 적용되는지 확인 (0007/0008은 빌드 보정 패치).

## 3. 빌드 (Qt 6.7 + MSVC v143/v144)

**Qt 환경 변수 + MSVC 환경 변수**가 모두 설정된 셸을 사용한다 — "x64 Native
Tools Command Prompt for VS 2022"(또는 BuildTools)를 열고 Qt bin을 PATH에 추가:

```cmd
set QT_DIR=C:\Qt\6.7.3\msvc2019_64
set PATH=%QT_DIR%\bin;%PATH%
```

`6.7.3`은 실제 설치한 패치 버전으로 치환 (`dir C:\Qt`). `qmake -v` 출력이 `Using Qt version 6.7.x ... msvc2019_64`인지 확인 — 시스템에 다른 Qt(예: 6.11 MinGW)가 있으면 PATH 우선순위가 엉킬 수 있다.

qmake로 generate + jom/nmake로 build:

```cmd
cd /d D:\Hongsun\moonlight-qt
qmake moonlight-qt.pro
jom    :: 또는 nmake
```

> 첫 빌드는 수십 분. 이후 증분 빌드는 빠르다.

산출: `app\release\Moonlight.exe`.

### 3.5 런타임 DLL deploy (빌드 직후 필수)

`qmake`+`jom`은 `Moonlight.exe`만 만든다 — Qt/OpenSSL/SDL2/ffmpeg 런타임 DLL은
같은 폴더에 없어 그대로 실행하면 `libcrypto-3-x64.dll이(가) 없어...` 류 시스템
오류가 난다. 업스트림 `scripts\build-arch.bat`이 deploy 전체를 처리하지만 v1
검증엔 과하므로 핵심만 뽑는다. **반드시 레포 루트를 cwd로** (상대경로 `libs\...`가
다른 cwd에선 안 맞아 copy가 조용히 실패):

```cmd
cd /d D:\Hongsun\moonlight-qt
copy libs\windows\lib\x64\*.dll app\release\
copy AntiHooking\release\AntiHooking.dll app\release\
copy app\SDL_GameControllerDB\gamecontrollerdb.txt app\release\
windeployqt --release --qmldir app\gui --no-opengl-sw --no-compiler-runtime --no-sql app\release\Moonlight.exe
```

- `copy libs\windows\lib\x64\*.dll` — `libcrypto`/`libssl`/`SDL2`/`opus`/`avcodec` 등 11개. `11개 파일이 복사되었습니다`가 떠야 OK.
- `windeployqt`는 §3에서 Qt bin을 PATH에 잡은 셸이어야 동작. 새 cmd면 §3 `set PATH` 재실행.
- VC 런타임(`vcruntime140.dll`/`msvcp140.dll`)까지 missing이면 [VC++ 2015-2022 재배포 패키지](https://aka.ms/vs/17/release/vc_redist.x64.exe) 설치.

deploy 후 `dir app\release\*.dll`이 비어 있지 않아야 한다.

### MSI 패키지 (선택)

```cmd
msbuild wix\Moonlight.sln /p:Configuration=Release /p:Platform=x64
```

`wix\Moonlight\bin\Release\Moonlight.msi` 가 생성된다. 이 MSI가 0004 패치의
`HKCR\moonlight` 레지스트리 등록을 포함한다.

## 4. 사전점검 (Windows)

빌드본을 단독으로 실행하기 전:

1. **포트 충돌 해소** — 기존에 설치된 moonlight-qt가 있다면 종료 (`taskkill /F /IM Moonlight.exe`). PcView가 같은 host 행을 두 번 보이는 혼란을 피한다.
2. **mDNS 차단 해제** — Windows Defender Firewall이 moonlight-qt의 UDP 5353을
   막지 않게 첫 실행 시 "사설 네트워크" 허용.
3. **이전 SmartClassroom 등록 검증** — 다른 fork가 `HKCR\moonlight`을 등록한
   적이 있는지 확인:
   ```cmd
   reg query HKCR\moonlight /s
   ```
   기존 항목이 있으면 MSI 재설치가 그것을 덮어쓴다.

## 5. 검증 시나리오 (Windows 수동)

자동 테스트 없음 (T10 Sunshine 패치와 동일 정책 — fork 패치는 실호스트 검증
중심).

### 5.1 빌드 통과

`app\release\Moonlight.exe`가 생성되고 그냥 실행했을 때 PcView가 정상 표시.

### 5.2 MSI 설치 후 레지스트리 확인 (관리자 cmd)

```cmd
reg query HKCR\moonlight /s
```

출력에 다음 4개 항목이 모두 나오면 OK:

- `HKCR\moonlight` (Default) `= URL:Moonlight Protocol`
- `HKCR\moonlight` `URL Protocol = `(빈 문자열)
- `HKCR\moonlight\DefaultIcon` `= "<install path>\Moonlight.exe",0`
- `HKCR\moonlight\shell\open\command` `= "<install path>\Moonlight.exe" "%1"`

### 5.3 URL 시나리오 ① — 등록되지 않은 IP (토큰 보관 검증)

cmd에서:

```cmd
start "" "moonlight://connect?token=ABC1234567890123456789&host-id=42&host=192.0.2.10&port=47989"
```

기대 동작:

- Moonlight 창이 뜬다 (PcView).
- moonlight-qt 콘솔/로그 (Windows: `%LOCALAPPDATA%\Moonlight Game Streaming Project\Moonlight.log`)에 다음 라인이 찍힌다:
  - `T13 connect requested host= "192.0.2.10" port= 47989 host-id= 42 token-prefix= "ABC12345"`
  - `T13: requesting addNewHost for "192.0.2.10" port 47989 host-id= 42`
  - polling이 host에 도달하면 (192.0.2.10이 실제 Sunshine을 띄우고 있어야 함):
    `T13: stamped pending connect on host <name> after polling resolved it`
- PcView의 호스트 목록에 192.0.2.10 항목이 등장.

### 5.4 URL 시나리오 ② — 단일 인스턴스 forward

Moonlight가 실행 중인 상태에서 위 5.3 명령을 다시 호출:

기대 동작:

- 새 Moonlight 창이 뜨지 **않음** (두 번째 인스턴스가 `return 0`으로 종료).
- 기존 인스턴스 로그에:
  - `T13: dispatching moonlight://connect host= ...`
  - (host가 이미 m_KnownHosts에 있으면) `T13: stamped pending connect on known host <name>`

### 5.5 URL 시나리오 ③ — 기존 페어링된 호스트

이미 페어링된 호스트의 IP로 URL을 호출:

기대 동작:

- PcView가 그 호스트를 "Paired"로 표시.
- 사용자가 그 호스트를 클릭 → 통상 stream segue로 진입.
- 토큰은 `NvComputer::pendingConnectToken`에 보관됨 — 실제 NvHTTP Bearer 헤더
  주입은 **T14 후속**. T13 v1에서는 보관만.

### 5.6 URL 시나리오 ④ — 미페어링 호스트 (T13 폴백 동작)

페어링되지 않은 호스트 IP로 URL을 호출:

기대 동작:

- PcView가 해당 호스트를 "Not paired"로 표시.
- 사용자 클릭 → **표준 PIN 입력 화면**으로 진입 (T13 v1 폴백 — T14 머지 전).
- 사용자가 PIN을 직접 입력하면 통상 페어링.
- KPI("입력 0개")는 미충족이지만 회귀 없음.

### 5.7 End-to-end (SmartClassroom 연동)

1. SmartClassroom broker + frontend 가동 (`docker compose up --build` + `pnpm dev`).
2. 브라우저에서 로그인 → 캘린더에서 예약 → `[접속]` 클릭.
3. 브라우저가 `moonlight://connect?...` URL 호출 → Windows가 등록된 핸들러로
   Moonlight.exe 기동 → 시나리오 5.5 (페어링됨) 또는 5.6 (미페어링) 중 하나로
   진입.

## 6. macOS · Linux 빌드 (v1.1 후속)

이 절은 v1 범위 밖이지만 향후 검증 참조:

### macOS

- Qt for macOS + Xcode
- `qmake moonlight-qt.pro && make`
- `.app` 번들 + `hdiutil`로 dmg 생성 (업스트림 `scripts/generate-dmg.sh`)
- Info.plist의 `CFBundleURLTypes`는 LaunchServices가 자동 인덱싱.
- 검증: `lsregister -dump | grep -i moonlight://`

### Linux (AppImage)

- Qt for Linux + linuxdeployqt
- 업스트림 빌드 스크립트 (`scripts/generate-appimage.sh`)
- AppImage 사용자는 **첫 실행 후 수동 등록 필요**:
  ```bash
  xdg-mime default com.moonlight_stream.Moonlight.desktop x-scheme-handler/moonlight
  ```
- 검증: `xdg-mime query default x-scheme-handler/moonlight`

## 7. 알려진 hazard

- **shallow clone**: 현 `D:/Hongsun/moonlight-qt` 가 shallow면 `git tag --list`가
  비어 v6.1.0 checkout 불가. `git fetch upstream --tags --unshallow` 선행.
- **stale QLocalServer socket**: 비정상 종료 후 named pipe가 남아 있을 수 있다.
  0002 패치의 `scT13StartSingleInstanceServer`가 `QLocalServer::removeServer()`
  로 정리한다 — 첫 인스턴스 시작 시 자동.
- **Qt 5 vs 6 호환**: 업스트림 `app.pro`가 `lessThan(QT_MAJOR_VERSION, 6)`
  분기를 두는지 확인. v6.1.0 핀이라면 같은 시점 업스트림 CI를 따른다.
- **NvHTTP Bearer 미주입 (스코프 안)**: T13만 머지된 상태에서 token은
  `pendingConnectToken`에만 보관되고 NvHTTP 헤더에 안 실린다. 사용자는 통상
  PIN 화면을 본다 — 회귀가 아니라 v1 의도된 폴백. T14가 본격 KPI 달성.
- **IPv6 host 인코딩**: 프런트 `buildMoonlightUrl`이 `URLSearchParams`에 IP를
  raw 통과. IPv6 `[fe80::1]` 형태가 URL에 들어갈 때 안전한지 확인 필요. v1
  강의실 PC는 IPv4 가정이라 비범위.
- **macOS code signing**: URL 스킴 등록은 entitlements 변경 없이 Info.plist
  만으로 가능. 노타라이즈 영향 없을 것으로 추정 — v1.1 macOS 검증 시 재확인.
- **방화벽이 페어링 라운드트립을 보류 (e2e 2026-05-21 발견)**: MSI 없이
  `app\release\Moonlight.exe`를 직접 실행하면 첫 네트워크 사용 시 Windows
  Defender Firewall 경고창이 뜬다. 허용 전까지 소켓이 보류돼 — **Sunshine
  웹UI에서 PIN을 넣어 "성공"이 떠도 Moonlight의 `PendingPairingTask`가 PIN 이후
  라운드트립 응답을 못 받아 PIN 다이얼로그가 안 닫힌다.** 경고창 "허용"으로 즉시
  해소. T13 코드와 무관 — 정식 MSI 배포는 `wix/Moonlight/Product.wxs`의
  `<fire:FirewallException>`이 설치 시 방화벽 예외를 자동 등록하므로 안 뜬다.
  §5 시나리오 ③·④ 전에 Moonlight·Sunshine을 한 번씩 띄워 경고를 미리 허용해 둘 것.
- **같은 PC loopback 스트리밍 = 검은 화면 (e2e 2026-05-21 발견)**: Sunshine
  호스트와 Moonlight 클라이언트를 *같은 Windows 데스크톱*에서 띄워 "Desktop"을
  스트리밍하면 화면이 검게만 나온다 — Windows Desktop Duplication API가 자기
  캡처 출력을 다시 캡처하는 피드백 루프. **T13·스트리밍 코드 결함이 아니다.**
  실제 배포(강의실 PC ↔ 학생 PC = 별도 기기)에선 발생하지 않는다. URL 핸들러
  검증만이 목적이면 검은 화면은 무시 가능 — 스트림 화질까지 보려면 별도 기기 2대로.
