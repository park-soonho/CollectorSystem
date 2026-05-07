#!/usr/bin/env python3
"""
gen_certs.py - 개발/테스트용 자체서명(Self-Signed) SSL 인증서 생성
운영 환경에서는 Let's Encrypt 또는 CA 발급 인증서를 사용하세요.
"""

import subprocess
import os
import sys

CERT_DIR = os.path.join(os.path.dirname(__file__), "../certs")


def generate_self_signed_cert():
    os.makedirs(CERT_DIR, exist_ok=True)
    key_file  = os.path.join(CERT_DIR, "server.key")
    cert_file = os.path.join(CERT_DIR, "server.crt")

    if os.path.exists(key_file) and os.path.exists(cert_file):
        print(f"[INFO] 인증서가 이미 존재합니다: {CERT_DIR}")
        return key_file, cert_file

    print("[INFO] 자체서명 SSL 인증서 생성 중...")
    cmd = [
        "openssl", "req", "-x509",
        "-newkey", "rsa:4096",
        "-keyout", key_file,
        "-out",    cert_file,
        "-days",   "365",
        "-nodes",
        "-subj",   "/C=KR/ST=Seoul/L=Seoul/O=CollectorSystem/CN=localhost",
        "-addext", "subjectAltName=IP:0.0.0.0,IP:127.0.0.1,DNS:localhost"
    ]

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"[ERROR] openssl 실패:\n{result.stderr}", file=sys.stderr)
        sys.exit(1)

    print(f"[OK] 인증서 생성 완료")
    print(f"     KEY : {key_file}")
    print(f"     CERT: {cert_file}")
    return key_file, cert_file


if __name__ == "__main__":
    generate_self_signed_cert()
