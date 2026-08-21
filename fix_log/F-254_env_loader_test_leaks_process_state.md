# F-254 · 환경설정 테스트가 프로세스 상태를 누출해 후속 API 테스트가 순서 의존 실패

| 항목 | 값 |
|---|---|
| 심각도 | 오류 |
| 분류 | 코드버그 |
| 대상 | `project_code/backend/tests/test_config.py:21-42` · `project_code/backend/config.py:90-94` · `project_code/backend/tests/test_api.py:93-99` |
| 발견일 | 2026-08-21 |
| 상태 | 수정완료 |

## 근거

`project_docs/dev/F-189_AI_규칙_초안_개선_방안.md` §12 — “환경변수 미설정 상태에서 전체 오프라인 검증 통과”.

`docs/F-189_수정_기록.md`는 `python -m pytest -q backend/tests siap/tests sim/tests`가 438건 전부 통과한다고 기록한다. 개별 테스트는 같은 초기 환경에서 파일 실행 순서와 무관하게 같은 결과를 내야 한다.

## 현상

`test_loads_supported_values_and_ignores_blank_keys()`는 `load_env_file()`을 호출해 `KMA_API_KEY=kma-test-key`를 실제 `os.environ`에 넣는다. 이 쓰기는 `monkeypatch.setenv()`를 거치지 않으므로 테스트 종료 때 복구되지 않는다.

그 뒤 `test_health_7_0937_6_3()`를 실행하면 `api.py`의 `os.environ.get(dms.API_KEY_ENV) is None`이 거짓이 되어, 초기 프로세스에는 KMA 키가 없었는데도 `public_data_fallback=False`가 반환된다. API 테스트 단독 실행은 통과하지만 `test_config.py` 뒤에 배치하면 실패한다.

## 영향

전체 디렉터리의 현재 기본 수집 순서에서는 `test_api.py`가 먼저라 438건이 우연히 통과한다. 파일 순서 변경, 선택 실행, 병렬화 또는 테스트 러너 변경 시 동일 코드가 실패하므로 F-189 회귀시험의 독립성과 신뢰성이 깨진다.

## 재현

```powershell
cd 최종_제출물_폴더/ICT_Test/project_code
Remove-Item Env:KMA_API_KEY -ErrorAction SilentlyContinue
python -m pytest -q -p no:cacheprovider backend/tests/test_api.py::test_health_7_0937_6_3
# 1 passed

Remove-Item Env:KMA_API_KEY -ErrorAction SilentlyContinue
python -m pytest -q -p no:cacheprovider backend/tests/test_config.py backend/tests/test_api.py::test_health_7_0937_6_3
# 1 failed, 7 passed
# assert body[public_data_fallback] is True
# E assert False is True
```

개발본에서도 같은 결과가 재현된다.

## 제안

로더 호출로 추가된 환경변수를 테스트 종료 전에 명시적으로 복원하거나, `load_env_file()`이 사용할 환경 매핑을 주입할 수 있게 하여 테스트가 실제 프로세스 전역 상태를 남기지 않도록 한다. 순서 반전 회귀 테스트도 고정한다.

---

## 작업자 처리 기록

| 일시 | 상태 | 내용 |
|---|---|---|
| 2026-08-21 | 수정완료 | `load_env_file(..., environ=...)` 환경 매핑 주입점을 추가하고 `test_config.py`가 전용 매핑만 사용하도록 바꿔 프로세스 환경 누출을 제거했다. 보고된 역순 실행을 포함한 표적 테스트 12건과 제출본·수정본 전체 테스트 각 440건이 통과했다. |

