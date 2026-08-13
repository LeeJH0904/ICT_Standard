# F-200 · SSE 재연결 시 누락 프레임 복구를 구현하지 않음

| 항목 | 값 |
|---|---|
| 심각도 | 위험 |
| 분류 | 문서불일치 |
| 대상 | `project_code/web/static/stream.js:23,72` · `project_code/web/verify.html:217,252` |
| 발견일 | 2026-08-12 |
| 상태 | 수정완료 |

## 근거

화면 설계서 §10은 SSE 폴백·재연결 때 마지막 수신 시각을 기준으로 `listFrames?since=`를 호출하여 누락 프레임을 복구하도록 정한다. 이는 TTAK.KO-10.0937 6.4의 지속적 환경 데이터·장치 상태 모니터링 요구와 일치하므로 설계 문서가 옳다.

## 현상

`stream.js`는 재연결 성공 시 폴링을 중지할 뿐 복구 콜백이나 마지막 시각을 전달하지 않는다. `verify.html`의 폴링도 `{limit: 100}` 조회만 수행하며 `since`를 사용하지 않는다.

## 영향

연결 단절 동안 100건을 초과한 프레임은 재연결 뒤 복구할 수 없어 검증 화면의 연속성이 깨진다.

## 재현

설계서의 SSE 복구 절과 `stream.js`의 `onopen`, `verify.html`의 프레임 조회 호출을 대조했다. 구현 어디에도 `since` 또는 마지막 수신 시각을 전달하는 경로가 없다. 실제 브라우저 단절·재연결 화면은 브라우저가 없어 검증하지 못했다.

---

## Claude 처리 기록

| 일시 | 상태 | 내용 |
|---|---|---|
| 2026-08-12 | 신규→확인 | 근거 재확인 — 실제 절 번호는 §10 이 아니라 **§3.2**(신고문의 조항 인용이 틀렸다, "누락 보정 | 폴백 중 놓친 프레임은 재연결 직후 `listFrames?since=` 로 채운다" 행). `stream.js`의 `es.onopen`이 `stopPolling()`·`setStatus(LIVE)`만 하고 복구 호출이 없음을, `verify.html`의 `onPollTick: loadFrames`가 매초 `listFrames({limit:100})`(since 없음)만 부름을 코드로 확인 — 신고 내용과 일치. `openapi.json`의 `listFrames`·`listViolations`엔 이미 `since`(ISO 8601) 파라미터가 있고 `backend/api.py`도 이미 `_iso_to_epoch(since)`로 `repository.list_frames(since=...)`에 결선돼 있어(예: `/alerts`·`/frames`·`/frames/violations` 전부) 백엔드 쪽 공백은 없고 프런트엔드 결선만 빠졌음을 확인 |
| 2026-08-12 | 확인→수정완료 | **`static/stream.js`**: `onReconnect` 콜백 신설 — `es.onerror`에서 `recovering=true`로 표시해 두고, 다음 `es.onopen`이 그 표시가 있을 때만(최초 연결은 제외) 1회 호출한다. "언제 재연결했는지"는 이 파일만 알고 "since= 에 무엇을 넣을지"(화면이 마지막으로 확인한 프레임 시각)는 호출자만 알아 책임을 그대로 나눴다. **`static/fmt.js`**: `epochToIso(epochSeconds)` 신설(기존 `isoToEpoch`의 반대 방향, `since=`에 넘길 ISO 문자열을 만드는 용도). **`verify.html`**: `recoverMissedFrames()` 신설 — `state.frames[0].t`(정렬상 가장 최신, 없으면 `loadFrames()`로 완전 재조회)를 `since=`로 `listFrames`/`listViolations`(현재 필터 유지)를 호출해 놓친 프레임을 오래된 것부터 `upsertFrame()`(내부적으로 `unshift`)해 목록 맨 위에 최신 순으로 다시 쌓는다. `connectStream({..., onReconnect: recoverMissedFrames})`로 결선. `onPollTick: loadFrames`(폴백 중 매초 최신 100건 새로고침)는 그대로 둔다 — 이번 수정은 그 100건 창을 넘는 프레임까지 재연결 시점에 정확히 닫는 안전망이다. 근본 원인(정적 검증기 어디도 이 결선을 보지 않음)도 닫기 위해 `tools/web_live_verify.py`에 `stream.js`가 `onReconnect` 훅을 갖고 `verify.html`이 그것을 `since=` 호출과 함께 결선했는지 텍스트로 확인하는 검사 신설(22→**23**항목, 브라우저 없이 단절·재연결을 실제 재현할 수 없다는 원 신고의 한계를 그대로 이어받아 헤드리스 시나리오는 시도하지 않았다). **결함 주입 검증**: `verify.html`에서 `onReconnect: recoverMissedFrames,` 줄을 제거한 사본 → 신설 검사가 `FAIL ... ['verify.html: connectStream({onReconnect:...}) 결선 없음']`으로 즉시 검출, 원복 후 23/23 재통과 확인. 검증: `python tools/web_live_verify.py` **23/23** · `python project_docs/web/web_verify.py` **68/68**(불변) · `pytest siap/tests/ backend/tests/ sim/tests/`(project_code/) **375/375** · `pytest tools/tests/` **28/28** |

