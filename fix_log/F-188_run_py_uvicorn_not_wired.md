# F-188 · run.py 가 아직 uvicorn 을 기동하지 않음 — API 서버가 실행 경로에서 뜨지 않는다

| 항목 | 값 |
|---|---|
| 심각도 | 위험 |
| 분류 | 문서불일치 |
| 대상 | `project_code/run.py` (자체 docstring) |
| 발견일 | 2026-08-11 |
| 상태 | 수정완료 |

## 근거

`run.py` 자신의 모듈 docstring(단계 5에서 작성) — "'5. uvicorn 기동'은 여전히 단계 6(`services/`·`api.py`)의 몫이라 없다." 아키텍처 설계서 §9.1~§9.2 기동 순서도 5단계 중 마지막이 uvicorn 기동이다.

## 현상

단계 6에서 `backend/api.py::create_app()`을 완성했지만, `run.py`의 세 모드 함수(`_run_simulate`·`_run_replay`·`_run_hardware`)는 여전히 `SiapLink`를 기동하고 관찰 시간(`--duration`) 동안 대기한 뒤 **정상 종료**만 한다 — `create_app()`을 호출하거나 `uvicorn.run()`을 부르는 코드가 없다. `python run.py --mode simulate`를 실행해도 HTTP 서버는 뜨지 않는다.

## 영향

시연 시나리오·2차 발표에서 `web/`(단계 7)가 실제로 API를 두드리려면 서버가 떠 있어야 하는데, 지금은 `run.py` 실행이 끝나 버린다. 이번 단계의 4개 출구 명령(`pytest backend/tests/`·`route_verify.py`·`gate_e2e.py`·`nodetype_verify.py`)은 전부 `create_app()`이 만든 앱 객체를 직접(ASGI로) 두드려 검증하므로 이 결선 없이도 통과하지만, 실제 재현 경로(`python run.py --mode simulate`)의 최종 완결에는 필요하다.

## 재현

```bash
python run.py --mode simulate --duration 3
# "가상 노드 서버 기동" ~ "종료 — 등록 노드 N개" 까지만 찍히고 끝난다.
# 다른 터미널에서 curl http://127.0.0.1:8000/api/v1/health 를 시도하면 연결 거부.
```

## 제안

`_run_simulate`/`_run_replay`/`_run_hardware`가 `link.start(...)` 이후 `siap.build.FrameBuilderImpl(gcg_id, mode, registry=link)`(주의: `registry=link` — `FrameBuilder._lookup_device_kind()`가 필요로 하는 것은 `.devices(node_id)` 메서드뿐이라 `SiapLink` 자신을 그대로 넘길 수 있다, `backend/api.py::create_app()` 독스트링 참고)로 빌더를 만들고, `backend.api.create_app(db_path=db_path, link=link, builder=builder, run_mode=..., proto_mode=args.proto)`로 앱을 만들어 `uvicorn.run(app, host="127.0.0.1", port=8000)`을 부른다. `--duration`은 uvicorn 이 떠 있는 동안의 의미로 재해석하거나(무기한 실행 + Ctrl-C), 별도 플래그(`--serve`)로 분리한다. `sim/inject.py`(F-084)를 감싼 `inject_fn` 콜백(`simulate` 모드는 `virtual_node.py`의 로컬 제어 채널로 `sim.inject.vector_bytes()`의 원본 바이트를 흘려보내면 된다, `backend/api.py::create_app()` 독스트링 참고)도 이 지점에서 함께 배선한다 — 지금은 `inject_fn=None`이라 `POST /sim/inject`가 항상 409를 반환한다.

---

## Claude 처리 기록

| 일시 | 상태 | 내용 |
|---|---|---|
| 2026-08-11 | 보류 | 단계 6 출구 명령(4종)은 `create_app()`을 직접 테스트하므로 이 결선 없이 전부 통과한다 — `run.py` 변경은 이번 단계 "범위: services/+api.py"를 벗어나는 별도 작업이라 시간 배분상 미뤘다. 재검토 시점: 단계 7(`web/`) 착수 전 — 화면이 실제 API를 두드리려면 이 결선이 선행돼야 한다 |
| 2026-08-11 | 수정완료 | 제안(§) 그대로 구현 — `--serve` 플래그 신설(기본값 없음이면 기존 동작 그대로 유지, 회귀 없음). 셋 다(`_run_simulate`/`_run_replay`/`_run_hardware`) `--serve`일 때 `siap.build.FrameBuilderImpl(1, args.proto, registry=link)`로 빌더를 만들고 `backend.api.create_app(...)` → `uvicorn.run(app, host="127.0.0.1", port=args.http_port)`(Ctrl-C 로 종료)을 부르는 공용 헬퍼 `_serve_app()`으로 수렴시켰다. `simulate` 모드는 `_make_inject_fn()`(신설)로 `POST /sim/inject`를 실제로 배선 — `sim/inject.py`의 로컬 제어 채널(`_cli_inject`)에 `INJECT <id>`를 보내 `virtual_node.py`가 골든 벡터 원본 바이트를 그대로 흘려보내게 하고, 반환값은 같은 `vector_bytes()`라 "영상 속 hex == golden.jsonl" 근거가 그대로 유지된다. `replay`·`hardware`는 라이브 주입 채널이 없어(전자는 재생 서버가 명령을 안 받고, 후자는 CLAUDE.md §1-1이 실물 링크 조작을 금지) `inject_fn=None`을 그대로 두었다 — `api.py` 자체가 이미 409로 정직하게 거부한다. **실측 스모크 테스트(수동)**: `python run.py --mode simulate --serve`를 실제로 띄우고 `curl /api/v1/health`(200, `io_thread_alive:true`)와 `POST /api/v1/sim/inject {"vector_id":"X01"}`(실제 X01 골든 바이트가 주입돼 `INVALID_VERSION` 판정)까지 end-to-end 확인, `replay --serve`도 health 200 + inject 409(설계대로) 확인. **신설 검증기**: `tools/run_live_verify.py` — `run.py`를 실제 서브프로세스로 띄우고 HTTP로 두드린다(기존 4개 출구 명령은 전부 `create_app()` 앱 객체를 직접 ASGI로 두드려 프로세스 기동 자체는 아무도 보지 않았다). **결함 주입 검증**: `if args.serve:`를 전부 `if False and args.serve:`로 바꿔치기 → 4개 검사 전부 실패(exit 1, health 타임아웃으로 실제 원인까지 출력) 확인 후 원상복구, 6/6 재통과. **부수 발견**: 이 작업 중 `tools/where.py`가 로컬에 남아 있던 구버전 스키마의 `project_code/backend/runtime.db`(이전 세션 산출물, `elements_json` 컬럼 없음)로 `sqlite3.OperationalError`를 내는 것을 발견 — `_prepare_db_path()`의 기존 계약("파일 있으면 그대로 연다, 마이그레이션 없음")대로 그 파일을 삭제해 재생성되게 함(스키마 변경 시 로컬 `runtime.db` 재생성이 필요하다는 기존 문서화된 동작, 새 결함 아님). 검증: `pytest siap/tests/ backend/tests/` **343/343**(무변화) · `python tools/run_live_verify.py`(신설) **6/6** · `python fix_log/meta_verify.py` **107/107**(신설 검증기 CP949 검사 2건 포함) · `python tools/where.py` — 단계 0 `run.py --mode simulate/replay` 둘 다 `[OK]`, 단계 5·6 `통과` 유지, 현재 단계 7 재확인 |
