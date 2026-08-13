# F-126 · COMBINED_PROPERTY의 Num. of Devices와 N 불일치를 수용

| 항목 | 값 |
|---|---|
| 심각도 | 오류 |
| 분류 | 코드버그 |
| 대상 | `project_code/firmware/core/siap_frame.c:122-129,364-423` |
| 발견일 | 2026-08-08 |
| 상태 | 수정완료 |

## 근거

0943 표 7-13 — `Num. of Devices`는 “노드에 연결된 디바이스 수”다. 0943 §7.3.3.4 — “노드-디바이스 통합 속성은 노드 속성과 해당 노드에 연결된 N개 디바이스의 속성 정보를 포함한다.” 표 7-16은 `DEVICE_PROPERTY`를 `(N*240)` bit로 정의한다.

## 현상

`siap_element_count()`는 Payload Length에서 N을 구하지만 고정부의 `NODE_PROPERTY.Num. of Devices`와 비교하지 않는다. `S_FIXED`는 원시 버퍼를 `on_fixed`에 전달할 뿐 코덱 자체가 N과 대조하지 않고 콜백 계약에도 필수 검사로 적혀 있지 않다.

`RES_SET_CONNECTION`에 `Num. of Devices=2`, 실제 `DEVICE_PROPERTY` 1개, Payload Length=39를 넣은 51byte 프레임을 먹이자 C 디코더는 `derived_n=1`을 넘기면서 최종 SUCCESS를 반환했다.

## 영향

같은 프레임이 디바이스 수를 2와 1로 동시에 주장해도 정상 처리된다. F-068에서 골든 생성기·검증기에 고정한 표 7-13/7-16 불변식이 실제 펌웨어 디코더에는 강제되지 않아 기능 2가 모순을 놓친다.

## 재현

```text
헤더 Payload Length=39 -> N=1
NODE_PROPERTY.Num. of Devices=2
DEVICE_PROPERTY 실제 개수=1

derived_n=1 node_property_num_devices=2 end_rsc=0 ends=1
PROBE_EXIT=0

기존 test_siap_frame 104/104, test_golden 253/253 통과
```

## 제안

COMBINED_PROPERTY 3종에서 고정부를 디코드한 뒤 `Num. of Devices == n`을 강제하고 불일치를 `INVALID_FORMAT`/7.3.1로 고정하는 반례를 추가해야 한다.

---

## Claude 처리 기록

| 일시 | 상태 | 내용 |
|---|---|---|
| 2026-08-08 | 확인 | `siap_frame.c` 의 `SIAP_DEC_ST_FIXED` 완료 분기가 `on_fixed` 콜백에 원시 바이트만 넘기고, `NODE_PROPERTY.Num. of Devices` 를 `siap_element_count()` 가 역산한 `d->n` 과 비교하지 않음을 소스에서 확인. `siap_types.h` 의 `SIAP_LAYOUT` 표에서 `elem==SIAP_DP_BYTES && fixed>=SIAP_NP_BYTES` 조건을 만족하는 kind 가 정확히 보고된 "COMBINED_PROPERTY 3종"(`REQ_SET_NODE_DEVICE_PROPERTY_ALL`·`RES_SET_CONNECTION`·`RES_GET_NODE_DEVICE_PROPERTY_ALL`)뿐임을 대조 |
| 2026-08-08 | 수정완료 | `SIAP_DEC_ST_FIXED` 완료 지점에 검사를 추가: `elem_len==SIAP_DP_BYTES && fixed_len>=SIAP_NP_BYTES` 인 경우에만(정확히 COMBINED_PROPERTY 3종을 식별) 고정부의 마지막 byte(NODE_PROPERTY 는 항상 고정부 끝에 오므로 그 마지막 byte 가 `Num. of Devices`)를 `d->n` 과 비교하고, 불일치 시 `on_fixed` 콜백에 넘기기 전에 `INVALID_FORMAT`/`SIAP_CLAUSE_7_3_1` 로 거부·drain 한다(기존 위반 처리 패턴과 동일). 회귀 테스트 `V10`(6종)을 `test_siap_frame.c` `case_stream_violations()` 에 신설 — 보고된 반례 그대로(`Num. of Devices=2`, 실제 `DEVICE_PROPERTY` 1개, Payload Length=39) 재현해 거부되는지, `on_fixed`/`on_element` 가 호출되지 않는지 확인. 결함 주입: 신설 검사 블록만 되돌린 사전수정본으로 빌드·실행 — `V10` 2개 항목이 정확히 실패(121/123)함을 확인, 수정본 복원 후 123/123 재통과. `test_bitpack`(41/41)·`test_status_codes`(53/53)·`test_golden`(253/253, 골든 53건 — SM2 등 기존 N=1 케이스 무회귀 확인)·`tools/core_purity_verify.py`(6/6) 확인. `make clean` 으로 빌드 산출물 정리 |
