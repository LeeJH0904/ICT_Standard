# F-096 · dev_verify.py 가 하위 프로세스 stdout 을 항상 UTF-8 로 잘못 가정

| 항목 | 값 |
|---|---|
| 심각도 | 오류 |
| 분류 | 코드버그 |
| 대상 | `project_docs/dev/dev_verify.py:195` (섹션 4 — 출구 조건 통과 건수 대조) |
| 발견일 | 2026-08-08 |
| 상태 | 수정완료 |

## 근거

CLAUDE.md §3.5 표(F-045): "검증기 콘솔 출력 문자는 CP949 표현 가능 범위 안에서 고른다 (한국어 Windows 콘솔 기본 코드페이지가 CP949)." 이 결정은 "출력 문자를 고른다"는 방향이었고, 하위 프로세스를 **캡처해서 다시 디코딩하는** 지점은 다루지 않았다 — 그 지점에서 실제로 인코딩이 어긋났다.

## 현상

`단계 0` 착수 중 `tools/run_all.py`(신설)로 `project_docs/dev/dev_verify.py`를 돌리자 "출구 조건이 인용한 통과 건수가 실측과 일치 (F-090)" 검사가 `test_contract.py`·`golden_verify.py`·`verify.py` 세 곳 모두에서 "통과 수 미출력"으로 실패했다.

원인: `dev_verify.py` 195행이 `subprocess.run([sys.executable, "-B", str(p)], capture_output=True, ...)` 로 하위 스크립트를 실행하고 `r.stdout.decode("utf-8", "replace")` 로 디코딩한다. 그런데 파이썬 표준 출력이 **콘솔이 아니라 파이프**(subprocess capture)로 연결되면 PEP 528 의 Windows 콘솔 UTF-8 처리가 적용되지 않고, `locale.getpreferredencoding()` 을 따른다 — 이 저장소가 개발되는 한국어 Windows 환경에서는 **CP949**다. 즉 하위 스크립트(`test_contract.py` 등)는 한글을 CP949 바이트로 썼는데, 부모 프로세스(`dev_verify.py`)는 그 바이트를 UTF-8 로 디코딩했다. 디코딩 가능한 바이트 시퀀스가 아니므로 `errors="replace"` 가 한글 전체를 U+FFFD 로 치환했고, 그 결과 `re.search(r"(\d+)/(\d+) 통과", out)` 의 리터럴 "통과" 가 출력 어디에도 나타나지 않아 매치가 실패했다. 예외 없이 "통과 수 미출력"으로만 보여 원인이 드러나지 않는다.

재현(직접 검증, 저장소 루트에서):

```
python -c "
import subprocess, sys
p = r'project_docs/contracts/test_contract.py'
r = subprocess.run([sys.executable, '-B', p], capture_output=True,
                    cwd='project_docs/contracts', timeout=60)
print(r.stdout[-40:])   # b'...\xc5\xeb\xb0\xfa\r\n' — CP949, UTF-8 아님
"
```

## 영향

`tools/run_all.py`(단계 0 신설 검증기)가 전체 회귀를 돌릴 때마다 `dev_verify.py`가 거짓 실패한다. "각 단계 완료 후 사용자에게 확인받는다"는 절차에서 매 단계 회귀가 원인 불명으로 붉게 뜨면, 실제 결함과 이 인코딩 잡음을 구분할 수 없어진다 — 심사자 환경(로케일 미상)에서 동일 클래스의 버그가 다른 형태로 재발할 위험도 있다(영어 Windows는 cp1252, 한국어 Windows는 cp949로 서로 다르게 깨진다).

## 재현

```
# 위 "재현" 절 참고. 고치기 전: python project_docs/dev/dev_verify.py 가
# "test_contract.py: 통과 수 미출력" 등 3건의 드리프트로 실패한다.
```

## 제안

하위 파이썬 프로세스를 실행할 때 `env`에 `PYTHONIOENCODING=utf-8` · `PYTHONUTF8=1` 을 강제해, 호출자의 OS 로케일과 무관하게 항상 UTF-8 로 쓰게 한다.

---

## Claude 처리 기록

| 일시 | 상태 | 내용 |
|---|---|---|
| 2026-08-08 | 확인 | 개발 착수 단계 0에서 `tools/run_all.py`를 처음 돌리며 자체 발견했다(GPT 지적 아님 — F-069와 같은 유형). 위 "재현" 절 그대로 재현됨을 직접 확인했다. |
| 2026-08-08 | 수정완료 | `project_docs/dev/dev_verify.py`에 `_utf8_env()`를 추가하고 195행의 `subprocess.run` 호출에 `env=_utf8_env()`를 넣었다. 같은 결함 유형을 이번 단계에서 신설한 `tools/run_all.py`·`tools/where.py`에도 동일하게 적용했다(둘 다 하위 프로세스를 캡처해 UTF-8로 디코딩한다). **회귀 테스트**: `dev_verify.py`에 하위 프로세스로 `python -c "print('통과')"`를 실행해 왕복이 무손실인지 직접 확인하는 검사를 추가했다(`_utf8_env()`를 빼면 이 자리에서 즉시 실패한다). 검증: `dev_verify.py` 74/75(3건 드리프트) → **76/76**. `tools/run_all.py` 9/10 → **10/10**. `fix_log/meta_verify.py` 55/55 유지. |
