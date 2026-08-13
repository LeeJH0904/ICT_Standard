# F-143 · send 상한 회귀 테스트가 2배 지연을 허용함

| 항목 | 값 |
|---|---|
| 심각도 | 오류 |
| 분류 | 코드버그 |
| 대상 | `project_code/siap/tests/test_link.py:75` |
| 발견일 | 2026-08-09 |
| 상태 | 수정완료 |

## 근거

`CLAUDE.md` §3.5 및 개발 착수 지시서 §3.5 단계 3 — “`send()` 대기 상한 = `Timeout × (Retry Count + 1)`.” F-138은 이 계약을 큐잉부터 회신까지 호출 전체에 적용했다.

## 현상

`test_send_bounded_even_when_read_always_errors_f138()`은 `recv_timeout=1`, `num_retry=1`을 사용해 계약 상한을 2초로 명시하면서도 실제 assertion은 `elapsed < 4.0`이다. 따라서 상한을 거의 2배 초과하는 구현도 통과한다.

현재 구현을 독립 계측하면 약 2.02초에 반환해 F-138 구현 수정 자체는 확인된다. 그러나 런타임에서 `SiapNodeLink.send`의 반환을 1초 늦추는 결함을 주입하자 총 3.032초로 계약을 초과했는데도 동일 테스트가 PASS했다.

## 영향

F-138의 핵심 계약이 다시 깨져도 단계 3 pytest 98/98이 초록으로 남을 수 있다. 이미 기존 F-138이 2.36초 대기를 상한 위반으로 판정했던 것과도 기준이 모순된다.

## 재현

저장소 파일을 수정하지 않고 `SiapNodeLink.send`를 원본 호출 뒤 1초 더 대기하는 래퍼로 런타임 교체한 후 기존 테스트 함수를 직접 호출했다.

```
INJECT: send return delayed by 1.0s; test still PASS;
observed=3.032s, contract upper=2.000s

프로세스 종료코드: 0
```

## 제안

계약 상한에 작은 스케줄링 허용치만 더한 경계로 검사하고, 허용치보다 큰 지연을 주입하면 반드시 실패하는 대조 반례를 메타 검증에 고정해야 한다.

---

## Claude 처리 기록

| 일시 | 상태 | 내용 |
|---|---|---|
| 2026-08-09 | 확인 | `test_send_bounded_even_when_read_always_errors_f138()`의 assertion이 계약 상한 2초에 `elapsed < 4.0`이라는 2배 여유를 두고 있음을 소스에서 확인. 보고된 재현(런타임에서 `SiapNodeLink.send`를 원본 호출 뒤 1초 추가 대기로 감싸는 몽키패치)을 그대로 실행해 elapsed≈3.0s 로 계약을 50% 초과했는데도 이 테스트가 PASS함을 확인. 같은 자리에서 자체적으로 추가 탐지: 바로 아래 `test_send_times_out_when_no_response()`도 같은 계약(2초 상한)에 `elapsed < 5.0`이라는 2.5배 여유를 두는 동일 결함을 갖고 있음을 확인 — 보고서는 `test_link.py:75` 한 곳만 지목했지만 같은 원인·같은 파일의 자매 테스트라 함께 처리 대상에 포함 |
| 2026-08-09 | 수정완료 | 두 테스트 모두 하드코딩된 여유(4.0/5.0)를 `fast_profile.recv_timeout * (fast_profile.num_retry + 1)`(계약값 자체)에서 유도한 상한 + 스케줄링 여유 0.5초로 교체 — `assert elapsed < upper + 0.5`. 여유를 0으로 두지 않은 이유는 스레드 스케줄링·GIL 경합의 정상적인 지터까지 실패로 잡으면 다른 부하 상황에서 불안정(flaky)해지기 때문이며, 실측(정상 구현 ~2.02~2.03s)과 결함 재현(~3.0s) 사이에 충분한 폭이 있어 0.5초로도 판별력이 확보된다. **결함 주입**: 보고서와 동일한 방식(`SiapNodeLink.send`를 몽키패치해 반환 직전 1초 추가 대기)으로 두 테스트를 함께 재실행 — 둘 다 정확히 FAIL(`3.05s`·`3.01s` 모두 `2.5s` 초과)함을 확인. 저장소 파일은 건드리지 않는 런타임 몽키패치라 원복 불필요. 정상 실행 시 `pytest siap/tests/test_link.py -k "f138 or times_out"` **2/2** 재통과, 전체 `pytest siap/tests/ backend/tests/` **98/98** 재통과 |
