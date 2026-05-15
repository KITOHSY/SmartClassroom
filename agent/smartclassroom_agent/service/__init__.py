"""OS 서비스 wrapper.

- windows.py: pywin32(win32serviceutil) — Windows 서비스 등록/시작/중지
- systemd.py: unit 파일 생성 헬퍼 (Linux 테스트/특수 환경용)

둘 다 optional import — 해당 OS가 아니어도 패키지 import는 성공.
"""

from __future__ import annotations
