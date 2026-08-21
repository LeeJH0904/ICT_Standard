# 스마트팜 상호운용 표준 참조 구현

> **2026 ICT 표준 챌린지 공모전(TTA) 출품작.**
> 이 저장소는 스마트팜 **앱**이 아니라, **TTA 표준 3종의 참조 구현(reference implementation)이자 상호운용성 검증 도구**다.
서로 다른 MCU 3종이 동일한 표준 프로토콜로 혼용 동작하고, 하드웨어 없이도 표준 준수를 기계로 검증할 수 있음을 증명하는 것이 목적이다.

---

## 1. 적용 표준

| 표준번호 | 범위 | 구현 위치 |
|---|---|---|
| `TTAK.KO-10.0943` | 노드↔제어기 바이너리 프로토콜 (SIAP) | `project_code/firmware/` · `project_code/siap/` |
| `TTAK.KO-10.1369-Part1` | 데이터 요구사항 · ER 참조모델 | `project_code/backend/models.py` · `schema.sql` |
| `TTAK.KO-10.0937` | 클라우드 서비스 요구사항 (**선택 적용 — §1.1**) | `project_code/backend/services/` |

표준에서 유래한 상수·로직에는 조항 번호가 주석으로 달려 있고, 테스트 함수명에도
조항 번호가 들어 있어(예: `test_invalid_format_7_3_1`) 심사자가 테스트 목록만으로
준수 항목을 확인할 수 있다.

### 1.1 `TTAK.KO-10.0937` 적용 범위 (선택 적용)

이 참조 구현은 0937 클라우드 서비스 요구사항 중 **상호운용성 검증과 데모에 필요한 핵심 흐름**을 선택 적용한다.
아래 표가 적용·미적용 범위를 밝힌다 — 미적용 항목은 설계상 의도된 후속 과제이며,
미적용을 밝히지 않아 전체 준수로 오인되지 않도록 여기 공개한다.

| 0937 조항 | 서비스 | 적용 | 미적용(후속 과제) |
|---|---|---|---|
| 6.1 | EMS 장치관리 | 장치 등록·변경·연결·조회 | **삭제/논리적 폐기** |
| 6.2 | DMS 데이터관리 | 수집 데이터 등록·연결·조회 | **수정·삭제** — 불변 감사 이력을 택한 설계 결정 |
| 6.3 | MMS 모델관리 | 시드 모델 조회·실행 + 제어 규칙 초안·**사람 승인** 흐름 | **모델 등록·수정 API · 데이터 접근 인증·인가 · 개발자·서비스별 호출·전송량 집계** |
| — | FMS · FCS | 온실·구동 제어 및 승인 게이트 흐름 | — |
| — | FOS | — | **범위 외** |

> - `MMS`의 `X-User-Id` 헤더는 **인증이 아니라** DB 사용자 실재 확인이다 — 외부 신원을 보장하지 않는다.
> - 위 미적용 항목은 표준 위반이 아니라 **범위 선언**이다. 적용한 흐름은 §5의 테스트와 화면(기능 1~3)으로 재현·확인할 수 있다.

---

## 2. 빠른 시작 (오프라인 · 3단계)

### ① 오프라인 설치 (동봉된 wheels/ 사용, 네트워크 불필요)

```bash
python -m venv .venv
# Windows:  .venv\Scripts\activate     |  Linux/macOS:  source .venv/bin/activate

pip install -r project_code/requirements.txt --no-index --find-links project_code/wheels/
```

직접 의존성은 `fastapi` · `uvicorn` · `pyserial` 3개 뿐이며, 전이 의존성까지
플랫폼별 바이너리 휠이 `project_code/wheels/`에 들어 있다.

### ② 실행 (가상 노드 + 웹 대시보드)

```bash
python project_code/run.py --mode simulate --serve
```

실행되면 브라우저에서 **http://127.0.0.1:8000/** 을 연다.

### ③ 화면 확인

