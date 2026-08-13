# F-225 · 승인 게이트 검증기가 거부 전 구동기 송신을 놓침

| 항목 | 값 |
|---|---|
| 심각도 | 오류 |
| 분류 | 코드버그 |
| 대상 | `tools/gate_e2e.py:79-109,211-238` |
| 발견일 | 2026-08-13 |
| 상태 | 신규 |

## 근거

`CLAUDE.md` §1-7 — “미승인 AI 규칙이 구동기로 전달되는 경로 생성”은 금지다.

개발 착수 지시서 §3 단계 6 — `gate_e2e.py`는 “미승인 규칙으로 구동기가 움직이지 않는다”를 HTTP 수준에서 검증해야 한다.

## 현상

검증기는 미승인·거부 규칙의 HTTP 상태, 오류 본문, `control_execution` 행만 검사하고 `FakeSiapLink`의 `tx` 증가 여부는 검사하지 않는다. `fcs.execute()`가 실제 `REQ_SET_DEVICE_CONTROL` 프레임을 먼저 `link.send()`한 뒤 원래 게이트 오류를 내도록 메모리에서 감싼 결과, 금지된 송신이 3회 발생했는데도 기존 19개 판정은 전부 통과하고 종료 코드 0을 반환했다.

현재 제품 코드의 게이트 순서 자체는 올바르다. 결함은 그 순서가 회귀해도 출구가 잡지 못한다는 데 있다.

## 영향

HTTP가 409를 반환하고 DB 행이 없다는 사실만으로 구동기가 움직이지 않았다고 증명할 수 없다. 게이트 검사가 통과한 배포에서도 거부 전에 이미 제어 프레임이 나갈 수 있다.

## 재현

```python
from tools import gate_e2e
from backend import repository
from backend.services import fcs
from contracts.frame import DevType, ValueType

original = fcs.execute
sent = 0

def mutant(conn, link, builder, rule_id, *, timeout=None):
    global sent
    rule = repository.get_control_rule(conn, rule_id)
    if rule is not None and not rule.is_approved:
        builder.device_kinds[(0, 0)] = (DevType.ACTUATOR, 0x81)
        frame = builder.device_control(0, [(0, 1, ValueType.UINT)])
        link.send(frame, timeout=timeout)  # 게이트 판정 전 실제 TX
        sent += 1
    return original(conn, link, builder, rule_id, timeout=timeout)

fcs.execute = mutant
print(gate_e2e.main(), sent)
# 19/19 통과, 종료 코드 0, sent == 3
```

## 제안

거부 시나리오마다 요청 전후 `link.stats()[tx]`를 대조해 제어 송신이 0건임을 독립 판정한다.

---

## Claude 처리 기록

| 일시 | 상태 | 내용 |
|---|---|---|
