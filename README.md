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
│  │ • save_to_db ◄──┐   │  │ • OS/라이브러리 버전 수집 ─────┐   │  │
│  │ • schedule (5분)│   │  │ • 취약점 정보 수집            │   │  │
│  └─────────────────┼───┘  └───────────────────────────────┼───┘  │
│                    │                                      │        │
│  ┌─────────────────▼──────────────────────────────────────▼────┐  │
│  │  PostgreSQL Writer (psycopg2 / SQLAlchemy)                  │  │
│  │                                                              │  │
│  │  • Agent 리소스 데이터 INSERT (5분마다)                      │  │
│  │    └─> resource_metrics 테이블                              │  │
│  │                                                              │  │
│  │  • Ansible 수집 데이터 INSERT (실행 시)                     │  │
│  │    └─> ansible_collected 테이블                             │  │
│  │                                                              │  │
│  │  • 수집 히스토리 INSERT                                      │  │
│  │    └─> collection_history 테이블                            │  │
│  │                                                              │  │
│  │  • 트랜잭션 관리 & 에러 처리                                 │  │
│  └──────────────────────────┬───────────────────────────────────┘  │
│                             │                                      │
└───────┬─────────────────────┼────────────────────┬─────────────────┘
        │                     │                    │
        │ HTTP                │ SQL INSERT         │ SSH (ansible)
        │ :7000/7001          │ :15432             │
        │                     │                    │
   ┌────┴─────┬───────────────┼─────┬─────────┬───┴──┐
   │          │               │     │         │      │
┌──▼───┐ ┌───▼──┐ ┌──────────▼┐ ┌──▼───┐ ┌───▼──┐ ┌▼─────┐
│Agent1│ │Agent2│ │  Agent3   │ │Agent4│ │AgentN│ │ ... │
│      │ │      │ │           │ │      │ │      │ │     │
│:8001 │ │:8001 │ │   :8001   │ │:8001 │ │:8001 │ │:8001│
│:8443 │ │:8443 │ │   :8443   │ │:8443 │ │:8443 │ │:8443│
│:7000 │ │:7000 │ │   :7001↑  │ │:7000 │ │:7000 │ │:7000│
│      │ │      │ │           │ │      │ │      │ │     │
│Flask │ │Flask │ │   Flask   │ │Flask │ │Flask │ │Flask│
│API   │ │API   │ │   API     │ │API   │ │API   │ │API  │
│      │ │      │ │           │ │      │ │      │ │     │
│psutil│ │psutil│ │   psutil  │ │psutil│ │psutil│ │psutl│
│리소스│ │리소스│ │   리소스  │ │리소스│ │리소스│ │리소스│
└──┬───┘ └───┬──┘ └─────┬─────┘ └───┬──┘ └───┬──┘ └──┬──┘
   │         │          │           │        │       │
   └─────────┴──────────┴───────────┴────────┴───────┘
                        │
                        │ PostgreSQL :15432
                   ┌────▼──────────────────────────────────┐
                   │  PostgreSQL Database                  │
                   │  PORT: 15432                          │
                   │                                       │
                   │  ┌──────────────────────────────────┐ │
                   │  │ resource_metrics                 │ │
                   │  │ ─────────────────────────────    │ │
                   │  │ Agent에서 수집한 리소스 메트릭    │ │
                   │  │                                  │ │
                   │  │ • server_name  (서버 식별)       │ │
                   │  │ • timestamp    (수집 시각)       │ │
                   │  │ • cpu_usage    (CPU 사용률)      │ │
                   │  │ • memory_usage (메모리)          │ │
                   │  │ • disk_usage   (디스크)          │ │
                   │  │ • network_io   (네트워크)        │ │
                   │  │                                  │ │
                   │  │ INSERT: 5분마다 (schedule)       │ │
                   │  └──────────────────────────────────┘ │
                   │                                       │
                   │  ┌──────────────────────────────────┐ │
                   │  │ ansible_collected                │ │
                   │  │ ─────────────────────────────    │ │
                   │  │ Ansible로 수집한 시스템 정보     │ │
                   │  │                                  │ │
                   │  │ • server_name     (서버 식별)    │ │
                   │  │ • os_version      (OS 버전)      │ │
                   │  │ • kernel_version  (커널)         │ │
                   │  │ • libraries       (라이브러리)   │ │
                   │  │ • vulnerabilities (취약점)       │ │
                   │  │ • packages        (패키지)       │ │
                   │  │ • system_info     (시스템 설정)  │ │
                   │  │                                  │ │
                   │  │ INSERT: Ansible 실행 시          │ │
                   │  └──────────────────────────────────┘ │
                   │                                       │
                   │  ┌──────────────────────────────────┐ │
                   │  │ collection_history               │ │
                   │  │ ─────────────────────────────    │ │
                   │  │ 수집 작업 히스토리               │ │
                   │  │                                  │ │
                   │  │ • id              (작업 ID)      │ │
                   │  │ • run_time        (실행 시각)    │ │
                   │  │ • success_count   (성공 수)      │ │
                   │  │ • failed_servers  (실패 목록)    │ │
                   │  │ • duration_sec    (소요 시간)    │ │
                   │  │                                  │ │
                   │  │ INSERT: 수집 작업 완료 시        │ │
                   │  └──────────────────────────────────┘ │
                   └───────────────────────────────────────┘
