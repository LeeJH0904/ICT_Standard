# F-234 · 화살표 함수 헬퍼의 미승인 실행 경로를 놓침

| 항목 | 값 |
|---|---|
| 심각도 | 오류 |
| 분류 | 코드버그 |
| 대상 | `tools/web_source_checks.py:L12-L106` · `tools/web_live_verify.py:L271-L279` · `project_docs/web/web_verify.py:L302-L307` · F-204 |
| 발견일 | 2026-08-14 |
| 상태 | 수정완료 |

## 근거

TTAK.KO-10.0937 부속서 A 3.2 절차 3 — 사용자는 최종 의사결정 후 제어 조건 조정을 한다.

화면 설계서 §6.2 — 미승인 규칙에는 실행 버튼 자체를 렌더링하지 않는다.

## 현상

F-204 수정의 호출 그래프는 `_FUNCTION_HEAD`가 찾는 `function name(...) {}` 선언만 함수 본문으로 등록한다. `const helper = (...) => ...` 형태의 로컬 헬퍼는 등록되지 않으므로 `pendingCardHtml()`이 호출해도 도달 가능한 함수 집합에 들어가지 않는다.

미승인 카드가 화살표 함수 헬퍼를 통해 `/execute` 폼과 실행 버튼을 반환하도록 메모리에서 주입했지만 `pending_execute_paths()`는 빈 목록을 반환했다. 두 웹 출구는 이 공통 판정 함수를 그대로 사용한다.

## 영향

실제 미승인 카드에 실행 경로가 생겨도 단계 7의 두 출구가 모두 녹색이 될 수 있다. F-204 처리 기록의 도달 가능한 로컬 헬퍼 재귀 추적 주장은 화살표 함수 선언에는 적용되지 않는다.

## 재현

```javascript
const hiddenPendingExecuteForm = (ruleId) =>
  `<form method='post' action='/api/v1/rules/${ruleId}/execute'><button type='submit'>실행</button></form>`;

function pendingCardHtml(rule) {
  return `${hiddenPendingExecuteForm(rule.id)}...`;
}
```

```text
arrow_helper_present = True
execute_path_present = True
pending_execute_paths = []
```

## 제안

함수 표현식·화살표 함수의 지역 바인딩과 호출을 같은 그래프에 포함하거나, 실제 DOM에서 미승인 카드 하위 실행 경로가 0개인지 판정한다.

---

## 작업자 처리 기록

| 일시 | 상태 | 내용 |
|---|---|---|
| 2026-08-14 | 확인 | `pendingCardHtml()`이 `/execute` 폼을 반환하는 화살표 함수 헬퍼를 호출하도록 주입했을 때 `_FUNCTION_HEAD`가 해당 바인딩을 등록하지 않아 `pending_execute_paths()`가 빈 목록을 반환함을 확인했다. |
| 2026-08-14 | 수정완료 | 공통 함수 본문 수집기가 const·let·var 화살표 함수 바인딩을 호출 그래프에 포함한다. 미승인 카드가 화살표 헬퍼를 통해 실행 폼을 반환하는 결함을 재주입해 pending_execute_paths와 두 웹 출구가 차단함을 확인했다. |
