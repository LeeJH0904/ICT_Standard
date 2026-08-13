# F-141 · C 디코더가 위반 헤더의 거짓 길이만큼 미래 프레임을 폐기함

| 항목 | 값 |
|---|---|
| 심각도 | 오류 |
| 분류 | 코드버그 |
| 대상 | `project_code/firmware/core/siap_frame.c:270` · `project_code/firmware/core/siap_frame.c:337` |
| 발견일 | 2026-08-09 |
| 상태 | 수정완료 |

## 근거

`CLAUDE.md` §3.5 및 펌웨어 설계서 §5.7 — “S_DRAIN 이나 헤더 위반 후 … 1 byte 씩 전진하며 다음 12 byte 를 헤더로 시험한다. 아래 4조건을 모두 만족할 때만 프레임 시작으로 인정한다.” 4조건은 `Version`·`resolve_kind`·`Transmission Type`·`element_count`다.

## 현상

`handle_header_complete()`은 Version·Message Type·Payload Length 형식·Transmission Type·Node ID 위반에서 `begin_drain(d, h.payload_len)`을 호출한다. `begin_drain()`은 아직 신뢰할 수 없는 위반 헤더의 `payload_len`을 `drain_remaining`에 그대로 저장하고, `SIAP_DEC_ST_DRAIN`은 이후 도착하는 바이트를 헤더 후보로 시험하지 않은 채 그 수만큼 무조건 버린다.

Version=0x99, Payload Length=12인 위반 헤더가 실제 payload 없이 끝나고 정상 ACK 12byte가 바로 이어지는 스트림을 먹이면, 위반 1건만 보고되고 정상 ACK 전부가 drain된다. 설계서가 선언한 “헤더 위반 후 1byte 전진 4조건 재동기”가 실행되지 않는다. Python F-140과 원인은 같지만 대상 구현과 실패 시점이 다르다. Python은 이미 버퍼에 있는 뒤 프레임을 즉시 삭제했고, C는 미래에 도착하는 뒤 프레임을 삭제한다.

## 영향

손상되거나 공격적인 헤더 하나가 뒤따르는 정상 요청·응답·ACK를 최대 65,535byte까지 유실시킬 수 있다. 정상 ACK 유실은 불필요한 재전송·타임아웃·연결 단절로 이어지며, C 펌웨어의 자체 재동기 보장과 Python/C 대칭 주장을 깨뜨린다.

## 재현

저장소 소스를 수정하지 않고 임시 C 하니스를 GCC stdin으로 빌드해 다음 순서로 `siap_dec_feed()`에 입력한다.

```
1. Version=0x99, msg_type=ACK, payload_len=12인 헤더 12byte
2. Version=0x12, msg_type=ACK, payload_len=0인 정상 헤더 12byte

실측 출력:
after bad-header + valid-ACK: invalid=1 success=0 headers=0 state=0 drain_remaining=0
```

정상이라면 `invalid=1`, `success=1`, `headers=1`이어야 한다. 현재는 정상 ACK가 헤더 콜백에도 도달하지 않는다.

## 제안

헤더 단계 위반에서는 `payload_len` 기반 선폐기를 하지 말고 즉시 §5.7의 1byte 슬라이딩 재동기로 전환해야 한다. 이미 실제로 소비해 경계가 확정된 고정부·요소 뒤의 잔여 폐기와, 헤더 자체가 위반인 경우를 구분해야 한다.

---

## Claude 처리 기록

| 일시 | 상태 | 내용 |
|---|---|---|
| 2026-08-09 | 확인 | 보고된 재현 시나리오를 그대로 실행해 확인 — `handle_header_complete()`의 비-resync 분기에서 헤더 위반 5종(Version·resolve_kind 실패·element_count<0·Transmission Type·on_header 의 Node ID 거부) 전부가 아직 어떤 구조로도 확인되지 않은 `h.payload_len` 을 그대로 `begin_drain()` 에 넘겨, `SIAP_DEC_ST_DRAIN` 이 그 수만큼 이후 도착하는 바이트를 무조건 폐기함을 소스에서 확인. Version=0x99·payload_len=12 뒤에 정상 ACK 12byte 를 이어 붙이면 위반 1건만 보고되고 정상 ACK 가 통째로 drain 됨을 재현. §5.7 설계 자체(상태도·프로세 텍스트)도 "헤더 위반 → S_DRAIN(plen 만큼 버림)"으로 이 동작을 그대로 규정하고 있어, 구현뿐 아니라 설계 문서도 함께 틀렸음을 확인 |
| 2026-08-09 | 수정완료 | **코드**: `handle_header_complete()`의 5개 헤더 위반 호출부(Version·resolve_kind None·element_count<0·Transmission Type·on_header 거부) 전부 `begin_drain(d, h.payload_len)` → `begin_drain(d, 0)` 으로 변경 — remaining=0 이면 `begin_drain()` 이 즉시 `SIAP_DEC_ST_HDR`+`resync=true` 로 전이해, 아무것도 선폐기하지 않고 바로 §5.7 1byte 슬라이딩 재동기로 넘어간다. `S_FIXED`/`S_ELEM` 단계 위반(F-126·F-127·on_fixed/on_element 거부·dmi/dp 디코드 실패)의 `begin_drain(d, remaining)` 호출은 그대로 두었다 — 그 시점에는 4조건이 전부 통과해 `payload_len` 이 이미 구조적으로 검증된 뒤라 실제 잔여를 정확히 아는 상태이기 때문이다(코드에 이 구분을 주석으로 명시). **설계 문서**: `펌웨어_설계서.md` §5.1 상태도의 "헤더 위반 → S_DRAIN(plen 만큼 버림)" 화살표를 "헤더 위반 → S_SYNC(재동기, F-141)"로, `S_DRAIN` 설명 문단에 이 값어치가 "payload_len 이 구조적으로 확인된 뒤"에만 성립한다는 단서를 추가. §5.7 재동기 규칙 텍스트도 "S_DRAIN 이나 헤더 위반 후"를 "S_DRAIN 완료 후, 또는 헤더 위반 즉시(선폐기 없이)"로 정정하고 두 경로의 차이를 설명하는 문단을 추가. **회귀 테스트**: `test_siap_frame.c::case_resync_header_violation_nonzero_payload_len_f141()` 신설 — 기존 `case_resync()`(RS1/RS3)는 위반 헤더의 payload_len 이 우연히 0이라 이 결함을 전혀 가리지 못했으므로, payload_len=12(뒤따르는 정상 ACK 와 우연히 같은 길이)인 위반 헤더로 재현 그대로를 재구성. **결함 주입**: `siap_frame.c` 를 백업한 뒤 Python find/replace 로 5개 호출부를 전부 `begin_drain(d, h.payload_len)` 으로 되돌리고 재빌드 — 신설 검사 2건(RSN1의 상태 확인, RSN2의 프레임 인식)이 정확히 FAIL 하고 기존 RS1/RS3 는 여전히 PASS(우연히 안 걸림을 재확인)함을 확인 후 백업 파일로 원복, 재빌드하여 148/148 전량 통과 재확인 |
