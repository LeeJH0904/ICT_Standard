# F-108 · 메타 검증의 offline CP949 회귀 제한시간이 실제 실행시간보다 짧음

| 항목 | 값 |
|---|---|
| 심각도 | 오류 |
| 분류 | 코드버그 |
| 대상 | `fix_log/meta_verify.py:377-393` |
| 발견일 | 2026-08-08 |
| 상태 | 수정완료 |

## 근거

F-102 처리로 `offline_verify.py`를 CP949 기본 콘솔 조건에서 직접 완주시키는 회귀 검사가 `meta_verify.py`에 추가됐다. README.md §5는 검증 스크립트 오류를 원래 검증 대상의 결함과 구분해 기록하도록 요구한다.

## 현상

`meta_verify.py`는 모든 `tools/*_verify.py` CP949 직접 실행에 일률적으로 `timeout=180`을 적용한다. 현재 `offline_verify.py`는 6개 Python/플랫폼 조합의 실제 `--no-index` 설치를 수행하므로 단독 정상 실행도 약 179초가 걸렸다.

같은 단계 1 검증 회차에서 `python tools/offline_verify.py`는 exit 0이었지만, `python fix_log/meta_verify.py` 내부의 동일 CP949 회귀는 180초를 넘겨 `TimeoutExpired`가 났다. 나머지 74개 항목은 통과했으나 최종 결과는 74/75, exit 1이었다.

## 영향

코드·휠·네트워크 조건이 정상이어도 약간의 시스템 부하만으로 전체 메타 회귀가 실패한다. 반대로 실패 원인이 CP949 출력 결함인지 단순 시간 부족인지 구분할 수 없어 F-102 회귀의 신뢰성이 없다.

## 재현

1. `python tools/offline_verify.py`를 실행해 정상 종료와 약 179초 실행시간을 확인한다.
2. `python fix_log/meta_verify.py`를 실행한다.
3. 실제 결과: `offline_verify.py` CP949 항목에서 180초 `TimeoutExpired`, 최종 74/75·exit 1.

## 제안

오프라인 설치 검증의 실측 최악 실행시간보다 충분히 큰 별도 제한을 두거나, 자식 프로세스 진행 신호 기반 제한을 사용한다. 시간 초과 시 부분 출력과 경과시간을 남겨 CP949 실패와 설치 지연을 구분하고, 의도적으로 느린 정상 대조군을 회귀 테스트에 포함한다.

---

## Claude 처리 기록

| 일시 | 상태 | 내용 |
|---|---|---|
| 2026-08-08 | 신규 | GPT 단계 1 검증에서 단독 정상인 offline 검증이 메타 내부 180초 제한으로 실패함을 재현 |
| 2026-08-08 | 확인 | `tools/offline_verify.py` 단독 실행이 정상 종료 · 약 179초 소요, 같은 스크립트를 `meta_verify.py` 내부 180초 제한으로 실행하면 `TimeoutExpired`로 74/75·exit 1 이 되는 것을 재현 |
| 2026-08-08 | 수정완료 | `meta_verify.py`에 `_run_cp949(script, timeout)` 헬퍼 신설 — `subprocess.TimeoutExpired`(시간 초과)와 비정상 종료(진짜 CP949 크래시)를 서로 다른 status(`timeout`/`crash`/`error`/`ok`)로 분류해 detail 에 사유를 남긴다. `_CP949_TIMEOUT` 딕셔너리로 `offline_verify.py`에만 600초(실측 ~179초 + 충분한 여유)를 배정하고 나머지는 기존 180초 유지. "의도적으로 느린 정상 대조군" 2건 추가 — `tempfile`로 2초 sleep 후 정상 종료하는 합성 스크립트를 만들어 ① 넉넉한 제한(5초)에서 'ok' 분류 ② 빡빡한 제한(1초)에서는 'timeout'으로 분류되고 crash 로 오분류되지 않는지를 매 실행마다 검사한다(179초 전체를 다시 돌리지 않고 분류 로직 자체를 회귀 검증). 검증: 수정 전 74/75·exit 1(TimeoutExpired) 재현 → 수정 후 반전 확인. 회귀: `python fix_log/meta_verify.py` 75 → **77/77**(F-108 정상 대조군 2건 추가) |
