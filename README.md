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

## 시스템 아키텍처

### 전체 구성도

```
┌─────────────────────────────────────────────────────────────────────┐
│                        MASTER SERVER                                │
│                                                                     │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │  웹 대시보드 & API                                            │  │
│  │  • HTTP  :8001  • HTTPS :8443                                │  │
│  │  • API   :7000 (기본) / :7001 (충돌 시 자동 전환)             │  │
│  └──────────────────────────────────────────────────────────────┘  │
│                                                                     │
│  ┌─────────────────────┐  ┌────────────────────────────────────┐  │
│  │ ResourceCollector   │  │ Ansible Automation                 │  │
│  │                     │  │                                    │  │
│  │ • detect_agent_port │  │ • SSH 키 기반 접속                 │  │
│  │ • collect_all       │  │ • Agent 배포 (agent_server.py)    │  │
│  │ • save_excel        │  │ • 원격 명령 실행                   │  │
│  │ • schedule (5분)    │  │ • OS/라이브러리 버전 수집          │  │
│  │                     │  │ • 취약점 정보 수집                 │  │
│  └─────────────────────┘  └────────────────────────────────────┘  │
│                                                                     │
└──────┬──────────────────────────────────┬───────────────────────────┘
       │                                  │
       │ HTTP GET /api/resource           │ SSH (ansible/ssh-keygen)
       │ :7000 or :7001                   │ • agent 배포
       │                                  │ • 명령어 실행
       │                                  │ • 정보 수집
       │                                  │
  ┌────┴─────┬─────────┬─────────┬────────┴──┐
  │          │         │         │           │
┌─▼────┐ ┌──▼───┐ ┌───▼──┐ ┌───▼───┐ ┌────▼─────┐
│Agent1│ │Agent2│ │Agent3│ │Agent4 │ │ Agent N  │
│      │ │      │ │      │ │       │ │          │
│:8001 │ │:8001 │ │:8001 │ │:8001  │ │ :8001    │
│:8443 │ │:8443 │ │:8443 │ │:8443  │ │ :8443    │
│:7000 │ │:7000 │ │:7001↑│ │:7000  │ │ :7000    │
│      │ │      │ │      │ │       │ │          │
│Flask │ │Flask │ │Flask │ │Flask  │ │ Flask    │
│API   │ │API   │ │API   │ │API    │ │ API      │
│      │ │      │ │      │ │       │ │          │
│psutil│ │psutil│ │psutil│ │psutil │ │ psutil   │
│수집  │ │수집  │ │수집  │ │수집   │ │ 수집     │
└──────┘ └──────┘ └──────┘ └───────┘ └──────────┘
```

### Master 서버 주요 기능

**1. 리소스 모니터링 (ResourceCollector)**
- 5분마다 자동 수집 (schedule)
- Agent 포트 자동 탐지 (7000 → 7001)
- Excel 파일 날짜별 누적 저장
- 웹 대시보드 실시간 표시

**2. Ansible 자동화**
- SSH 키 기반 무인증 접속 (ssh-keygen)
- Agent 자동 배포 (`agent_server.py`)
- 원격 명령어 실행
- 서버 정보 수집:
  - OS 버전 및 패치 정보
  - 설치된 라이브러리 목록
  - 보안 취약점 정보
  - 시스템 설정 정보

> **주의**: Ansible은 **수집 전용**이며 실시간 모니터링은 하지 않습니다.

### Agent 서버 기능

**리소스 수집**
- CPU 사용률 / 코어수
- 메모리 전체/사용/사용률
- 디스크 전체/사용/사용률
- 네트워크 송신/수신

**API 제공**
- HTTP  :8001
- HTTPS :8443
- API   :7000 (충돌 시 :7001 자동 전환)

**로컬 저장**
- JSON 파일: `/tmp/server_resource.json`
- psutil 기반 실시간 수집

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

## 데이터 흐름

### 1. 리소스 모니터링 흐름
```
┌─────────┐     ┌──────┐     ┌─────────┐     ┌────────┐     ┌──────────┐     ┌──────┐
│ psutil  │ --> │ JSON │ --> │Flask API│ --> │ Master │ --> │DataFrame │ --> │Excel │
│ (Agent) │     │ 파일 │     │:7000/01 │     │requests│     │ (pandas) │     │누적  │
└─────────┘     └──────┘     └─────────┘     └────────┘     └──────────┘     └──────┘
                                                                  │
                                                                  v
                                                            ┌──────────┐
                                                            │Dashboard │
                                                            │:8001/8443│
                                                            └──────────┘

• 주기: 5분마다 자동 실행 (schedule)
• 타임아웃: 10초
• 저장: reports/server_resources_YYYYMMDD.xlsx (날짜별 누적)
```

### 2. Ansible 배포/수집 흐름
```
┌────────┐     ┌─────────┐     ┌──────────┐     ┌─────────┐
│ Master │ --> │SSH 접속 │ --> │ Ansible  │ --> │ Agent   │
│        │     │ssh-keygen    │ Playbook │     │ 서버    │
└────────┘     └─────────┘     └──────────┘     └─────────┘
                                      │
                    ┌─────────────────┼──────────────────┐
                    │                 │                  │
              ┌─────v─────┐    ┌─────v──────┐    ┌──────v──────┐
              │ Agent 배포│    │ 명령어 실행│    │ 정보 수집   │
              │ (deploy)  │    │ (command)  │    │ (gather)    │
              └───────────┘    └────────────┘    └─────────────┘
                                                        │
                                    ┌───────────────────┼───────────────────┐
                                    │                   │                   │
                              ┌─────v──────┐    ┌──────v──────┐    ┌───────v────────┐
                              │OS 버전     │    │라이브러리   │    │보안 취약점     │
                              │패치 정보   │    │설치 목록    │    │시스템 설정     │
                              └────────────┘    └─────────────┘    └────────────────┘

• 방식: SSH 키 기반 무인증 접속
• 배포: agent_server.py 자동 설치
• 수집: 시스템 정보, 패키지, 취약점 (모니터링 X)
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
│   ├── master_server.py         # Master 메인 (리소스 수집)
│   ├── ansible/                 # Ansible 자동화
│   │   ├── playbooks/           # 배포/수집 플레이북
│   │   ├── inventory/           # Agent 서버 목록
│   │   └── roles/               # 역할별 태스크
│   ├── .env.example
│   └── collector-master.service
├── common/
│   ├── __init__.py
│   └── port_utils.py            # 포트 자동 감지
├── certs/
│   └── gen_certs.py             # 자체서명 인증서 생성
├── reports/                     # Excel 결과 파일
├── docs/
│   └── architecture.html        # 아키텍처 다이어그램
├── tests/
│   └── test_port_utils.py
├── requirements.txt
├── .gitignore
└── README.md
```
