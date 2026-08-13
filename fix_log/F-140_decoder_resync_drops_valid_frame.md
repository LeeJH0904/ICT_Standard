# F-140 · 초기 위반 헤더가 뒤의 정상 프레임까지 삭제함

| 항목 | 값 |
|---|---|
| 심각도 | 오류 |
| 분류 | 코드버그 |
| 대상 | `project_code/siap/codec.py:547` · `project_code/siap/codec.py:706` |
| 발견일 | 2026-08-09 |
| 상태 | 수정완료 |

## 근거

CLAUDE.md §3.5 및 SIAP 메시지 명세서 §6 #10 — 위반 뒤 재동기는 `Version + resolve_kind + Transmission Type + element_count` 4조건을 동시에 만족하는 시작점을 1바이트씩 찾아야 한다. 이는 프레임 경계 미규정으로 인한 영구 유실을 막기 위한 자체 결정이다.

## 현상

`decode_frame()`은 Version 위반을 payload 수신 여부보다 먼저 반환한다. `Decoder._try_extract()`는 그 위반 Frame의 신뢰할 수 없는 `header.payload_len`을 그대로 사용해 `12 + payload_len`만큼 버퍼를 삭제한 뒤 재동기 모드로 들어간다. Version=0x99, payload_len=65535인 12바이트 헤더 뒤에 정상 12바이트 프레임을 이어 넣으면 두 프레임 24바이트가 모두 삭제되고 정상 프레임은 나오지 않는다.

## 영향

공격적이거나 손상된 헤더 하나가 뒤에 이미 도착한 정상 트래픽 전체를 삼킨다. 선언한 재동기 규칙이 가장 필요한 초기 헤더 위반에서 작동하지 않는다.

## 재현

```text
bad = Header(version=0x99, payload_len=0xFFFF, valid other fields)
good = valid NOTI_KEEP_ALIVE header
list(Decoder(node_known=True).feed(bad + good))
-> [INVALID_VERSION] only; internal buffer length 0
```

## 제안

경계를 신뢰할 수 없는 초기 헤더 위반에서는 선언된 1바이트 재동기 탐색이 버퍼의 후속 후보를 보존하도록 한다.

---

## Claude 처리 기록

| 일시 | 상태 | 내용 |
|---|---|---|
| 2026-08-09 | 확인 | 재현 시나리오(Version=0x99·payload_len=0xFFFF 위반 헤더 + 정상 12byte 프레임을 이어 붙임)를 그대로 실행 — `Decoder._try_extract()`가 위반 프레임의 `header.payload_len`(검증되지 않은 값)을 그대로 신뢰해 `total = 12+65535`만큼(버퍼 실제 길이로 클램프되어 24byte 전부) 지운다는 것, 그 결과 뒤에 이미 도착해 있던 정상 프레임까지 함께 삭제됨을 확인 |
| 2026-08-09 | 수정완료 | `_try_extract()`에서 `frame.violations`가 있으면 `total = 12+payload_len` 전체를 지우는 대신 헤더 12byte만 지우고 `self._resync = True`로 재동기 모드에 진입하도록 변경 — 이미 버퍼에 있는 나머지 바이트(위반 프레임의 남은 부분이든 뒤따르는 정상 프레임이든)를 잃지 않고 §5.7 4조건 1byte 스캔으로 다시 찾는다. 회귀 테스트 추가: `test_codec.py::test_decoder_resync_preserves_trailing_valid_frame_after_header_violation_f140`(재현 시나리오 그대로, 정상 프레임 생존 확인), `test_decoder_resync_recovers_frame_split_across_multiple_feeds_after_violation_f140`(같은 스트림을 두 번의 `feed()` 호출로 나눠도 복구되는지). 결함 주입(옛 무조건 `total` 삭제로 되돌림) 후 두 테스트가 정확히 실패함을 확인(`assert 1 == 2`)하고 원복 — `pytest siap/tests/` 재통과. **참고(이번 수정 범위 밖)**: C 펌웨어(`node_state.c`/`siap_frame.c`)의 스트리밍 디코더도 원리상 같은 종류의 신뢰 문제를 가질 수 있다 — `begin_drain()`이 위반 프레임의 `payload_len`을 그대로 `drain_remaining`에 써서, 바이트 단위로 도착하는 이후 스트림에서 그만큼을 무조건 폐기한다(다만 실패 양상은 다르다: Python처럼 이미 버퍼에 있는 바이트를 즉시 삼키는 게 아니라 향후 도착할 바이트를 삼킨다). 이 발견은 F-140의 대상(`siap/codec.py`)이 아니고 stage 2c에서 이미 검증 완료된 코드를 건드리므로, 사용자 보고 후 별도 판단을 받는 것이 맞다고 판단해 이번에는 고치지 않았다 |
