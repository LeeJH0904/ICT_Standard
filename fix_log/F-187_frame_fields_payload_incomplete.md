# F-187 · Frame.fields 가 헤더 7필드만 채우고 가변부(DEVICE_MAIN_INFO 등) 필드 분해가 없음

| 항목 | 값 |
|---|---|
| 심각도 | 위험 |
| 분류 | 문서불일치 |
| 대상 | `project_code/backend/api.py::_header_field_slices` · `fix_log/F-085_frame_view_contract_incomplete.md` |
| 발견일 | 2026-08-11 |
| 상태 | 수정완료 |

## 근거

F-085(2026-08-07) 처리 기록 — "서버가 프로토콜 계층의 판독 결과를 `FieldSlice(name, bit_offset, bit_width, raw_value)` 형태로 내보내고... 화면은 이 메타데이터만 렌더링한다." `openapi.json`의 `Frame.fields`는 `required`이고 설명에 "헤더 7필드 + 고정부 + 가변 요소 N개분의 전체 분해"라고 적혀 있다.

## 현상

단계 6 구현 중 `_header_field_slices()`는 `frame_log`에 이미 스칼라로 저장된 헤더 7필드(Version·Message Type·Transmission Type·Message Identifier·Payload Length·GCG ID·Node ID)만 `FieldSlice`로 되돌린다. `DEVICE_MAIN_INFO`·`DEVICE_PROPERTY` 등 가변 요소의 필드 분해는 만들지 않는다 — `element` 는 항상 `null`이다.

이유: 가변 요소 분해는 `Value`가 `Value Type`(INT/UINT/FLOAT)에 따라 32bit 를 다르게 해석해야 하는 등 표준 해석이라 프로토콜 계층(`siap/codec.py`)의 몫인데(CLAUDE.md §3.4), `frame_log`는 그 분해 결과를 저장하지 않고 `raw_hex`만 갖는다. `backend/`가 `siap/` 내부 심볼을 import할 수 없어(CLAUDE.md §2.2), 저장 시점(`ingest.handle()`)에 `Frame` 객체(`contracts/frame.py`, 이미 파싱된 `device_main_infos`·`device_properties`)로부터 분해하거나 `contracts/frame.py`에 새 순수 함수를 추가해야 한다 — 어느 쪽이든 `contracts/` 변경(CLAUDE.md §5 절차: 조항 근거 제시 → 사용자 확인 → 골든 벡터 재생성 → 양쪽 코덱 테스트 재통과) 또는 `frame_log` 스키마 확장이 필요해 이번 단계(`services/`+`api.py`) 범위를 벗어난다.

## 영향

기능 2 화면(검증 뷰)의 필드 분해 패널이 헤더까지만 보여주고, `DEVICE_MAIN_INFO`(예: `Value`)나 `DEVICE_PROPERTY`(예: `Period`)의 비트 단위 표시는 아직 못 한다. 심사자가 페이로드 필드를 직접 보려면 `raw_hex`를 손으로 다시 잘라야 한다.

## 제안

두 방향 중 하나. ① `contracts/frame.py`에 `field_slice(frame: Frame) -> list[FieldSlice]` 순수 함수를 추가하고(§5 절차), `ingest.handle()`이 그 결과를 `frame_log`에 함께 저장(스키마 확장) — 정상 경로. ② `frame_log.raw_hex`와 이미 저장된 `kind`(런타임에 `resolve_kind()`로 유도 가능)만으로 `api.py`가 헤더 이후 가변부를 다시 파싱하지 않고, 대신 프레임 조회 시 `siap/codec.py`를 그 요청에 한해 호출하는 별도 조회 전용 배선을 두는 방법(계층 규칙 예외 지점을 명확히 문서화해야 함). 이번 제출 범위에서는 ①이 더 원칙에 맞는다.

---

## Claude 처리 기록

