# F-127 · 표준 예약값 4종을 정상 프레임으로 수용

| 항목 | 값 |
|---|---|
| 심각도 | 오류 |
| 분류 | 코드버그 |
| 대상 | `project_code/firmware/core/siap_frame.c:122-201,364-440,495-506` |
| 발견일 | 2026-08-08 |
| 상태 | 수정완료 |

## 근거

0943 표 7-10 — `RSC 0x0A~0xFF`는 Reserved다. 표 7-12 — `NEC 0x0A~0xFF`는 Reserved다. 표 7-13 — `NODE_PROPERTY.Status 0x03~0xFF`는 RESERVED다. 표 7-15 — `Transfer Mode 0x03`과 `Status 0x03~0xFF`는 Reserved다.

## 현상

`siap_decode_dmi()`는 `Value Type`과 `Subtype`을 검사하지만, `siap_decode_np()`와 `siap_decode_dp()`는 위 예약값 도메인을 검사하지 않는다. 스트리밍 고정부 경로도 RSC·NEC 값을 검사하지 않고 `on_fixed`에 넘긴 뒤 최종 `SUCCESS`를 보고한다. 송신의 `siap_tx_put_rsc()`·`siap_tx_put_nec()`와 구조체 인코더도 같은 예약값을 생성한다.

임시 C 프로브로 다음 4종을 실제 프레임으로 인코드해 수신기에 넣었고 모두 `rsc=0x00`, `clause=NONE`으로 끝났다.

- `NODE_PROPERTY.Status=0x03`
- `DEVICE_PROPERTY.Transfer Mode=0x03, Status=0x03`
- `RSC=0x0A`
- `NEC=0x0A`

기존 단계 2b 출구는 같은 상태에서 `test_siap_frame 123/123`, `test_status_codes 53/53`, `test_golden 253/253`으로 전부 통과했다.

## 영향

표준이 예약한 값을 정상 데이터·상태 코드로 송수신한다. 기능 2가 표 7-14의 예약 `Value Type`만 잡고 같은 표준의 다른 예약 도메인은 정상으로 표시하므로 표준 준수 판정이 불완전하다.

## 재현

1. 정상 헤더 뒤에 위 네 페이로드 중 하나를 붙인다.
2. `siap_dec_init()` 후 프레임 바이트를 `siap_dec_feed()`에 순서대로 넣는다.
3. `on_end` 결과를 확인한다.
4. 실측 결과: 네 경우 모두 `SIAP_RSC_SUCCESS`, `SIAP_CLAUSE_NONE`.

## 제안

표 7-10~7-15의 각 유효 도메인을 송신과 수신 양쪽에서 강제하고, 예약값마다 기대 RSC와 clause를 고정한 반례를 단계 2b 테스트에 추가한다.

---

## Claude 처리 기록

| 일시 | 상태 | 내용 |
|---|---|---|
| 2026-08-08 | 확인 | 보고된 4개 반례(`NODE_PROPERTY.Status=0x03`·`DEVICE_PROPERTY.Transfer Mode=0x03`·`RSC=0x0A`·`NEC=0x0A`)를 스트리밍 디코더에 직접 넣어 전부 `SIAP_RSC_SUCCESS`로 종료됨을 재현. `siap_decode_dmi`는 `value_type`/`subtype`을 검사하지만 `siap_decode_np`(status)·`siap_decode_dp`(transfer_mode/status)·스트리밍 FIXED 경로(RSC/NEC)는 예약값 도메인을 검사하지 않음을 소스에서 확인. 인코드 쪽(`siap_encode_np`·`siap_encode_dp`·`siap_tx_put_rsc`·`siap_tx_put_nec`)도 동일하게 미검사임을 확인 |
| 2026-08-08 | 수정완료 | `siap_types.h`에 도메인 판정 함수 4종(`siap_rsc_valid`·`siap_nec_valid`·`siap_transfer_mode_valid`·`siap_status_valid`, 기존 `siap_trans_type_valid`와 동일 원칙) 신설. 인코드 측: `siap_encode_np`(status, bp_write 전 검사로 all-or-nothing 유지)·`siap_encode_dp`(transfer_mode/status, main DMI 인코딩 전 검사)·`siap_tx_put_rsc`/`siap_tx_put_nec`(enum 밖 캐스팅 방어) 4곳에 검사 추가. 디코드 측: `siap_decode_dp`에 transfer_mode/status 검사 추가(요소 30byte 전부 읽은 뒤 판정, §5.6 고정폭 원칙 유지) — 이것으로 ELEM 경로(DEVICE_PROPERTY)는 완결. FIXED 경로(RSC·NEC·NODE_PROPERTY.Status)는 원시 바이트만 `on_fixed`로 넘어가는 구조라 별도 처리가 필요해, `siap_dec_feed`의 `SIAP_DEC_ST_FIXED` 완료 지점(F-126과 같은 자리)에 검사를 추가 — 종류별 식별은 opaque byte 크기(예: RSC+MCP도 우연히 8byte)로는 안 되므로 `_kind_has_leading_rsc()`·`_np_offset_in_fixed()` 두 헬퍼로 `siap_kind_t` 를 직접 식별. 회귀 테스트 20종 신설: `case_struct_roundtrip`에 ST9~ST13(인코드 거부 5종), `case_stream_violations`에 V11~V14(디코드 거부 4종, 그중 V13·V14는 인코더가 이제 예약값을 거부하므로 `bp_write`로 원시 바이트를 직접 구성해 "이미 만들어진 악성 프레임"을 재현). 결함 주입: `siap_frame.c`의 F-127 추가분 전체를 되돌린 사전수정본으로 빌드·실행 — 신설 20종 중 13종이 정확히 실패(130/143, ST9~ST13·V11~V14의 판정 항목)함을 확인, 수정본 복원 후 143/143 재통과. `test_bitpack`(41/41)·`test_status_codes`(53/53)·`test_golden`(253/253, 골든 53건 — 기존 정상 벡터가 새 도메인 검사에 오탐되지 않음 확인)·`tools/core_purity_verify.py`(6/6, 신설 헬퍼가 보드 매크로로 오판되지 않음) 회귀 확인 |
