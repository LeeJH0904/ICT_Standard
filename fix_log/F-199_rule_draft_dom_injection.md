# F-199 · 규칙 초안이 이스케이프 없이 DOM에 삽입됨

| 항목 | 값 |
|---|---|
| 심각도 | 오류 |
| 분류 | 코드버그 |
| 대상 | `project_code/web/rules.html:151,199,210,226,240` |
| 발견일 | 2026-08-12 |
| 상태 | 수정완료 |

## 근거

화면 설계서 §6.2는 미승인 규칙에 실행 버튼 자체가 없어야 한다고 정한다. `CLAUDE.md` §1-7은 AI가 제안한 미승인 규칙이 액추에이터 경로로 갈 수 없도록 요구한다. TTAK.KO-10.0937 부록 A 3.2 절차 3도 최종 의사결정 뒤 사용자가 제어 조건을 조정하도록 한다.

## 현상

서버가 반환한 `rule.draft_text`를 템플릿 문자열에 그대로 넣고 `innerHTML`로 렌더링한다. 초안 생성 API는 임의 문자열을 저장하고 그대로 반환하므로 HTML 속성 및 이벤트 처리기가 저장형 DOM 주입으로 해석될 수 있다.

## 영향

개발자가 미승인 카드에 실행 버튼을 넣지 않았더라도, 주입된 마크업이 동일 출처 API를 호출하는 UI를 만들 수 있어 DOM 구조 자체로 보장하려던 방어가 무력화된다.

## 재현

실행 서버의 초안 생성 API에 아래 문자열을 전송했다.

```html
<img src=x onerror="document.documentElement.dataset.stage7_poc=1">
```

생성·조회 API가 문자열을 변형 없이 왕복시키고, `rules.html`의 미승인·승인·기각 목록 생성부가 이 값을 이스케이프 없이 `innerHTML`에 넣는 것을 확인했다. 브라우저가 없어 이벤트의 실제 실행 화면은 별도로 검증하지 못했다.

---

## Claude 처리 기록

| 일시 | 상태 | 내용 |
|---|---|---|
| 2026-08-12 | 확인 | `rules.html`의 `pendingCardHtml`·`approvedCardHtml`·`rejectedCardHtml`이 `rule.draft_text`·`rule.condition_expr`·`rule.reject_reason`(및 `rule.id`, 장치 라벨 등)을 이스케이프 없이 템플릿 리터럴에 넣고, `renderPending`/`renderApproved`가 그 결과를 `innerHTML`에 대입함을 소스에서 확인. 지적된 라인(151·199·210·226·240)이 정확히 이 3개 출처 보간 + 2개 innerHTML 대입 지점과 일치함을 확인 |
| 2026-08-12 | 수정완료 | `static/fmt.js`에 `escapeHtml(value)` 신설(& < > " ' 5문자 치환, 텍스트·속성값 양쪽에서 안전). `rules.html`의 `pendingCardHtml`·`approvedCardHtml`·`rejectedCardHtml`·`renderExecutions`·`renderPublicData`·`loadDeviceOptions`에서 서버가 돌려준 자유 텍스트·id 전부를 `escapeHtml(...)`로 감쌌다(원 지적 대상인 draft_text·condition_expr·reject_reason 외에, 같은 파일 안의 동일 패턴인 device 라벨·집행 이력·공공데이터도 함께 — CLAUDE.md §1-7 "미승인 규칙이 구동기로 전달되는 경로" 방어와 같은 성격의 방어를 한 파일 안에서 절반만 적용하면 남은 절반이 다음 라운드에 같은 지적을 반복시킨다). **회귀 테스트**: `tools/web_live_verify.py`에 `rule.draft_text`·`condition_expr`·`reject_reason`이 `escapeHtml()` 없이 원문 그대로 보간되는 패턴이 없는지 보는 정적 검사 추가. **결함 주입 검증**: 임시 스테이징 사본에서 `escapeHtml(rule.draft_text)` 3곳 중 하나를 `rule.draft_text`로 되돌려 새 검사가 정확히 `FAIL`(재발 지점 3건 보고)로 잡고 `19/20`으로 실패함을 확인, 원복 후 실제 코드로 재실행해 `web_verify.py` 68/68·`web_live_verify.py` 20/20 전부 PASS로 복귀함을 확인. |

