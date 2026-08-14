# CLAUDE.md — 프로젝트 규약

> 이 문서는 **작업자**가 따르는 프로젝트 규약이다. 역할 선택과 분리의 정본은 `ROLES.md`다.
> 파일명은 기존 조항 참조와 도구 호환을 위해 유지하며, 특정 AI 제품 사용을 요구하지 않는다.

> 이 파일은 매 세션 먼저 읽는다. 작업 전 §0과 §1을 반드시 확인할 것.

---

## 0. 이 프로젝트가 증명해야 하는 것

**2026 ICT 표준 챌린지 공모전(TTA) 출품작.** TTA 표준 3종을 실제로 구현해 동작함을 증명하는 것이 목적이다.

> 이것은 "스마트팜 앱"이 **아니다.** **TTA 표준의 참조 구현(reference implementation)이자 상호운용성 검증 도구**다.

| 반드시 성립해야 하는 주장 | 코드에서의 근거 |
|---|---|
| 서로 다른 MCU 3종이 **동일 표준 프로토콜로 혼용 동작**한다 | `project_code/firmware/core/`를 수정하지 않고 Uno / Pro Mini / ESP32가 모두 동작 |
| 하드웨어 없이 **표준 준수를 검증**할 수 있다 | `project_code/firmware/tests/` 호스트 유닛테스트가 단독 실행 |
| 노드 추가 시 **서버 코드 수정이 0줄**이다 | `project_code/backend/`에 노드 종류 하드코딩 금지 |
| 표준의 **실구현 장애 지점을 발견하고 해소**했다 | `strict` / `extended` 모드 분리, `docs/standard-findings.md` |

**적용 표준 (이 3종 외에는 표준으로 계상하지 않는다)**

| 표준번호 | 범위 | 담당 계층 |
|---|---|---|
| `TTAK.KO-10.0943` | 노드↔제어기 바이너리 프로토콜 (SIAP) | `project_code/firmware/` · `siap/` |
| `TTAK.KO-10.1369-Part1` | 데이터 요구사항 · ER 참조모델 | `project_code/backend/models.py` · `schema.sql` |
| `TTAK.KO-10.0937` | 클라우드 서비스 요구사항 | `project_code/backend/services/` |

---

## 1. 절대 금지 (공모전 실격·감점 사유)

작업 중 아래에 해당하는 코드를 발견하면 **즉시 멈추고 사용자에게 보고한다.**

| # | 금지 | 이유 |
|---|---|---|
| 1 | **합성 데이터** — `random.uniform()`, `math.sin(t)`, 하드코딩된 가짜 센서값을 로그·데모에 사용. **예외: §7 "실측 로그" 행이 정한 단계 4~7 한정 골든 벡터 재사용**(F-148·F-152) — 무작위·주기함수 생성이 아니라 손으로 만들고 코드로 검증된 골든 벡터 원본을 그대로 쓰며, 단계 8에서 실측 캡처로 교체된다 | 공고문 "명백한 허위" 조항. 사인파 온도는 즉시 드러남 |
| 2 | **실제 API 키·비밀번호·토큰 커밋** | 심사 제외 사유. 반드시 `project_code/fixtures/` 목업 폴백 |
| 3 | **실행파일 커밋** — `.hex` `.bin` `.elf` `.exe` `.apk` | 공고문이 제외 요구 |
| 4 | **개인 식별정보** — `@author`, 이름, 학교, 소속, 연락처, 호스트명, 개인 경로 | 블라인드 심사 위반 |
| 5 | **`project_code/firmware/core/`를 특정 보드용으로 수정** | "동일 응용계층" 주장이 무너짐 |
| 6 | **`project_code/backend/`에 노드 종류·디바이스 종류 하드코딩** | "서버 코드 수정 0줄" 주장이 무너짐 |
| 7 | **미승인 AI 규칙이 구동기로 전달되는 경로 생성** | 2차 평가 "사람 검토 지점" 항목의 핵심 |
| 8 | **`socat` 등 외부 도구 의존** | 심사자 OS 무관성. TCP 소켓만 사용 |
| 9 | **네트워크 필수 의존** | 오프라인 설치가 기본 경로 (`project_code/wheels/`) |

**검증 명령** (제출 전 필수) — `python fix_log/meta_verify.py` 가 아래 셋을 자동으로 돌린다.
오탐 허용 목록(예: OpenAPI 예약어 `"type": "apiKey"`)은 그 스크립트에 사유와 함께 적는다.

```bash
grep -rniE "api[_-]?key|password|token|secret|@author" --include="*.py" --include="*.c" --include="*.h" --include="*.ino" .
grep -rnE "random\.|math\.sin|np\.random" --include="*.py" project_code/
find . -name "*.hex" -o -name "*.bin" -o -name "*.elf"
```

---

## 2. 디렉터리 구조와 소유

**설계는 `project_docs/`, 구현은 `project_code/`.** 둘을 대칭으로 두고 섞지 않는다 —
`tools/` 만 양쪽을 함께 읽으므로 저장소 루트에 둔다.

