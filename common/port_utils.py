"""
port_utils.py - 포트 사용 여부 감지 및 자동 할당 유틸리티
Agent / Master 공통 사용
"""

import socket
import logging

logger = logging.getLogger(__name__)


def is_port_in_use(port: int, host: str = "0.0.0.0") -> bool:
    """해당 포트가 현재 사용 중인지 확인"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            s.bind((host, port))
            return False  # 바인딩 성공 = 포트 미사용
        except OSError:
            return True   # 바인딩 실패 = 포트 사용 중


def resolve_api_port(primary: int = 7000, fallback: int = 7001) -> int:
    """
    API 포트 결정:
    primary(7000) 사용 가능 → 7000
    사용 중              → fallback(7001)
    """
    if not is_port_in_use(primary):
        logger.info(f"API 포트: {primary} (기본)")
        return primary

    logger.warning(f"포트 {primary} 사용 중 → {fallback} 로 전환")
    if not is_port_in_use(fallback):
        return fallback

    raise RuntimeError(
        f"포트 {primary}, {fallback} 모두 사용 중입니다. "
        "환경을 확인하고 포트를 확보해주세요."
    )