| 경로 | 화면 | 기능 |
|---|---|---|
| `/index.html` | 노드·디바이스 실시간 대시보드 | 등록 노드와 최근 수신값 (기능 1) |
| `/verify.html` | 표준 준수 검증 | 프레임 주입 → 위반 판정·근거 조항 표시 (기능 2) |
| `/rules.html` | 규칙·승인 | 공공데이터 → 규칙 초안 생성 → 사람 승인 게이트 → 구동 (기능 3) |
| `/settings.html` | 설정 | 노드·임계값 설정 |

> 웹은 외부 CDN·번들러 없이 순수 바닐라 JS로 되어 있어 오프라인에서 그대로 뜬다.

---

## 3. 실행 모드

전송 계층 한 곳만 교체하면 하드웨어 없이 동일 코드가 동작한다.

```bash
# 실측 로그 재생 (기본) — project_code/logs/*.jsonl 의 실측 프레임을 그대로 재생
python project_code/run.py --mode replay --serve

# 가상 노드 (양방향, 제어 명령 수신) — 데모·개발 기본 경로
python project_code/run.py --mode simulate --serve

# 실제 하드웨어 (보드 연결 시)
python project_code/run.py --mode hardware --port COM6 --serve
```

### 주요 옵션:
`--serve`                                      (REST+웹 기동, 미지정 시 관측만 하고 종료)
`--http-port 8000`                             (포트 지정)
`--mode {replay,simulate,hardware}`            (실행 모드 지정)
`--proto {strict,extended}`
`--db <경로>`                                  (없으면 `schema.sql`+`fixtures/seed.sql`로 새로 생성)
`--capture <경로>`                             (수신·송신 프레임을 jsonl로 실측 캡처).

---

## 4. 공공데이터 활용 (기상청 단기예보 API)

공공데이터가 **표시**에 그치지 않고 표준 서비스의 **제어 판단을 위한 규칙 생성의 보조 기준**으로 활용된다.


### API 신청 항목
기상청 API 허브 -> 에특보 -> 단기예보 -> 4.3 단기예보조회 -> API 활용 신청


```
기상청 단기예보 API    ──▶    public_data_record (1369-P1 데이터모델)
(키 부재 시 목업 폴백)                │
                                      ▼
                        MMS 고온 경보 (0937 6.3)     ──▶   규칙 초안 생성
                        예보 최고기온(TMX) vs 작물 임계값       │
                                                                ▼
                                                         사람 승인 게이트 ──▶ 구동
```

- **수집**: `backend/services/dms.py` — 환경변수 `KMA_API_KEY`가 있으면 기상청 단기예보조회서비스(VilageFcstInfoService_2.0) 실 API를 호출하고,
없거나 실패하면 `fixtures/kma_forecast_mock.json`으로 **자동 폴백**한다 (오프라인 기본 경로).

- **저장**: `public_data_source` · `public_data_record` 테이블(표준 데이터모델).

- **활용**: `backend/services/mms.py`가 예보 최고기온을 작물별 임계값과 비교해 고온 경보와 제어 권고 초안을 만든다.

- **노출**: `GET /api/v1/publicdata/sources` · `GET /api/v1/publicdata/records`, 화면은 `rules.html`.


> 목업 값은 무작위·주기함수로 생성하지 않고 손으로 고정한 실제 응답 구조다 (합성 데이터 금지 원칙 준수).

### 4.1 생성형 AI 규칙 초안 — 선택적 OpenAI 연동

AI 기능은 OpenAI Responses API 를 사용한다. 
실제 AI 호출은 선택 사항이며, 키·모델 부재나 통신·응답 검증 실패 시 기존 임계값 초안으로 자동 전환한다.

```powershell
Copy-Item project_code/.env.example project_code/.env
notepad project_code/.env
python project_code/run.py --mode simulate --serve
```

`.env`에는 다음 다섯 항목만 입력할 수 있다.