```
ICT_Standard/
├── ROLES.md                     역할 선택·분리 정본
├── CLAUDE.md                 ← 작업자 프로젝트 규약(호환 파일명)
├── GPT.md                        검증자 역할 지시서(호환 파일명)
│
├── project_docs/             ★ 설계 문서 (읽기 전용 참조. 코드가 이걸 따른다)
│   ├── db/                       DB 스키마 설계서 · schema.sql · verify.py
│   ├── siap/                     SIAP 메시지 명세서 · spec_verify.py · spec_examples.json
│   ├── api/                      API 명세서 · openapi.json · api_verify.py
│   ├── contracts/                Frame 구조 명세서 · frame.py · siap_iface.py · test_contract.py
│   ├── contracts/vectors/        골든벡터 명세서 · golden_layout.py · golden.jsonl · golden_verify.py
│   ├── services/                 0937 요구사항 대조표 · 0937_clauses.json · services_verify.py
│   ├── web/                      화면 설계서 · web_verify.py
│   ├── firmware/                 펌웨어 설계서 · firmware_verify.py
│   ├── demo/                     시연 시나리오 · demo_verify.py
│   └── dev/                      개발 착수 지시서(에이전트) · 개발 운영 가이드(사람)
│                                 · 검증자 프롬프트(사람) · dev_verify.py
│
├── project_code/             ■ 구현 — 개발 단계에서 채운다
│   ├── contracts/                ◆ 모듈 경계 — 변경 시 §5 절차 필수
│   │   ├── frame.py                  Frame · MsgKind · WIRE_CODE · LAYOUT · Subtype
│   │   ├── siap_iface.py             SiapLink · FrameBuilder Protocol
│   │   ├── fake_link.py              개발용 대역 SiapLink
│   │   └── vectors/golden.jsonl      골든 테스트 벡터 53건 (+ golden_ext.jsonl 5건)
│   │
│   ├── firmware/             ▶ 프로토콜 계층 (C)
│   │   ├── core/                     하드웨어 의존성 0
│   │   │   ├── bitpack.c/.h              비트 read/write 4개 함수
│   │   │   ├── siap_types.h              contracts/frame.py의 C 대응
│   │   │   ├── siap_frame.c/.h           인코딩 · 디코딩 · N 산출
│   │   │   ├── node_state.c/.h           등록 · 제어 상태 머신
│   │   │   └── subtype_registry.h        Subtype 코드 (치환 지점 1/2)
│   │   ├── arduino_sensor_node/      Uno — 핀 매핑 · ADC · Serial 바인딩만
│   │   ├── arduino_actuator_node/    Pro Mini
│   │   ├── esp32_node/               ESP32 — 전송 계층만 다름
│   │   ├── attiny85_min/             확장성 검증용 (데모 경로 아님)
│   │   └── tests/                    호스트 유닛테스트 + Makefile
│   │
│   ├── siap/                 ▶ 프로토콜 계층 (Python, 게이트웨이)
│   │   ├── codec.py                  bytes ↔ Frame (치환 지점 2/2)
│   │   ├── transport.py              hardware / replay / simulate
│   │   ├── registry.py               노드 세션 (in-memory)
│   │   ├── control.py                제어 송신 · 재전송
│   │   ├── build.py                  FrameBuilder 구현
│   │   ├── link.py                   SiapLink 구현
│   │   └── tests/
│   │
│   ├── sim/                      virtual_node.py · replayer.py · inject.py
│   ├── logs/                     실측 프레임 로그 (합성 금지)
│   │
│   ├── backend/              ● 서비스 계층
│   │   ├── db.py                     ★ 연결 팩토리 — PRAGMA를 여기서만 건다
│   │   ├── schema.sql                project_docs/db/schema.sql 과 동기
│   │   ├── models.py                 읽기 전용 dataclass (ORM 미사용)
│   │   ├── repository.py             SQL 담당
│   │   ├── ingest.py                 ★ Frame 소비 지점 — 유일한 경계
│   │   ├── api.py                    REST + SSE
│   │   ├── services/                 ems · dms · mms · fms · fcs
│   │   └── tests/
│   │
│   ├── web/                  ● index.html(기능1) · verify.html(기능2)
│   │                             · rules.html(기능3) · settings.html(설정)
│   │                             외부 CDN·번들러·localStorage 금지. 설계는 project_docs/web/
│   ├── fixtures/                 기상청 API 목업 · seed.sql
│   ├── wheels/                   오프라인 의존성
│   ├── requirements.txt
│   └── run.py                    진입점 — SiapLink 호출만
│
├── tools/                    ◇ 구현↔설계 대조 검증기 (개발 단계에서 신설)
│                             project_docs/**/*_verify.py 가 '설계 문서'를 본다면
│                             tools/*_verify.py 는 '구현이 그 설계와 같은가'를 본다.
│                             양쪽을 함께 읽으므로 어느 한쪽에 속하지 않는다.
│                             run_all.py 가 전량 + 기존 검증기를 함께 돌린다
│
├── fix_log/                      발견 사항 인덱스 · 개별 건 · 기록 규약 (§11)
├── docs/                     △ 제출용 문서 (§6). 개발 단계에서 신설
│
└── 표준 문서 md 파일/         ▲ 표준 원문 · 공고문 · 진행보고서 — **제출물에서 제외한다**
    ├── 0937 … / 0943 … / 1369-1 …   표준 3종 md · pdf · 이미지
    ├── 2026 ICT 표준 챌린지 공모전_공고문.md
    └── 진행보고서.md                 전체 진행 동향의 정본
```

### 2.1 제출물에서 제외하는 것

패키징 시 zip 에 넣지 않는다. `tools/offline_verify.py` 가 검사한다.

| 대상 | 이유 |
|---|---|
| `표준 문서 md 파일/` | TTA 표준 원문 재배포. 심사자는 이미 표준을 가지고 있다 |
| `.omc/` · `__pycache__/` · `.git/` | 도구 상태·캐시. 공고문이 빌드 산출물 제외를 요구 |
| `_to_delete/` · `_stage*/` | 작업 중 생기는 임시 사본 |

### 2.2 계층 규칙

`project_code/` 안에서만 성립한다. **이 문서에서 `contracts/` · `firmware/` · `siap/` ·
`sim/` · `backend/` · `web/` 를 경로 없이 쓰면 전부 `project_code/` 아래를 가리킨다.**
`project_docs/` 아래를 가리킬 때는 반드시 그 접두어를 붙인다.

```
firmware/ siap/ sim/  ──╂ contracts/Frame ╂──  backend/ web/
      (표준 해석 담당)                          (렌더링 · 저장 담당)
```

- `backend/`, `web/`은 `siap/` 내부 심볼을 **import하지 않는다.** `contracts/`와 `SiapLink`만 참조한다.
- `siap/`은 `backend/`를 **import하지 않는다.**
- `backend/ingest.py`의 `handle(frame)` **위쪽에 로직을 두지 않는다.** Frame이 어디서 왔는지 서비스 계층이 알면 안 된다.
- `project_code/` 는 `project_docs/` 를 **import하지 않는다.** 설계 문서의 산출물(`frame.py` 등)은 단계 1에서 `project_code/contracts/` 로 **이관**한다.

