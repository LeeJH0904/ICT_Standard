# F-102 · offline_verify가 CP949 기본 콘솔에서 전 항목 OK 뒤 중단

| 항목 | 값 |
|---|---|
| 심각도 | 오류 |
| 분류 | 코드버그 |
| 대상 | `tools/offline_verify.py:224,236-249` |
| 발견일 | 2026-08-08 |
| 상태 | 수정완료 |

## 근거

개발 착수 지시서 §3.0 출구 ③은 `python tools/offline_verify.py`의 직접 실행 성공을 요구한다.

`CLAUDE.md` §3.5의 F-045 결정은 검증기 콘솔 출력 문자를 한국어 Windows 기본 코드페이지인 CP949 표현 가능 범위 안에서 고르도록 한다.

## 현상

현재 기본 콘솔의 `sys.stdout.encoding`은 `cp949`다. 검증기는 다섯 검사에 모두 `[OK]`를 출력한 뒤, 마지막 상세 문구의 em dash U+2014를 출력하면서 `UnicodeEncodeError`로 중단하고 종료 코드 1을 반환했다.

`tools/run_all.py`는 자식 프로세스에 UTF-8 환경을 강제하므로 같은 검증기가 그 경로에서는 OK가 되어 10/10으로 표시된다. 따라서 전체 회귀 결과가 지시서의 직접 출구 실패를 가린다.

F-045는 기존 `spec_verify.py`의 같은 콘솔 결함을 고친 항목이다. 이번 건은 단계 0에서 새로 추가된 `tools/offline_verify.py`가 그 회귀 검사 대상에 포함되지 않아 실제 출구에서 재발한 별도 대상이다.

## 영향

한국어 Windows 기본 환경에서 단계 0의 필수 출구가 실패한다. 오프라인 설치와 정책 검사가 모두 성공해도 스크립트 종료 코드가 1이므로 단계 완료를 주장할 수 없다.

## 재현

1. `python -c 'import sys; print(sys.stdout.encoding)'`이 `cp949`인지 확인한다.
2. 저장소 루트에서 `python tools/offline_verify.py`를 실행한다.
3. 다섯 번째 `[OK]` 뒤 `tools/offline_verify.py:224`의 상세 문구 출력에서 U+2014 인코딩 예외와 종료 코드 1을 확인한다.

## 제안

콘솔 출력에서 CP949 비표현 문자를 제거하거나 스크립트 자체가 안전한 출력 정책을 적용한다. `tools/*_verify.py` 전량의 기본 CP949 직접 실행도 회귀 검사에 포함한다.

---

## Claude 처리 기록

| 일시 | 상태 | 내용 |
|---|---|---|
| 2026-08-08 | 신규 | GPT 단계 0 재검증에서 지시서의 직접 출구 명령으로 재현 |
| 2026-08-08 | 수정완료 | 원인은 두 가지였다. ① `tools/offline_verify.py`에 다른 `*_verify.py`(spec_verify.py·dev_verify.py 등)가 다 갖고 있는 `sys.stdout.reconfigure(errors="replace")` 2중 방어 가드가 아예 없었다 — 신설 시 빠뜨렸다. ② F-097 수정 때 넣은 상세 문구에 em dash(U+2014)가 섞여 있었다(`tools/offline_verify.py:224`, 이번에 CP949-safe 하이픈으로 교체). 같은 클래스의 실사용 버그를 `tools/where.py`(`main()`의 MANUAL 분기 print 1곳)·`tools/run_all.py`(빈 스크립트 목록 분기 print 1곳)에서도 찾아 함께 고쳤다 — 둘 다 이번엔 트리거되지 않았지만 동일한 em dash + 가드 부재였다. 세 파일 모두에 CP949 reconfigure 가드를 추가했다. 재현 검증: `PYTHONIOENCODING=cp949 python tools/offline_verify.py`/`tools/where.py`/`tools/run_all.py` 전부 exit 0. 회귀: `fix_log/meta_verify.py`에 ① `tools/*_verify.py`(현재 offline_verify.py) 를 실제로 cp949 강제 후 직접 실행하는 검사(제안이 요구한 "기본 CP949 환경 직접 실행"을 문자 그대로 구현 — `run_all.py`처럼 자식에 UTF-8을 강제하면 이 버그가 다시 가려지므로 반대로 cp949를 강제한다), ② `tools/*.py` 전체의 `print()` 리터럴을 AST로 정적 추출해 CP949 표현 가능성을 검사하는 가벼운 보조 검사(where.py·run_all.py는 오프라인 설치를 반복 호출해 무거워 subprocess 대신 이 방식을 씀)를 추가 |
