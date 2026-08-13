# F-142 · xcodec이 C 덤프의 비정상 종료를 무시함

| 항목 | 값 |
|---|---|
| 심각도 | 오류 |
| 분류 | 코드버그 |
| 대상 | `tools/xcodec_verify.py:73` · `tools/xcodec_verify.py:102` |
| 발견일 | 2026-08-09 |
| 상태 | 수정완료 |

## 근거

개발 착수 지시서 §3.5 단계 3 — `tools/xcodec_verify.py`는 C 인코더 출력과 Python 인코더 출력을 교차 검증하는 출구다. `CLAUDE.md` §6.2 — 검증기는 독립 입력을 대조하고, “실행 가능한 것은 직접 실행 결과를 판정”해야 한다.

## 현상

`_build_and_run_c_dump()`는 C 덤프를 `subprocess.run()`으로 실행하지만 `run.returncode`를 검사하지 않는다. stdout을 파싱한 딕셔너리와 stderr만 반환하며, `main()`은 출력 건수와 내용만 맞으면 “dump_golden 빌드·실행 성공”으로 판정한다.

실제 `dump_golden`을 정상 실행한 뒤 stdout은 그대로 두고 반환코드만 7로 강제하는 런타임 주입을 적용하자, 검증기는 여전히 8/8·종료코드 0으로 통과했다. 즉 C 테스트가 내부 assertion·sanitizer·정리 오류 등으로 실패해도 실패 전에 53건 출력을 냈다면 단계 출구가 성공으로 위조된다.

## 영향

신설 검증기가 자신이 실행한 C 구현의 실패 상태를 보지 않는다. “이 검사를 통과하면서 틀린 코드”가 실제로 존재하므로 F-080 유형의 거짓 초록 사각지대가 남는다.

## 재현

저장소 파일을 수정하지 않고 `tools.xcodec_verify`의 `subprocess.run`을 감싸, 실행파일 이름이 `dump_golden`일 때 실제 stdout·stderr를 보존한 채 `CompletedProcess.returncode=7`만 주입했다.

```
INJECT: real dump_golden stdout preserved, returncode forced to 7
...
PASS  dump_golden 빌드·실행 성공
...
8/8 통과

검증기 자체 종료코드: 0
```

## 제안

`run.returncode != 0`이면 출력 내용과 무관하게 실행 실패로 반환하고, 메타 검증에 “완전한 정상 stdout + 비정상 종료코드” 반례를 고정해야 한다.

---

## Claude 처리 기록

| 일시 | 상태 | 내용 |
|---|---|---|
| 2026-08-09 | 확인 | `_build_and_run_c_dump()`가 `subprocess.run()`의 `CompletedProcess.returncode`를 받아 두고도 어디서도 검사하지 않고 stdout 파싱 결과만 반환함을 소스에서 확인. 보고된 재현(실제 stdout·stderr 는 그대로 두고 `returncode` 만 7로 주입)을 그대로 실행해 `main()`이 8/8·전체 종료코드 0 으로 통과함을 확인 |
| 2026-08-09 | 수정완료 | `_build_and_run_c_dump()`의 반환형에 `run.returncode`를 4번째 값으로 추가(반환 튜플이 이제 재인코딩 hex·위반 판정·stderr·종료코드 4-튜플). `main()`에 `t("dump_golden 정상 종료 (exit code 0) (F-142)", c_returncode == 0, ...)` 검사를 다른 어떤 내용 검사보다 먼저 추가해, 출력 건수·내용과 무관하게 종료코드 자체를 판정 대상으로 삼는다(검사 8종 → **9종**). 회귀는 이 신설 검사 자체가 매 실행마다 도는 영구 가드다 — 별도 pytest 회귀 파일을 두지 않은 이유는 이 검증기가 실행 대상(빌드된 `dump_golden` 바이너리)을 실제로 실행해야만 재현 가능한 결함이라, `tools/run_all.py`/개발 착수 지시서 §3.5 출구 경로에서 이미 매번 실행되기 때문이다. **결함 주입**: `subprocess.run`을 런타임에 감싸 `dump_golden` 실행 결과의 `returncode`만 7로 강제하는 방식으로 보고된 재현을 재구성 — 신설 검사가 정확히 FAIL 하고(8/9), **검증기 자체의 종료코드도 0→1로 바뀜**을 확인. 저장소 파일은 건드리지 않는 방식(런타임 몽키패치)이라 원복 불필요. 정상 실행 시 `python tools/xcodec_verify.py` **9/9** 재통과, `tools/run_all.py` **13/13**(xcodec_verify.py 포함) 재통과 |