---

## 3. 표준 준수 규칙

### 3.1 조항 번호를 코드에 남긴다

**표준에서 유래한 모든 상수·로직에 조항 번호를 주석으로 단다.** 이것이 표준 활용성 점수의 근거다.

```c
/* 표 7-14: DEVICE_MAIN_INFO — 56 bit */
#define SIAP_DMI_BYTES 7
```
```python
# 7.3.1 표 7-10 — Response Status Code
class RSC(IntEnum): ...
```

### 3.2 테스트 함수명에 조항 번호를 넣는다

```python
def test_relation_uniqueness_7_2_4_2(): ...   # 1369-P1 7.2.4.2
def test_invalid_format_7_3_1(): ...          # 0943 7.3.1
```
심사자가 테스트 목록만 봐도 준수 항목이 보여야 한다.

### 3.3 위반 판정에는 반드시 `clause`를 채운다

```python
Violation(code=RSC.INVALID_FORMAT, code_name="INVALID_FORMAT",
          clause="7.3.1", detail="Payload Length=24, 실제 수신 18byte")
```
화면에 `INVALID_FORMAT (0x09) — 7.3.1절` 형태로 그대로 출력된다.

### 3.4 표준 해석은 프로토콜 계층에만 존재한다

`backend/`, `web/`은 표준 조항을 **다시 해석하지 않는다.** `siap/`이 판정한 `violations`를 렌더링만 한다.

### 3.5 표준 미규정 사항은 결정하고 기록한다

