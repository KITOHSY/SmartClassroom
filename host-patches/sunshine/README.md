# SmartClassroom — Sunshine 호스트 패치 (T10)

SmartClassroom 포크가 Sunshine 게임 스트리밍 호스트에 적용하는 패치 모음이다.
`git format-patch`로 export 되었고, **고정된 업스트림 태그 위에** 순서대로 적용한다.

## 고정 업스트림 (pinned)

- 업스트림 레포: `LizardByte/Sunshine`
- **고정 태그: `v2025.628.4510`** (commit `65f14e1003f831e776c170621bd06d8292f65155`)
- 포크 레포: `D:/Hongsun/Sunshine` — origin `github.com/KITOHSY/Sunshine`, upstream `LizardByte/Sunshine`
- 패치 브랜치: `smartclassroom/t10-token-pin` (이 태그 기준)

업스트림 추적 주기·담당자는 미정 — EXP.md §11 "fork 유지보수" / T20 운영 트랙.

## 패치 목록 (순서대로 적용)

| # | 파일 | 내용 | 변경 파일 |
|---|------|------|-----------|
| 0001 | `0001-T10-add-broker_api_token-config-key.patch` | `sunshine.conf`에 `broker_api_token` 키 추가 | `src/config.h`, `src/config.cpp` |
| 0002 | `0002-T10-add-Bearer-token-authentication-path-to-confight.patch` | `confighttp` `authenticate()`에 Bearer 토큰 인증 경로 추가 | `src/confighttp.cpp` |

합계 `src/` 3파일 / +44줄. 플랫폼 독립적 — Win/Linux 공통.

## 무엇을 / 왜 (T10)

SmartClassroom Broker가 Sunshine config API(특히 `POST /api/pin`)를 **사람 개입 없이**
호출할 수 있도록, 기존 Basic Auth 외에 **정적 Bearer 토큰 인증 경로**를 추가한다.
"원클릭 접속(입력 0개)" — 학생이 Moonlight↔Sunshine 페어링의 4자리 PIN을 직접
타이핑하지 않게 하기 위함.

동작:

- `sunshine.conf`에 `broker_api_token = <secret>`을 설정하면 활성화된다.
- 요청에 `Authorization: Bearer <secret>` 헤더가 있으면, 그 값을 `broker_api_token`과
  **상수시간 비교**해 일치 시 인증 통과 — username/password 불필요.
- IP-origin 게이트(`origin_web_ui_allowed`)는 그대로 적용된다.
- 키를 설정하지 않으면 Bearer 경로는 비활성 → **기존 Basic Auth 동작 100% 유지**.

이 토큰은 **호스트별 정적 시크릿**(예약별 connect 토큰이 아님)이다. Broker가 호스트마다
발급·보관하고, 인스톨러가 `sunshine.conf`에 주입한다 — T11 `agent.yaml`의 agent 토큰과
같은 프로비저닝 모델.

**범위 밖 (T08 위임):** 예약별 connect 토큰을 Broker `/tokens/verify`로 되묻는 동적
검증은 T08(자동 페어링) 소관. 필요 시 이 패치 시리즈에 후속 패치로 추가한다.

## 적용 방법

이미 포크 레포에 패치 브랜치가 있으면 그대로 사용:

```bash
cd /d/Hongsun/Sunshine
git checkout smartclassroom/t10-token-pin
```

깨끗한 클론에 적용하려면:

```bash
git clone https://github.com/KITOHSY/Sunshine.git --recurse-submodules
cd Sunshine
git checkout -b smartclassroom/t10-token-pin v2025.628.4510
git am /d/Hongsun/SmartClassroom/host-patches/sunshine/*.patch
```

빌드·검증 절차는 `BUILD.md` 참조.

## 업스트림 태그 bump 시

1. 새 태그로 `git checkout -b smartclassroom/t10-token-pin-<새태그> <새태그>`
2. `git am *.patch`로 패치 재적용 → 충돌 해결
3. `git format-patch <새태그>..HEAD -o host-patches/sunshine`로 패치 재-export
4. 이 README의 고정 태그/commit 갱신
