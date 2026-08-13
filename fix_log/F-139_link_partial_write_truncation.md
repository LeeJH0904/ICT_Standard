# F-139 · Python 링크가 부분 쓰기 잔여를 버림

| 항목 | 값 |
|---|---|
| 심각도 | 오류 |
| 분류 | 코드버그 |
| 대상 | `project_code/siap/link.py:137` · `project_code/siap/transport.py:45` |
| 발견일 | 2026-08-09 |
| 상태 | 수정완료 |

## 근거

`transport.Transport.write()` 계약 — 실제로 쓴 바이트 수를 반환하고 부분 쓰기를 허용하며 “호출자가 남은 바이트를 재시도한다.” `link.py::_write()`도 전량 송신을 계약으로 선언한다. F-133은 같은 부분 쓰기 유실을 C 상태 머신에서 이미 수정했다.

## 현상

`_write()`는 첫 호출이 일부를 쓰고 다음 호출이 0을 반환하면 루프를 `break`한다. 남은 데이터는 보관·재시도하지 않으며 호출자에게 실패를 알리지도 않고 `tx` 통계를 1 증가시킨다. 10바이트 입력에 4바이트 후 0을 반환하는 Transport를 넣으면 수신 데이터는 `b'0123'`뿐인데 성공으로 집계된다.

## 영향

일시적 UART/소켓 백프레셔가 정상 프레임을 절단한다. 이후 재전송은 전체 프레임을 다시 붙여 보내므로 스트림 경계까지 오염될 수 있고, 통계는 유실을 숨긴다.

## 재현

```text
write #1: 요청 10byte 중 4byte 반환
write #2: 0 반환
SiapNodeLink._write(b'0123456789')
실제 출력 b'0123', stats['tx'] == 1
```

## 제안

0 반환을 성공 종료로 취급하지 말고 잔여를 보존해 유한 정책으로 재시도하거나 명시적 송신 실패로 전달한다.

---

## Claude 처리 기록

| 일시 | 상태 | 내용 |
|---|---|---|
| 2026-08-09 | 확인 | `_write()`가 `n <= 0`이면 즉시 `break`해 잔여 바이트를 버리고도 `self._stats["tx"] += 1`을 무조건 실행함을 소스에서 확인 — Transport.write() 계약("부분 쓰기를 허용… 호출자가 남은 바이트를 재시도한다")을 지키지 않음을 확인 |
| 2026-08-09 | 수정완료 | `_write()`를 재작성 — `n<=0`을 즉시 `break`하지 않고 유한 횟수(최대 50회, 회당 10ms 대기) 재시도한다. 그래도 다 못 보내면 `stats['tx']`를 올리지 않고 `False`를 반환한다(성공을 조용히 위조하지 않는다). 반환형을 `None`→`bool`로 바꿨다(호출자는 현재 결과를 무시하지만, 최소한 통계는 정직하다). 회귀 테스트 추가: `test_link.py::test_write_retries_partial_writes_and_reports_truth_f139`(청크 크기를 다양하게 주는 가짜 Transport로 재시도 후 전량 성공 확인), `test_write_gives_up_after_bounded_stalls_and_does_not_report_success_f139`(영구적으로 막힌 Transport에서 `False` + `stats['tx']==0` 확인). 결함 주입(옛 `break` 버전으로 되돌림) 후 두 테스트가 정확히 실패함을 확인(`AssertionError: assert b'0123' == b'0123456789'` 등)하고 원복 — `pytest siap/tests/` 재통과 |
