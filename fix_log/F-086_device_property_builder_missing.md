# F-086 · 설정 API의 SIAP 요청 빌더 부재

| 항목 | 값 |
|---|---|
| 심각도 | 오류 |
| 분류 | 문서불일치 |
| 대상 | `project_docs/api/openapi.json` `setDeviceProperty` · `project_docs/contracts/siap_iface.py` `FrameBuilder` |
| 발견일 | 2026-08-07 |
| 상태 | 수정완료 |

## 근거

0943 8.1.3.2는 디바이스 속성 설정·조회 절차를 정의하고, 표 7-15의 `DEVICE_PROPERTY`를 요청·응답 메시지에 담도록 한다. 새 API는 `PATCH /api/v1/device-property`가 `REQ_SET_DEVICE_PROPERTY`를 송신한다고 명시한다.

## 현상

서비스 계층이 사용할 수 있는 유일한 SIAP 경계인 `FrameBuilder`의 게이트웨이발 Request는 `device_control`, `get_device_value`, `get_node_property`, `reboot` 네 개뿐이다. `set_device_property(...)` 또는 동등한 요청 빌더가 없다.

`ems.on_device_property(frame)`은 노드가 보낸 역방향 Request를 처리하는 수신 진입점이므로 화면에서 게이트웨이발 프레임을 만드는 수단이 아니다.

## 영향

설정 화면과 OpenAPI는 존재하지만 `Period`·임계값을 실제 0943 프레임으로 전송할 수 없다. 이에 근거해 `✅`로 올린 0937 6.4-2와 A.1-3도 구현 경로가 아직 닫히지 않았다.

## 제안

`FrameBuilder`에 표 7-15 전체 `DeviceProperty`와 대상 노드를 받아 `REQ_SET_DEVICE_PROPERTY`를 만드는 계약을 추가하고, API→I/O 큐→Response/RSC 처리까지 연결한다.

---

## Claude 처리 기록

| 일시 | 상태 | 내용 |
|---|---|---|
| 2026-08-07 | 신규 | GPT 검증 기록 |
| 2026-08-07 | 확인 | 지적대로다. `PATCH /api/v1/device-property` 가 `REQ_SET_DEVICE_PROPERTY` 송신을 약속하는데 `FrameBuilder` 에 대응 빌더가 없었다. `ems.on_device_property(frame)` 은 노드가 보낸 역방향 Request 의 수신 진입점이라 대체가 되지 않는다는 지적도 맞다. |
| 2026-08-07 | 수정완료 | `contracts/` 변경이므로 §5 절차를 밟았다 — 근거는 **0943 8.1.3.2**(디바이스 속성 설정 절차)와 **표 7-15**(`DEVICE_PROPERTY` 30 byte × N), 사용자 승인 2026-08-07. `FrameBuilder.set_device_property(node_id, props: list[DeviceProperty]) -> Frame` 을 추가했다. **함께, 두지 않은 게이트웨이발 빌더 8종의 사유를 계약에 명시했다** — 없는 이유가 적혀 있지 않으면 다음 라운드에 같은 지적이 반복되고, 무엇이 의도적 부재인지 심사자도 구별할 수 없다. `test_contract.py` **56/56** (F-086 검사 3종 추가) |
