# smartclassroom-agent

T11 — SmartClassroom 강의실 PC에 설치되는 호스트 상태 보고 에이전트.

## 역할

30초 주기로 broker에 heartbeat 보고:
- 시스템 메트릭 (CPU/메모리/uptime)
- Sunshine 세션 상태 (프로세스/활성 사용자/클라이언트 수)
- (옵션) GPU 메트릭 (nvidia-smi)
- broker 자기-RTT

Broker 인증은 admin이 사전 발급한 `tokens.purpose='agent'` Bearer 토큰. mTLS는 T20 운영 트랙으로 위임.

## 빠른 시작 (개발)

```cmd
:: agent/ 안에서
uv sync --extra dev
uv run python -m smartclassroom_agent doctor
uv run python -m smartclassroom_agent run --config ./agent.yaml
```

`agent.yaml`:
```yaml
broker_url: "http://localhost:8000"
host_id: 1
agent_token: "<raw token from POST /api/v1/hosts>"
interval_seconds: 30
```

## 검증

```cmd
uv run ruff check .
uv run mypy smartclassroom_agent
uv run pytest -v
```

## 배포

v1은 manual install. Windows 서비스 등록: `python -m smartclassroom_agent install-service --config <path>`. 자동 업데이트 채널은 T20 운영 트랙.

## 모노레포 위치

`broker/`(FastAPI 백엔드) + `frontend/`(React) + **`agent/`(본 패키지)** 가 형제 루트. CLAUDE.md 모노레포 룰에 따라 파일을 위로 끌어올리지 말 것.
