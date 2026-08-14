# API 명세서 — REST + SSE

> **범위**: 화면(`web/`)과 서비스 계층(`backend/`) 사이의 HTTP 표면
> **정본**: `project_docs/api/openapi.json` (OpenAPI 3.1.0). 이 문서는 **왜 그렇게 정했는지**를 적는다
> **검증**: `python project_docs/api/api_verify.py` — **71/71 통과** (§7)
> **선행 문서**: `DB_스키마_설계서.md`(응답의 출처) / `Frame_구조_명세서.md`(프로토콜 타입) / `아키텍처_설계서.md` §10

---

## 1. 이 API가 증명해야 하는 것

REST 표면은 그 자체로 표준이 아니다. 세 표준 어디에도 HTTP 엔드포인트 규정은 없다. 그렇다면 이 문서의 존재 이유는 하나다 — **표준 3종의 요구가 화면까지 손상 없이 도달하는가**를 보이는 것.

| 주장 | API 표면에서의 근거 |
|---|---|
| 노드가 늘어도 **서버 코드 수정 0줄** | 경로·스키마 어디에도 노드/디바이스 종류가 없다. `subtype`은 열거되지 않은 문자열이다 |
| 표준 해석이 **한 곳에만** 있다 | 위반 판정 필드(`code`·`clause`·`detail`)를 그대로 전달만 한다. 재판정 엔드포인트가 없다 |
| **AI 출력이 직접 구동기를 제어하지 않는다** | 초안 생성 요청이 실행 가능한 필드를 받지 못하고, 규칙 실행 요청에는 본문이 아예 없다 |
| 데이터가 **1369-Part1 모델 그대로**다 | 응답 필드명이 논리적 모델의 속성명과 1:1. 검증기가 `schema.sql`과 대조한다 |

> 심사자가 `openapi.json` 하나만 열어봐도 위 넷이 보여야 한다. 그래서 각 오퍼레이션 설명에 조항 번호를 남겼고, 남았는지를 검증기가 검사한다.

**주장하지 않는 것도 같이 적는다.** 승인 기록이 보장하는 것은 *"이 식별자가 제출되었고 이후 위조되지 않았다"* 까지다. *"그 사람이 실제로 최종 결정했다"* 는 **신원 보장이 아니다** — 인증이 없기 때문이다(§2.1, F-052). 기획서·시연 설명에서도 이 선을 넘지 않는다.

---

## 2. 확정된 형식 결정

| 항목 | 결정 | 이유 |
|---|---|---|
| 문서 형식 | **JSON** (`openapi.json`) | 검증 스크립트가 표준 라이브러리 `json`만으로 돈다. YAML은 PyYAML이 필요해 직접 의존성이 3 → 4개가 되고 `wheels/`에도 실린다 (CLAUDE.md §4.3) |
| OpenAPI 버전 | **3.1.0** | JSON Schema 2020-12와 정합. `type: ["string","null"]`을 쓸 수 있어 nullable 컬럼을 그대로 표현한다 |
| 경로 접두사 | `/api/v1` | 화면이 정적 파일과 같은 오리진에서 붙는다. CORS 설정이 필요 없다 |
| 필드 표기 | **snake_case** | 1369-Part1 속성명·DB 컬럼명과 1:1. camelCase로 바꾸면 대조가 사람 눈으로만 가능해진다 |
| 시각 표기 | ISO 8601 문자열. 단 `frame_log.t`만 epoch 실수 | 프레임 로그는 밀리초 이하 간격이 의미가 있고 replay 타이밍 계산의 입력이다 |
| 오류 형식 | RFC 9457 `application/problem+json` + `clause`·`constraint` | 표준에서 유래한 거부는 **조항 번호와 차단한 DB 제약 이름**을 함께 돌려준다 |
| 인증 | **`X-User-Id` 헤더만** | 표준 3종 어디에도 인증 방식 규정이 없다. 승인 게이트가 "누가"를 기록하게 하는 최소 장치이며, 그 이상은 범위 밖임을 명시한다 |

### 2.1 인증은 범위 밖이다 — 그래서 무엇이 보장되지 않는지 적는다 (F-052)

