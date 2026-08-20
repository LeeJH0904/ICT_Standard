# F-251 · 검증 도구 이동으로 전체 검증 진입점의 저장소 루트 계산이 붕괴

| 항목 | 값 |
|---|---|
| 심각도 | 오류 |
| 분류 | 코드버그 |
| 대상 | `project_docs/siap/tools/*.py` · `CLAUDE.md:334` · `project_docs/dev/개발_착수_지시서.md:337,353` |
| 발견일 | 2026-08-20 |
| 상태 | 수정완료 |

## 근거

제출본 `README.md:3-6`은 이 프로젝트가 “하드웨어 없이도 표준 준수를 기계로 검증할 수 있음을 증명”한다고 선언한다. `CLAUDE.md:334`와 개발 착수 지시서 §4는 전체 출구 명령을 `python tools/run_all.py`로 고정한다.

## 현상

저장소 루트의 `tools/`가 사라지고 검증기들이 `project_docs/siap/tools/`로 이동했지만, 각 도구의 루트 계산은 이동 전 구조를 그대로 사용한다. 예를 들어 `run_all.py:26`은 `Path(__file__).resolve().parent.parent`를 저장소 루트로 보므로 현재는 `project_docs/siap`을 루트로 계산한다. 그 결과 `project_docs/siap/project_code`와 `project_docs/siap/project_docs`처럼 존재하지 않는 경로를 검사한다.

문서에 적힌 `python tools/run_all.py`는 파일 부재로 시작조차 못 하고, 현 위치를 직접 실행한 `python project_docs/siap/tools/run_all.py`도 12개 중 2개만 통과한다. 통과한 일부 검사도 대상 부재로 검사를 건너뛴 결과다. `fix_log/meta_verify.py` 역시 64/68로 실패하고, 도구 테스트는 `_asgi_client`·`sim` import 오류로 수집 단계에서 중단된다.

## 영향

개발 완료의 통합 출구와 기존 결함 회귀 가드가 모두 무효다. 실제로 F-252와 F-253은 구현·문서에 재발해 있었지만, 현재 정식 실행 경로로는 정상적으로 검출할 수 없다. 표준 준수 근거의 독립 재현성과 향후 수정 안전망이 동시에 깨진다.

## 재현

```powershell
Test-Path .\tools
# False

python .\tools\run_all.py
# can't open file ... tools/run_all.py

python .\project_docs\siap\tools\run_all.py
# 2/12 통과, exit 1

python .\fix_log\meta_verify.py
# 64/68 통과, exit 1

python -m pytest .\project_docs\siap\tools\tests
# collection error: _asgi_client / sim 모듈을 찾지 못함
```

## 제안

검증 도구를 문서가 정한 루트 `tools/`로 복원하거나, 모든 도구가 공통 루트 탐색기를 사용하도록 바꾸고 문서·import 경로·도구 테스트를 함께 갱신한다. 이후 `run_all.py`와 `meta_verify.py`를 깨끗한 작업 트리에서 다시 통과시킨다.

---

## 작업자 처리 기록

| 일시 | 상태 | 내용 |
|---|---|---|
| 2026-08-20 | 확인 | 루트 `tools/` 부재와 `project_docs/siap/tools/run_all.py`의 `REPO_ROOT = parent.parent`를 확인했다. 현 위치에서 전체 검증을 직접 실행해 12개 중 2개만 통과하고 나머지가 `project_docs/siap/project_code`·`project_docs/siap/project_docs`를 찾는 실패를 재현했다. |
| 2026-08-20 | 수정완료 | 검증 도구 전체를 문서 정본의 저장소 루트 `tools/`로 복원해 기존 `REPO_ROOT = parent.parent` 계산과 import를 정상화했다. 복원 후 드러난 웹 도구 테스트의 낡은 문자열 기대 2건도 동등한 현행 구현 표현으로 갱신했다. `test_run_all.py`에 루트·도구/설계 검증기 발견 회귀 2건 추가. tools 테스트 55/55와 F-251 전용 2/2, `run_all.py` 21/21 통과. |