| 일시 | 상태 | 내용 |
|---|---|---|
| 2026-08-11 | 보류 | 단계 6(`services/`+`api.py`) 범위로 닫을 수 없다 — `contracts/` 변경(§5 절차, 사용자 확인 필요) 또는 `frame_log` 스키마 확장이 선행돼야 한다. 헤더 7필드는 `_header_field_slices()`로 채워 `Frame.fields`의 `required` 계약 자체는 위반하지 않는다(빈 배열이 아니다). 재검토 시점: 화면(`web/`, 단계 7) 구현 시 — 검증 뷰가 실제로 페이로드 필드를 보여줘야 하는 시점에 `contracts/` 변경 여부를 사용자와 다시 확인한다 |
| 2026-08-11 | 수정완료 | **재검토 결과 원래 제안(①, `contracts/frame.py` 변경)을 뒤집었다.** 실제 구현을 앞두고 보니 `_header_field_slices()`와 완전히 같은 패턴 — 비트폭 "표"를 `api.py`에 두고 **이미 디코딩된 값만 옮겨 적는다** — 을 그대로 확장하면 `contracts/frame.py`를 전혀 건드리지 않고 해결된다는 것을 발견했다. `ingest.handle()`이 애초에 `siap/codec.py`가 완전히 디코딩한 `Frame`(`.device_main_infos`·`.device_properties`)을 인자로 받으므로, 그 값을 `frame_log.elements_json`(신설 컬럼)에 그대로 저장해 두면 `api.py`가 조회 시점에 재해석 없이 펼치기만 하면 된다 — 표준 해석은 여전히 `siap/codec.py` 한 곳뿐이다(§3.4). 이는 fix_log의 원래 결론과 다른 방향이라, 그대로 진행하지 않고 **`AskUserQuestion`으로 사용자에게 두 방식(① 원안 contracts/ 변경 vs ② api.py만 확장)을 제시해 확인받았다** — ②를 선택받아 진행했다(§1.3 "설계 문서와 다르게 구현해야 하면 STOP" 원칙 적용, 이번엔 대상이 fix_log 자체의 기존 결론이었다). **구현**: `schema.sql`(`backend/`·`project_docs/db/` 양쪽 동기)에 `frame_log.elements_json TEXT` 신설. `ingest.py::_serialize_elements()`가 `device_properties`/`device_main_infos`를 JSON으로 직렬화해 `insert_frame_log()`에 함께 전달(값은 이미 해석된 것을 그대로 옮길 뿐). `api.py`에 `_DMI_FIELD_LAYOUT`(표 7-14, 56bit)·`_DP_EXTRA_FIELD_LAYOUT`(표 7-15 추가 184bit) 상수 신설 — `siap/codec.py::encode_dmi()`/`encode_dp()`의 `w.write(...)` 순서·폭을 그대로 옮겼다(재해석 아님, `_HEADER_FIELD_LAYOUT`과 같은 원칙). `_payload_field_slices()`가 `elements_json`을 헤더 96bit 뒤에 이어붙는 `FieldSlice` 목록으로 편다. `Value`류 5필드(FLOAT 포함)는 FieldSlice.raw 계약("부호 없는 32bit 원시값")을 지키기 위해 `_value_to_raw_bits()`로 IEEE-754/2의 보수 역산 — 이는 고정 산술 규칙이지 표준 재해석이 아니다(§3.4가 막는 건 판정 로직 중복이다). **파급 수정**: `project_docs/api/api_verify.py`의 `INTERNAL` 표에 `frame_log.elements_json` 추가(F-085 원칙 — `fields` 자체는 저장하지 않고 매 요청 재계산하므로 코덱↔DB 드리프트가 없다는 기존 근거와 정합). `DB_스키마_설계서.md`의 별도 DDL 사본도 동기화. **회귀 테스트**: `test_ingest.py` +2(DEVICE_PROPERTY/DEVICE_MAIN_INFO 각각 elements_json 저장 확인), `test_api.py` +1(`GET /frames/{id}`가 헤더 7 + DMI 6필드를 정확한 bit_offset·bit_width·raw(IEEE-754 포함)로 반환하는지 end-to-end 확인). 검증: `pytest siap/tests/ backend/tests/` 340→**343/343** · `python project_docs/db/verify.py` **109/109**(무변화) · `python tools/db_live_verify.py` **15/15** · `python project_docs/api/api_verify.py` **71/71** · `python tools/route_verify.py`·`gate_e2e.py`(19/19)·`nodetype_verify.py`·`services_verify.py` 전부 유지 · `python fix_log/meta_verify.py` **105/105**(스키마 사본 3곳 동기 확인 포함) |
