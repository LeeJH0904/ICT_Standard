# F-235 · 프로토콜 상대 CSS CDN을 외부 의존으로 탐지하지 못함

| 항목 | 값 |
|---|---|
| 심각도 | 오류 |
| 분류 | 코드버그 |
| 대상 | `tools/web_source_checks.py:L120-L131` · `tools/web_live_verify.py:L225-L228` · `project_docs/web/web_verify.py:L285-L289` · F-230 |
| 발견일 | 2026-08-14 |
| 상태 | 수정완료 |

## 근거

공고문 「소스코드 제출 안내」 재현성 — 제출물만으로 실제 실행 가능한 전체 소스코드를 제출해야 한다.

공고문 외부 API·서비스 — 평가자가 실행할 수 있도록 테스트 수단·목업·샘플 응답·외부 의존 없는 형태 중 하나를 제공해야 한다.

화면 설계서 §10 — 외부 스크립트·폰트·CDN 참조 0건을 단계 7에서 검사한다.

## 현상

F-230 수정의 CSS 정규식은 `http://`와 `https://`만 찾는다. CSS에서 유효한 프로토콜 상대 URL `//cdn.example.invalid/...`은 현재 페이지가 HTTP이면 외부 HTTP CDN으로 해석되지만 검사에 걸리지 않는다.

```css
@import url(//cdn.example.invalid/theme.css);
```

## 영향

네트워크가 차단된 평가 환경에서 스타일 재현이 실패하는 화면도 단계 7의 오프라인·CDN 출구를 통과한다.

## 재현

```text
external_css_references의 입력:
app.css = @import url(//cdn.example.invalid/theme.css);
결과 = []
```

현재 제품 `app.css`에는 이 외부 참조가 없다. 결함은 회귀 검증기의 사각지대다.

## 제안

CSS `@import`와 `url()` 값에서 `http:`, `https:`, `//`를 모두 외부 참조로 판정한다.

---

## 작업자 처리 기록

| 일시 | 상태 | 내용 |
|---|---|---|
| 2026-08-14 | 확인 | `@import url(//cdn.example.invalid/theme.css)`를 `external_css_references()`에 입력했을 때 현재 `https?://` 전용 정규식이 탐지하지 못해 빈 목록을 반환함을 확인했다. |
| 2026-08-14 | 수정완료 | CSS @import와 url()이 http://·https://뿐 아니라 // 프로토콜 상대 외부 참조도 탐지한다. @import와 배경 URL 반례를 F-235 전용 회귀 테스트로 고정했고 두 웹 출구에서 차단됨을 확인했다. |
