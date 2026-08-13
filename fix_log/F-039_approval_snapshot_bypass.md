# F-039 · 승인 스냅샷의 NULL·조건 변조 우회

| 항목 | 값 |
|---|---|
| 심각도 | 치명 |
| 분류 | 코드버그 |
| 대상 | `project_docs/db/schema.sql:360-408,599-629`, `project_docs/db/verify.py:237-254` |
| 발견일 | 2026-08-03 |
| 상태 | 수정완료 |

## 근거

0937 부속서 A 3.2 절차 3 — "사용자는 최종 의사결정 후 제어 조건 조정을 한다."

진행보고서 §2 — "애플리케이션 코드 버그로도 우회되지 않는다."

## 현상

`control_rule`은 승인 상태에서도 `action_json=NULL`을 허용한다. `trg_exec_command_matches_approved`의 비교식은 `NEW.command_json <> NULL`일 때 SQL NULL이 되어 트리거 조건이 참이 아니므로 임의 명령이 통과한다. 또한 승인 후 `action_json`만 불변이고 `condition_expr`은 자유롭게 변경할 수 있어 사용자가 승인한 자동제어 조건을 사후 변조할 수 있다.

## 영향

승인된 NULL 규칙에 임의 AI 명령을 붙이거나, 승인 조건을 더 넓게 바꿔 제어를 실행할 수 있다. 사람 승인 게이트가 내용 수준에서 다시 우회되므로 프로젝트 핵심 주장에 직접 반한다.

## 재현

```sql
INSERT INTO control_rule(..., condition_expr, action_json, approved_at, approved_by)
VALUES (..., 'temp>40', NULL, 't', 'u');

INSERT INTO control_execution(..., rule_id, command_json)
VALUES (..., 'r', '{"value":1}');       -- 현재 성공

UPDATE control_rule SET condition_expr='temp>0' WHERE id='r'; -- 현재 성공
```

## 제안

승인 상태에서는 실행 가능한 action과 condition을 모두 필수로 만들고, 승인 후 두 필드를 하나의 불변 스냅샷으로 보호한다. NULL 비교는 `IS NOT` 또는 명시적 NULL 분기로 다룬다.

---

## Claude 처리 기록

| 일시 | 상태 | 내용 |
|---|---|---|
| 2026-08-03 | 확인 | 재현 성공. `act=NULL` 승인 규칙에 `cmd='{"value":1}'` 실행이 통과했다. 원인은 SQL 3값 논리 — `NEW.command_json <> NULL` 이 NULL 이라 트리거 WHEN 이 참이 되지 않는다. `condition_expr` 사후 변경도 무제약이었다 |
| 2026-08-03 | 수정완료 | ① `control_rule` 에 CHECK 추가 — 승인 상태면 `action_json`·`condition_expr` 둘 다 NOT NULL. ② `trg_exec_command_matches_approved` 의 비교를 NULL 안전한 `IS NOT` 으로 교체. ③ `trg_rule_condition_immutable_after_approval` 신설 — 승인 후 조건식도 봉인. 승인은 (조건·명령·승인자)를 한 번에 채우는 단일 UPDATE 로만 가능해졌다 |
| 2026-08-03 | 수정완료 | 회귀 테스트 6종 추가: NULL 명령/NULL 조건식 차단, 명령 없는 승인 UPDATE 차단, 원자적 승인 후 실행 허용, 승인 후 조건식 변조 차단, NULL 승인 경유 임의 명령 차단. `verify.py` 61 → 67종 전부 통과. 별도로 수정 전/후 최소 스키마를 각각 만들어 `<>` 는 우회되고 `IS NOT` 은 차단됨을 독립 확인 |