```

### Master 서버 주요 기능

**1. 리소스 모니터링 (ResourceCollector)**
- 5분마다 자동 수집 (schedule)
- Agent 포트 자동 탐지 (7000 → 7001)
- **Excel 파일 날짜별 누적 저장**
- **PostgreSQL DB 저장 (실시간 INSERT :15432)**
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
- **수집 데이터 PostgreSQL 저장 (:15432)**

**3. 데이터베이스 저장 (PostgreSQL :15432)**
- **Agent 리소스 메트릭**: `resource_metrics` 테이블 (5분마다)
- **Ansible 수집 정보**: `ansible_collected` 테이블 (실행 시)
- **수집 히스토리**: `collection_history` 테이블 (작업 완료 시)
- 장기 트렌드 분석 가능
- 쿼리 기반 리포팅

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

### 1. 리소스 모니터링 흐름 (Agent → PostgreSQL)
```
┌─────────┐     ┌──────┐     ┌─────────┐     ┌────────┐     ┌──────────┐
│ psutil  │ --> │ JSON │ --> │Flask API│ --> │ Master │ --> │DataFrame │
│ (Agent) │     │ 파일 │     │:7000/01 │     │requests│     │ (pandas) │
└─────────┘     └──────┘     └─────────┘     └────────┘     └─────┬────┘
                                                                   │
                        ┌──────────────────────────────────────────┼──────────────┐
                        │                                          │              │
                   ┌────▼─────────────────┐                 ┌──────▼──────┐  ┌───▼────────┐
                   │ PostgreSQL :15432    │                 │Excel 파일   │  │ Dashboard  │
                   │                      │                 │날짜별 누적  │  │ :8001/8443 │
                   │ resource_metrics     │                 │ (openpyxl)  │  │ (실시간)   │
                   │ ─────────────────    │                 └─────────────┘  └────────────┘
                   │ INSERT               │
                   │ • server_name        │
                   │ • timestamp          │
                   │ • cpu_usage          │
                   │ • memory_*           │
                   │ • disk_*             │
                   │ • network_*          │
                   │                      │
                   │ psycopg2 / SQLAlchemy│
                   └──────────────────────┘

• 주기: 5분마다 자동 실행 (schedule)
• 타임아웃: 10초
• 저장: 
  - PostgreSQL :15432 → resource_metrics 테이블 (시계열)
  - Excel: reports/server_resources_YYYYMMDD.xlsx (날짜별 누적)
  - Dashboard: 메모리 캐시 (최신 데이터)
```

### 2. Ansible 배포/수집 흐름 (Ansible → PostgreSQL)
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
              └───────────┘    └────────────┘    └──────┬──────┘
                                                         │
                                    ┌────────────────────┼──────────────────┐
                                    │                    │                  │
                              ┌─────v──────┐    ┌───────v──────┐    ┌──────v─────────┐
                              │OS 버전     │    │라이브러리    │    │보안 취약점     │
                              │패치 정보   │    │설치 목록     │    │시스템 설정     │
                              └─────┬──────┘    └───────┬──────┘    └──────┬─────────┘
                                    │                   │                  │
                                    └───────────────────┼──────────────────┘
                                                        │
                                                ┌───────▼──────────────────┐
                                                │ Master                   │
                                                │ PostgreSQL Writer        │
                                                └───────┬──────────────────┘
                                                        │
                                                ┌───────▼──────────────────┐
                                                │ PostgreSQL :15432        │
                                                │                          │
                                                │ ansible_collected        │
                                                │ ──────────────────       │
                                                │ INSERT                   │
                                                │ • server_name            │
                                                │ • os_version             │
                                                │ • kernel_version         │
                                                │ • libraries (JSONB)      │
                                                │ • vulnerabilities (JSONB)│
                                                │ • packages (JSONB)       │
                                                │ • system_info (JSONB)    │
                                                │ • collected_at           │
                                                │                          │
                                                │ psycopg2 / SQLAlchemy    │
                                                └──────────────────────────┘

• 방식: SSH 키 기반 무인증 접속
• 배포: agent_server.py 자동 설치
• 수집: 시스템 정보, 패키지, 취약점 (모니터링 X)
• 저장: PostgreSQL :15432 → ansible_collected 테이블
• 형식: JSONB 컬럼 활용 (라이브러리, 취약점, 패키지 등)
```

