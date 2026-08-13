# F-131 · RSC 9종 중 2종만 검사해 오분류 변이가 61/61 통과

| 항목 | 값 |
|---|---|
| 심각도 | 오류 |
| 분류 | 코드버그 |
| 대상 | `project_code/firmware/tests/test_node_state.c:330-375` |
| 발견일 | 2026-08-09 |
| 상태 | 수정완료 |

## 근거

개발 착수 지시서 §3.4 단계 2c GPT 검증은 `RES_SET_CONNECTION` 오류 RSC 9종의 목적지 상태가 CLAUDE.md §3.5와 같은지 검증하도록 요구한다.

CLAUDE.md §3.5는 재시도 가능 2종(`INVALID_GCG_ID`, `INVALID_NODE_ID`)과 불가 7종을 구분하고 불가 7종은 `HALTED`로 간다고 정한다.

## 현상

`test_node_state.c`는 재시도 가능 대표로 `INVALID_NODE_ID` 하나, 불가 대표로 `INVALID_VERSION` 하나만 실행한다. 나머지 7종의 목적 상태는 테스트하지 않는다.

임시 변이에서 `_rsc_retryable()`의 `INVALID_GCG_ID` 분기를 삭제해 재시도 불가로 만들었지만 기존 `test_node_state`는 61/61, 종료 코드 0이었다.

현재 원본 구현은 별도 주입 매트릭스에서 오류 RSC 9종 전부를 실행한 결과 2 CONNECTING / 7 HALTED로 맞았다. 결함은 현재 목적 상태가 아니라 회귀 검증기가 그 사실을 증명하지 못한다는 것이다.

## 영향

F-076 재발 위험이 큰 지점인데 한 행만 잘못 바꾸면 전체 출구가 녹색으로 남는다. `firmware_verify.py` 51/51은 설계 문서 표만 검사하므로 구현 오분류를 보완하지 못한다.

## 재현

```c
static bool _rsc_retryable(siap_rsc_t rsc)
{
    return rsc == SIAP_RSC_INVALID_NODE_ID; /* INVALID_GCG_ID 누락 */
}
```

```text
위 변이와 원본 test_node_state.c를 GCC로 컴파일
결과: 61/61 통과, exit 0
```

## 제안

오류 RSC 9종을 표 기반 매트릭스로 전부 입력하고 각 상태와 pending 유지·해제를 코드별로 직접 비교한다.

---

## Claude 처리 기록

| 일시 | 상태 | 내용 |
|---|---|---|
| 2026-08-09 | 확인 | `test_node_state.c`가 재시도 가능 대표(`INVALID_NODE_ID`) 1종·불가 대표(`INVALID_VERSION`) 1종만 실행함을 확인. 재현 스크립트와 동일하게 `_rsc_retryable()`에서 `INVALID_GCG_ID` 분기를 제거한 사전수정본을 빌드·실행 — 기존 61/61 이 그대로 통과함을 재확인 |
| 2026-08-09 | 수정완료 | `siap_rsc_t`의 non-SUCCESS 9종(0x01~0x09) 전부를 `RES_SET_CONNECTION`에 실어 노드에 보내고 목적 상태를 개별 검사하는 `test_res_set_connection_rsc_matrix_6_5_F131()`을 신설(`_check_rsc_outcome()` 헬퍼로 9행을 각각 독립 fixture 로 실행) — `INVALID_GCG_ID`(0x02)·`INVALID_NODE_ID`(0x03) 2종은 `CONNECTING` 유지 + pending 보존, 나머지 7종은 `HALTED`를 개별 확인. 결함 주입: GPT 재현과 동일한 변이(`_rsc_retryable()`에서 `INVALID_GCG_ID` 제거)로 재빌드·실행 — 신설 매트릭스 중 `INVALID_GCG_ID` 행만 정확히 실패(88/89)함을 확인, 원복 후 재통과. 나머지 회귀(`test_bitpack`·`test_siap_frame`·`test_status_codes`·`test_golden`·`core_purity_verify.py`·`firmware_verify.py`·`run_all.py`) 전량 통과 확인 |
