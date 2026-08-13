# F-217 · 가상 노드가 무효 디바이스 제어를 적용하고 SUCCESS 회신

| 항목 | 값 |
|---|---|
| 심각도 | 오류 |
| 분류 | 코드버그 |
| 대상 | `project_code/sim/virtual_node.py:398` · `project_code/sim/virtual_node.py:423` |
| 발견일 | 2026-08-12 |
| 상태 | 신규 |

## 근거

0943 §8.1.5 — “디바이스 (액추에이터)를 사용자가 제어하고자 할 경우” `REQ_SET_DEVICE_CONTROL`을 전송한다. 0943 §7.3.1은 요청 처리가 정상이 아닐 때 표 7-10의 오류 코드를 담도록 하며, 표 7-10은 `INVALID_DEVICE_ID=0x04`, `INVALID_DEVICE_TYPE=0x05`를 정의한다.

## 현상

`VirtualNodeServer._handle()`은 `REQ_SET_DEVICE_CONTROL`의 각 요소를 `device_id`만으로 찾아 값을 바꾼다. 대상이 센서인지, 요청 Type/Subtype/Value Type이 등록 속성과 같은지 확인하지 않는다. 대상 ID가 존재하지 않아도 마지막에 무조건 기본값 `RSC_SUCCESS`인 `RES_SET_DEVICE_CONTROL`을 보낸다.

실제 wire 재현에서 노드 3의 온도 **센서** 값을 제어하자 값이 `1103783526`에서 `1106247680`으로 바뀌고 RSC 0x00이 왔다. 존재하지 않는 `device_id=99`도 RSC 0x00이었다.

## 영향

simulate 대역이 실제 펌웨어 상태 머신과 갈린다. 하드웨어 없는 기본 경로에서 잘못된 제어 요청이 성공으로 보이므로, 표준 표 7-10 오류 처리와 실제 노드 상호운용성을 거짓으로 재현한다.

## 재현

```text
1. VirtualNodeServer의 기본 node_id=3, device_id=1(온도 센서)을 선택한다.
2. REQ_SET_DEVICE_CONTROL DMI(device_id=1, Type=SENSOR, Subtype=온도)를 _handle()에 전달한다.
3. 센서 값이 실제로 변경되고 RES_SET_DEVICE_CONTROL의 RSC가 0x00임을 확인한다.
4. device_id=99, Type=ACTUATOR 요청도 같은 방식으로 전달한다.

실측:
SENSOR_CONTROL before=1103783526 after=1106247680 rsc=0x0
UNKNOWN_DEVICE response_rsc=0x0
```

---

## Claude 처리 기록

| 일시 | 상태 | 내용 |
|---|---|---|
| | | |
