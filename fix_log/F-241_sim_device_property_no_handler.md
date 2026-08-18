# F-241 · simulate 가상 노드가 REQ_SET_DEVICE_PROPERTY를 미처리해 설정 적용이 타임아웃한다

| 항목 | 값 |
|---|---|
| 심각도 | 오류 |
| 분류 | 코드버그 |
| 대상 | `sim/virtual_node.py::_handle` · `sim/_wire.py` |
| 발견일 | 2026-08-18 |
| 상태 | 수정완료 |

## 근거

0943 8.1.3.2 `REQ_SET_DEVICE_PROPERTY`(표 7-2 "양방향") — 게이트웨이가 노드로
DEVICE_PROPERTY×N을 보내 수집 주기·전송 모드·전송 임계를 설정하고, 노드는
`RES_SET_DEVICE_PROPERTY`(표 7-3)로 회신한다. settings 화면은 0937 6.4-2 ·
부속서 A 1.3 근거로 이 경로를 사용한다.

## 현상

`backend/services/ems.py::set_device_property()`는 표준대로 `REQ_SET_DEVICE_PROPERTY`
프레임을 만들어 `link.send()`로 노드에 보내고 `RES`를 기다린 뒤 성공일 때만 DB를
갱신한다. 그러나 simulate 모드의 노드인 `sim/virtual_node.py::_handle()`은
`MT_REQ_SET_DEVICE_CONTROL`(구동기 제어)만 처리하고 `REQ_SET_DEVICE_PROPERTY`는
`else`("미처리 메시지") 분기로 빠져 **아무 회신도 하지 않는다.** 그래서 게이트웨이가
`Timeout × (Retry+1)`만큼 기다리다 504로 실패하고 DB는 갱신되지 않는다.

단위 테스트(`backend/tests/test_api.py`)는 모든 REQ에 자동 SUCCESS를 돌려주는
**FakeLink**를 쓰므로 이 갭을 드러내지 못했다 — 실제 `virtual_node`와 동작이 다르다.

## 영향

settings 페이지의 수집 주기·전송 모드·전송 임계 설정이 **유일한 재현 실행 모드
(simulate)에서 전혀 동작하지 않는다.** 시연·심사자 재현 경로에서 이 화면이 죽어
있으며, 0937 6.4-2 · 부속서 A 1.3 요구(EMS 구동 주기 관리)의 실제 동작 증명이
빠진다.

## 재현

```
cd project_code
rm -f runtime.db
python run.py --mode simulate &   # 노드 등록 대기(~8s)
# node 0x3 센서의 install_id 를 /api/v1/nodes/3/devices 로 얻어
curl -s -X PATCH http://127.0.0.1:8000/api/v1/device-property \
  -H "Content-Type: application/json" -H "X-User-Id: demo-user-1" \
  -d '{"selector":{"install_id":"<sensor-install-id>"},"property":{"period_sec":7,"lower_value":5,"upper_value":40}}'
# → HTTP 504 "node_id=3 가 응답 시간 안에 회신하지 않았다" (약 6초 후)
# → DB의 period_sec 는 기본값 그대로, 반영 안 됨
```

## 제안

`sim/_wire.py`에 `MT_REQ_SET_DEVICE_PROPERTY`(0x0004) · `MT_RES_SET_DEVICE_PROPERTY`
(0x0404) · `decode_dp()` · `decode_req_set_device_property()` ·
`build_res_set_device_property()`를 추가하고, `virtual_node._handle`에 수신 핸들러를
두어 대상 device_id에 설정을 반영한 뒤 `RES_SET_DEVICE_PROPERTY(SUCCESS)`로 회신한다.
FakeLink가 아니라 virtual_node를 직접 대상으로 하는 회귀 테스트를 추가한다.

---

## 작업자 처리 기록

| 일시 | 상태 | 내용 |
|---|---|---|
| 2026-08-18 | 확인 | simulate 스택 기동 후 PATCH를 실제 실행해 504 타임아웃·DB 미반영을 재현. 원인은 `virtual_node._handle`의 `REQ_SET_DEVICE_PROPERTY` 핸들러 부재 |
| 2026-08-18 | 수정완료 | `sim/_wire.py`에 REQ/RES 코드·`decode_dp`·`decode_req_set_device_property`·`build_res_set_device_property` 추가. `virtual_node._handle`에 수신 핸들러 추가(대상 device_id에 transfer_mode·period·lower/upper 반영 후 RES SUCCESS 회신, 미등록 device_id는 전량 검증 후 INVALID_DEVICE_ID). SimDevice에 적용 필드 추가, `_device_property` 선언이 적용값을 반영. 회귀 테스트 `test_virtual_node.py`에 virtual_node 직접 대상 3종 추가. 실행본·제출본 동시 반영 |
