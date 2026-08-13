# F-137 · 주입 처리기의 연결 성공이 런타임 registry에 반영되지 않음

| 항목 | 값 |
|---|---|
| 심각도 | 치명 |
| 분류 | 코드버그 |
| 대상 | `project_code/siap/link.py:190` · `project_code/siap/registry.py:4` |
| 발견일 | 2026-08-09 |
| 상태 | 수정완료 |

## 근거

TTAK.KO-10.0943 8.1.1 — 연결 설정은 노드가 GCG와 조회·설정·알림 기능을 운용하기 위한 “초기 연결승인 절차”다. `registry.py`는 `link.py`가 `REQ_SET_CONNECTION` 처리를 마친 뒤 `register()`를 호출한다고 계약한다. 아키텍처 설계서 §3.1은 실제 상위 처리를 `on_frame=backend.ingest.handle`로 주입한다고 정한다.

## 현상

`_default_reply()` 경로만 `self._registry.register()`를 호출한다. 실제 운용 경로인 `_on_frame` 주입 시 `_dispatch()`는 콜백의 성공 `RES_SET_CONNECTION`을 그대로 반환하고 registry를 갱신하지 않는다. 성공 응답 직후 registry 크기는 0이며 같은 노드의 다음 정상 프레임은 `INVALID_NODE_ID`가 된다. 같은 이유로 `device_control()`의 종류 조회가 실패하면 `ACTUATOR/WINDOW_OPENER`라는 임의값으로 대체된다.

## 영향

backend를 연결하는 순간 기본 테스트에서는 되던 연결 승인이 런타임 세션에 반영되지 않는다. 이후 조회·알림·제어가 모두 미등록 경로로 빠져 기능 1의 Plug & Play와 실제 통합 경로가 붕괴한다.

## 재현

```text
link._on_frame = callback_returning_SUCCESS_RES_SET_CONNECTION
link._dispatch(REQ_SET_CONNECTION) -> RES_SET_CONNECTION/SUCCESS
len(link.registry()) -> 0
decode next NOTI_KEEP_ALIVE with registry.is_known -> INVALID_NODE_ID
```

## 제안

연결 성공의 런타임 상태 반영 책임을 기본 처리기와 주입 처리기에서 공통으로 거치는 한 지점에 두고, 미등록 디바이스 제어는 임의 subtype을 만들지 말고 실패시킨다.

---

## Claude 처리 기록

| 일시 | 상태 | 내용 |
|---|---|---|
| 2026-08-09 | 확인 | `link.py::_dispatch()`가 `_on_frame`이 주입되면 `_default_reply()`를 전혀 부르지 않고, `registry.register()`/`unregister()` 호출이 오직 `_default_reply()` 안에만 있음을 소스에서 확인 — `on_frame` 경로에서 성공한 `REQ_SET_CONNECTION`이 registry에 반영되지 않음을 확인. `build.py::_lookup_device_kind()`가 registry 조회 실패 시 `DevType.ACTUATOR`/`Subtype.WINDOW_OPENER`로 조용히 대체함을 확인 — 실제로 존재 여부를 모르는 디바이스 종류를 지어내 제어 프레임에 싣는 것으로, CLAUDE.md §1-1(합성 데이터 금지)의 정신과 같은 문제로 판단 |
| 2026-08-09 | 수정완료 | (1) `link.py`에 `_apply_registry_effects(frame, reply)` 신설 — `_io_loop()`가 `_dispatch()` 직후(경로 무관) 호출한다. 회신 Frame 자체(`reply.node_property`/`reply.device_properties`)에서 등록 내용을 읽으므로 `_default_reply()`·주입된 `on_frame` 어느 쪽이 만든 회신이든 동일하게 처리된다. `_default_reply()`에서 직접 `register()`/`unregister()` 호출 제거(중복 방지, 갱신 지점을 하나로 좁힘). (2) `build.py::_lookup_device_kind()`를 방어적 대체 대신 `ValueError` 발생으로 변경 — registry가 없거나 그 노드에 device_id가 없으면 실패시킨다. 회귀 테스트 추가: `test_link.py::test_on_frame_success_still_registers_f137`(주입된 콜백이 SUCCESS 회신을 만들어도 `link.registry()`에 반영되는지), `test_build.py::test_device_control_fails_without_registry_f137` + `test_device_control_fails_for_unregistered_device_f137`(ValueError 발생 확인), 기존 `test_gateway_originated_builders_encode_cleanly`에서 `REQ_SET_DEVICE_CONTROL`을 분리해 `test_device_control_encodes_cleanly_with_registry`로 별도 작성(registry 필요). 결함 주입(`_apply_registry_effects()` 호출 제거) 후 `test_on_frame_success_still_registers_f137`이 정확히 실패함을 확인하고 원복 — `pytest siap/tests/` 93/93 재통과 |
