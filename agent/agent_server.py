"""
agent/agent_server.py

대상 서버에 설치되는 Agent.
- 시스템 리소스를 수집해 JSON 파일로 저장
- REST API 제공
    · HTTP  : 0.0.0.0:8001
    · HTTPS : 0.0.0.0:8443  (SSL)
- API 포트 : 7000 (사용 중이면 자동으로 7001)
"""

import os
import sys
import json
import ssl
import logging
import threading
from datetime import datetime
from pathlib import Path

import psutil
from flask import Flask, jsonify, request
from werkzeug.serving import make_server

# ── 경로 설정 ──────────────────────────────────────────
BASE_DIR   = Path(__file__).resolve().parent.parent
CERT_DIR   = BASE_DIR / "certs"
COMMON_DIR = BASE_DIR / "common"
sys.path.insert(0, str(BASE_DIR))

from common.port_utils import resolve_api_port

# ── 환경 변수 설정 ──────────────────────────────────────
SERVER_NAME        = os.getenv("SERVER_NAME", "agent-server")
RESOURCE_FILE_PATH = os.getenv("RESOURCE_FILE_PATH", "/tmp/server_resource.json")
HTTP_PORT          = int(os.getenv("HTTP_PORT",  "8001"))
HTTPS_PORT         = int(os.getenv("HTTPS_PORT", "8443"))
SSL_CERT           = os.getenv("SSL_CERT",  str(CERT_DIR / "server.crt"))
SSL_KEY            = os.getenv("SSL_KEY",   str(CERT_DIR / "server.key"))

# ── 로깅 ────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
)
logger = logging.getLogger("agent")

# ── API 포트 결정 ────────────────────────────────────────
API_PORT = resolve_api_port(primary=7000, fallback=7001)

# ── Flask 앱 ─────────────────────────────────────────────
app = Flask(__name__)


# ────────────────────────────────────────────────────────
# 리소스 수집
# ────────────────────────────────────────────────────────
def collect_resources() -> dict:
    """psutil 로 시스템 리소스 수집"""
    try:
        cpu = psutil.cpu_percent(interval=1)
        mem = psutil.virtual_memory()
        dsk = psutil.disk_usage("/")
        net = psutil.net_io_counters()

        return {
            "server_name": SERVER_NAME,
            "api_port":    API_PORT,
            "timestamp":   datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "cpu": {
                "usage_percent": cpu,
                "core_count":    psutil.cpu_count(),
            },
            "memory": {
                "total_gb":      round(mem.total / 1024**3, 2),
                "used_gb":       round(mem.used  / 1024**3, 2),
                "usage_percent": mem.percent,
            },
            "disk": {
                "total_gb":      round(dsk.total / 1024**3, 2),
                "used_gb":       round(dsk.used  / 1024**3, 2),
                "usage_percent": dsk.percent,
            },
            "network": {
                "bytes_sent_mb": round(net.bytes_sent / 1024**2, 2),
                "bytes_recv_mb": round(net.bytes_recv / 1024**2, 2),
            },
        }
    except Exception as e:
        logger.error(f"리소스 수집 오류: {e}")
        return None


def save_to_file(data: dict) -> bool:
    try:
        Path(RESOURCE_FILE_PATH).parent.mkdir(parents=True, exist_ok=True)
        with open(RESOURCE_FILE_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        logger.error(f"파일 저장 오류: {e}")
        return False


# ────────────────────────────────────────────────────────
# API 라우트 (포트 7000 / 7001)
# ────────────────────────────────────────────────────────
@app.route("/health", methods=["GET"])
def health():
    return jsonify({
        "status":      "healthy",
        "server_name": SERVER_NAME,
        "api_port":    API_PORT,
        "http_port":   HTTP_PORT,
        "https_port":  HTTPS_PORT,
        "timestamp":   datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    })


@app.route("/api/resource", methods=["GET"])
def get_resource():
    """실시간 리소스 수집 후 반환"""
    data = collect_resources()
    if data is None:
        return jsonify({"error": "리소스 수집 실패"}), 500
    save_to_file(data)
    return jsonify(data), 200


@app.route("/api/resource/file", methods=["GET"])
def get_resource_from_file():
    """마지막으로 저장된 리소스 파일 반환"""
    try:
        p = Path(RESOURCE_FILE_PATH)
        if not p.exists():
            return jsonify({"error": "리소스 파일 없음"}), 404
        with open(p, encoding="utf-8") as f:
            return jsonify(json.load(f)), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/port", methods=["GET"])
def get_port_info():
    """Master 가 현재 사용 중인 API 포트를 조회하는 엔드포인트"""
    return jsonify({
        "server_name": SERVER_NAME,
        "api_port":    API_PORT,
        "http_port":   HTTP_PORT,
        "https_port":  HTTPS_PORT,
    })


# ────────────────────────────────────────────────────────
# 서버 실행 헬퍼
# ────────────────────────────────────────────────────────
def _run_http():
    """HTTP 서버 (8001)"""
    logger.info(f"HTTP  서버 시작: 0.0.0.0:{HTTP_PORT}")
    srv = make_server("0.0.0.0", HTTP_PORT, app)
    srv.serve_forever()


def _run_https():
    """HTTPS 서버 (8443)"""
    if not (Path(SSL_CERT).exists() and Path(SSL_KEY).exists()):
        logger.warning(
            f"SSL 인증서를 찾을 수 없습니다 ({SSL_CERT}). "
            "HTTPS 서버를 시작하지 않습니다. "
            "certs/gen_certs.py 를 실행해 인증서를 생성하세요."
        )
        return

    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.load_cert_chain(SSL_CERT, SSL_KEY)

    logger.info(f"HTTPS 서버 시작: 0.0.0.0:{HTTPS_PORT}")
    srv = make_server("0.0.0.0", HTTPS_PORT, app, ssl_context=ctx)
    srv.serve_forever()


def _run_api():
    """API 서버 (7000 또는 7001) — 내부 Master 전용"""
    logger.info(f"API   서버 시작: 0.0.0.0:{API_PORT}  (내부 전용)")
    srv = make_server("0.0.0.0", API_PORT, app)
    srv.serve_forever()


# ────────────────────────────────────────────────────────
# 메인
# ────────────────────────────────────────────────────────
def main():
    logger.info("=" * 60)
    logger.info(f"  Agent Server: {SERVER_NAME}")
    logger.info(f"  HTTP  : 0.0.0.0:{HTTP_PORT}")
    logger.info(f"  HTTPS : 0.0.0.0:{HTTPS_PORT}")
    logger.info(f"  API   : 0.0.0.0:{API_PORT}")
    logger.info("=" * 60)

    # 초기 리소스 수집 & 파일 저장
    data = collect_resources()
    if data:
        save_to_file(data)
        logger.info("초기 리소스 수집 완료")

    # 세 개의 포트를 각각 별도 스레드에서 실행
    threads = [
        threading.Thread(target=_run_http,  daemon=True, name="http"),
        threading.Thread(target=_run_https, daemon=True, name="https"),
        threading.Thread(target=_run_api,   daemon=True, name="api"),
    ]

    for t in threads:
        t.start()

    logger.info("모든 서버가 기동되었습니다. 종료하려면 Ctrl+C")
    try:
        for t in threads:
            t.join()
    except KeyboardInterrupt:
        logger.info("Agent 서버 종료")


if __name__ == "__main__":
    main()
