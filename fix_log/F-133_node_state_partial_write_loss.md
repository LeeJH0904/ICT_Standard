# F-133 · UART 포화 시 미전송 헤더가 덮어써져 프레임이 유실

| 항목 | 값 |
|---|---|
| 심각도 | 오류 |
| 분류 | 코드버그 |
| 대상 | `project_code/firmware/core/node_state.c:150-190` · `project_code/firmware/tests/test_node_state.c:44-51` |
| 발견일 | 2026-08-09 |
| 상태 | 수정완료 |

## 근거

펌웨어 설계서 §5.8 — `siap_io_t.write`는 요청보다 적게 쓸 수 있고 UART 버퍼 포화 시 인코더가 미기록 잔여를 보존해 다음 `siap_node_poll()`에서 이어서 써야 한다.

`siap_types.h:318-319`도 `write`를 논블로킹·부분 쓰기 허용 계약으로 선언하고, `siap_frame.h:160-162`는 잔여를 윈도우에 남긴다고 정한다.

## 현상

`NOTI_DEVICE_VALUE` 인코딩은 헤더를 `_tx_flush()`한 직후 결과가 `SIAP_TX_PENDING`인지 확인하지 않고 `siap_tx_reset()`으로 같은 인코더를 초기화해 첫 DMI 요소를 쓴다. UART가 헤더 일부만 받고 다음 호출에서 0을 반환하면 헤더의 미전송 잔여가 DMI로 덮어써진다.

기존 페이크 `fio_write()`는 매번 요청 길이 전부를 받아 부분 쓰기 경로를 실행하지 않는다. poll마다 4 byte만 받고 이후 0을 반환하는 페이크를 사용하자 완성되어야 할 header 12 + DMI 7 = 19 byte가 보존되지 않았다. 기존 61개는 전부 통과하고 이 반례만 실패했다.

## 영향

실제 UART 송신 버퍼가 포화되면 잘린 헤더와 고아 DMI 바이트가 전송되어 게이트웨이가 프레임을 디코드할 수 없다. 재전송도 같은 경로를 사용하므로 복구가 보장되지 않는다. 설계서가 명시한 논블로킹 스트리밍 계약 위반이다.

## 재현

```text
1. fio_write를 poll당 최대 4 byte, 이후 0 반환으로 구성
2. RUNNING에서 Period 만료로 NOTI_DEVICE_VALUE 송신
3. 다음 poll마다 quota 4 byte를 다시 부여
4. 기대 총길이 19 byte 보존
5. 실제 19 byte 아님 -> 주입 테스트 FAIL, 총 61/62
```

## 제안

하나의 청크가 완전히 flush되기 전에 같은 인코더 윈도우를 reset하지 않는 송신 상태를 두고, `test_node_state`에 0 반환을 포함한 backpressure 페이크를 추가한다.

---

## Claude 처리 기록

| 일시 | 상태 | 내용 |
|---|---|---|
| 2026-08-09 | 확인 | `NOTI_DEVICE_VALUE`뿐 아니라 `RES_GET_DEVICE_PROPERTY`·`RES_GET_NODE_DEVICE_PROPERTY_ALL`·`RES_GET_DEVICE_VALUE` 4곳 모두가 같은 패턴(헤더 flush 결과를 안 보고 곧장 `siap_tx_reset()`으로 다음 요소를 쌓음)임을 소스에서 확인 — F-133 은 이 4곳 전부에 해당하는 구조적 결함 |
| 2026-08-09 | 수정완료 | 4곳을 공통 "다중 청크 송신 시퀀서"(`siap_tx_seq_t`, `node_state.h`)로 통합 재작성. 불변식: **이전 청크가 `tx_busy==false`로 완전히 빠져나가기 전에는 절대 `siap_tx_reset()`을 부르지 않는다** — `_tx_seq_pump()`의 `while` 루프 조건이 이를 강제하고, 부분 쓰기로 `tx_busy`가 true 로 남으면 그 poll 에서는 다음 청크를 만들지 않고 그대로 반환해 다음 `siap_node_poll()`이 이어받는다. `siap_node_poll()`에 `if (!node->tx_busy) _tx_seq_pump(node);`를 추가해 매 poll 마다 시퀀스를 이어간다. `_pending_encode()`의 NOTI_DEVICE_VALUE 분기와 `_reply_get_device_property/_reply_get_node_device_property_all/_reply_get_device_value` 3개를 전부 이 시퀀서 경유로 교체(코드 중복 제거 겸함). 회귀 테스트 `test_multi_chunk_send_survives_partial_write_F133()` 신설 — `fake_io_t`에 `budget_enabled`/`budget_left`(poll 당 write 상한을 흉내내는 백프레셔) 필드를 추가하고 poll 당 4byte 로 제한한 상태에서 헤더 12B+DMI 7B=19B 프레임이 여러 poll 에 걸쳐 손실 없이 완성되는지 확인. 결함 주입: `_tx_seq_pump()`의 `while` 조건에서 `!node->tx_busy` 가드를 제거한 사전수정본으로 실행 — 신설 검사 3건이 정확히 실패(86/89)함을 확인, 원복 후 재통과. `test_bitpack`(41/41)·`test_siap_frame`(143/143)·`test_status_codes`(53/53)·`test_golden`(253/253)·`core_purity_verify.py`(7/7)·`firmware_verify.py`(51/51)·`tools/run_all.py`(12/12) 회귀 확인. 잔여 관찰(수정 범위 밖으로 판단, 별건 보고): 서로 다른 두 프레임이 같은 poll 안에서 경합하는 경우(이전 다중 청크 시퀀스가 아직 끝나지 않았는데 새 RES_* 응답이 시작되는 등)는 `node->enc`의 부분 전송분 자체는 손상되지 않지만 `tx_seq` 메타데이터가 새 요청으로 덮어써져 이전 시퀀스의 "남은 요소"가 조용히 누락될 수 있다 — 실제 발생하려면 51byte 미만 UART 백로그가 쌓인 채 완전한 요청 프레임이 같은 poll 에 도착해야 해 드물지만, 완전한 해결에는 송신 큐가 필요해 이번 4건 범위를 벗어난다고 판단, 세션 보고에서 사용자에게 알림 |
