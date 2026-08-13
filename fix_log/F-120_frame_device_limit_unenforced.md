# F-120 · C 프레임 코덱이 N=16 상한을 강제하지 않음

| 항목 | 값 |
|---|---|
| 심각도 | 오류 |
| 분류 | 코드버그 |
| 대상 | `project_code/firmware/core/siap_frame.c:18-49` |
| 발견일 | 2026-08-08 |
| 상태 | 수정완료 |

## 근거

TTAK.KO-10.0943은 N과 Timeout 관계를 규정하지 않는다(F-065). 이에 대한 프로젝트 결정은 CLAUDE.md §3.5의 “노드당 디바이스 상한 N = 16”이다. 펌웨어 설계서 §3.2는 “본 구현은 §9의 N=16 상한을 넘는 프레임을 `INVALID_FORMAT`으로 거부한다”고 명시한다.

## 현상

`siap_element_count()`는 나눗셈으로 N을 구한 뒤 N=0만 검사하고 `SIAP_MAX_DEVICES_PER_NODE`를 넘는지 검사하지 않는다. `siap_resolve_kind()`도 이 반환값이 0 이상이면 정상 종류로 확정한다.

실제 C 프로브 결과는 다음과 같다.

```text
REQ_SET_DEVICE_CONTROL plen=119 -> N=17
RES_SET_CONNECTION plen=519 -> N=17
resolve control N17 -> kind=13 clause=0
```

## 영향

N=17 이상 프레임이 `INVALID_FORMAT`이 아니라 정상 프레임으로 상위 계층에 전달된다. Timeout 2초와 메모리/디바이스 테이블 산정의 전제인 프로젝트 상한이 코드에서 강제되지 않는다.

## 재현

1. `siap_element_count(SIAP_REQ_SET_DEVICE_CONTROL, 119)`를 호출한다. 요소 크기 7바이트이므로 N=17이다.
2. `siap_resolve_kind(0x000C, 119, SIAP_MODE_STRICT, &clause)`를 호출한다.
3. 실제 결과: N=17, 정상 kind, clause NONE. 기대: 거부 및 `INVALID_FORMAT` 판정 경로.

## 제안

N 산출 뒤 `SIAP_MAX_DEVICES_PER_NODE` 초과를 거부하고 N=16 허용/N=17 거부를 `test_siap_frame`과 골든 경계 벡터에 고정한다. Python 계약과의 정책 위치도 함께 일치시킨다.

---

## Claude 처리 기록

| 일시 | 상태 | 내용 |
|---|---|---|
| 2026-08-08 | 확인 | 보고서의 두 프로브(`siap_element_count(SIAP_REQ_SET_DEVICE_CONTROL,119)`→17, `siap_resolve_kind(0x000C,119,...)`→정상 kind/clause=NONE)를 그대로 재현 — `siap_element_count()`가 나눗셈 후 N=0 만 보고 `SIAP_MAX_DEVICES_PER_NODE` 초과를 검사하지 않음을 확인. `contracts/frame.py::element_count()`도 동일하게 상한이 없어, 이 프로젝트 결정(CLAUDE.md §3.5 "N=16")이 C·Python 어느 쪽에도 코드로 강제돼 있지 않음을 확인 |
| 2026-08-08 | 수정완료 | **CLAUDE.md §5 절차** — ① 근거: CLAUDE.md §3.5(N=16 상한, F-064) · 펌웨어 설계서 §3.2/§9(501byte 최대 프레임 전제) ② 2026-08-08 사용자 승인(F-118~F-120 일괄 처리 승인) ③ `contracts/frame.py`에 `MAX_DEVICES_PER_NODE=16` 상수 신설, `element_count()`에 `n > MAX_DEVICES_PER_NODE` 거부 분기 추가, `siap_frame.c::siap_element_count()`에 동일 상한(`SIAP_MAX_DEVICES_PER_NODE`, 이미 `siap_types.h`에 정의돼 있었으나 미사용) 미러링 ④ 이 절에 이력 기록. 골든에 B11(REQ_SET_DEVICE_CONTROL, N=17, `INVALID_FORMAT/7.3.1`)을 `golden_layout.py`에 신설하고 재생성(52→53건, 경계 10→11, violation 8→9) — `golden_verify.py`의 `derive()`(바이트 독립 재판정)에도 동일 상한 조건을 추가해 교차검증을 유지했다. `test_contract.py`(Python, N=16/17 경계 4케이스)와 `test_siap_frame.c`(C, 동일 4케이스, EC5)에 회귀 케이스 신설. CLAUDE.md·개발_착수_지시서.md·`web_verify.py`의 벡터/검사 건수 인용도 갱신. 결함 주입 재현: `siap_element_count()`의 상한 분기를 되돌리면 `test_siap_frame`의 EC5 4건과 `test_golden`의 B11 관련 3건이 즉시 FAIL 함을 확인 후 재적용. 회귀: `python project_code/contracts/test_contract.py` **62/62** · `make && ./test_siap_frame` **104/104** · `./test_golden` **253/253** · `python project_docs/contracts/vectors/golden_verify.py` **31/31** · `python project_docs/web/web_verify.py` **62/62** |
