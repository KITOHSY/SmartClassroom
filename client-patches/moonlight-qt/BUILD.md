# SmartClassroom — Moonlight Qt 패치 빌드 & 검증 (T13/T14)

이 문서는 T13+T14 패치 시리즈가 적용된 moonlight-qt fork(`smartclassroom/t13-url-handler` 브랜치, 업스트림 태그 `v6.1.0` 기준)를 **Windows에서 MSVC + Qt online installer**로 빌드해 `moonlight://connect?...` URL 핸들러와 T14 자동 연결(자동 페어링 + 자동 스트림)을 끝까지 검증하는 절차다.

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
있는지 / 패치 파일들이 0001~0011 순서대로 적용되는지 확인. 0001~0008 = T13(0007/0008은
빌드 보정), 0009/0010 = T14 본체(자동 연결 — 빌드 보정 없이 첫 빌드 통과), 0011 = T14
e2e 보정(broker URL percent-encoding 디코딩 — `main.cpp` 두 곳에서
`queryItemValue("broker", QUrl::FullyDecoded)`).

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

### T14 자동 연결 시나리오 (5.5 ~ 5.8)

5.5~5.8은 T14 자동 페어링·자동 스트림을 검증한다. **실호스트 풀체인 전제**:
T10 패치본 Sunshine 호스트(`sunshine.conf`에 `broker_api_token` 설정) + Broker
(admin이 해당 호스트에 `sunshine_broker_token` 등록) + 프런트가 `broker` 파라미터를
포함한 URL을 생성. T14 URL은 `moonlight://connect?token=&host-id=&host=&port=&broker=`
형태 — `broker`는 Broker base URL(예: `http://192.168.1.50:8000`).

로그는 `%LOCALAPPDATA%\Moonlight Game Streaming Project\Moonlight.log` 의 `T14:`
라인으로 추적 (`T14: auto-connect started` / `headless pairing` / `Broker relayed
PIN` / `auto-connect streaming` / `auto-connect failed`).

**같은 PC loopback hazard**: Sunshine 호스트와 Moonlight를 같은 데스크톱에서 띄우면
스트림 화면이 검다(§7). URL 핸들러·자동 흐름 검증엔 무방하나 스트림 화질까지 보려면
강의실 PC ↔ 학생 PC = 별도 기기 2대 필요. **방화벽 hazard**(§7): MSI 없이 exe 직접
실행 시 첫 실행에서 Moonlight·Sunshine 방화벽 경고를 미리 "허용"해 둘 것.

### 5.5 시나리오 ① — 이미 페어링된 호스트 → 자동 스트림

이미 페어링된 호스트로 T14 URL 호출 (포털 `[접속]` 또는 cmd `start "" "moonlight://..."`).

기대 동작:

- 모달 "Connecting to <host>..." 진행 팝업이 잠깐 뜬다.
- 다이얼로그·클릭 0회 — 페어링을 건너뛰고 바로 `StreamSegue`로 진입해 "Desktop"
  스트리밍 시작.
- 로그: `T14: auto-connect started for <host> (already paired)` →
  `T14: auto-connect streaming Desktop from <host>`.

### 5.6 시나리오 ② — 미페어링 호스트 원클릭 (입력 0개 KPI)

페어링되지 않은 호스트로 T14 URL 호출.

기대 동작 — **이것이 "사용자 입력 0개" KPI 검증**:

- 진행 팝업 "Pairing with <host>..." 표시.
- **사용자가 PIN을 입력하지 않는다.** Moonlight가 PIN을 생성 → 로컬 페어링 핸드셰이크
  시작 + `ScBrokerClient`가 Broker `POST /api/v1/pairing`로 PIN 전달 → Broker가
  Sunshine `/api/pin`에 relay → 페어링 자동 완료.
- 페어링 후 "Loading app list..." → "Desktop" 앱 잡히면 자동으로 `StreamSegue` 진입.
- 다이얼로그·클릭·키 입력 **0회**.
- 로그: `T14: auto-connect started ... (needs pairing)` → `starting headless pairing`
  → `Broker relayed PIN` → `headless pairing succeeded` → `auto-connect paired ...
  waiting for app list` → `auto-connect streaming Desktop`.