| 항목 | 결정 |
|---|---|
| 엔디안 | **big-endian (network byte order)** |
| FLOAT | **IEEE-754 single precision, 4 byte** |
| 가변 요소 개수 N | `Payload Length` 역산 (`contracts/frame.py`의 `LAYOUT`) |
| N=0 | 고정부 있음 → 허용 / 가변부만 → 거부 |
| Subtype 코드값 | 자체 할당. 항목은 1369-P1 6.3.3 / 6.3.4 |
| USER DEPENDENT 5필드 타입 (표 7-15) | `DEVICE_MAIN_INFO.Value Type` 을 따른다 (F-022) |
| `MSG_CONTROL_PROFILE` 시간 단위 (표 7-18) | 3필드 전부 **sec** — 단위가 명시된 `Period` 에 맞춤 (F-033) |
| `Value` 32bit 범위 초과 | **거부한다.** 마스킹 래핑 금지. INT `-2^31..2^31-1` / UINT `0..2^32-1` (F-044) |
| 위반 Notify 회신 | **회신하지 않는다.** ACK 는 헤더뿐이라 오류 RSC 를 실을 수단이 없다 (F-040) |
| 위반 Request 회신 | 대응 `RES_*` 에 위반 RSC 를 실어 회신한다 — 7.3.1 · 표 7-10 근거 (F-040) |
| 재전송 시 `Message Identifier` | **유지한다.** 새로 발번하면 노드가 중복 요청으로 처리한다 (F-041) |
| `send()` 대기 상한 | `Timeout × (Retry Count + 1)` — 표 7-18 두 값에서 유도 (F-041) |
| replay 입력 방향 | 게이트웨이 기준 `dir="rx"` 만 주입. `tx` 는 기대 출력 (F-042) |
| 노드당 디바이스 상한 | **N = 16.** AVR SRAM 2KB + `Timeout ≥ 2 × wire_time` 에서 유도 (F-064) |
| NEC 알림의 판정 | **위반이 아니다.** `violations` 는 비우고 alert 저장 + ACK 회신 (F-060) |
| 응답 매칭 조건 | `Node ID` + `Message Identifier` + **`Message Type`**. 셋 다 맞아야 대기 해제 (F-046) |
| 승인 스냅샷의 대상 | `control_rule.target_install_id` 컬럼이 정본. JSON 안의 값이 아니다 (F-049) |
| 검증기 콘솔 출력 문자 | **CP949 표현 가능 범위 안에서 고른다.** `meta_verify.py` 가 강제 (F-045) |
| 가변 요소 위반 시 적용 의미론 | **요소 단위 즉시 적용 + 첫 위반에서 중단.** 전량 롤백하지 않는다 — 요소가 자기완결적이라 잘못된 값은 적용되지 않으며, 전량 거부는 480 byte 버퍼를 요구해 스트리밍 결정과 충돌한다 (펌웨어 §5.6) |
| 프레임 재동기 규칙 | **펌웨어(C)**: `Version` + `resolve_kind` + `Transmission Type` + `element_count` **4조건 동시 만족** 시에만 프레임 시작으로 인정. `T_gap` = 20 ms (펌웨어 §5.7, F-069). **게이트웨이(Python, `siap/codec.py`)**: `Version` 일치 + **등록된 Node ID**(F-146→F-151) — resolve_kind·Transmission Type·element_count 는 `decode_frame()` 자신이 위반으로 검사·보고하는 항목과 같아서, 재동기 게이트에 그대로 두면 연속 위반 주입(시연 §3.1 S4-b) 중 두 번째 위반부터 "노이즈"로 오인돼 유실됐다(F-146). Version 만으로 완화하자 이번엔 위반 프레임이 남긴 잔여 payload 바이트가 우연히 Version 값과 같을 때 뒤따르는 정상 프레임을 삼키는 회귀가 나 Node ID 조건을 더했다(F-151, 오탐률 1/256→약 2⁻²²). 단, Node ID 미등록만이 위반 목표인 X02 류를 위해 — Node ID 가 미등록이어도 resolve_kind·Transmission Type·element_count 가 전부 자기충족적으로 유효하면 후보로 인정하는 예외를 둔다. 표준 미규정 영역(F-069)이라 구현마다 다른 규칙을 쓸 수 있다는 §5.7 원문 전제를 그대로 따른 것이며, 정상 통신 경로에서는 두 규칙의 결과가 같다 |
| `RES_SET_CONNECTION` 오류 RSC 시 노드 거동 | 재시도 **가능 2종**(`INVALID_GCG_ID`·`INVALID_NODE_ID`) / **불가 7종**. 불가는 **`HALTED`** 로 간다 — 아래 행이 정본이다 (펌웨어 §6.5, F-072·F-076) |
| `NOTI_DEVICE_VALUE` 재전송 시의 값 | **재인코딩 시점의 현재값.** `msg_id` 는 유지한다. 원본 보관은 7×N byte 를 요구해 스트리밍 결정과 충돌한다 (펌웨어 §6.2-a) |
| 연결이 영구 불가할 때의 노드 거동 | **`HALTED`** — 로컬 표시만 하고 **완전 정지한다.** 수신 프레임에 ACK 도 회신하지 않으며 **상태 무관 전이의 유일한 예외**다. 전원 재인가로만 벗어난다. 거부된 노드의 `NOTI_ERROR` 는 게이트웨이가 `INVALID_NODE_ID` 로 되받아 도달하지 않는다 (펌웨어 §6.1·§6.5, F-072·F-076) |
| 디바이스 샘플링·오류 감지 주기 | **표준 미규정.** 표 7-15의 `Period`는 표준상 **데이터 전달주기**이며, 본 구현은 별도 샘플링 주기 필드가 없으므로 이를 **내부 스캔 간격으로도 재사용한다** — 이 재사용은 표준 필드 의미의 재정의가 아니다. 오류 감지(8.2.1.1)도 이 스캔에 얹는다 (펌웨어 §6.3, F-130) |
| `Transfer Mode`(표 7-15) = Both 의 전송 조건 | **이 구현에서 Periodic과 동일하게 동작한다**(이벤트 조기 감지 없음). 디바이스별 두 번째 스케줄이나 전역 이벤트 틱을 검토했으나 AVR 2KB SRAM·타이머 3종 예산과 충돌하는 폭으로 구현이 커져 채택하지 않았다 (펌웨어 §6.3, F-130) |
| 디바이스 `Period` = 0 의 의미 | **사실상 매 poll 마다 스캔**(가장 촘촘한 감시)으로 허용한다. §4.1-a 는 0을 거부하지 않는다 — 표준은 하한을 규정하지 않는다 (펌웨어 §6.3, F-130) |
| `NOTI_ERROR`(NEC, 표 7-12) → `alert.severity` 매핑 | 0943은 NEC에 심각도 등급을 두지 않는다. **전원·배터리 계열(`ERROR_PWR`·`ERROR_BATTERY`·`ERROR_BATTERY_LOW`·`ERROR_BATTERY_OFF`)은 `CRITICAL`, 그 외(수신·타이머 오류 등 일시적 이상)는 `WARN`** — 장치가 곧 통신 불능이 되는 원인인지로 가른다 (`backend/ingest.py::_nec_severity`, 단계 5) |
| 장치상태 서브타입 중 2물리량 이상을 갖는 것(관수펌프 압력+분사도, 송풍기 전원+바람세기, 냉난방기 전원+온도+바람세기)의 `NOTI_DEVICE_VALUE` 반영 | 0943 `DEVICE_MAIN_INFO`(표 7-14)는 디바이스 1개당 값 1개만 나른다 — 이 프레임 구조로 두 물리량을 동시에 표현할 수 없다. **주 필드(첫 물리량)에만 `Value`를 싣고 나머지는 NULL로 둔다.** 전원(on/off) 필드는 NOT NULL이므로 **`Value != 0`을 켜짐으로 해석**한다. 물리량마다 별도 `device_id`로 나누는 것은 `contracts/` 계약 확장이라 §5 절차 대상이며 이번 단계 범위가 아니다 (`backend/repository.py::record_device_state`, 단계 5) |
| 한 `NOTI_DEVICE_VALUE` 프레임에 장치상태·환경상태가 함께 실렸을 때 `operating_env`(1369-P1 7.1(10)) 결속 대상 | `env_state_id`가 `UNIQUE`라 환경상태 1건은 정확히 하나의 장치상태에만 귀속된다 — 프레임에 장치상태가 2건 이상이면 어느 것과 짝지어야 하는지 프레임 구조만으로는 정할 수 없다(1369-P1 미규정). **장치상태가 정확히 1건일 때만 결속하고, 2건 이상이면 그 프레임의 `operating_env`는 전부 건너뛴다** — 모호한 추정으로 잘못된 짝을 만들지 않는다. 환경상태·장치상태 자체(`env_measurement`·`device_state_data`)는 이 판단과 무관하게 항상 기록된다 (`backend/ingest.py::_handle_device_value`, 단계 5, F-156·F-164) |
| 동적으로 연결된 장치(`REQ_SET_DEVICE_PROPERTY`/`REQ_SET_NODE_DEVICE_PROPERTY_ALL`, F-198 — `REQ_SET_CONNECTION`이 아니다)의 `device_manage`(1369-P1 7.1(7)) 관리자 | 이 참조 구현에는 "장치 관리자를 지정"하는 별도 입력이 없다(API 명세서 §3 쓰기 7건에 없음) — 그렇다고 비워 두면 표준의 N:1 관계가 정상 Plug & Play 경로에서 영구히 성립하지 않는다(F-176). **장치가 설치된 온실의 관리자(`greenhouse_manage`, 7.1(3)로 이미 N:1 확정)를 그 장치의 관리자로도 삼는다** — 이 데모는 온실 1개 고정이라 결과가 유일하게 결정된다. 별도 관리자 지정 API가 생기면(§5-2류 확장) 그때 이 기본값을 대체한다 (`backend/ingest.py::_handle_device_property`, `backend/repository.py::link_device_manage`, 단계 5, F-176) |
| 노드가 자신의 디바이스 구성(`DEVICE_PROPERTY×N`)을 게이트웨이에 선언하는 시점 | 0943 8.1.3.3(`REQ_SET_NODE_DEVICE_PROPERTY_ALL`, 표 7-2 "양방향")은 절차 자체를 규정하지 않는다. `REQ_SET_CONNECTION`(8.1.1)은 페이로드가 없어(`LAYOUT (0,0)`) 이 선언을 실을 수 없다 — 예전 버전은 여기 바인딩돼 있어 디바이스 등록이 한 번도 실행되지 않는 죽은 코드였다(F-198). **`RES_SET_CONNECTION`(RSC=SUCCESS) 수신 직후, 매 연결 세션마다 `REQ_SET_NODE_DEVICE_PROPERTY_ALL` 1회로 전체 구성을 선언한다.** 이후 개별 변경은 `REQ_SET_DEVICE_PROPERTY`(부분 집합)로 동기화한다 — 게이트웨이 런타임 registry(`siap/registry.py::merge_device_properties`)는 `..._ALL`을 전체 교체, `REQ_SET_DEVICE_PROPERTY`를 `device_id` 기준 병합으로 구분해 반영한다 (`backend/ingest.py::_handle_device_property`, `sim/virtual_node.py`, `siap/link.py::_apply_registry_effects`, 단계 4/6 재작업, F-198) |
| MMS `threshold` 모델(0937 6.3-6)의 임계값·권장 조치 문구 출처 | 작물별 고온 기준값·장치별 권장 문구를 담을 표준 규정 테이블이 없다. Python 상수로 두면 새 작물 기준이나 새 장치(송풍기·냉난방기 등) 모델을 추가할 때마다 `backend/`를 고쳐야 해 §1-6·§0 주장 3이 무너진다(F-190). **임계값은 모델의 `input_spec`이 이미 선언한 대로 호출자가 `inputs['crop_tmax_c']`로 공급한다(6.3-3 "입력값") — 없으면 추측하지 않고 그렇게 응답한다. 권장 조치 문구는 모델의 `output_spec.recommend_action`을 그대로 쓴다(6.3-2 "출력값" 메타정보)** — 새 모델은 `control_model` 행 등록만으로 추가되고 `backend/services/mms.py`는 바뀌지 않는다 (`backend/services/mms.py::_threshold_draft`, 단계 6, F-190) |

