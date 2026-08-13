# F-206 · 계층 검증기가 project_docs 금지를 contracts에만 적용

| 항목 | 값 |
|---|---|
| 심각도 | 오류 |
| 분류 | 코드버그 |
| 대상 | `tools/layer_verify.py:L210` |
| 발견일 | 2026-08-12 |
| 상태 | 신규 |

## 근거

`CLAUDE.md` §2.2 — `project_code/`는 `project_docs/`를 import하지 않는다. 단계 1 출구도 `project_code -x-> project_docs`를 선언한다.

## 현상

검증기 제목과 달리 `project_docs` 탐지는 `project_code/contracts/`에만 적용된다. `backend/`, `siap/`, `sim/` 등의 같은 금지 import는 검사하지 않는다.

## 영향

F-025 import가 다른 구현 계층으로 재유입돼도 단계 1 출구가 7/7로 거짓 통과한다.

## 재현

임시 `project_code/backend/bad.py`에 `from project_docs.contracts import frame`을 쓰고 검증기의 `ROOT`·`PROJECT_CODE`를 임시 트리로 바꿔 `main()`을 호출했다.

```text
_top_level_modules(bad.py) -> ['project_docs']
layer_verify.main()        -> 7/7 통과, exit 0
```

파서는 금지 모듈을 인식했지만 디렉터리 범위 때문에 놓쳤다.

## 제안

`project_code/` 아래 모든 Python 파일을 검사하고 임시 하위 패키지 위반을 회귀 테스트로 둔다.

---

## Claude 처리 기록

| 일시 | 상태 | 내용 |
|---|---|---|

