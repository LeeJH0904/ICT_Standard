# F-230 · CSS `@import` CDN을 웹 출구가 놓침

| 항목 | 값 |
|---|---|
| 심각도 | 오류 |
| 분류 | 코드버그 |
| 대상 | `tools/web_live_verify.py:L70,L206` · `project_docs/web/web_verify.py:L265` |
| 발견일 | 2026-08-13 |
| 상태 | 신규 |

## 근거

공고문 「소스코드 제출 안내」 재현성(필수) — “공모 접수 시 제출물만으로 실제 실행(재현)이 가능한 전체 소스코드를 제출해야 함.” 외부 API·서비스 조항 — 평가자가 실행할 수 있도록 테스트용 접근 수단, 목업·샘플 응답, 외부 의존 없는 형태 중 하나를 반드시 제공해야 한다. `CLAUDE.md` §1-9는 네트워크 필수 의존을 금지하고, 화면 설계서 §10은 외부 스크립트·폰트·CDN 참조 0건을 단계 7 검사 대상으로 정한다.

## 현상

`web_live_verify.py`의 `ALL_TXT`는 HTML과 JavaScript만 포함해 CSS를 읽지 않는다. 외부 참조 검사도 `src`·`href` 속성만 찾는다. `web_verify.py` 역시 HTML의 `src`·`href`만 검사한다. 따라서 실제 로드되는 `static/app.css` 맨 앞에 아래 외부 CDN 의존을 넣어도 두 단계 7 출구가 모두 통과한다.

```css
@import url(https://cdn.example.invalid/theme.css);
```

현재 제품 `app.css`에는 외부 `@import`가 없다. 결함은 현재 코드 위반이 아니라 검증기가 그 위반의 재발을 막지 못한다는 것이다.

## 영향

외부 네트워크가 없으면 스타일을 재현할 수 없는 화면도 `web_verify.py` 68/68과 `web_live_verify.py` 23/23을 통과한다. 단계 7의 CDN·오프라인 출구가 거짓 양성이다.

## 재현

제품 파일을 수정하지 않고 `pathlib.Path.read_text`를 메모리에서 대체하여 `app.css` 읽기 결과 앞에 위 `@import` 한 줄을 붙인 뒤 두 검증기를 실행했다.

```text
python project_docs/web/web_verify.py -> 68/68, exit 0
python tools/web_live_verify.py       -> 23/23, exit 0
```

## 제안

실제 로드되는 CSS 전량을 검사 입력에 포함하고 `@import`, `url(http://...)`, `url(https://...)`를 파싱해 외부 의존으로 판정한다.

---

## Claude 처리 기록

| 일시 | 상태 | 내용 |
|---|---|---|