승인 게이트는 두 문제를 푼다고 오해되기 쉽다. 실제로는 하나만 푼다.

| 문제 | 이 구현이 보장하는가 | 근거 |
|---|---|---|
| **무결성** — 승인 내용과 승인자 기록이 사후 위조되지 않는가 | **보장한다** | DB 트리거 8종 (F-030 · F-039 · F-048 · F-049 · F-091) - 정본 목록은 DB 스키마 설계서 4장 봉인 트리거 표 |
| **신원** — 그 식별자가 정말 그 사람인가 | **보장하지 않는다** | 인증 없음. `X-User-Id`는 호출자의 자체 주장이다 |

`X-User-Id`에 대해 서버가 확인하는 것은 **그 문자열이 사용자정보에 실재하는가**(외래키)뿐이다. 기존 사용자 ID를 알면 누구든 그 이름으로 승인할 수 있다. 표준 3종 어디에도 인증 방식 규정이 없어 구현하지 않았고, localhost 단일 사용자 데모 범위에서는 수용 가능한 결정이다.

**대신 세 곳에 명시한다.**

1. `openapi.json`의 `securitySchemes.UserIdHeader` 설명 — *"이것은 인증이 아니다"*
2. §1 주장표의 "주장하지 않는 것"
3. 시연 시나리오와 기획서 — 사람 승인의 증거력을 무결성 범위로 한정해 서술

검증기가 1번 문구의 존재를 검사한다. 문서에서 슬그머니 사라지면 FAIL이다.

> **실서비스로 넘어간다면** 최소한 세션 기반 사용자 확인이 필요하다. 데이터 모델 쪽 재료는 이미 있다 — 1369-Part1 7.2.2.8 온실관리 관계로 "이 온실을 관리하는 사용자만 승인 가능"이라는 인가(authorization) 제약까지는 DB로 좁힐 수 있다. 다만 그것도 **인가이지 인증이 아니다.** 남은 일정과 98종 제약 테스트의 안정성을 고려해 이번 제출 범위에서는 넣지 않는다.

---

## 3. 엔드포인트 23종 (경로 22)

| 메서드 | 경로 | 태그 | 표준 근거 |
|---|---|---|---|
| GET | `/api/v1/health` | system | 아키텍처 §6.3 |
| GET | `/api/v1/nodes` | ems | 0943 8.1.1 |
| GET | `/api/v1/nodes/{nodeId}` | ems | 0943 표 7-13 |
| GET | `/api/v1/nodes/{nodeId}/devices` | ems | 0943 표 7-15 / 1369-P1 7.2.2.5 |
| GET | `/api/v1/telemetry` | fms | 1369-P1 6.3.3 |
| GET | `/api/v1/device-states` | fms | 1369-P1 6.3.4 |
| GET | `/api/v1/alerts` | fms | 0937 6.4 · 6.5 |
| GET | `/api/v1/frames` | conformance | 0943 7.3 |
| GET | `/api/v1/frames/violations` | conformance | 0943 7.3.1 · 표 7-10 |
| GET | `/api/v1/frames/{frameId}` | conformance | 0943 그림 7-1 |
| GET | `/api/v1/stream` | conformance | 0943 8.1.1 / 0937 6.4·6.5 |
| GET | `/api/v1/publicdata/sources` | dms | 0937 6.2 |
| GET | `/api/v1/publicdata/records` | dms | 0937 6.2 |
| GET | `/api/v1/rules` | mms | 0937 6.3 |
| **POST** | `/api/v1/rules` | mms | 0937 6.3 |
| GET | `/api/v1/rules/{ruleId}` | mms | 0937 6.3 |
| **POST** | `/api/v1/rules/{ruleId}/approve` | mms | 0937 부속서 A 3.2 |
| **POST** | `/api/v1/rules/{ruleId}/execute` | fcs | 0937 6.5 |
| **POST** | `/api/v1/control` | fcs | 0937 부속서 A 1·2 |
| GET | `/api/v1/executions` | fcs | 0937 6.5 |

