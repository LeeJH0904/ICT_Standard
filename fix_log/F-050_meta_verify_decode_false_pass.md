# F-050 · 메타 검증기가 출력 디코딩 실패를 PASS로 처리함

| 항목 | 값 |
|---|---|
| 심각도 | 오류 |
| 분류 | 코드버그 |
| 대상 | `fix_log/meta_verify.py:226-235` |
| 발견일 | 2026-08-03 |
| 상태 | 수정완료 |

## 근거

공고문 3장 「소스코드 제출 안내」 — "제출물만으로 실제 실행(재현)이 가능한 전체 소스코드"

F-045 처리 기록은 검증기 출력 전체를 CP949로 검사하고 종료코드까지 확인한다고 명시한다.

## 현상

메타 검증기는 자식 검증기를 `text=True, encoding="utf-8"`로 읽는다. 한국어 Windows에서 자식은 CP949 바이트를 쓰므로 `_readerthread`가 `UnicodeDecodeError`로 죽는다. `subprocess.run()` 자체는 예외를 올리지 않고 `stdout=None`, `returncode=0`을 반환하며, 코드는 `run.stdout or ""`로 빈 출력을 검사해 CP949 가능 및 종료코드 0을 모두 PASS로 기록한다.

## 영향

검사하려던 출력 전체가 사라졌는데도 `22/22 통과`가 출력된다. F-045의 근본 대응이 실제로는 작동하지 않으며 메타 검증 결과가 거짓 양성이다.

## 재현

```text
subprocess.run(... text=True, encoding="utf-8")
→ _readerthread UnicodeDecodeError
→ returncode=0, stdout=None
→ offenders=[] → PASS
```

## 제안

자식 출력을 bytes로 받고 CP949 표현 가능성 검사는 의도한 문자 원본을 잃지 않는 방식으로 수행한다. `stdout is None` 또는 디코딩 실패는 반드시 FAIL이어야 한다.

---

## Claude 처리 기록

| 일시 | 상태 | 내용 |
|---|---|---|
| 2026-08-03 | 확인 | 타당. CPython `subprocess` 의 Windows 구현(`_readerthread`)은 리더 스레드에서 디코딩하며, 그 스레드가 죽어도 `_communicate` 는 `stdout = stdout[0] if stdout else None` 으로 **None** 을 돌려주고 예외를 올리지 않는다. 소스(`subprocess.py`)에서 직접 확인했다. POSIX 는 `_translate_newlines` 에서 예외가 전파되어 FAIL 이 되지만, F-045 가 대상으로 삼은 환경이 바로 Windows 다 |
| 2026-08-03 | 수정완료 | 자식 출력을 **bytes 로 받는다**(`text`·`encoding` 제거). 디코딩을 검증기가 명시적으로 하고, `stdout is None` · 빈 출력 · UTF-8 디코딩 실패를 전부 FAIL 로 만들었다. 종료코드 확인은 실행 실패 경로에서도 반드시 기록되도록 분리했다 |
| 2026-08-03 | 수정완료 | 자식의 `PYTHONIOENCODING=utf-8`·`PYTHONUTF8=1` 을 강제해 바이트열을 플랫폼 무관하게 고정했다. 고정하지 않으면 자식의 F-045 stdout 가드가 문자를 `?` 로 바꿔 **검사 대상 자체가 사라진다** — 거짓 통과의 두 번째 경로였다 |
| 2026-08-03 | 수정완료 | 결함 주입으로 재검증했다. 저장소 사본의 `test_contract.py` 출력에 U+2014 를 심자 `FAIL ... U+2014 '—'` 로 검출되고 메타 검증이 21/22, 종료코드 1 이 됐다. 출력 길이(`3059자`)를 함께 표기해 '검사할 출력이 있었다'는 것도 눈으로 확인되게 했다 |
