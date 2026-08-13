# F-105 · 계층 검증기가 상대 import와 동적 import를 놓침

| 항목 | 값 |
|---|---|
| 심각도 | 오류 |
| 분류 | 코드버그 |
| 대상 | `tools/layer_verify.py:45-78` |
| 발견일 | 2026-08-08 |
| 상태 | 수정완료 |

## 근거

CLAUDE.md §2.2는 `backend/`·`web/`이 `siap/` 내부 심볼을 import하지 않고 `contracts/`와 `SiapLink`만 참조하도록 요구한다. 개발 착수 지시서 §3.1은 이 규칙을 AST 기반으로 확인하는 `tools/layer_verify.py`를 단계 1 산출물과 출구에 포함한다.

## 현상

`_top_level_modules()`는 `ast.ImportFrom`의 `level > 0`을 전부 같은 패키지 내부 참조라고 가정해 검사에서 제외한다. 그러나 `project_code/backend/x.py`의 `from ..siap import codec`는 실제로 상위 `project_code.siap`을 참조한다. 금지 의존성이 존재하는데도 검증기는 7/7, exit 0이었다.

또한 `importlib.import_module(siap.codec)`로 같은 의존성을 만들면 AST에 `Import`/`ImportFrom` 노드가 없으므로 역시 7/7, exit 0이다. 대조군 `import siap.codec`는 같은 위치에서 정상적으로 exit 1이 되어, 반례의 통과가 테스트 구성 문제가 아니라 탐지 사각지대임을 확인했다.

## 영향

서비스 계층이 프로토콜 내부 구현에 직접 결합되어도 단계 1 계층 출구가 녹색이다. 이후 패키지 배치와 import 문법에 따라 같은 의존성이 통과와 실패로 달라져 CLAUDE.md §2.2의 경계가 자동으로 보장되지 않는다.

## 재현

1. 임시 복사본의 `project_code/backend/x.py`에 `from ..siap import codec`를 작성한다.
2. `python tools/layer_verify.py`를 실행한다.
3. 실제 결과: 7/7, exit 0.
4. 같은 파일을 `import siap.codec`로 바꾸면 exit 1, `importlib.import_module(siap.codec)`로 바꾸면 다시 7/7, exit 0이다.

## 제안

검사 대상 파일의 패키지 위치와 `ImportFrom.level`을 함께 해석해 절대 모듈 경로를 복원한다. 동적 import는 허용 목록을 둔 정적 탐지 또는 실행 시 import 추적으로 막고, 위 세 변형을 독립 회귀 반례로 고정한다.

---

## Claude 처리 기록

| 일시 | 상태 | 내용 |
|---|---|---|
| 2026-08-08 | 신규 | GPT 단계 1 검증에서 상대 import·동적 import가 7/7로 통과하는 반례 재현 |
| 2026-08-08 | 확인 | 제시된 3변형(상대 import, 동적 import, 대조군 정상 상대 import)을 각각 임시 파일로 재현 — `from ..siap import codec`(6/7, FAIL 검출됨 확인 전에는 미검출) 및 `importlib.import_module("siap.codec")` 모두 수정 전에는 통과함을 확인 |
| 2026-08-08 | 수정완료 | `tools/layer_verify.py`에 `_package_parts()`(파일의 `PROJECT_CODE` 기준 dotted 패키지 경로 계산)와 `_resolve_relative()`(importlib._bootstrap._resolve_name과 동일한 규칙으로 레벨→절대 base 복원, 패키지 깊이를 넘으면 보수적으로 위반 판정) 신설. `_top_level_modules()`가 `ImportFrom.level > 0`을 더 이상 건너뛰지 않고 절대 경로로 되돌려 최상위 이름을 판정하도록 수정. `ast.Call`을 순회해 `importlib.import_module(...)`/`__import__(...)`의 문자열 리터럴 인자도 최상위 이름으로 추가(변수·f-string 등 실행 시점에만 정해지는 인자는 정적 분석의 근본적 한계로 다루지 않음 — 다른 `*_verify.py`들과 같은 원칙). 결함 주입 재현: `from ..siap import codec`(6/7 FAIL) · `importlib.import_module("siap.codec")`(6/7 FAIL) · 정상 대조군 `from . import repository`(7/7 PASS, 오탐 없음) 전부 기대대로 재현 후 임시 파일 제거. 부수 수정 — 검사 본문이 모듈 최상위에서 `sys.exit()`까지 호출해 `import layer_verify`가 프로세스를 그대로 죽이던 구조를, `where.py`·`offline_verify.py`와 같은 `main()`+`if __name__=="__main__":` 가드로 리팩터링(순수 함수 `_top_level_modules`/`_package_parts`/`_resolve_relative`는 모듈 최상위 유지, 실행부만 `main()` 안으로). 이로써 `fix_log/meta_verify.py`가 `import layer_verify`로 내부 함수를 직접 반례 검증할 수 있게 되어 §5-a에 F-105 회귀 4건(상대 import·`import_module`·`__import__`·정상 상대 import 오탐 없음)을 추가 — meta_verify.py의 "수정완료 코드버그에 대응 회귀 테스트 존재"(F-043) 요구를 충족시킴(최초 수정 직후에는 이 요구가 빠져 있어 별도로 보완). 회귀: `python tools/layer_verify.py` **7/7** 유지(가드 리팩터링 후에도 단독 실행 동일) · `python fix_log/meta_verify.py` 77 → **81/81**(F-105 4건 추가) |