**쓰기는 7건이다.** 전부 **사람이 유발한 쓰기**다 — 규칙을 만들고, 승인·거부하고, 실행을 지시하고, 수집 설정을 바꾸고, 위반 벡터를 주입한다. **수집 데이터를 API로 넣는 경로는 존재하지 않는다** — 있으면 합성 데이터 주입 통로가 되어 CLAUDE.md §1 #1에 걸린다. 검증기가 허용 집합과 **정확히 대조**한다(개수만 세면 경로가 통째로 바뀌어도 통과한다, F-056).

| 쓰기 | 조항 | 신설 |
|---|---|---|
| `POST /rules` | 0937 6.3 MMS 초안 생성 | |
| `POST /rules/{id}/approve` | 0937 부속서 A 3.2 승인 게이트 | |
| `POST /rules/{id}/reject` | 0937 부속서 A 3.2 거부 | **F-083** |
| `POST /rules/{id}/execute` | 0937 6.5 FCS | |
| `POST /control` | 0937 부속서 A 1·2 수동 제어 | |
| `PATCH /device-property` | 0937 6.4-2 · A.1-3 수집 설정 | **화면 설계** |
| `POST /sim/inject` | 0943 7.3.1 위반 주입 (simulate·replay 전용) | **F-084** |

> **아키텍처 §4.4를 이 단계에서 고쳤다 (F-053).** 초안은 *"DB 쓰기는 I/O 스레드 단독, API 스레드는 읽기 전용(제어 실행 기록만 예외)"* 이었는데, `POST /rules`와 `/approve`는 `control_rule`을 쓰므로 그 예외에 들어가지 않는다. 문서대로 구현하면 **규칙을 저장할 방법이 없다.**
>
> 소유권의 단위를 스레드가 아니라 **테이블**로 바꿨다(아키텍처 §4.4-a). 노드에서 온 데이터는 I/O 스레드가, 사람이 유발한 쓰기는 API 스레드가 쓴다. 교차하는 테이블은 `control_execution` 하나뿐이고 — API가 INSERT, I/O가 응답 필드만 UPDATE — 행의 생애와 컬럼이 분리된다. WAL + `busy_timeout=5000` + `BEGIN IMMEDIATE`가 직렬화를 처리한다.

---

## 4. 설계 판단

### 4.1 노드 종류가 경로에도 스키마에도 없다

가장 쉬운 설계는 `/api/v1/sensors/temperature`, `/api/v1/actuators/valve` 같은 경로다. **그렇게 만드는 순간 "서버 코드 수정 0줄"이 거짓말이 된다.** 새 센서를 붙이면 경로가 늘어난다.

그래서 종류는 **데이터**로만 존재한다.

```
GET /api/v1/telemetry?subtype=TEMPERATURE     ← subtype 은 enum 이 아닌 자유 문자열
GET /api/v1/nodes/3/devices                   ← 응답의 subtype 필드는 레지스트리 조회 결과
```

`Node` 스키마에는 종류 필드가 아예 없다. 0943 표 7-13 `NODE_PROPERTY`에도 없기 때문이다 — 표준을 직역한 결과가 곧 확장성이 된다.

**장치상태는 서브타입마다 속성이 실제로 다르다**(창개폐기=개폐정도, 관수펌프=압력+분사도). 이걸 `oneOf` 6종으로 열거하면 7번째 서브타입에서 스키마를 고쳐야 한다. `attributes` 객체에 서브타입 테이블의 컬럼을 그대로 담아, **DB에 테이블 하나를 더해도 API가 변하지 않게** 했다.

```json
{ "subtype": "IRRIGATION_VALVE", "attributes": { "open_level": 100, "valid_range": "0-100" } }
```

> 대가: 클라이언트가 `attributes` 안을 타입 안전하게 다룰 수 없다. 이 프로젝트에서는 **확장성 주장이 타입 안전성보다 중요**하므로 받아들인다. 화면은 키를 그대로 표시하면 된다.

### 4.2 승인 게이트를 API 표면으로 옮겼다

DB는 이미 트리거 8종으로 승인과 거부를 봉인했다(F-017 · F-030 · F-039 · F-048 · F-049 · F-091). 그럼에도 API를 그냥 CRUD로 열면, **"막히긴 하는데 시도는 할 수 있는"** 상태가 된다. 심사자가 보기에 이건 설계가 아니라 방어다.

