# T10 패치 적용 Sunshine 빌드·검증 — Windows

SmartClassroom T10 패치를 적용한 Sunshine를 Windows에서 빌드·검증하는 절차다.
**일반 빌드 절차의 정본은 포크 레포의 `docs/building.md`** — 이 문서는 T10 특화
단계(패치 적용, stale 캐시 정리, T10 기능 검증)만 다룬다.

## 0. 사전 점검

`D:/Hongsun/Sunshine/build/`의 `CMakeCache.txt`는 더 이상 존재하지 않는
`C:/msys64/mingw64` 컴파일러를 가리키는 **stale 캐시**다 (4단계에서 폐기 후 재구성).

## 1. MSYS2 설치

`D:/Hongsun/msys2-x86_64-20260322.exe` 실행 → `C:/msys64`.
이후 빌드 명령은 모두 **"MSYS2 UCRT64"** 셸에서 실행한다 (mingw64 아님 — 업스트림
CI가 ucrt64를 사용).

## 2. 의존성 설치

"MSYS2 UCRT64" 셸에서 (패키지 목록의 정본은 포크 레포 `docs/building.md`):

```bash
pacman -Syu          # 셸 재시작을 요구하면 다시 실행
dependencies=(
  "git"
  "mingw-w64-ucrt-x86_64-cmake"
  "mingw-w64-ucrt-x86_64-ninja"
  "mingw-w64-ucrt-x86_64-cppwinrt"
  "mingw-w64-ucrt-x86_64-curl-winssl"
  "mingw-w64-ucrt-x86_64-MinHook"
  "mingw-w64-ucrt-x86_64-miniupnpc"
  "mingw-w64-ucrt-x86_64-nodejs"
  "mingw-w64-ucrt-x86_64-nsis"
  "mingw-w64-ucrt-x86_64-onevpl"
  "mingw-w64-ucrt-x86_64-openssl"
  "mingw-w64-ucrt-x86_64-opus"
  "mingw-w64-ucrt-x86_64-toolchain"
)
pacman -S --needed "${dependencies[@]}"
```

## 3. 패치 적용

```bash
cd /d/Hongsun/Sunshine
git checkout smartclassroom/t10-token-pin     # 패치가 이미 커밋된 브랜치
git submodule update --init --recursive
```

(깨끗한 클론은 `README.md`의 "적용 방법" — `git am *.patch` 참조.)

## 4. stale 캐시 폐기 + 구성·빌드

```bash
cd /d/Hongsun/Sunshine
rm -rf build
cmake -B build -G Ninja -S .
ninja -C build
```

첫 빌드는 의존성 컴파일로 수십 분 소요된다. T10 변경은 `src/config.*` /
`src/confighttp.cpp` 3파일뿐이라, 이후 증분 재빌드는 빠르다.

## 5. T10 기능 검증

빌드된 Sunshine의 `sunshine.conf`에 테스트 키를 추가하고 재시작:

```
broker_api_token = test-secret-0123456789
```

Moonlight에서 이 호스트로 페어링을 1건 시도해 **대기 상태**로 둔 뒤, config UI
포트(기본 `47990`, HTTPS)에 대해 `cmd.exe`에서:

```cmd
:: (1) 정상 토큰 → 페어링 처리 (웹 UI·사람 개입 없음)
curl -k -X POST https://localhost:47990/api/pin ^
  -H "Authorization: Bearer test-secret-0123456789" ^
  -H "Content-Type: application/json" ^
  -d "{\"pin\":\"1234\",\"name\":\"e2e\"}"

:: (2) 잘못된 토큰 → 401
curl -k -X POST https://localhost:47990/api/pin ^
  -H "Authorization: Bearer wrong-token" ^
  -H "Content-Type: application/json" ^
  -d "{\"pin\":\"1234\",\"name\":\"e2e\"}"

:: (3) 토큰 없음 → 401
curl -k -X POST https://localhost:47990/api/pin ^
  -H "Content-Type: application/json" ^
  -d "{\"pin\":\"1234\",\"name\":\"e2e\"}"
```

기대 결과:

| 시나리오 | 기대 |
|---|---|
| (1) 정상 토큰 | 페어링이 웹 UI·사람 개입 없이 처리 — PIN이 맞으면 `{"status":true}`, 틀리면 `{"status":false}` |
| (2) 잘못된 토큰 | `401` + `{"status":false,"error":"Unauthorized"}` |
| (3) 토큰 없음 | `401` (동일) |
| (회귀) Basic Auth 웹 UI | 기존대로 로그인·동작 — 영향 없음 |

`broker_api_token`을 비워 두면 (1)도 `401`이 되어야 한다 (키 미설정 시 Bearer 경로
비활성).

## Linux 빌드

강의실 PC는 Windows 타깃이므로 Linux 빌드는 v1 범위 밖이다. 필요 시 포크 레포
`docs/building.md`의 Linux 절차에 동일 패치를 적용하면 된다 — T10 변경은 플랫폼
독립적이다.
