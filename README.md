# CollectorSystem

Master-Agent 구조로 여러 서버의 리소스를 수집하고 Excel 로 저장하는 모니터링 시스템.

## 포트 구성

| 역할 | 포트 | 프로토콜 |
|------|------|---------|
| 웹 대시보드 (HTTP) | **8001** | HTTP |
| 웹 대시보드 (HTTPS) | **8443** | HTTPS / SSL |
| 내부 API (기본) | **7000** | HTTP |
| 내부 API (충돌 시 자동 전환) | **7001** | HTTP |

> `7000` 포트가 이미 사용 중이면 Agent/Master 모두 자동으로 `7001`로 전환됩니다.

---

## 아키텍처

```
┌───────────────────────────────────────────────────────────┐
│  Master Server                                            │
│                                                           │
│  :8001 (HTTP)  ─┐                                        │
│  :8443 (HTTPS) ─┤─ Flask 대시보드                        │
│  :7000 or 7001 ─┘─ 내부 API (자동 선택)                  │
│                                                           │
│  ResourceCollector                                        │
│  └─ detect_agent_port()  ← 7000/7001 자동 탐지           │
│  └─ collect_all()        ← 전체 Agent 수집               │
│  └─ save_excel()         ← reports/*.xlsx                │
│  └─ schedule (5분마다)                                    │
└──────────────────┬────────────────────────────────────────┘
                   │  GET /api/resource (7000 or 7001)
          ┌────────┼────────┬────────────┐
          │        │        │            │
    ┌─────▼──┐ ┌───▼───┐ ┌──▼────┐ ┌───▼────┐
    │Agent 1 │ │Agent 2│ │Agent 3│ │Agent N │
    │        │ │       │ │       │ │        │
    │:8001   │ │:8001  │ │:8001  │ │:8001   │
    │:8443   │ │:8443  │ │:8443  │ │:8443   │
    │:7000↗  │ │:7000↗ │ │:7000↗ │ │:7000↗  │
    │ or7001 │ │ or7001│ │ or7001│ │ or7001 │
    └────────┘ └───────┘ └───────┘ └────────┘
```

## 포트 자동 감지 흐름

```
Agent 시작
    │
    ├─ 7000 포트 여유? ──YES──> API 포트 = 7000
    │
    └─ NO
         └─ 7001 포트 여유? ──YES──> API 포트 = 7001
                   │
                   └─ NO → RuntimeError (관리자 확인 필요)

Master 수집 시
    │
    ├─ GET {host}:7000/api/port 시도 → 성공? → 해당 포트 사용
    └─ 실패 → GET {host}:7001/api/port 시도
```

## 설치

```bash
git clone https://github.com/park-soonho/CollectorSystem.git
cd CollectorSystem
pip install -r requirements.txt
```

## SSL 인증서 생성 (개발/테스트용)

```bash
python certs/gen_certs.py
```

운영 환경에서는 Let's Encrypt 또는 CA 발급 인증서를 사용하세요.

## Agent 실행 (각 대상 서버)

```bash
cd agent
cp .env.example .env
vi .env             # SERVER_NAME 등 수정

python agent_server.py
```

로그 출력 예시:
```
2024-01-01 12:00:00 [INFO] agent - API 포트: 7000 (기본)
2024-01-01 12:00:00 [INFO] agent - HTTP  서버 시작: 0.0.0.0:8001
2024-01-01 12:00:00 [INFO] agent - HTTPS 서버 시작: 0.0.0.0:8443
2024-01-01 12:00:00 [INFO] agent - API   서버 시작: 0.0.0.0:7000
```

7000이 사용 중인 경우:
```
2024-01-01 12:00:00 [WARNING] - 포트 7000 사용 중 → 7001 로 전환
2024-01-01 12:00:00 [INFO] agent - API   서버 시작: 0.0.0.0:7001
```

## Master 실행 (중앙 수집 서버)

`master/master_server.py` 의 `AGENT_SERVERS` 목록 수정:

```python
AGENT_SERVERS = [
    {"name": "web-server-1", "host": "http://192.168.1.10"},
    {"name": "db-server-1",  "host": "http://192.168.1.20"},
]
```

```bash
cd master
cp .env.example .env
python master_server.py
```

대시보드 접속:
- HTTP  : http://서버IP:8001
- HTTPS : https://서버IP:8443

## API 엔드포인트

### Agent (:7000 or :7001)

| Method | Path | 설명 |
|--------|------|------|
| GET | `/health` | 헬스 체크 |
| GET | `/api/resource` | 실시간 리소스 수집 |
| GET | `/api/resource/file` | 저장된 리소스 파일 반환 |
| GET | `/api/port` | 현재 사용 포트 정보 |

### Master (:8001 / :8443)

| Method | Path | 설명 |
|--------|------|------|
| GET | `/` | 웹 대시보드 |
| GET | `/api/status` | Master 상태 |
| GET | `/api/resources` | 최신 수집 데이터 |

## systemd 서비스 등록

```bash
# Agent 서버
sudo cp agent/collector-agent.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable collector-agent
sudo systemctl start collector-agent

# Master 서버
sudo cp master/collector-master.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable collector-master
sudo systemctl start collector-master
```

## 테스트

```bash
pip install pytest
pytest tests/
```

## 디렉토리 구조

```
CollectorSystem/
├── agent/
│   ├── agent_server.py          # Agent 메인
│   ├── .env.example
│   └── collector-agent.service
├── master/
│   ├── master_server.py         # Master 메인
│   ├── .env.example
│   └── collector-master.service
├── common/
│   ├── __init__.py
│   └── port_utils.py            # 포트 자동 감지
├── certs/
│   └── gen_certs.py             # 자체서명 인증서 생성
├── reports/                     # Excel 결과 파일
├── tests/
│   └── test_port_utils.py
├── requirements.txt
├── .gitignore
└── README.md
```