세 곳에서 **시도 자체를 불가능하게** 했다.

| 엔드포인트 | 받지 않는 것 | 효과 |
|---|---|---|
| `POST /rules` | `action`, `target_install_id`, `approved_*` | 생성형 AI 출력이 실행 가능한 형태로 저장될 경로가 없다. `additionalProperties: false` |
| `POST /rules/{id}/approve` | `approved_by`, `approved_at` | 승인자는 `X-User-Id` 헤더, 시각은 서버 시계. 클라이언트가 정할 수 없다 |
| `POST /rules/{id}/execute` | **요청 본문 전체** | 명령과 대상을 승인 스냅샷에서 서버가 읽는다. 승인과 다른 제어가 나갈 입력 자체가 없다 |

승인 요청은 `condition_expr` · `action` · `target_install_id` **셋 모두 필수**다. 부분 승인이라는 상태가 없다 — DB의 원자적 승인 UPDATE(F-039)와 정확히 대응한다.

```
POST /api/v1/rules/r-01/approve
X-User-Id: u-01
{ "condition_expr": "forecast.tmax > 33",
  "action": { "value": 1, "value_type": "UINT", "duration_sec": 1200 },
  "target_install_id": "inst-valve-01" }
```

### 4.3 `action`에 대상 장치를 넣지 않는다 (F-049 후속)

F-049에서 `control_rule.target_install_id` 컬럼을 승인 스냅샷의 정본으로 확정했다. 그때 남겨둔 숙제가 *"`action_json` 안에도 대상을 중복 표기할 것인가"* 였다.

**넣지 않는다.** 근거 셋.

1. 두 곳에 두면 어긋난다. 어긋났을 때 어느 쪽이 맞는지 판정할 규칙이 또 필요해진다.
2. SQL은 JSON을 파싱하지 못한다. 컬럼만이 트리거로 대조 가능한 유일한 형태다.
3. `ControlAction`이 순수하게 *"무엇을"* 만 담으면 규칙 실행(`RULE`)과 수동 제어(`MANUAL`)가 같은 타입을 쓸 수 있다. 전자는 대상을 규칙에서, 후자는 요청 본문의 `install_id`에서 얻는다.

```
ControlAction = { value, value_type, duration_sec }      ← '무엇을'
대상('어느 장치를') = RULE   → control_rule.target_install_id
                    MANUAL → ManualControlRequest.install_id
```

**필드를 빼는 것만으로는 부족했다 (F-051).** JSON Schema는 `additionalProperties`를 생략하면 미선언 속성을 **허용**한다. `RuleDraftRequest` 등 최상위 요청 본문에는 `additionalProperties: false`를 걸었지만 중첩된 `ControlAction`에는 빠져 있어서, 아래가 스키마상 유효했다.

```json
{ "condition_expr": "temp > 40",
  "action": { "value": 1, "value_type": "UINT", "install_id": "B" },
  "target_install_id": "A" }
```

대상 A와 B가 동시에 승인 스냅샷에 남고, 구현·화면마다 다른 값을 고를 수 있다. `ControlAction`을 닫힌 객체로 만들었고, **검증기가 이 반례를 실제로 넣어보고 거부되는지 확인한다** — "스키마에 필드가 없다"만 보면 같은 실수를 또 놓친다.

### 4.3-a `value` 범위를 `value_type`이 정한다 (F-054)

`value`를 조건 없는 `number` 하나로 두면 UINT에 음수를, INT에 2^31을, 정수 자리에 소수를 실을 수 있다. F-044에서 프로토콜 계층은 이미 이 값들을 거부하게 만들었지만, **API 계약만 보고 만든 클라이언트는 전송 불가능한 요청을 정상으로 판단한다.** 실패가 SIAP 빌더까지 미뤄지는 것도 나쁘다.

OpenAPI 3.1은 JSON Schema 2020-12이므로 `if`/`then`으로 분기할 수 있다.

| `value_type` | `value` 제약 | 근거 |
|---|---|---|
| `INT` | `integer`, `-2^31 .. 2^31-1` | 0943 표 7-14 (32 bit, 2의 보수) |
| `UINT` | `integer`, `0 .. 2^32-1` | 0943 표 7-14 |
| `FLOAT` | `number`, `±3.4028234663852886e38` | IEEE-754 single의 최대 유한값 (표준 미규정 → 자체 결정) |