새 미규정 사항을 만나면 결정하고 **이 표(§3.5)와 관련 설계 문서의 결정 표에 추가한 뒤** 사용자에게 보고한다. `docs/standard-findings.md`는 §3.6의 `표준결함`(표준 원문 자체의 결함) 전용 정본이다 — 미규정 결정(이 절)은 그리로 이관하지 않는다(F-134).

### 3.6 표준의 결함은 발견 즉시 기록한다

현재까지 **19건** (0943 13건 + 1369-P1 6건). 정본은 `SIAP_메시지_명세서.md` §6 과 `DB_스키마_설계서.md` §5 이며, 개발 착수 후 `docs/standard-findings.md`로 통합한다. 총계는 `fix_log/bug_fix_list.md`의 `표준결함` 행 수와 항상 일치해야 한다.
새로 발견하면 **표준 조항 번호 · 내용 · 등급 · 본 구현의 처리**를 표에 추가한다.

---

## 4. 코딩 규칙

### 4.1 공통

- 주석·문서·커밋 메시지는 **한국어**. 식별자는 영어
- 파일 인코딩 UTF-8, 개행 LF
- **의존성 최소화.** 새 패키지 추가 전 사용자에게 확인 — `wheels/` 오프라인 패키징과 200MB 제한에 직결

### 4.2 C (`firmware/`)

- C99. AVR 타깃 기준으로 작성 (Uno/Pro Mini: flash 32KB, SRAM 2KB)
- **비트 패킹 필수.** `bitpack.c`의 4개 함수만 사용한다. **쓰기 2종은 범위 초과 시 `false` 를 반환하고 아무것도 기록하지 않는다** — 마스킹 래핑 금지(F-044)를 규약이 아니라 구조로 강제한다. 반환값을 버리면 `-Werror=unused-result` 로 빌드가 실패한다 (F-075·F-078)

```c
/* SIAP_WUR = __attribute__((warn_unused_result)) — 반환값을 버리면 컴파일 경고 (F-078) */
SIAP_WUR bool bp_write    (uint8_t *buf, size_t *bitpos, uint32_t val, uint8_t nbits);
         uint32_t bp_read (const uint8_t *buf, size_t *bitpos, uint8_t nbits);
SIAP_WUR bool bp_write_f32(uint8_t *buf, size_t *bitpos, float val);
         float bp_read_f32(const uint8_t *buf, size_t *bitpos);
```

- **C 구조체 직접 캐스팅 금지.** `Message Type`(14bit), `GCG/Node ID`(각 20bit), `Subtype`(9~16bit)이 바이트 경계를 넘는다
- 동적 할당(`malloc`) 사용 금지. 고정 버퍼만
- `core/`는 `Arduino.h`, `<stdio.h>` 등 플랫폼 헤더를 include하지 않는다
- 코드 변경 후 `avr-size`로 flash/SRAM 측정치를 기록

### 4.3 Python (`siap/`, `backend/`)

- Python 3.11+, 타입 힌트 필수
- **디코딩 실패 시 예외를 던지지 않는다.** `violations`가 채워진 `Frame`을 반환한다
- dataclass는 `frozen=True`
- **ORM을 쓰지 않는다.** `schema.sql`이 정본이며 트리거·CHECK가 여기 있다. `models.py`는 읽기 전용 dataclass, SQL은 `repository.py`
- **DB 연결은 `backend/db.py` 팩토리에서만 만든다.** `foreign_keys=ON`은 SQLite 기본값이 OFF이므로 연결마다 켜야 하고, 한 곳에서만 켜야 빠뜨리지 않는다
- **시리얼·소켓은 SIAP I/O 스레드가 단독 소유한다.** 다른 스레드에서 직접 쓰지 않는다. 송신은 `link.send()` 경유
- **DB 쓰기 소유권은 테이블 단위다** (아키텍처 §4.4-a). 노드에서 온 데이터는 I/O 스레드가, 사람이 유발한 쓰기(`control_rule`·`control_execution` INSERT·`public_data_*`)는 API 스레드가 쓴다. 교차 지점은 `control_execution` 하나뿐이며 컬럼이 분리되어 있다. 연결마다 `busy_timeout=5000`, 읽고-고치기는 `BEGIN IMMEDIATE`
- **의존성은 `fastapi` · `uvicorn` · `pyserial` 3개다.** 추가 전 사용자 확인, 추가 즉시 `wheels/` 검증