### 5.7 시나리오 ③ — Broker 다운 (폴백, hang 없음)

Broker를 내린 상태(또는 URL의 `broker`를 도달 불가 주소로)에서 미페어링 호스트
URL 호출.

기대 동작:

- 진행 팝업 표시 후, `ScBrokerClient` 전송 타임아웃(15s) 또는 연결 실패 →
  자동 흐름 종료.
- 팝업이 닫히고 에러 다이얼로그 표시 → 사용자는 표준 PcView 화면에 남아 수동
  페어링 가능. **Moonlight가 멈추지(hang) 않는다.**
- 로그: `T14: Broker pairing relay failed ... broker_unreachable` →
  `T14: auto-connect failed`.

### 5.8 시나리오 ④ — 페어링 실패 (폴백, hang 없음)

페어링이 실패하도록 유도(예: Broker에 등록된 `sunshine_broker_token`을 호스트
실제 값과 불일치하게) 후 미페어링 호스트 URL 호출.

기대 동작:

- 진행 팝업 → 페어링 실패 감지 → 폴백(에러 다이얼로그) → PcView 수동, hang 없음.
- phase-1(`getservercert`) bounded timeout(30s)이 PIN 미도달 시 무한 대기를 막는다.
- 로그: `T14: headless pairing failed` 또는 `Broker pairing relay failed` →
  `auto-connect failed`.

### 5.9 사용자 입력 0회 회귀 체크리스트

moonlight-qt는 연결 흐름 자동 테스트 하네스가 없다(T10 Sunshine 패치와 동일 정책).
"사용자 입력 0회" KPI 회귀는 **시나리오 5.6의 스크립트화된 수동 체크리스트**로 갈음:

1. 미페어링 호스트 준비 (필요 시 Sunshine 신뢰 저장소에서 클라이언트 인증서 제거).
2. 포털 로그인 → 예약 → `[접속]` 클릭. **이 클릭 이후 키보드·마우스 입력 금지.**
3. 통과 기준: Moonlight 기동 → 자동 페어링 → "Desktop" 스트림 도달까지 **추가 입력 0회**.
4. 실패 시 로그의 `T14:` 라인으로 어느 단계에서 멈췄는지 진단.

### 5.10 End-to-end (SmartClassroom 연동)

1. SmartClassroom broker + frontend 가동 (`docker compose up --build` + `pnpm dev`).
2. 브라우저에서 로그인 → 캘린더에서 예약 → `[접속]` 클릭.
3. 브라우저가 `moonlight://connect?...&broker=...` URL 호출 → Windows가 등록된
   핸들러로 Moonlight.exe 기동 → 시나리오 5.5(페어링됨) 또는 5.6(미페어링)으로
   자동 진입.

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
- **T14 자동 연결은 호스트 online을 기다린다**: T14 자동 흐름은 대상 호스트가
  polling으로 resolve돼 `CS_ONLINE`이 된 뒤에만 트리거된다. 호스트가 꺼져 있거나
  도달 불가면 진행 팝업이 아예 안 뜬다 — hang이 아니라 의도된 동작(폴링이 호스트를
  못 찾을 뿐). URL의 `host`/`port`가 실제 Sunshine 스트리밍 포트와 맞는지 확인.
- **T14 `broker` 파라미터 도달성**: `moonlight://` URL의 `broker`는 학생 PC에서
  도달 가능한 Broker base URL이어야 한다. 프런트는 `window.location.origin`을 넣으므로
  (학생 브라우저·Moonlight가 같은 PC) 통상 자동 충족. Broker 미도달 시 시나리오 5.7
  폴백.
- **"Desktop" 앱 전제**: T14 자동 스트림은 호스트 앱 목록에서 "Desktop"(대소문자
  무시)을 고른다. Sunshine 기본 설정이 이 앱을 노출하므로 정상 운영에선 항상 잡히나,
  강의실 PC 배포 시 이 기본 앱 유지가 전제(T20). 못 찾으면 첫 앱으로 폴백.
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