**FLOAT에도 범위가 있다 (F-055).** `type: number`만 두면 `1e39`처럼 single precision으로 패킹할 수 없는 값이 승인 스냅샷과 DB까지 들어간 뒤 전송 단계에서 `OverflowError`로 늦게 실패한다. 상한은 `struct`가 반올림으로 받아주는 경계(약 `3.40282357e38`)가 아니라 **표현 가능한 최대 유한값**으로 잡았다 — 더 좁고 설명하기 쉽다. 범위 안의 정밀도 손실은 float32의 성질이므로 오류가 아니다.

프로토콜 계층도 같이 고쳤다. `spec_verify.pack_value()`가 `struct`의 `OverflowError`를 그대로 흘려보내지 않고 `ValueRangeError`로 바꾼다 — 호출자가 잡아야 할 예외가 하나로 유지된다. `inf`·`nan`도 거부한다.

**그 계약이 한 단계 더 앞에서 깨져 있었다 (F-058).** `10**400`은 범위 검사에 닿기도 전에 `float()` 변환에서 `OverflowError`를 낸다. 변환까지 감싸 정규화했고, **정수 경로의 같은 누출도 함께** 고쳤다. 두 계층의 반례 집합에 변환 실패 케이스를 넣어 다시 어긋나지 않게 했다.

검증기는 **F-044의 경계·초과 반례를 그대로 재사용**한다. 인코딩 계층과 API 계층이 같은 반례 집합으로 검증되므로 두 곳의 판정이 어긋날 수 없다.

### 4.4 위반 프레임을 API가 다시 판정하지 않는다

`GET /frames/violations`의 응답 필드는 `code` · `code_name` · `clause` · `detail` 넷이고, 전부 `siap/codec.py`가 채운 값이다. **API에는 판정 로직이 없고, 재판정 엔드포인트도 없다.** 화면은 이렇게만 렌더링한다.

```
INVALID_FORMAT (0x09) — 7.3.1절
Payload Length=24, 실제 수신 18byte
```

`clause`가 응답에 있는 것이 기능 2의 핵심이다 — 심사자가 화면에서 조항 번호를 보고 표준 원문을 펼칠 수 있다.

### 4.5 오류 응답이 조항과 제약 이름을 돌려준다

DB 트리거가 차단하면 그 사실을 삼키지 않고 그대로 올린다.

```json
{ "type": "about:blank",
  "title": "미승인 규칙으로는 제어를 실행할 수 없다",
  "status": 409,
  "detail": "control_execution requires an approved rule",
  "clause": "0937 A.3.2",
  "constraint": "trg_exec_requires_approval" }
```

`constraint`는 디버깅 편의가 아니라 **증거**다. 심사자가 이 이름으로 `schema.sql`을 grep하면 차단의 근거가 애플리케이션 코드가 아니라 DDL에 있음을 즉시 확인할 수 있다.

### 4.6 SSE 이벤트 6종

| event | data | 화면 |
|---|---|---|
| `node_up` | `Node` | 기능 1 — 카드 자동 생성 |
| `node_down` | `Node` | 기능 1 |
| `frame` | `Frame` | 기능 2 — 정상 프레임 흐름 |
| `violation` | `Frame` (`is_valid=false`) | 기능 2 — 붉은 격리 영역 |
| `alert` | `Alert` | 0937 6.4 · 6.5 |
| `execution` | `Execution` | 기능 3 — 제어 왕복 결과 |

