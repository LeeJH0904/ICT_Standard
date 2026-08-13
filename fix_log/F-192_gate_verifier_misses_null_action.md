# F-192 · 승인 게이트 검증기가 action=NULL 허용 변이를 놓침

| 항목 | 값 |
|---|---|
| 심각도 | 오류 |
| 분류 | 코드버그 |
| 대상 | `tools/gate_e2e.py:79-204` |
| 발견일 | 2026-08-11 |
| 상태 | 수정완료 |

## 근거

개발 착수 지시서 §3.8은 `gate_e2e.py`가 DB 트리거를 믿지 않고 HTTP 레벨에서 승인 게이트를 공격해야 한다고 정한다.

`CLAUDE.md` §6.2 — 검증기는 정상·반례를 실제로 넣고 판정을 대조해야 하며, “필드가 있다”와 “값이 반드시 온다”를 구분해야 한다(F-091·F-095).

단계 6 추가 지시는 승인 없이 실행, 거부된 규칙, 승인 후 대상 변조와 함께 `action`이 NULL인 승인 경유를 직접 시도하도록 요구한다.

## 현상

현재 API는 `action=NULL`을 HTTP 400으로 올바르게 거부한다. 그러나 `gate_e2e.py`의 6개 시나리오에는 이 반례가 없다.

`_validate_control_action(None)`만 유효한 기본 명령으로 바꾸는 메모리 내 변이를 주입했다. 그 결과 action=NULL 승인이 HTTP 200으로 바뀌었지만 기존 `gate_e2e.py`는 여전히 16/16, 종료 코드 0으로 통과했다.

```text
CURRENT action=NULL approval: 400
MUTANT action=NULL approval: 200
MUTANT gate_e2e exit: 0
```

## 영향

F-039·F-091에서 반복된 SQL NULL/JSON null 계열 회귀가 API에 재발해도 단계 6 출구가 잡지 못한다. 승인 게이트의 가장 중요한 음성 테스트 하나가 자동 회귀에서 빠져 있다.

## 재현

```python
from backend import api
from tools import gate_e2e

original = api._validate_control_action
def mutant(action):
    if action is None:
        return {"value": 0, "value_type": "UINT"}
    return original(action)

api._validate_control_action = mutant
assert gate_e2e.main() == 0       # 실측 16/16 통과
# 같은 앱에서 action=None 승인 요청은 실측 HTTP 200
```

---

## Claude 처리 기록

| 일시 | 상태 | 내용 |
|---|---|---|
| 2026-08-11 | 확인 | 재현 성공 — 재현 스니펫 그대로 `api._validate_control_action`을 mutant로 바꿔치기하면 `action=NULL` 승인이 HTTP 200으로 통과하는데도 기존 `gate_e2e.py`(시나리오 1~6)는 16/16로 통과했다. 실제 API 자체는 이미 400을 정확히 돌려준다(`_validate_control_action`이 `isinstance(action, dict)`를 먼저 검사) — 회귀를 못 잡는 것은 검증기의 공백이지 API의 결함이 아니다. |
| 2026-08-11 | 수정완료 | `tools/gate_e2e.py`에 시나리오 7 신설(`scenario_null_action_approval_rejected`) — `action=None`으로 승인 시도 시 (1) 400 (2) 그 규칙이 승인 상태로 바뀌지 않음(`approved_at is None`) (3) 그래서 execute도 여전히 409, 3가지를 확인한다. **결함 주입 검증**: F-192 재현 스니펫의 mutant를 그대로 실행 → 신설 시나리오 3건이 정확히 실패(16/19, exit 1)하고 기존 시나리오 1~6은 영향 없이 통과함을 확인 후 원상복구. 검증: `python tools/gate_e2e.py` 16→**19/19** · `pytest siap/tests/ backend/tests/` **333/333** · `python fix_log/meta_verify.py` **102/102** |

