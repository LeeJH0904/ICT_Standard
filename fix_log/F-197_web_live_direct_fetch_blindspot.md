# F-197 · fetch 경로 검증기가 직접 fetch 반례를 놓침

| 항목 | 값 |
|---|---|
| 심각도 | 오류 |
| 분류 | 코드버그 |
| 대상 | `tools/web_live_verify.py:86-126` |
| 발견일 | 2026-08-12 |
| 상태 | 수정완료 |

## 근거

개발 착수 지시서 단계 7 GPT 검증은 화면이 fetch하는 경로 전부를 실행 라우트와 직접 대조하도록 요구한다. `CLAUDE.md` §1-9는 외부 CDN·서비스 의존을 금지한다.

## 현상

검증기는 `static/api.js`의 래퍼 정의만 정규식으로 추출하고 외부 참조는 HTML의 `src`·`href`만 본다. 다른 JavaScript 또는 인라인 스크립트의 직접 `fetch()`는 검사하지 않는다.

## 영향

화면이 존재하지 않는 실행 경로나 외부 URL을 직접 호출해도 `fetch 경로와 실행 라우트 일치` 및 외부 의존 금지 검사를 통과할 수 있다.

## 재현

저장소를 변경하지 않고 검증용 임시 복사본의 실제 로드 모듈 `project_code/web/static/a11y.js` 끝에 아래 반례를 추가했다.

```javascript
fetch("https://example.invalid/unlisted", {method: "POST"});
```

그 상태에서도 `web_verify.py`는 62/62, `web_live_verify.py`는 16/16으로 통과했다. 임시 복사본은 검증 뒤 삭제했다.

---

## Claude 처리 기록

| 일시 | 상태 | 내용 |
|---|---|---|
| 2026-08-12 | 확인 | `tools/web_live_verify.py:83-121`이 `api.js`의 `request(...)` 래퍼 정의(`DEF_RE`)와 각 화면의 `api.<name>()` 호출만 대조하고, `fetch(`를 직접 호출하는 코드는 어디에도 스캔하지 않음을 소스에서 확인. GPT가 보고한 재현(임시 사본의 `a11y.js`에 `fetch("https://example.invalid/unlisted", ...)` 추가)을 그대로 재실행해 `web_verify.py` 62/62·`web_live_verify.py` 16/16이 그대로 유지됨을 확인 |
| 2026-08-12 | 수정완료 | `tools/web_live_verify.py`에 검사 3종 추가 — ① `api.js` 밖의 모든 파일에서 `fetch(` 호출 0건 ② `api.js` 자신도 `request()` 안 1곳에서만 `fetch(` 호출 ③ 어느 파일에서든 `fetch(`에 외부 절대 URL 문자열 리터럴을 직접 넘기지 않음. **결함 주입 검증**: 임시 스테이징 사본에 GPT의 PoC(`a11y.js` 끝에 `fetch("https://example.invalid/unlisted", {method:"POST"})` 추가)를 재현한 뒤 새 검증기를 돌려 `FAIL` 2건(직접 fetch 금지·외부 URL 금지)이 정확히 잡히고 `17/19`로 실패함을 확인, 원복 후 실제 코드로 재실행해 `20/20`(F-199 검사 포함) 전부 PASS로 복귀함을 확인. |