폴백은 1초 폴링이다(아키텍처 §8.1). SSE는 단방향이므로 제어 명령은 항상 POST로 나간다 — 스트림으로 제어가 들어올 경로를 만들지 않는다(CLAUDE.md §1 #7).

### 4.7 페이지네이션은 하나의 형태로 통일한다

모든 목록은 `{ items, total, limit, offset }`이다. 커서 방식이 더 정확하지만, 심사자가 `?limit=5`로 직접 두드려볼 수 있는 단순함을 택했다. `limit` 상한은 500 — 프레임 로그가 수만 건이 되어도 브라우저가 죽지 않게 한다.

---

## 5. 스키마 30종과 데이터 출처

| 스키마 | 출처 테이블 | 유도 필드 (컬럼 아님) |
|---|---|---|
| `Node` | 인메모리 레지스트리 + `device_install_info` | — |
| `Device` | `device_install_info` | `device_kind`, `subtype`(레지스트리 조회) |
| `TelemetryPoint` | `env_state_data` + `env_measurement` | `install_id`(`env_measure` 관계) |
| `DeviceState` | `device_state_data` + `dsd_*` | `attributes`, `install_id` |
| `Alert` | `alert` | — |
| `Frame` | `frame_log` | `header`, `kind`, `element_count`, `violations` |
| `FrameHeader` | `frame_log` (분해) | — |
| `Violation` | `frame_violation` | — |
| `PublicDataSource` / `Record` | `public_data_source` / `public_data_record` | — |
| `Rule` | `control_rule` | `action`(JSON 파싱), `approved`(파생) |
| `Execution` | `control_execution` | `command`(JSON 파싱), `result_rsc_name` |

**검증기가 이 표를 강제한다.** 응답 필드가 실재 컬럼인지, 반대로 컬럼이 사유 없이 빠지지 않았는지 양방향으로 대조한다. 개명은 `command_json → command`, `action_json → action` 둘뿐이며 검증기에 명시되어 있다.

---

## 6. 이 문서가 정하지 않은 것

| 항목 | 확정 시점 |
|---|---|
| `condition_expr` 문법 | 기능 3 구현 시. DB는 문자열로만 보관하며 평가는 서비스 계층이 한다 |
| 생성형 AI 제공자·프롬프트 | 기능 3 구현 시. **fixtures 폴백 필수** |
| 기상청 API 응답의 `payload` 내부 구조 | 출처 원문을 그대로 담으므로 강제하지 않는다 |
| 화면 레이아웃·폴링 주기 튜닝 | 구현 시 |
| 인증 | **범위 밖.** §2.1 — 무엇이 보장되지 않는지 함께 적는다 |
| 인가(온실 관리자만 승인 가능) | **이번 제출 범위 밖.** 1369-P1 7.2.2.8로 DB 제약화가 가능하나 일정과 기존 제약 테스트 안정성을 우선했다 |

---

## 7. 검증 결과 — 71/71 통과

`api_verify.py`는 `openapi.json`을 **독립된 출처와 대조**한다. 자기 자신에서 생성한 값을 정답으로 삼지 않는다(CLAUDE.md §10).

| 분류 | 항목 |
|---|---|
| **문서 구조** | OpenAPI 3.1 / `operationId` 20건 고유 / `$ref` 42건 전부 해소 / 고아 스키마 없음 / 경로 파라미터 전부 선언 |
| **`schema.sql` 대조** | 응답 필드가 전부 실재 컬럼(또는 명시된 유도 필드) / 컬럼 미노출 없음(개명·내부 전용 제외) |
| **enum 대조** | 알림 `kind`·`severity` / 실행 `origin` / 규칙 `origin` / 프레임 `direction` — DB CHECK와 일치 |
| **하드코딩 금지** | `subtype`을 스키마에도 질의 파라미터에도 열거하지 않음 |
| **`frame.py` 대조** | `Node.status` = 계약 `Status` / `value_type` = 계약 `ValueType` / **비트 폭 15필드**가 0943 명시값과 일치 |
| **승인 게이트** | 초안 요청이 실행 가능 필드를 받지 않음 / `AI_DRAFT`가 `draft_text`를 받지 않음(F-083) / 승인 요청이 스냅샷 3요소 필수 / 승인자·시각을 실을 수 없음 / `ControlAction`에 대상 없음 / 규칙 실행에 본문 없음 / 승인·수동제어에 사용자 헤더 필수 / 쓰기 7건이 허용 집합과 정확히 일치 / 설정 경로에 제어값 없음 |
| **닫힌 요청 본문 (F-051)** | 제어·승인 요청 스키마 4종이 전부 `additionalProperties: false` |
| **반례 거부 (F-051·F-054·F-055·F-058)** | `ControlAction` **반례 17종 전부 거부 / 정상값 8종 전부 허용** — 스키마에 넣어보고 확인한다 |
| **쓰기 표면 (F-056)** | 쓰기 경로가 허용 집합과 **정확히 일치**(개수가 아니라 집합) / **7건의 태그가 `mms` 3 · `fcs` 2 · `ems` 1 · `conformance` 1** — F-094: "넷 다 mms·fcs" 는 쓰기 4건 시절의 문장이었다 |
| **한계 명시 (F-052)** | `securityScheme` 선언 / *"이것은 인증이 아니다"* 문구 존재 / 승인·수동제어에 `security` 요구 |
| **표준 근거** | 모든 표준 유래 오퍼레이션 설명에 조항 번호 존재 |

### 7.0 반례를 넣어보는 검증기 — 의존성 없이

`ControlAction` 검사는 **스키마에 필드가 있나 없나를 보는 것으로는 부족**하다(F-051이 정확히 그 틈으로 통과했다). 반례를 실제로 평가해야 한다.

`jsonschema` 패키지를 쓰면 직접 의존성이 4개가 되고 `wheels/`에 실린다(CLAUDE.md §4.3). 그래서 필요한 키워드만 구현한 **60줄짜리 평가기를 검증기 안에 두었다** — `type`·`enum`·`const`·`minimum`·`maximum`·`required`·`properties`·`additionalProperties`·`allOf`·`if`/`then`.

> 이 평가기 자체는 개발 중 `jsonschema` 4.26.0과 **20개 케이스에서 판정이 전부 일치**함을 확인했다. 그 대조는 개발 시 1회성이며, 제출물은 표준 라이브러리만으로 돈다.

### 7.1 검증기가 실제로 잡은 것

작성 중 3건이 FAIL로 걸렸다.

| 검출 | 성격 |
|---|---|
| `Execution.origin` enum이 `control_rule`의 CHECK와 대조됨 | **검증기 결함** — `origin` 컬럼이 두 테이블에 있는데 첫 매치를 썼다. 테이블 범위로 좁혀 수정 |
| `command_json`/`action_json` 미노출로 오판정 | **검증기 결함** — 개명 매핑을 몰랐다. `RENAMED` 표를 명시해 수정 |
| 5개 오퍼레이션 설명에 조항 번호 없음 | **명세 결함** — 검사를 완화하지 않고 조항을 채워 넣었다 |
| `find("frame.py")`가 캐시의 pandas 파일을 집음 | **검증기 결함** — 숨김·패키지 디렉터리를 제외하도록 수정. 잘못 집으면 조용히 통과하지 않고 실패하게 했다 |
| 쓰기 경로 검사가 **개수만 셈** | **검증기 결함** — `POST /rules`를 지우고 `POST /health`를 만들어도 4건이라 통과했다. 허용 집합과 정확히 대조하도록 바꾸고 같은 변형으로 재검증했다 (F-056) |

세 번째가 이 검증기를 둔 이유다. CLAUDE.md §3.1의 *"표준에서 유래한 모든 것에 조항 번호를 남긴다"* 는 사람이 지키면 반드시 빠진다.

**그럼에도 초판에서 세 건이 새 나갔다** — `ControlAction`이 열려 있었고(F-051), 정수 범위가 없었고(F-054), FLOAT 범위도 없었다(F-055). 앞의 둘은 *"선언된 필드만 보는"* 검사가 원인이고, 셋째는 **반례 집합 자체가 FLOAT를 안 다뤘다.** 검사 방식을 고쳐도 반례가 빠져 있으면 같은 결과다 — 지금은 세 타입 전부의 경계·초과를 넣는다.

---

## 8. 다음 단계

1. 골든 테스트 벡터 53건 (`contracts/vectors/golden.jsonl`)
2. 펌웨어 설계서 — 노드 상태 머신·비트 패킹·메모리 예산
3. 시연 시나리오 — 영상 2분 구성
4. **작업자 개발 착수** — `backend/api.py`가 이 명세를 구현하고, FastAPI가 생성하는 `/openapi.json`이 본 문서와 일치하는지 대조하는 테스트를 둔다
