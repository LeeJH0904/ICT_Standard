# F-237 · AVR UART 버퍼 포화 시 논블로킹 계약 위반

| 항목 | 값 |
|---|---|
| 심각도 | 오류 |
| 분류 | 코드버그 |
| 대상 | `Branch_2` AVR 보드 2종 `uart_write()` |
| 발견일 | 2026-08-16 |
| 상태 | 수정완료 |

## 근거

펌웨어 설계서 §5.8 — “블로킹하지 않는다 — 블로킹하면 그동안 수신 바이트가 유실된다.”

## 현상

`n = (avail > 0 && avail < len) ? avail : len`이므로 `availableForWrite()==0`일 때도 `n=len`이 되어 `Serial.write(buf,len)`을 호출한다. 두 AVR 스케치가 같은 결함을 갖는다.

## 영향

버퍼 포화 시 poll 루프가 블로킹되어 수신·ACK·타이머 처리가 지연될 수 있다.

## 재현

```text
avail=0, len=12 => n=12, Serial.write 호출
board_verify 결과: FAIL 0
```

## 제안

여유 0이면 0을 반환하고 0·부분·충분 용량 반례를 고정한다.

---

## 작업자 처리 기록

| 일시 | 상태 | 내용 |
|---|---|---|
| 2026-08-17 | 확인 | 두 AVR 스케치(`arduino_sensor_node.ino`·`arduino_actuator_node.ino`)의 `uart_write` 가 `n = (avail>0 && avail<len) ? avail : len` 이라 `avail==0` 에서 `n=len` 으로 떨어지고, `if(n==0)` 가드는 이 경로를 못 잡아 포화 버퍼에 `Serial.write(buf,len)` 이 호출됨을 확인. 펌웨어 설계서 §5.8 "블로킹하지 않는다" 위반. |
| 2026-08-17 | 수정완료 | 두 파일 모두 `int avail = availableForWrite(); if (avail <= 0) return 0; uint16_t n = (avail<len)?avail:len; return Serial.write(buf,n);` 로 교체 — 여유 0이면 0을 돌려주고, 쓰기 길이가 항상 `avail` 이하라 블로킹하지 않는다(0·부분·충분 용량 3케이스 모두 안전). **회귀**: `tools/board_verify.py` 에 `_check_uart_nonblocking()` 신설 — 두 스케치의 `uart_write` 본문에 `availableForWrite` 와 `avail <= 0 → return 0` 가드가 있는지 정적 검사(avr 툴체인 없이 상시 실행). `board_verify.py` 11/12 PASS(신설 항목 PASS, FAIL 0). |