### 3. PostgreSQL 데이터베이스 스키마 (PORT: 15432)

```sql
-- ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
-- 연결 정보
-- ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
-- Host: localhost (또는 Master 서버 IP)
-- Port: 15432
-- Database: collector_db
-- User: collector_user
-- ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

-- ┌─────────────────────────────────────────────────────────┐
-- │ 1. Agent 리소스 메트릭 (5분마다 INSERT)                 │
-- └─────────────────────────────────────────────────────────┘
CREATE TABLE resource_metrics (
    id              SERIAL PRIMARY KEY,
    server_name     VARCHAR(100) NOT NULL,
    api_port        INTEGER,
    timestamp       TIMESTAMP NOT NULL,
    
    -- CPU
    cpu_usage       FLOAT,
    cpu_cores       INTEGER,
    
    -- Memory
    memory_total_gb FLOAT,
    memory_used_gb  FLOAT,
    memory_percent  FLOAT,
    
    -- Disk
    disk_total_gb   FLOAT,
    disk_used_gb    FLOAT,
    disk_percent    FLOAT,
    
    -- Network
    net_sent_mb     FLOAT,
    net_recv_mb     FLOAT,
    
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 인덱스 (서버별 시계열 조회 최적화)
CREATE INDEX idx_resource_server_time 
    ON resource_metrics(server_name, timestamp DESC);

-- 인덱스 (CPU 임계값 조회)
CREATE INDEX idx_resource_cpu 
    ON resource_metrics(cpu_usage) 
    WHERE cpu_usage > 80;


-- ┌─────────────────────────────────────────────────────────┐
-- │ 2. Ansible 수집 데이터 (Ansible 실행 시 INSERT)         │
-- └─────────────────────────────────────────────────────────┘
CREATE TABLE ansible_collected (
    id              SERIAL PRIMARY KEY,
    server_name     VARCHAR(100) NOT NULL,
    
    -- OS 정보
    os_version      TEXT,
    kernel_version  TEXT,
    
    -- JSON 형식 데이터
    libraries       JSONB,           -- 설치된 라이브러리 목록
                                     -- 예: {"python": ["requests", "flask"], "apt": ["nginx"]}
    
    vulnerabilities JSONB,           -- 취약점 정보
                                     -- 예: [{"cve": "CVE-2024-1234", "severity": "HIGH"}]
    
    packages        JSONB,           -- 패키지 정보
                                     -- 예: {"nginx": "1.18.0", "python3": "3.9.2"}
    
    system_info     JSONB,           -- 기타 시스템 정보
                                     -- 예: {"firewall": "active", "selinux": "enforcing"}
    
    collected_at    TIMESTAMP NOT NULL,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 인덱스 (서버별 최신 데이터 조회)
CREATE INDEX idx_ansible_server 
    ON ansible_collected(server_name, collected_at DESC);

-- 인덱스 (JSONB 검색 - 취약점)
CREATE INDEX idx_ansible_vuln 
    ON ansible_collected USING GIN (vulnerabilities);


-- ┌─────────────────────────────────────────────────────────┐
-- │ 3. 수집 히스토리 (수집 작업 완료 시 INSERT)              │
-- └─────────────────────────────────────────────────────────┘
CREATE TABLE collection_history (
    id              SERIAL PRIMARY KEY,
    run_time        TIMESTAMP NOT NULL,
    collection_type VARCHAR(50),     -- 'resource' 또는 'ansible'
    total_servers   INTEGER,
    success_count   INTEGER,
    failed_count    INTEGER,
    failed_servers  TEXT[],          -- 실패한 서버 목록
    duration_sec    FLOAT,
    error_log       TEXT,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 인덱스 (시간순 조회)
CREATE INDEX idx_history_time 
    ON collection_history(run_time DESC);
```

### 4. PostgreSQL 연결 설정

**환경변수 (.env)**
```bash
# PostgreSQL 연결 정보
DB_HOST=localhost
DB_PORT=15432
DB_NAME=collector_db
DB_USER=collector_user
DB_PASSWORD=your_secure_password

# 연결 풀 설정
DB_POOL_SIZE=5
DB_MAX_OVERFLOW=10
```

**Python 연결 예시 (SQLAlchemy)**
```python
from sqlalchemy import create_engine
from sqlalchemy.pool import QueuePool

DATABASE_URL = f"postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

engine = create_engine(
    DATABASE_URL,
    poolclass=QueuePool,
    pool_size=5,
    max_overflow=10,
    pool_pre_ping=True  # 연결 유효성 체크
)
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
