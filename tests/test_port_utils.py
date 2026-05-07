"""
tests/test_port_utils.py
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from common.port_utils import is_port_in_use, resolve_api_port


def test_is_port_in_use_free():
    # 99999 는 사용 중일 가능성이 없음
    assert is_port_in_use(99999) is False


def test_resolve_returns_primary_when_free():
    port = resolve_api_port(primary=19999, fallback=19998)
    assert port == 19999


def test_resolve_fallback(monkeypatch):
    """primary 가 사용 중인 상황 시뮬레이션"""
    call_count = {"n": 0}

    def fake_in_use(port):
        call_count["n"] += 1
        return port == 19999   # primary 만 사용 중

    monkeypatch.setattr("common.port_utils.is_port_in_use", fake_in_use)
    port = resolve_api_port(primary=19999, fallback=19998)
    assert port == 19998
