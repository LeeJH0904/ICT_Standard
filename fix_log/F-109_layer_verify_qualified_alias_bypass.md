# F-109 · 계층 검증기가 패키지 접두어와 별칭 동적 import를 놓침

| 항목 | 값 |
|---|---|
| 심각도 | 오류 |
| 분류 | 코드버그 |
| 대상 | `tools/layer_verify.py:86-135` |
| 발견일 | 2026-08-08 |
| 상태 | 수정완료 |

## 근거

CLAUDE.md §2.2는 `backend/`·`web/`이 `siap/` 내부 심볼을 import하지 못하도록 한다. F-105는 상대 import와 정적 문자열 동적 import까지 같은 계층 규칙으로 검사하도록 수정완료됐다.

이 건은 F-105의 기존 세 재현을 반복하지 않는다. F-105 보완 뒤에도 남은, 서로 다른 두 정적 표기 방식의 반례다.

## 현상

`_top_level_modules()`는 일반 import에서 첫 번째 dotted component만 보므로 `import project_code.siap.codec`와 `from project_code.siap import codec`을 `project_code`로만 기록한다. 금지 이름 `siap`과 일치하지 않는다.

동적 import도 호출 함수의 실제 바인딩을 추적하지 않아 `from importlib import import_module as load; load(siap.codec)`를 `importlib`로만 기록한다.

두 소스를 각각 가짜 `backend/_attack.py`의 내용으로 메모리 주입해 `layer_verify.main()` 전체 판정을 실행했다. 두 경우 모두 금지 의존성이 있는데도 7/7, exit 0이었다. `__import__(project_code.siap.codec)`도 같은 첫 component 문제로 탐지되지 않았다.

## 영향

F-105 수정완료 회귀 4종을 모두 통과하면서도 backend가 siap 구현에 직접 결합할 수 있다. import 표기만 바꾸면 동일 계층 위반의 판정이 달라져 CLAUDE.md §2.2 자동 출구가 완결되지 않는다.

## 재현

1. `backend/` 파일에 `import project_code.siap.codec`를 둔 것으로 `layer_verify.main()`을 실행한다.
2. 실제 결과: 7/7, exit 0.
3. 같은 위치에 `from importlib import import_module as load; load(siap.codec)`를 둔다.
4. 실제 결과: 다시 7/7, exit 0.

## 제안

`PROJECT_CODE` 자체가 namespace/package 접두어로 등장하면 다음 component를 계층 이름으로 해석한다. 동적 import는 `ImportFrom`의 별칭 심벌 테이블을 구성해 `import_module as ...` 호출까지 추적한다. 위 세 변형을 F-105 회귀와 별개로 고정한다.

---

## Claude 처리 기록

| 일시 | 상태 | 내용 |
|---|---|---|
| 2026-08-08 | 신규 | GPT 단계 1 재검증에서 패키지 접두어·별칭 동적 import가 실제 main 7/7을 통과하는 반례 재현 |
| 2026-08-08 | 확인 | 제시된 반례(`import project_code.siap.codec`, `from importlib import import_module as load; load("siap.codec")`)를 backend/ 에 실제 주입 후 `python tools/layer_verify.py` 실행 — 수정 전 각각 7/7·exit 0 통과함을 확인 |
| 2026-08-08 | 수정완료 | `_effective_top(parts)` 신설 — 첫 구성요소가 `PROJECT_CODE.name`("project_code")이면 다음 구성요소를 실질 최상위 계층 이름으로 취급(저장소 루트가 `sys.path`에 있는 실행 방식까지 같은 규칙으로 판정). `_dynamic_import_aliases(tree)` 신설 — `from importlib import import_module as X` 로 지역에 들어온 이름 전부를 사전 수집해, `Name` 호출 판정 시 고정된 `{"import_module","__import__"}` 대신 이 집합을 쓰도록 변경(속성 호출 `foo.import_module(...)`은 기준 객체 이름을 애초에 안 봐서 `importlib as il` 별칭은 이미 안전했음). `ast.Import`·`ast.ImportFrom`(절대/상대)·동적 import 문자열 리터럴 세 경로 모두에 `_effective_top()`을 적용. 결함 주입 재현: `import project_code.siap.codec`(6/7 FAIL) · `from importlib import import_module as load; load("siap.codec")`(6/7 FAIL) · `__import__("project_code.siap.codec")`(정적 함수 단위 확인) · 정상 상대 import + 무관 별칭(`import_module` → `json`)(7/7 PASS, 오탐 없음) 전부 기대대로 재현 후 임시 파일 제거. 회귀: `python tools/layer_verify.py` **7/7** 유지 · `fix_log/meta_verify.py` §5-a 에 F-105 자리 옆으로 F-109 반례 5건 추가(qualified import·qualified from-import·별칭 동적 import·dunder qualified·무관 별칭 오탐 없음) |
