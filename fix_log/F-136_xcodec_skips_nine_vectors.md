# F-136 · xcodec 검증기가 골든 9건을 교차 비교에서 제외함

| 항목 | 값 |
|---|---|
| 심각도 | 오류 |
| 분류 | 코드버그 |
| 대상 | `tools/xcodec_verify.py:8` · `tools/xcodec_verify.py:103` |
| 발견일 | 2026-08-09 |
| 상태 | 수정완료 |

## 근거

개발 착수 지시서 §3.5 단계 3 — “C 인코더 출력 ↔ Python 인코더 출력을 골든 53건 전량에서 바이트 비교.” CLAUDE.md §6.2 — “검증기는 검증 대상 파일 하나만 읽지 않는다.”

## 현상

검증기는 `judgement in (normal, alert)`인 44건만 C와 Python에서 decode→encode하고, `violation` 9건은 `44+9=53`이라는 항등식에만 포함한다. 실행 결과도 “44건 전량 바이트 일치”인데 전체 검증은 6/6으로 성공한다. 또한 빌더·발번기를 호출하지 않아 F-135의 실제 `0xFFFF→1` 구현이 존재해도 B04·B05의 완성 바이트를 다시 읽고 쓰는 검사만 통과한다.

## 영향

단계 출구가 요구한 53건 전량의 두 구현 대조를 증명하지 못한다. 현재의 표준 위반 코드가 검증기를 그대로 통과하므로 F-080 유형의 자기 순환 사각지점이 재발했다.

## 재현

```text
python tools/xcodec_verify.py
PASS 재인코딩 대상 44건 + 위반 판정 9건 = 53건
PASS C ↔ Python ↔ golden 44건 일치
6/6 통과

동시에 MsgIdAllocator의 실제 출력: 0xFFFF, 0x0001 (F-135)
```

## 제안

53개 벡터 모두에 대해 C·Python의 독립 입력 구성 또는 동등한 인코더 진입점을 호출하고, 위반 벡터는 제외하지 말고 양쪽의 거부 판정까지 전량 대조한다. 실제 발번기 경계도 독립 입력으로 포함한다.

---

## Claude 처리 기록

| 일시 | 상태 | 내용 |
|---|---|---|
| 2026-08-09 | 확인 | `tools/xcodec_verify.py`가 `judgement in (normal, alert)` 44건만 C↔Python 재인코딩 대조하고, `violation` 9건은 "44+9=53" 항등식 통과에만 쓰였을 뿐 양쪽 언어에서 독립적으로 재구성·대조되지 않음을 소스에서 확인. `dump_golden.c`가 violation 벡터의 판정(RSC+clause)을 아예 출력하지 않아 애초에 대조할 방법이 없었음을 확인 |
| 2026-08-09 | 수정완료 | `firmware/tests/dump_golden.c`를 확장 — judgement=violation 벡터도 디코드해 `"<id> VIOLATION <rsc> <clause>"` 형식으로 출력(`clause_to_str()` 신설, `parse_clause()`의 역함수). 이 과정에서 2차 결함 발견: dump_golden.c의 `g_on_header()`가 Node ID 등록 여부를 전혀 흉내내지 않아(위반 판정 자체를 시뮬레이션하지 않음) X02(unregistered_node)가 거짓으로 SUCCESS 판정됐다 — `test_golden.c::run_vector()`와 동일한 `self_node_id` 시뮬레이션(`extract_first_violation_code()`+`extract_int()` 신설)을 이식해 해소. `tools/xcodec_verify.py`를 재작성 — `_build_and_run_c_dump()`가 이제 (재인코딩 hex, {id:(rsc,clause)} 위반 판정) 두 딕셔너리를 반환하고, `main()`이 위반 9건에 대해 C 판정↔Python 판정(`codec.decode_frame().violations[0]`)↔golden.jsonl 기대값 3중 대조를 새 검사 항목으로 추가(6→8개 검사). 결함 주입(`dump_golden.c`의 self_node_id 판정 제거) 후 새 검사 2개가 정확히 실패(6/8, X02 SKIP)함을 확인하고 원복 — `python tools/xcodec_verify.py` 8/8 재통과(53건 = 재인코딩 44건 + 위반 판정 9건 전량 대조) |