- `KMA_API_KEY`: 기상청 실데이터 호출용. `https://apihub.kma.go.kr`에서 키 발급 후 입력.
- `OPENAI_API_KEY`와 `OPENAI_MODEL`: 실제 OpenAI 호출 시 필수다.
- `OPENAI_BASE_URL`: 기본값은 `https://api.openai.com/v1`이며 HTTPS만 허용한다.
- `OPENAI_TIMEOUT_SEC`: 기본값은 8초이고 1~30초 범위만 사용한다.
- `run.py`는 현재 작업 디렉터리와 무관하게 `project_code/.env`를 자동으로 읽는다.
  같은 이름의 프로세스 환경변수가 있으면 그 값을 우선하며, 빈 값은 미설정으로 본다.


상세 검증 방식은 `docs/ai-usage.md`, 실제/오프라인 시연 순서는 `docs/AI_규칙_초안_시연.md`를 따른다.

---

## 5. 동작 확인 (선택)

구동 자체에는 필요 없다. `project_code/`에 포함된 테스트로 동작을 재현·확인할 수 있다.

```bash
# 파이썬 단위·통합 테스트
cd project_code && python -m pytest siap/tests/ backend/tests/ sim/tests/

# 펌웨어 호스트 유닛테스트 (C, avr 툴체인 불필요)
cd project_code/firmware/tests && make && ./test_bitpack && ./test_siap_frame \
    && ./test_status_codes && ./test_golden && ./test_node_state
```

C 구현과 Python 구현은 동일한 골든 벡터(`contracts/vectors/golden.jsonl`)로 검증되며, 이 일치 자체가 상호운용성의 증거다.

---

## 6. 파일 구조

제출물은 독립 실행 가능한 `project_code/`와 검증·시연 근거인 `docs/`를 포함한다.

```
소스코드/
├── README.md                          ← 실행·구조 안내 (이 문서)
├── docs/                              ← AI 활용·검증 및 시연 절차
│   ├── index_페이지_활용_가이드.md
│   ├── rules_페이지_활용_가이드.md
│   ├── settings_페이지_활용_가이드.md
│   ├── verify_페이지_활용_가이드.md
│   ├── ai-usage.md
│   └── AI_규칙_초안_시연.md
│
└── project_code/                  ■ 구현 (구동에 필요한 전부)
    ├── .env.example                  OpenAI·기상청 환경변수 예시(실제 키 없음)
    ├── run.py                        진입점 — 실행 모드 선택
    ├── requirements.txt              직접 의존성 3개 (== 고정)
    ├── wheels/                       오프라인 설치용 휠 (네트워크 불필요)
    │
    ├── contracts/                    모듈 경계 — Frame 계약
    │   ├── frame.py · siap_iface.py
    │   └── vectors/golden.jsonl      골든 테스트 벡터 (C·Python 공통 검증)
    │
    ├── firmware/                  ▶ 프로토콜 계층 (C)
    │   ├── core/                     하드웨어 의존성 0 — 3종 보드 공통
    │   ├── arduino_sensor_node/      Uno   (핀·ADC·Serial 바인딩만)
    │   ├── arduino_actuator_node/    Pro Mini
    │   ├── esp32_node/               ESP32 (전송 계층만 다름)
    │   └── tests/                    호스트 유닛테스트 + Makefile
    │
    ├── siap/                      ▶ 프로토콜 계층 (Python 게이트웨이)
    │   ├── codec.py transport.py registry.py control.py link.py
    │   └── tests/
    │
    ├── sim/                          가상 노드 · 로그 재생 · 프레임 주입
    ├── logs/                         실측 프레임 로그 (합성 금지)
    │
    ├── backend/                   ● 서비스 계층
    │   ├── db.py                     연결 팩토리 (PRAGMA 단일 지점)
    │   ├── schema.sql                DB 스키마 정본 (테이블·트리거·CHECK)
    │   ├── models.py repository.py ingest.py api.py
    │   ├── services/                 ems · dms · mms · fms · fcs (0937)
    │   └── tests/
    │
    ├── web/                       ● index/verify/rules/settings + static/
    │                                 외부 CDN·번들러 없음 (순수 바닐라)
    └── fixtures/                     kma_forecast_mock.json · seed.sql
```
