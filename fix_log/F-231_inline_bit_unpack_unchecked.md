# F-231 · HTML 인라인 비트 언팩을 웹 출구가 놓침

| 항목 | 값 |
|---|---|
| 심각도 | 오류 |
| 분류 | 코드버그 |
| 대상 | `tools/web_live_verify.py:L229-L230` · `project_docs/web/web_verify.py:L269` |
| 발견일 | 2026-08-13 |
| 상태 | 신규 |

## 근거

`CLAUDE.md` §3.4 — “`backend/`, `web/`은 표준 조항을 다시 해석하지 않는다. `siap/`이 판정한 `violations`를 렌더링만 한다.” 화면 설계서 §10은 비트 언팩·프레임 디코딩을 금지하며 코덱은 `siap/` 한 곳뿐이라고 정한다. 개발 착수 지시서 §3.9는 화면이 비트 언팩을 하지 않는지를 단계 7 GPT 검증 대상으로 명시한다.

## 현상

`web_live_verify.py`의 시프트 검사는 `static/*.js`만 읽는다. 그러나 현재 네 화면의 실제 로직은 각 HTML의 인라인 `<script type=module>`에 있다. `web_verify.py`의 RSC·NEC·Subtype 검사도 `static/*.js`만 결합한다. 따라서 `verify.html`에 헤더 값을 직접 시프트하는 인라인 스크립트를 넣어도 두 검증기가 모두 통과한다.

숫자 키 기반 위반 코드→한국어 매핑도 `INVALID_*` 이름을 쓰지 않으면 `web_live_verify.py` 23/23을 통과했다. 현재 제품 화면에는 이러한 비트 언팩·숫자 매핑이 없다.

## 영향

프로토콜 해석이 `siap/`과 화면 두 곳으로 갈린 잘못된 구현이 단계 7 출구를 통과한다. 코덱 판정이나 코드값이 바뀌면 화면만 다른 결과를 표시할 수 있다.

## 재현

제품 파일을 수정하지 않고 `pathlib.Path.read_text`를 메모리에서 대체하여 `verify.html` 읽기 결과에 `const decodedVersion = (0x1200 >> 8) & 0xFF;`를 담은 인라인 스크립트를 덧붙인 뒤 실행했다.

```text
python project_docs/web/web_verify.py -> 68/68, exit 0
python tools/web_live_verify.py       -> 23/23, exit 0
```

## 제안

HTML의 인라인 스크립트까지 JavaScript 검사 입력에 포함하고, 단순 문자열 검색 대신 파싱된 스크립트의 시프트·마스크·코드값 분기와 매핑 객체를 검사한다.

---

## Claude 처리 기록

| 일시 | 상태 | 내용 |
|---|---|---|
