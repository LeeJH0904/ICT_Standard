# F-233 · 폴링이 SSE 누락 복구의 연속 커서를 잃음

| 항목 | 값 |
|---|---|
| 심각도 | 위험 |
| 분류 | 코드버그 |
| 대상 | `project_code/web/verify.html:L212-L264` · `project_code/web/static/stream.js:L56-L86` · F-205 |
| 발견일 | 2026-08-14 |
| 상태 | 수정완료 |

## 근거

TTAK.KO-10.0937 §6.4 — 농장 환경의 상태를 연속적으로 측정하여 결과를 집계 분석할 수 있다.

화면 설계서 §3.2 — 폴백 중 놓친 프레임은 재연결 직후 `listFrames?since=`로 채운다.

## 현상

F-205는 `collectAllPages()`로 고정된 `since`부터 `total`까지 페이지를 모두 소비하도록 바뀌었다. 그러나 폴링 폴백의 `onPollTick: loadFrames`가 매초 `state.frames`를 서버의 최신 100건으로 통째로 교체한다. 재연결 뒤 `recoverMissedFrames()`는 교체된 배열의 최신 항목 `state.frames[0].t`를 `since`로 사용한다.

따라서 단절 직전 마지막 연속 프레임이 50이고 단절 중 151건이 들어온 경우, 폴링이 최신 100건(101~200)을 읽은 뒤 복구 커서는 50이 아니라 200이 된다. `collectAllPages()`는 200 이후만 조회하므로 51~100의 50건은 여전히 영구 누락된다.

## 영향

F-205의 수정완료 기록과 구현 주석의 마지막 확인 프레임 이후 전부라는 주장이 실제 폴백 상태 전이에서는 성립하지 않는다. 빠른 유입이나 긴 단절에서 검증 화면의 위반 프레임 일부가 영구 누락된다.

## 재현

실제 `verify.html`에서 `loadFrames()`와 `recoverMissedFrames()` 함수 본문을 추출해 격리 실행했다.

```text
초기 state.frames[0].t = 50
loadFrames 응답 = 최신 100건, t=200..101
loadFrames 뒤 state.frames[0].t = 200
recoverMissedFrames의 요청 since = ISO(200)
영구 누락 구간 = 51..100
```

같은 구현에서 `python tools/run_all.py`는 20/20으로 통과한다.

## 제안

SSE 단절 순간의 마지막 연속 커서를 폴링 표시 목록과 별도 상태로 보존하고, 재연결 복구가 그 고정 커서를 사용하도록 한다.

---

## 작업자 처리 기록

| 일시 | 상태 | 내용 |
|---|---|---|
| 2026-08-14 | 확인 | 단절 직전 `state.frames[0].t=50`인 상태에서 폴링 응답 `200..101`이 표시 목록을 교체하면 기존 `recoverMissedFrames()`가 `since=200`을 사용하여 `51..100`을 영구 누락하는 상태 전이를 구현에서 확인했다. |
| 2026-08-14 | 수정완료 | stream.js가 최초 단절 때 onDisconnect를 호출하고 verify.html이 recoverySince를 폴링 표시 목록과 별도로 고정한다. 복구 실패 시 커서를 유지하고 전체 페이지 복구 성공 뒤에만 해제한다. 기존 목록 기반 since 계산을 재주입하면 전용 회귀 검사와 두 웹 출구가 실패함을 확인했다. |
