# F-203 · 수신 Frame 시각이 전부 0으로 저장됨

| 항목 | 값 |
|---|---|
| 심각도 | 오류 |
| 분류 | 코드버그 |
| 대상 | `project_code/contracts/frame.py:267` · `siap/codec.py` · `backend/ingest.py:125` · `web/index.html:74` · `verify.html:99` |
| 발견일 | 2026-08-12 |
| 상태 | 수정완료 |

## 근거

TTAK.KO-10.0937 6.4 — "농장 환경의 상태를 연속적으로 측정하여 결과를 집계, 분석할 수 있다" 및 "농장에 설치된 장치에 대한 상태정보를 제공할 수 있어야 한다."

Frame 구조 명세서 §3은 `Frame.t`를 "수신 시각"으로 정의하고, API 명세서 §1은 `frame_log.t`를 replay 타이밍 계산의 epoch 실수로 정의한다. 따라서 설계가 옳고 항상 0을 저장하는 구현이 틀렸다.

## 현상

`Frame.t` 기본값은 0.0인데 수신 디코드·링크 경로 어디에서도 실제 수신 시각을 채우지 않는다. `ingest.handle()`은 이 값을 그대로 `frame_log.t`에 저장한다. 임시 DB로 `run.py --mode simulate --serve`를 실행한 결과 1,409개 프레임의 `COUNT(DISTINCT t)=1`, `MIN(t)=MAX(t)=0.0`이었다. `/api/v1/nodes`의 `connected_at`·`last_seen_at`도 전부 1970-01-01이었다.

## 영향

활성 simulate 노드도 `index.html`의 60초 판정에서 "응답 없음"으로 표시되고, `verify.html`의 모든 프레임 시각이 1970년으로 보인다. `since`·`until` 조회와 누락 프레임 복구의 시각 기준도 성립하지 않아 0937 6.4 모니터링 이력이 무의미해진다.

## 재현

```powershell
python project_code/run.py --mode simulate --serve --db <임시DB>
# 실행 중인 임시 DB에서
python -c "import sqlite3; c=sqlite3.connect(r'<임시DB>'); print(c.execute('select count(*),count(distinct t),min(t),max(t) from frame_log').fetchone())"
```

실측 결과: `(1409, 1, 0.0, 0.0)`. `/api/v1/nodes`의 네 노드도 `last_seen_at=1970-01-01T09:00:00+09:00`이었다.

---

## Claude 처리 기록

| 일시 | 상태 | 내용 |
|---|---|---|
| 2026-08-12 | 신규→확인 | 근거 재현. `codec.decode_frame()`은 순수 함수라 수신 시각을 모르며(골든 벡터 재생·단독 코덱 테스트의 결정론을 지키기 위해 의도적임을 `siap/codec.py` 스트리밍 디코더 docstring에서 확인), 실제 수신 시각은 `siap/link.py::_io_loop()`가 전송 계층에서 바이트를 읽어 디코더가 완결된 `Frame`을 내보내는 순간만 안다. 그런데 이 파일 어디에도 `Frame.t`를 채우는 코드가 없어 기본값 0.0이 그대로 `backend/ingest.py:132`의 `t=frame.t`를 거쳐 `frame_log.t`에 저장됨을 확인 — 신고 내용과 일치 |
| 2026-08-12 | 확인→수정완료 | `siap/link.py`에 `import dataclasses` 추가, `_io_loop()`의 `for frame in self._decoder.feed(chunk):` 직후 `frame = dataclasses.replace(frame, t=time.time())`로 실제 수신 시각(epoch, `repository.py::_epoch_to_iso`가 기대하는 단위와 동일)을 채움 — `Frame`이 `frozen=True`라 `replace()`로 새 값을 만듦(CLAUDE.md §4.3). 이 한 지점만 고치면 `recvq`(→ `link.recv()`)와 `on_frame`(→ `backend.ingest.handle()`) 양쪽 소비자가 모두 실제 시각을 받는다 — `_dispatch()` 안에서 `on_frame`이 호출되기 전에 stamping이 끝나므로 순서 문제 없음. `web/index.html:74`·`verify.html:99`는 `last_seen_at`을 올바르게 소비만 하고 있어(코드 확인) 별도 수정 불필요, 근본 원인은 backend가 항상 1970을 내려준 것 하나뿐이었음. 회귀 테스트 `siap/tests/test_link.py::test_recv_stamps_real_wall_clock_time_f203` 신설 — `on_frame`으로 프레임을 캡처해 `Frame.t`가 0.0이 아니고 테스트 실행 구간 `[before, after]` 안에 있는지 확인. 결함 주입(`frame = dataclasses.replace(...)` 줄 제거) 후 새 테스트가 `assert 0.0 != 0.0`으로 즉시 실패함을 확인, 원복 후 `siap/tests/test_link.py` 10/10 재통과 확인. 실제 실행 검증: `run.py --mode simulate --serve --db <임시DB> --http-port 8799` 6초 구동 후 `frame_log`에서 `(22, 22, 1786511005.9, 1786511010.9)`(count, count(distinct t), min, max) — 22건 전부 서로 다른 실측 epoch 시각(2026-08-12 실행 시각과 일치), `curl /api/v1/nodes` 응답도 `connected_at`·`last_seen_at`이 `2026-08-12T14:03:5x+09:00`로 정상 표시됨(원 신고의 1970-01-01 재현과 반대 결과). `pytest siap/tests/ backend/tests/ sim/tests/` 375/375(신규 테스트 포함, 이전 374) 통과 |