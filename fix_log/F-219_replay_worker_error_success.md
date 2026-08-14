# F-219 · replay 작업 스레드 오류가 종료 코드 0으로 처리됨

| 항목 | 값 |
|---|---|
| 심각도 | 오류 |
| 분류 | 코드버그 |
| 대상 | `project_code/sim/replayer.py:73` · `project_code/sim/replayer.py:95` · `project_code/run.py:316` |
| 발견일 | 2026-08-12 |
| 상태 | 수정완료 |

## 근거

공고문 「소스코드 제출 안내」 재현성 — “서류 검증 단계에서 재현 불가 시 서면 평가에서 제외”된다. 개발 착수 지시서 §3.6 출구 ②는 `--mode replay`가 `logs/*.jsonl`을 재생해야 한다고 정한다.

## 현상

`Replayer._accept_and_play()`에는 `_play()` 예외를 호출자에게 전달하거나 저장하는 경로가 없다. 반면 `finally`에서 예외 여부와 무관하게 `done.set()`을 호출한다. `run.py`는 이 이벤트가 제한 시간 안에 켜졌는지만 `finished`로 보고 종료 코드 0을 반환한다.

`{not-json}` 한 줄인 로그로 실제 진입점을 실행하자 `JSONDecodeError` traceback이 `sim-replayer` 스레드에 출력됐고 재생·rx·tx가 모두 0건이었지만 프로세스 종료 코드는 0이었다.

## 영향

로그 손상·필드 누락·잘못된 hex 같은 재생 실패가 출구 성공으로 위장된다. 심사자가 제출 로그를 재현하지 못한 상태에서도 자동 검증은 성공으로 판정한다.

## 재현

```text
임시 로그 내용: {not-json}

python project_code/run.py --mode replay --log <임시 로그> --db <임시 DB>

stderr: Exception in thread sim-replayer ... JSONDecodeError
stdout: 재생 0건, rx=0 tx=0 위반=0
exit: 0
```

---

## Claude 처리 기록

| 일시 | 상태 | 내용 |
|---|---|---|
| 2026-08-13 | 확인 | `{not-json}` 로그를 실제 `run.py --mode replay`로 실행했다. `sim-replayer` 스레드에서 JSONDecodeError traceback이 발생하고 재생·rx·tx가 모두 0이어도 종료 코드가 0임을 재현했다. |
| 2026-08-13 | 수정완료 | 작업 스레드가 JSON/필드/hex/송수신 오류를 `Replayer.error`에 저장한 뒤 `done`을 설정하고, `run.py`와 독립 replayer 진입점이 오류를 출력해 종료 코드 1을 반환하도록 변경했다. 오류 저장을 임시 제거하자 전용 회귀가 실패했고 복원 후 통과했다. 실제 `run.main()` 회귀에서 malformed 로그와 TX 불일치가 모두 1, 정상 기본 로그가 0임을 확인했다. |
