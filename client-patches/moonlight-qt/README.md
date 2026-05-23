# SmartClassroom — Moonlight Qt 클라이언트 패치 (T13/T14)

SmartClassroom 포크가 [moonlight-qt](https://github.com/moonlight-stream/moonlight-qt)
클라이언트에 적용하는 패치 모음이다. `git format-patch`로 export 되었고,
**고정된 업스트림 태그 위에** 순서대로 적용한다 (`host-patches/sunshine/` 대칭).

## 고정 업스트림 (pinned)

- 업스트림 레포: `moonlight-stream/moonlight-qt`
- **고정 태그: `v6.1.0`** (commit `f786e94c7b2f943e24e65d7d74deb539b827fc84`)
- 포크 레포: `D:/Hongsun/moonlight-qt` — origin `github.com/KITOHSY/moonlight-qt`, upstream `moonlight-stream/moonlight-qt`
- 패치 브랜치: `smartclassroom/t13-url-handler` (이 태그 기준 — T13 + T14 누적)

업스트림 추적 주기·담당자는 미정 — EXP.md §11 "fork 유지보수" / T20 운영 트랙.

## 패치 목록 (순서대로 적용)

| # | 파일 | 내용 | 변경 파일 |
|---|------|------|-----------|
| 0001 | `0001-T13-add-connect-subcommand-and-CLI-parser.patch` | `connect` 서브커맨드 + `ConnectCommandLineParser` 추가 (`--connect-token` / `--host-id` / `--host` / `--port`) | `app/cli/commandlineparser.{h,cpp}` |
| 0002 | `0002-T13-add-moonlight-URL-handler-and-single-instance-fo.patch` | `moonlight://` URL 핸들러 + URL→CLI 확장 + `QLocalServer`/`QLocalSocket` 단일 인스턴스 forward + `ConnectRequested` 분기 (stub) | `app/main.cpp` |
| 0003 | `0003-T13-ComputerManager-connect-entry-point-pending-toke.patch` | `ComputerManager::requestConnect` + `stashPendingConnect` + `NvComputer::pendingConnectToken/pendingHostId` 비-영속 멤버 + main.cpp stub→실동작 교체 | `app/backend/nvcomputer.h`, `app/backend/computermanager.{h,cpp}`, `app/main.cpp` |
| 0004 | `0004-T13-register-moonlight-URL-protocol-in-WiX-installer.patch` | Windows WiX 인스톨러에 `HKCR\moonlight` URL Protocol 컴포넌트 등록 | `wix/Moonlight/Product.wxs` |
| 0005 | `0005-T13-register-moonlight-URL-scheme-in-macOS-Info.plis.patch` | macOS `Info.plist`에 `CFBundleURLTypes` (스킴 `moonlight`) 추가 | `app/Info.plist` |
| 0006 | `0006-T13-register-moonlight-URL-scheme-in-Linux-.desktop-.patch` | Linux `.desktop` 에 `MimeType=x-scheme-handler/moonlight;` + `Exec=moonlight %u` | `app/deploy/linux/com.moonlight_stream.Moonlight.desktop` |
| 0007 | `0007-T13-drop-setUrlHandler-call-Qt-6-signature-mismatch-.patch` | **빌드 보정** — 0002의 `QDesktopServices::setUrlHandler` lambda 호출이 Qt 6 시그니처(QObject\*+slot)와 불일치해 MSVC 빌드 실패(C2660). setUrlHandler 호출과 `<QDesktopServices>` include 제거 + single-instance receiver를 `scT13DispatchMoonlightUrl`로 직접 dispatch. macOS `QFileOpenEvent` 채널은 **v1.1 후속** (Q_OBJECT receiver 클래스 필요) | `app/main.cpp` |
| 0008 | `0008-T13-forward-declare-scT13DispatchMoonlightUrl-for-re.patch` | **빌드 보정** — 0007이 옮긴 호출이 함수 정의보다 앞에 있어 MSVC C3861. `scT13StartSingleInstanceServer` 정의 위에 `scT13DispatchMoonlightUrl` forward declaration 한 줄 추가 | `app/main.cpp` |
| 0009 | `0009-T14-add-ScBrokerClient-for-Broker-pairing-relay.patch` | **T14** — `ScBrokerClient`: Broker `POST /api/v1/pairing`로 `{connect-token, PIN}` 전송(`QNetworkAccessManager`+`QJsonDocument`). 헤드리스 페어링이 PIN 입력 없이 완료되게 하는 아웃바운드 채널 | `app/backend/scbrokerclient.{h,cpp}`(신규), `app/app.pro` |
| 0010 | `0010-T14-automatic-connect-broker-URL-headless-pairing-au.patch` | **T14** — moonlight:// URL `broker` 파라미터 + 헤드리스 페어링(`ComputerManager::beginHeadlessPairing`, `NvPairingManager` phase-1 bounded timeout) + 자동연결 상태머신(`ComputerManager`) + `main.qml` 진행 팝업·`StreamSegue` 자동 진입 | `app/backend/computermanager.{h,cpp}`·`nvcomputer.h`·`nvpairingmanager.{h,cpp}`, `app/cli/commandlineparser.{h,cpp}`, `app/gui/main.qml`, `app/main.cpp` |
| 0011 | `0011-T14-decode-percent-encoded-broker-URL-param.patch` | **T14 e2e 보정** — `scT13ExpandMoonlightConnectUrl`·`scT13DispatchMoonlightUrl`에서 `queryItemValue("broker")` 기본 `QUrl::PrettyDecoded` 모드가 `:` `/` (`%3A`/`%2F`)를 디코딩 안 해 `ScBrokerClient`가 `bad_broker_url`로 거부하던 버그. 두 곳 모두 `QUrl::FullyDecoded`로 변경. e2e(2026-05-24)에서 발견 | `app/main.cpp` |

T13 합계 `app/` + `wix/` 9파일 / 약 +515줄, −32줄. T14 추가 `app/` 12파일 / 약 +663줄,
−46줄 (0009 신규 클래스 +120, 0010 본체 +539/−44, 0011 e2e 보정 +2/−2). 0007/0008은
T10 0003/0004와 같은 부류의 빌드 보정 패치, 0011은 e2e 보정 패치 — 본래 0010과 한
커밋이어야 했으나 이미 export 후 e2e에서 발견된 거라 별도 패치로 분리. 4종 e2e 시나리오
(①미페어링 KPI·②페어링됨·③Broker미도달·④페어링실패) 전부 통과 (2026-05-24).

## 무엇을 / 왜 (T13)

SmartClassroom v1 KPI는 **"사용자 입력 0개"** — 학생이 웹 캘린더에서 `[접속]`을
누르면 자동으로 강의실 PC 스트리밍에 도달해야 한다.
[`frontend/src/lib/moonlight.ts`](../../frontend/src/lib/moonlight.ts)는
`moonlight://connect?token=<raw>&host-id=<id>&host=<ip>&port=<port>` URL을
조립해 OS에 던지지만, 업스트림 moonlight-qt에는 이 URL 스킴 핸들러가 없다
([issue #29](https://github.com/moonlight-stream/moonlight-qt/issues/29) 미해결).

T13은 fork에:

1. **URL 스킴 핸들러** — Windows/Linux는 argv 진입 시 `moonlight://...` 패턴을
   감지해 `connect` 서브커맨드 CLI 형태로 확장한다. macOS는
   `QDesktopServices::setUrlHandler` 로 `QFileOpenEvent` 채널을 잡아 같은
   디스패처로 합류한다.
2. **단일 인스턴스 forwarding** — 두 번째 인스턴스가 URL을 발견하면 첫 인스턴스에
   `QLocalSocket` 으로 forward 후 즉시 종료한다. PcView 창이 2개 뜨는 혼란 방지.
3. **`connect` CLI 서브커맨드** — `moonlight connect <host> [--port N] --connect-token <raw> [--host-id N]`. URL과 CLI가 한 디스패치 경로로 수렴.
4. **`ComputerManager` 진입점** — 받은 host/IP가 이미 알려진 호스트면 그
   `NvComputer`에 token/host-id를 즉시 stamp, 아니면 `addNewHost` 호출 후
   polling이 host를 resolve할 때 stamp.
5. **NvComputer 비-영속 멤버** — `pendingConnectToken`, `pendingHostId`. 영속
   저장 금지 (raw token 디스크 노출 + reservation 만료 후 stale).
6. **OS별 인스톨러 등록** — Windows WiX 레지스트리, macOS Info.plist, Linux
   .desktop MIME.

**범위 밖 (T13 시점 — 아래 "T14 (완료)" 참조):**
- 자동 페어링 + 자동 스트림 — 미페어링 호스트도 입력 0개로 도달. **T14가 0009/0010으로 구현 완료.**
- CLI 인자(URL 아닌)의 단일 인스턴스 forwarding — T13 v1은 URL만 forward. v1.1 후속.

T13만 머지된 상태는 **기존 페어링 호스트는 정상 stream, 미페어링 호스트는 통상 PIN
입력 화면으로 fall-through** — 회귀 없음. T14(0009/0010)가 미페어링 호스트의 자동
페어링·자동 스트림을 더해 "원클릭 접속(입력 0개)" KPI를 달성한다.

## 적용 방법

이미 포크 레포에 패치 브랜치가 있으면 그대로 사용:

```bash
cd /d/Hongsun/moonlight-qt
git checkout smartclassroom/t13-url-handler
```

깨끗한 클론에 적용하려면:

```bash
git clone https://github.com/KITOHSY/moonlight-qt.git --recurse-submodules
cd moonlight-qt
git remote add upstream https://github.com/moonlight-stream/moonlight-qt.git
git fetch upstream --tags
git checkout -b smartclassroom/t13-url-handler v6.1.0
git submodule update --init --recursive
git am /d/Hongsun/SmartClassroom/client-patches/moonlight-qt/*.patch
```

빌드·검증 절차는 `BUILD.md` 참조.

## 업스트림 태그 bump 시

1. 새 태그로 `git checkout -b smartclassroom/t13-url-handler-<새태그> <새태그>`
2. `git am *.patch`로 패치 재적용 → 충돌 해결
3. `git format-patch <새태그>..HEAD -o client-patches/moonlight-qt -- app/ wix/` 로
   패치 재-export (`-- app/ wix/` 경로 한정은 CI 워크플로 커밋이 시리즈에 섞이는
   것을 방지)
4. 이 README의 고정 태그/commit 갱신

## T14 (완료, 2026-05-22 — 패치 0009/0010)

T14는 T13의 토큰 보관 위에 **자동 페어링 + 자동 스트림**을 얹어 "원클릭 접속
(입력 0개)" KPI를 달성한다. T13 시점에 예상했던 "NvHTTP `Authorization: Bearer`
헤더 주입" 설계는 **채택되지 않았다** — connect 토큰은 Sunshine 호스트가 아니라
**Broker**로 가고, Sunshine 인증은 표준 페어링 핸드셰이크가 교환하는 클라이언트
인증서(mTLS)가 담당한다. T14의 실제 구조:

- **PIN-relay 모델 (T08과 짝)** — 페어링 PIN은 Moonlight가 생성하고, `ScBrokerClient`
  (0009)가 `POST {broker}/api/v1/pairing {token, pin}`으로 Broker에 넘긴다. Broker가
  그 PIN을 Sunshine `/api/pin`에 relay해 호스트 쪽 페어링 세션을 푼다 — 사용자는
  PIN을 입력하지 않는다. connect 토큰은 이 Broker 호출의 인증으로만 쓰인다.
- **헤드리스 페어링** — `ComputerManager::beginHeadlessPairing`이 PIN 생성 →
  로컬 페어링 핸드셰이크(`pairHost`) + 동시에 `ScBrokerClient` 호출. `NvPairingManager`
  는 인증서를 새로 발급받지 않고 기존 per-install 자가서명 인증서로 표준 핸드셰이크를
  수행하되, 헤드리스 경로의 phase-1(`getservercert`)에 bounded timeout을 둬 PIN이
  영영 안 와도(Broker 다운 등) 무한 hang하지 않는다.
- **자동 연결 + 자동 스트림** — `ComputerManager` 상태머신이 토큰 stamp된 호스트가
  online이 되면 (필요 시) 헤드리스 페어링 → "Desktop" 앱 탐색 → `Session` 생성 →
  `main.qml`이 `StreamSegue`로 자동 진입. GUI 개입 0회. 실패·타임아웃 시 표준
  PcView 수동 화면으로 폴백.

T13 시점의 "NvHTTP Bearer 헤더 주입 / `IdentityManager` Broker 인증서 발급"
문구는 폐기됐다 (EXP.md T14 완료조건 정정 참조).
