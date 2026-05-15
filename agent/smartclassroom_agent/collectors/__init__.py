"""Heartbeat 페이로드 수집기.

각 모듈은 동기 함수를 노출 — broker로 보낼 dict를 반환한다.
psutil/subprocess 같은 blocking I/O는 호출 측(heartbeat loop)에서 thread pool로 위임.
"""

from __future__ import annotations