### 4.4 구현 순서

**C를 먼저 쓰고 Python으로 옮긴다.** 반대 방향은 AVR의 메모리·정렬 제약을 놓친다.
두 구현은 동일한 `contracts/vectors/golden.jsonl` 로 검증되며, 이 일치 자체가 상호운용성 증거가 된다.

---

## 5. `contracts/` 변경 절차

`contracts/`는 모듈 경계다. 임의로 고치면 통합이 깨진다.

1. **표준 조항 번호를 근거로** 변경 사유를 제시한다 ("표 7-15에 따르면 Period는 14bit인데 계약에 16bit로 되어 있음")
2. **사용자에게 확인받는다**
3. `contracts/` 수정 → 골든 벡터 재생성 → `contracts/test_contract.py` + 양쪽 코덱 테스트 재통과
4. `docs/standard-findings.md`에 변경 이력을 남긴다

> 근거 없이 `contracts/`를 수정하지 않는다. 통합 실패의 유일한 원인이다.

---

## 6. 테스트 규칙

### 6.1 반드시 통과해야 하는 명령

```bash
cd project_code/firmware/tests && make && ./test_bitpack && ./test_siap_frame && ./test_status_codes && ./test_golden && ./test_node_state
cd project_code && python -m pytest siap/tests/ backend/tests/
python project_code/contracts/test_contract.py
python project_docs/api/api_verify.py  # openapi.json ↔ schema.sql · frame.py
python project_docs/contracts/vectors/golden_verify.py   # 골든 벡터 53건
python project_docs/firmware/firmware_verify.py          # 펌웨어 설계서 수치 대조
python project_docs/web/web_verify.py                    # 화면 ↔ API ↔ 골든 대조 · 접근성
python project_docs/demo/demo_verify.py                  # 시연 컷 산술 · 배점 커버리지
python project_docs/services/services_verify.py          # 0937 조항 33건 · 부속서 A 31건 대조
#   개발자 전용: --with-source <TTAK.KO-10.0937.md> 로 발췌본을 원문과 대조
python project_docs/dev/dev_verify.py                    # 개발 착수 지시서 · 운영 가이드 대조
python fix_log/meta_verify.py          # F-043 — 인덱스·문서 수치 대조
#
# 개발 착수 후에는 아래가 추가된다 (project_docs/dev/개발_착수_지시서.md §4)
python tools/run_all.py                # 구현↔설계 대조 검증기 전량 + 위 검증기 전량
```

### 6.2 골든 벡터 (`project_docs/contracts/vectors/golden.jsonl` → 단계 1에서 `project_code/contracts/vectors/` 로 이관, 당시 52건 → F-120(B11, N 상한 초과) 추가로 53건)

| 분류 | 개수 |
|---|---|
| 정상 메시지 34종 | 34 |
| 경계값 (N=0 / N=최대 / N 상한 초과 / 필드 최대·최소 / msg_id 랩어라운드) | 11 |
| 위반 케이스 (기능 2 주입 시나리오) | 8 |

- **손으로 만들고 코드로 검증한다.** 코드로 생성한 것을 정답으로 삼으면 자기 검증 순환이 된다.
  구체적으로는 **벡터마다 (필드명, 비트폭, 값) 을 손으로 적고**(`golden_layout.py`), 구조를 모르는
  비트 결합기만 통과시킨다. `project_docs/siap/spec_verify.py` 의 인코더를 **재사용하지 않는다** —
  같은 명세서를 두 번 타이핑해 같은 바이트가 나오는지가 교차 검증이다
- **`golden.jsonl` 을 직접 편집하지 않는다.** 정본은 `golden_layout.py` 의 레이아웃이다
- **검증기는 검증 대상 파일 하나만 읽지 않는다.** 자기 자신과의 일치만 보게 된다 (F-080). 적어도 하나의 **독립 입력**(표준 발췌 · 다른 설계 산출물 · 계약 파일)과 대조한다
- **"필드가 있다"와 "값이 반드시 온다"는 다르다 (F-091·F-092·F-095).** JSON Schema 의 `required` 는 **키의 존재만** 본다 — `nullable` 필드는 `required` 와 `minProperties` 를 모두 통과한다. 계약이 값을 보장해야 하면 분기마다 **타입까지 좁힌다**. 구조 검사(`oneOf` 가 있는가)로 끝내지 말고 **정상·반례를 실제로 넣어보고 판정을 대조한다**
- **직접 만든 검증 로직은 표준 구현과 교차 검증한다 (F-095).** 자체 JSON Schema 검사기로 자기 스키마를 검사하면 *구현하지 않은 키워드*가 조용히 통과로 바뀐다. `jsonschema` 가 설치돼 있으면 같은 매트릭스를 한 번 더 돌려 판정 일치를 확인하고, 없으면 **생략했다는 사실을 출력에 남긴다**
- **문서가 DDL·계약보다 강한 보장을 주장하지 않는다 (F-091).** 제약 개수·트리거 이름을 문서에 적었으면 `meta_verify.py` 가 실제 DDL 과 대조한다. 대상 문서를 목록으로 고정하지 않고 **`project_docs/**/*.md` 전수**로 본다 — 목록은 반드시 새 문서를 놓친다 (F-094)
- **역사적 수치는 시점을 붙여 적는다 (F-094).** `쓰기 4 → 5` 같은 전이 기록은 남기되 같은 줄에 *당시·이전·한때* 를 붙인다. 붙지 않은 수치는 **현재 주장**으로 간주해 실측과 대조한다
- `strict` 53건과 `extended` 5건을 **다른 파일에 둔다.** "표준을 이렇게 구현했다"와
  "표준을 이렇게 고치자"가 섞이면 심사자가 준수 근거를 구분할 수 없다
