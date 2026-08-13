# F-119 · C 골든 테스트가 기대 kind와 N을 대조하지 않음

| 항목 | 값 |
|---|---|
| 심각도 | 오류 |
| 분류 | 코드버그 |
| 대상 | `project_code/firmware/tests/test_golden.c:270-326` |
| 발견일 | 2026-08-08 |
| 상태 | 수정완료 |

## 근거

개발 착수 지시서 §3.3 출구는 골든 52건 전량 대조를 요구하고, GPT 검증 ①은 N 산출 분기가 Python `LAYOUT`과 줄 단위로 대응하는지 확인하도록 한다. `test_golden.c` 서두도 기대 `kind/n/judgement/violations`가 같은지 검사한다고 선언한다.

## 현상

`run_vector()`는 JSON에서 `judgement`, `hex`, 첫 violation만 추출한다. 디코더가 콜백으로 전달한 `g.kind`와 `g.n`은 저장하지만 JSON의 기대 `kind`와 `n`을 읽지도, 비교하지도 않는다.

`siap_resolve_kind(0x0007, 0)`이 `REQ_GET_NODE_PROPERTY` 대신 동일한 `(fixed=0, elem=0)` 레이아웃의 `REQ_GET_NODE_DEVICE_PROPERTY_ALL`을 반환하도록 임시 결함을 주입했다. B02만 F-116 제안대로 위반 판정으로 보정한 임시 골든에서 다음이 모두 통과했다.

```text
test_siap_frame   94/94, exit 0
test_status_codes 53/53, exit 0
test_golden       149/149, exit 0
```

## 영향

메시지 코드를 잘못된 논리 종류로 전달해 상위 상태 머신이 다른 동작을 수행해도 레이아웃과 원본 헤더 바이트만 같으면 단계 2b 전체 C 테스트가 녹색이다. 골든이 상호운용 의미를 검증한다는 주장이 성립하지 않는다.

## 재현

1. 임시 `siap_frame.c`에서 `msg_type=0x0007`, `payload_len=0`일 때 `SIAP_REQ_GET_NODE_DEVICE_PROPERTY_ALL`을 반환한다.
2. B02 판정만 `INVALID_FORMAT/7.3.1`로 보정한 임시 `golden.jsonl`을 사용한다.
3. 현재 CFLAGS로 2b 테스트 3종을 빌드·실행한다.
4. 실제 결과는 위와 같이 전부 exit 0이다.

## 제안

모든 벡터에서 JSON의 `kind`와 `n`을 독립 추출해 `g.kind`, `g.n`과 직접 비교한다. 동일 레이아웃 메시지끼리 잘못 매핑하는 결함 주입을 회귀로 고정한다.

---

## Claude 처리 기록

| 일시 | 상태 | 내용 |
|---|---|---|
| 2026-08-08 | 확인 | 보고서의 임시 결함(`msg_type=0x0007,plen=0`일 때 `SIAP_REQ_GET_NODE_DEVICE_PROPERTY_ALL` 오반환) + B02 판정 보정 골든으로 재현 — `test_golden.c`가 `g.kind`/`g.n`을 저장만 하고 JSON의 기대 `kind`/`n`과 비교하지 않아 149/149 거짓 통과함을 확인. 이 과정에서 **별도의 실제 결함**도 발견: `siap_resolve_kind()`가 단일 후보에도 항상 `element_count()`를 검사해 `contracts/frame.py::resolve_kind()`(단일 후보는 무조건 확정)와 분기 구조가 달랐다(펌웨어 설계서 §5.3 위반) — 최종 판정은 우연히 같았으나 별도 처리 필요로 판단 |
| 2026-08-08 | 수정완료 | ① `siap_resolve_kind()` 를 Python 원본과 동일하게 재작성(단일 후보 즉시 확정 / 다중 후보만 `element_count()` 루프) — 이 변경으로 `handle_header_complete()` 에 단일 후보 확정 후 별도 `element_count()` 재검사를 추가하고, `test_siap_frame.c` RK6(extended 0x0801) 테스트를 실제 동작에 맞춰 정정, RK1b·V9 케이스를 신설해 B02 형 경로(단일 후보 + element_count 실패)를 독립 검증. ② `test_golden.c` 에 `kind_from_str()`(34종 전량 수기 나열)를 신설하고, `run_vector()` 에서 헤더 바이트로부터 직접 `siap_resolve_kind()`/`siap_element_count()` 를 불러(FSM 콜백과 독립적으로) JSON 의 기대 `kind`/`n` 과 비교하는 검사 2종을 52건 전량에 추가. 결함 주입 재현: 보고서와 동일한 `msg_type=0x0007,plen=0 → REQ_GET_NODE_DEVICE_PROPERTY_ALL` 하드코딩을 `siap_resolve_kind()` 상단에 주입 → `test_golden` 이 정확히 `FAIL N03: siap_resolve_kind() 가 골든의 기대 kind와 일치` 로 검출(249/250), 원상복구 후 재확인. 회귀: `make && ./test_siap_frame` **104/104** · `./test_golden` **253/253**(F-120 의 B11 포함) · `python project_code/contracts/test_contract.py` **62/62** |
