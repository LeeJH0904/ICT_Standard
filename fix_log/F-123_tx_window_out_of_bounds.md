# F-123 · 송신 put 함수가 51byte 윈도우 밖에 기록

| 항목 | 값 |
|---|---|
| 심각도 | 오류 |
| 분류 | 코드버그 |
| 대상 | `project_code/firmware/core/siap_frame.h:132-167` · `siap_frame.c:448-504` |
| 발견일 | 2026-08-08 |
| 상태 | 수정완료 |

## 근거

0943 §7.3.3.4는 “노드 속성과 해당 노드에 연결된 N개 디바이스의 속성 정보를 포함한다”고 하며 표 7-16은 `DEVICE_PROPERTY`를 `(N*240)` bit로 정한다. 펌웨어 설계서 §5.8은 TX 윈도우를 51 byte로 제한하고 요소를 스트리밍한다고 결정한다.

## 현상

`siap_enc_t.win`은 51 byte지만 `siap_tx_put_*()`는 남은 용량을 검사하거나 자동 flush하지 않는다. `bitpack`에도 버퍼 용량 인자가 없다.

헤더 12 + RSC 1 + NODE_PROPERTY 8 + DEVICE_PROPERTY 30 = 51 byte를 정상 조립한 뒤 한 바이트 put을 호출하자 함수는 `true`를 반환하고 배열 밖 구조체 패딩을 덮었다.

```text
window=51 bitpos_before=408 byte51_before=A5 offsetof_bitpos=56
bitpos_after=416 byte51_after=5A
```

유효한 N=2 통합 속성을 flush 없이 연속 조립하면 두 번째 30byte 요소가 같은 경로로 침범한다. 기존 SM2 테스트는 N=1로 정확히 51 byte까지만 써서 통과한다.

## 영향

스택·정적 메모리와 `bitpos`·`sent`가 손상될 수 있다. 51byte SRAM 예산을 지키며 N>1을 송신한다는 설계가 현재 API에서 안전하게 강제되지 않는다.

## 재현

```text
1. siap_tx_put_hdr/rsc/np/dp 1회 -> bitpos 408
2. siap_tx_put_device_id(0x5A) -> true
3. ((unsigned char *)&enc)[51] == 0x5A

기존 출구: test_siap_frame 104/104, test_status_codes 53/53,
test_golden 253/253 모두 통과
```

## 제안

모든 송신 진입점이 남은 용량을 검사하고 요소 단위 flush를 강제해야 한다. N=2와 정확히 51/52 byte 경계를 회귀에 넣어야 한다.

---

## Claude 처리 기록

| 일시 | 상태 | 내용 |
|---|---|---|
| 2026-08-08 | 확인 | `siap_tx_put_hdr/rsc/np/dp` 등 6개 진입점 모두 `e->bitpos` 를 `SIAP_TX_WINDOW`(51byte) 와 대조하지 않고 곧장 `bp_write`/`siap_encode_*` 를 호출함을 소스에서 확인. `bitpack.h` 계약 자체에 버퍼 용량 인자가 없어(`bp_write(buf, bitpos, val, nbits)`) 하위 함수는 애초에 경계를 모른다 — 진입점(호출 전)에서 막아야 한다고 판단 |
| 2026-08-08 | 수정완료 | `siap_frame.c` 에 `_tx_has_room(e, need_bytes)` 헬퍼를 추가하고, `siap_types.h` 의 표준 유래 폭 상수(`SIAP_HEADER_BYTES`·`SIAP_RSC_BYTES`·`SIAP_NEC_BYTES`·`SIAP_NP_BYTES`·`SIAP_MCP_BYTES`·`SIAP_DID_BYTES`·`SIAP_DMI_BYTES`·`SIAP_DP_BYTES`)를 그대로 재사용해 6개 `siap_tx_put_*` 진입점 전부가 **encode 호출 전에** 남은 용량을 검사하도록 재작성 — 사후에 `bitpos` 만 되돌리는 방식은 이미 일어난 배열 밖 쓰기를 되돌리지 못하므로 채택하지 않음. `siap_result_t` 를 돌려주는 dmi/dp 경로는 기존 "bp_write 범위 초과" 실패와 동일한 `SIAP_RSC_INVALID_FORMAT`/`SIAP_CLAUSE_7_3_1` 을 재사용(네트워크로 나가지 않는 내부 신호이므로 `.ok` 만 보고 호출자가 flush 후 재시도해야 함을 주석에 명시). 회귀 테스트 `case_tx_window_capacity`(`TXCAP1~4`, 13종)를 `test_siap_frame.c` 에 신설 — 51byte 정확히 채운 뒤 추가 put 이 거부되는지, `win[]` 바로 뒤 구조체 패딩에 심은 카나리가 오염되지 않는지, N=2 통합 속성 재현, 헤더 경로(bool 반환)도 동일 계약을 지키는지 확인. 결함 주입: 6개 진입점의 용량 검사를 전부 되돌린 사전수정본으로 빌드·실행 — `TXCAP2/3/4` 7개 항목이 정확히 실패(110/117)하며 카나리 오염이 실측으로 재현됨을 확인, 수정본 복원 후 재빌드하여 117/117 재통과. `test_bitpack`(41/41)·`test_status_codes`(53/53)·`test_golden`(253/253, 골든 53건)·`tools/core_purity_verify.py`(6/6) 회귀 확인. `make clean` 으로 빌드 산출물 정리(F-111 원칙) |