- C · Python · backend 세 곳이 같은 파일로 테스트한다

### 6.3 위반 케이스 8종 (기능 2의 판정 기준)

| # | 주입 | 기대 코드 | clause |
|---|---|---|---|
| 1 | `Version` 조작 | `INVALID_VERSION` (0x01) | 7.3.1 |
| 2 | 미등록 `Node ID` | `INVALID_NODE_ID` (0x03) | 7.3.1 |
| 3 | `Payload Length` ≠ 실제 | `INVALID_FORMAT` (0x09) | 7.3.1 |
| 4 | `Message Type` = 0x000E (Reserved) | `INVALID_FORMAT` (0x09) | 표 7-2 |
| 5 | `Transmission Type` = 0x03 | `INVALID_TRANSMISSION_TYPE` (0x08) | 표 7-6 |
| 6 | `Value Type` = 0x03 (Reserved) | `INVALID_DATA_TYPE` (0x06) | 표 7-14 |
| 7 | 미등록 `Subtype` | `INVALID_DATA_SUBTYPE` (0x07) | 표 7-14 |
| 8 | `NEC` = 0x07 수신 | `ERROR_BATTERY_LOW` (0x07) | 7.3.2 |

---

## 7. 재현성 규칙

심사자에게는 라즈베리파이도 MCU도 없다. **교체 대상은 전송 계층 한 곳뿐이다.**

```python
URLS = {
    "hardware": "/dev/ttyUSB0",
    "replay":   "socket://127.0.0.1:5555",   # 실측 로그 재생
    "simulate": "socket://127.0.0.1:5556",   # 가상 노드 (양방향)
}
```

| 규칙 | 내용 |
|---|---|
| 기본 경로 | `python project_code/run.py --mode replay` / `--mode simulate` 두 줄로 동작 |
| 오프라인 설치 | `pip install -r project_code/requirements.txt --no-index --find-links project_code/wheels/` |
| 실측 로그 | `project_code/logs/*.jsonl` — 결측·위반·지연·오류알림을 **의도적으로 포함**. 합성 금지. **예외(단계 4~7 한정, F-148):** 실측 캡처는 단계 8(보드 3종 실물 통합)에만 존재한다. 그전까지 `logs/`는 골든 벡터 원본 바이트만 그대로 재생하는 파일(`sim/golden_log.py` 산출)로 채운다 — 개발_착수_지시서 §3.6(단계 4) "하지 않을 것"이 이미 "그전까지는 골든 벡터만 재생한다"고 명시했다. `sim/virtual_node.py`의 시뮬레이션 센서값도 같은 근거로 golden.jsonl의 DEVICE_MAIN_INFO.Value 를 재사용한다(아키텍처 설계서 §5.5, 2026-08-09 사용자 확인). 무작위·주기함수 생성(§1-1)은 이 예외에 포함되지 않는다 — 값은 손으로 만들고 코드로 검증된 골든 벡터 원본 그대로다 |
| 기상청 API | 키 부재 시 `project_code/fixtures/` 목업으로 **자동 폴백** |
| Docker | 보조 수단. 기본은 venv |
| 제출 크기 | 소스코드 zip **200MB 이하** (§2.1 제외 대상을 뺀 뒤) |

---

## 8. 세션 시작 시 확인

1. **`fix_log/bug_fix_list.md`에 상태가 `신규`인 항목이 있는가** — 있으면 §11 절차를 먼저 수행한다
2. `project_docs/` 의 관련 명세서를 읽었는가 — 코드는 명세서를 따른다. 명세서 없이 구현하지 않는다
3. 작업 대상이 어느 계층인가 — 계층을 넘는 import를 만들지 않는다
4. `contracts/`를 건드려야 하는가 — 그렇다면 §5 절차
5. 표준 조항 번호를 주석·테스트명에 넣었는가
6. §1 금지 사항에 걸리는 코드를 만들지 않았는가

**개발 착수 후에는** `project_docs/dev/개발_착수_지시서.md` 를 이 파일 다음으로 읽는다 — 현재 단계·읽을 문서·출구 명령이 거기 있다. 그 절에 지정되지 않은 문서는 읽지 않는다(컨텍스트 예산).
**`개발_운영_가이드.md` 와 `검증자_프롬프트.md` 는 사람용이므로 읽지 않는다.**

**여러 단계를 한 번에 진행하지 않는다.** 각 단계 완료 후 사용자에게 확인받는다.

---

## 9. 참조 문서

