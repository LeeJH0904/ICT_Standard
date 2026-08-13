# F-204 · 미승인 실행 버튼 검사가 헬퍼 렌더를 놓침

| 항목 | 값 |
|---|---|
| 심각도 | 오류 |
| 분류 | 코드버그 |
| 대상 | `tools/web_live_verify.py:L246` · `project_code/web/rules.html` |
| 발견일 | 2026-08-12 |
| 상태 | 신규 |

## 근거

TTAK.KO-10.0937 부속서 A 3.2 절차 3 — "사용자는 최종 의사결정 후 제어 조건 조정을 한다."

화면 설계서 §6.2 — 미승인 규칙에는 `disabled` 실행 버튼이 아니라 실행 버튼 자체를 렌더링하지 않는다.

## 현상

`web_live_verify.py`는 `pendingCardHtml()` 함수 본문만 정규식으로 잘라 `run-rule` 또는 `실행</button>` 문자열을 찾는다. 별도 헬퍼가 실행 폼을 반환하고 `pendingCardHtml()`이 그 헬퍼만 호출하면 실제 미승인 카드에 실행 버튼이 생겨도 검사 범위 밖이다.

## 영향

단계 7 핵심 검증 항목인 "미승인 규칙에 실행 버튼이 아예 없음"을 위반하는 화면이 두 웹 출구 검증기를 모두 통과한다. 서버 승인 게이트가 409로 차단하더라도 화면 계층의 실행 경로 부재 주장을 검증기가 증명하지 못한다.

## 재현

원본과 격리한 임시 사본의 `rules.html`에 아래 코드를 추가하고 미승인 카드 템플릿에서 `${hiddenPendingExecuteForm(id)}`를 호출했다.

```javascript
function hiddenPendingExecuteForm(ruleId) {
  return `<form method="post" action="/api/v1/rules/${ruleId}/execute">
    <button type="submit">실행</button>
  </form>`;
}
```

실행 결과:

```text
python tools/web_live_verify.py       -> 23/23 통과
python project_docs/web/web_verify.py -> 68/68 통과
```

## 제안

한 함수의 원문 부분 문자열이 아니라 실제 DOM을 렌더해 미승인 카드 하위에 실행 버튼·실행 폼·실행 엔드포인트가 0개인지 판정한다. 정적 검사만 유지한다면 함수 호출 관계와 HTML `form[action]`까지 최소한 추적한다.

---

## Claude 처리 기록

| 일시 | 상태 | 내용 |
|---|---|---|
