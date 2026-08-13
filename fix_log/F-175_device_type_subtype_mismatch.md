# F-175 · Device Type만 뒤집으면 정상 디코드 뒤 ingest 중단

| 항목 | 값 |
|---|---|
| 심각도 | 오류 |
| 분류 | 코드버그 |
| 대상 | `project_code/siap/codec.py:304` · `project_code/backend/ingest.py:235` |
| 발견일 | 2026-08-11 |
| 상태 | 수정완료 |

## 근거

TTAK.KO-10.0943 표 7-14는 Type을 센서 0x00·액추에이터 0x01로, Subtype을 센서-구동기 타입으로 정의하고 Value의 의미도 Type에 따라 센서값·제어값으로 구분한다. 표 7-10은 `INVALID_DEVICE_TYPE(0x05)`를 별도로 둔다.

Frame 구조 명세서 §2.3은 Subtype 최상위 비트로 센서와 액추에이터를 구분하고 `Subtype.dev_type`을 제공한다고 결정했다.

1369-P1 §7.1(6):

> 장치설치 정보는 1개의 장치 정보를 가지며, 1개의 장치정보는 설치된 다수의 장치설치 정보에 포함될 수 있다.

§7.2.2.5는 장치정보 식별자가 설치된 장치의 기본정보를 나타내는 외래키라고 규정한다.

## 현상

F-173 수정은 등록된 `siap_subtype`과 수신 `dmi.subtype`만 비교하며, 둘이 같으면 `dmi.dev_type`을 확인하지 않는다. 처리 기록의 Subtype 집합이 서로소이므로 subtype 하나로 dev_type 불일치까지 걸러진다는 주장은 성립하지 않는다.

`dev_type`은 표 7-14의 독립 1bit 필드라 같은 HUMIDITY subtype에 ACTUATOR를 함께 실을 수 있고, 현재 코덱도 이 조합을 정상 프레임으로 디코드한다.

## 영향

등록 정체성은 HUMIDITY/SENSOR인데 수신 프레임이 HUMIDITY/ACTUATOR이면 F-173 가드를 통과한다. 이후 서비스 계층이 `record_device_state`에 HUMIDITY를 넘겨 `ValueError`로 중단한다.

이 유효 판정 프레임 하나로 I/O 콜백의 DB 반영이 예외를 내며, F-173의 등록 정체성 대조 수정이 완결되지 않았다.

## 재현

node 3/device 1을 HUMIDITY/SENSOR로 등록한 뒤, 같은 subtype과 device ID를 유지하고 표 7-14의 Type bit만 ACTUATOR로 바꾼 프레임을 실제 `siap.codec`으로 인코드·디코드한 다음 `ingest.handle()`에 전달했다.

```text
RAW=12200000010007000010000301814042480000
DECODED_VALID=True
DECODED_VIOLATIONS=[]
DECODED_DEV_TYPE=ACTUATOR
DECODED_SUBTYPE=HUMIDITY
INGEST_OUTCOME=ValueError: 미등록 장치상태 subtype: HUMIDITY
ENV_ROWS=0
DEVICE_STATE_ROWS=0
```

제출된 `pytest siap/tests/ backend/tests/` 260/260과 `pytest backend/tests/` 158/158은 이 반례를 포함하지 않아 모두 통과한다.

---

## Claude 처리 기록

| 일시 | 상태 | 내용 |
|---|---|---|
| 2026-08-11 | 확인 | 재현 그대로 확인 — `DeviceMainInfo.dev_type`은 표 7-14의 독립 1bit 필드(`codec.py:333` `dev_type_raw = r.read(1)`)이고, `Subtype`은 `contracts/frame.py`의 `dev_type` 프로퍼티(`self.value & 0x80`)로 자기 자신의 정의상 dev_type을 이미 갖고 있음을 확인 — 즉 표준·계약 모두 "이 subtype이면 이 dev_type이어야 한다"는 정본을 갖고 있는데 codec.py는 디코드 시 그 둘을 대조하지 않고, F-173도 subtype 코드만 등록값과 비교해 dev_type 자체는 보지 않았다. 지적대로 "Subtype 집합이 서로소라 dev_type 불일치까지 걸러진다"는 F-173 처리 기록의 주장은 **알림이 등록과 다른 subtype을 보낼 때만** 성립하고, **같은 subtype에 다른 dev_type을 실은 경우**(이번 재현)는 걸러내지 못함을 인정 |
| 2026-08-11 | 수정완료 | **수정 위치는 `siap/codec.py`가 아니라 `backend/ingest.py`로 한정**했다 — 이유: `RSC.INVALID_DEVICE_TYPE`(표 7-10)을 codec.py의 `decode_frame()`이 실제로 판정하도록 만드는 것은 위반 8종 표(CLAUDE.md §6.3)에 9번째 케이스를 추가하는 프로토콜 계층 변경이라, 골든 벡터 신설(`golden_layout.py`, "손으로 만들고 코드로 검증") · C/Python 양쪽 디코더 동시 반영(§4.4, "C를 먼저 쓰고 Python으로 옮긴다") · `contracts/vectors/golden.jsonl` 재생성이 딸린 `contracts/` 변경 절차(CLAUDE.md §5, 표준 조항 근거 + 사용자 확인) 대상이다. 이번 신고 범위(ingest 크래시 방지)를 넘어서므로 별도 사용자 확인 없이 진행하지 않았다 — 아래 "보고" 참고. 대신 **backend 계층의 자체 데이터 무결성 가드**로 처리: `ingest.py::_handle_device_value`에서 subtype 일치(F-173) 확인 뒤 `dmi.dev_type is not Subtype(dmi.subtype).dev_type`이면 그 요소를 건너뛴다 — DB join 없이 `Subtype.dev_type` 프로퍼티(이미 계약에 존재, Frame 구조 명세서 §2.3)만으로 판정 가능해 새 쿼리가 필요 없었다. 이 검사가 통과하는 유효 프레임에 한해서만 `record_env_measurement`/`record_device_state` 분기가 실행되므로 `ValueError` 크래시가 원천 차단된다 |
| 2026-08-11 | 보고 | **`siap/codec.py`에 `RSC.INVALID_DEVICE_TYPE` 판정을 추가하는 프로토콜 계층 수정은 이번에 하지 않았다.** 표준(0943 표 7-10)이 이미 이 코드를 예비해 뒀고 근거도 명확하므로, 사용자가 원하면 별도로 CLAUDE.md §5 절차(조항 근거 제시 → 확인 → contracts 변경 → 골든 벡터 재생성 → 위반 케이스 표 갱신)를 밟아 진행할 수 있다 — 이번 backend 가드는 그 상위 수정이 없어도 크래시·오저장을 완전히 막는다 |
| 2026-08-11 | 회귀테스트 | `backend/tests/test_ingest.py::test_handle_device_value_dev_type_inconsistent_with_subtype_is_skipped` 신설 — 재현 그대로 HUMIDITY subtype + ACTUATOR dev_type 조합을 `ingest.handle()`에 넣어 예외 없이 끝나고 `env_measurement`·`device_state_data` 둘 다 0건임을 확인. `cd project_code && python -m pytest backend/tests/` **159/159** 재확인 |