| 문서 | 내용 |
|---|---|
| `project_docs/siap/SIAP_메시지_명세서.md` | 메시지 34종 페이로드 구성 · 비트 오프셋 · N 산출 · 예시 프레임 9건 |
| `project_docs/contracts/Frame_구조_명세서.md` | 모듈 경계 · `MsgKind`/`WIRE_CODE` 분리 · `SiapLink` |
| `project_docs/db/DB_스키마_설계서.md` | 테이블 31개 · ER 구조 · 무결성 제약 |
| `project_docs/arch/아키텍처_설계서.md` | 모듈 구성 · 동시성 모델 · 전송 계층 · 실행 모드 |
| `project_docs/firmware/펌웨어_설계서.md` | 계층 경계 · 메모리 예산 · 스트리밍 코덱 · 노드 상태 머신 · 보드 3종 바인딩 |
| `project_docs/services/0937_요구사항_대조표.md` | 0937 조항 33건 · 부속서 A 31건 ↔ 구현 대조. `services/` 모듈 배정의 정본 |
| `project_docs/services/0937_clauses.json` | 0937 종결어미 발췌 33건. **요구 강도의 정본** — 대조표에서 파생하지 않는다 (F-081) |
| `project_docs/web/화면_설계서.md` | 화면 4종 구성 · 화면↔API 대응 · 접근성(WCAG 2.1 AA) · 화면이 하지 않는 것 |
| `project_docs/demo/시연_시나리오.md` | 영상 2분 컷 시트 · 촬영 순서 · 블라인드 점검 · 2차 발표 라이브 시연 |
| `project_docs/dev/개발_착수_지시서.md` | **개발 세션의 진입점 (에이전트 전용).** 단계 11개 · 출구 명령 · 신설 검증기 · 설계 문서 경로표 |
| `project_docs/dev/개발_운영_가이드.md` | **사람용.** 단계 설계 근거 · 일정 · 축소 순서 · 독립 검증 운영. 에이전트는 읽지 않는다 |
| `project_docs/dev/검증자_프롬프트.md` | 단계별 독립 검증자 프롬프트. 정본은 `ROLES.md` · `GPT.md` · `fix_log/README.md` 이며 이 문서는 호출 방법만 정한다 |
| `project_docs/api/API_명세서.md` | REST + SSE 표면 · 승인 게이트의 API 반영 · 정본은 `openapi.json` |
| `project_docs/contracts/vectors/골든벡터_명세서.md` | 골든 벡터 53건 · 손으로 만든 근거 · 정본은 `golden_layout.py` |
| `docs/standard-mapping.md` | 표준 조항 ↔ 코드 위치 매핑 (구현하며 갱신) |
| `docs/standard-findings.md` | 표준 실구현 장애 지점 19건 (발견 시 추가) |
| `docs/subtype-registry.md` | Subtype 코드 레지스트리 |
| `docs/0937-requirements-matrix.md` | 0937 요구사항 대조표 (패키징 시 `project_docs/services/` 에서 이관) |
| `docs/ai-usage.md` | 생성형 AI 활용 단계 및 검증 방식 |

**표준 원문**: `표준 문서 md 파일/` — **저장소 안에 있다.** 외부 경로를 쓰지 않는다.
md + 이미지로 읽고, PDF는 불가피한 경우에만 사용자 확인 후 연다.
이 폴더는 개발·검증용이며 **제출물에서는 제외한다** (§2.1).

---

## 10. 자주 하는 실수

| 실수 | 대응 |
|---|---|
| 명세서 없이 코딩 시작 | `project_docs/`의 해당 명세서를 먼저 읽는다 |
| C 구조체를 그대로 캐스팅 | 20bit·1bit 필드 때문에 반드시 깨진다. `bitpack.c` 경유 |
| Python 먼저 쓰고 C로 이식 | AVR 제약을 놓친다. **C 먼저** |
| 골든 벡터를 코드로 생성 | 자기 검증 순환. 손으로 만들고 코드로 확인 |
| `backend/`에서 `siap/` import | 계층 위반. `contracts/`와 `SiapLink`만 |
| `violations`를 서비스 계층이 재판정 | 표준 해석이 두 곳에 생긴다. 렌더링만 |
| ESP32를 위해 `core/` 수정 | "동일 응용계층" 주장이 무너진다. 전송 계층에서만 흡수 |
| 대시보드에 노드 종류 하드코딩 | "서버 코드 수정 0줄" 주장이 무너진다 |
| `wheels/`를 마지막에 준비 | 용량 초과·의존성 누락이 늦게 드러난다. 조기에 검증 |

---

## 11. fix_log 처리 — 검증자 검증 결과 반영

검증자가 코드·문서를 독립적으로 점검하고 발견 사항을 `fix_log/`에 기록한다. **기록 규약은 `fix_log/README.md`가 정본이다.** 역할 분리는 `ROLES.md`, 검증자 역할 지시서는 `GPT.md`다.

### 11.1 세션 시작 시

`fix_log/bug_fix_list.md`를 열어 상태가 `신규`인 행을 확인한다. 있으면 다른 작업보다 먼저 처리한다.

### 11.2 처리 순서

```
요건위반  →  코드버그  →  문서불일치  →  표준결함(이관)  →  제안
```
같은 분류 안에서는 `치명` → `오류` → `위험` → `제안` 순.

### 11.3 분류별 처리

| 분류 | 처리 |
|---|---|
| `요건위반` | **최우선.** 공고문 조항을 직접 확인한 뒤 즉시 수정. 다른 작업 중단 |
| `코드버그` | 재현 → 수정 → **회귀 테스트 추가** (같은 버그가 다시 나지 않도록) |
| `문서불일치` | **표준 원문을 확인해 어느 쪽이 옳은지 먼저 판정한다.** 명세서가 틀렸으면 명세서를, 코드가 틀렸으면 코드를 고친다. 판정 근거를 처리 기록에 남긴다 |
| `표준결함` | 고치지 않는다. `docs/standard-findings.md`로 이관하고 상태를 `이관`으로 바꾼다. 기획서 4장(표준 실구현 검증 결과)의 자산이다 |

### 11.4 상태 전이

**상태를 바꾸는 것은 작업자뿐이다.** 검증자는 `신규`로만 추가한다.

| 전이 | 조건 |
|---|---|
| `신규` → `확인` | 재현·검증에 성공 |
| `확인` → `수정완료` | 코드·문서에 반영하고 테스트 통과 |
| `신규` → `기각` | 오탐 또는 의도된 설계. **사유를 개별 파일의 처리 기록에 반드시 남긴다** |
| `신규` → `보류` | 타당하나 일정상 미룸. **사유와 재검토 시점을 남긴다** |
| `신규` → `이관` | `표준결함` |

**인덱스의 행을 삭제하지 않는다.** 상태만 갱신한다 — 기록이 남아야 검증자가 같은 지적을 반복하지 않는다.

### 11.5 기각할 때의 원칙

오탐이라고 판단해도 **근거 없이 기각하지 않는다.** 표준 조항이나 설계 의도를 인용해 왜 문제가 아닌지 적는다. 근거를 못 대겠으면 기각이 아니라 `확인`으로 두고 사용자에게 판단을 요청한다.

### 11.6 사용자 보고

fix_log 항목을 처리한 뒤에는 **무엇을 어떤 상태로 바꿨는지** 요약해 보고한다. 특히 `기각`과 `보류`는 사용자가 동의하지 않을 수 있으므로 사유를 함께 알린다.
