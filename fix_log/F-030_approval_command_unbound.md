# F-030 · 승인 내용과 실제 제어 명령이 결합되지 않음

| 항목 | 값 |
|---|---|
| 심각도 | 오류 |
| 분류 | 문서불일치 |
| 대상 | `project_docs/db/schema.sql:363-408,597-613`, `project_docs/arch/아키텍처_설계서.md` §3.2·§7.3 |
| 발견일 | 2026-08-03 |
| 상태 | 수정완료 |

## 근거

0937 부속서 A 3.2 절차 3 — "사용자는 최종 의사결정 후 제어 조건 조정을 한다"

아키텍처 §7.3 — 사용자 검토·수정·승인 뒤 `control_execution`을 기록하고 그 명령을 송신한다.

## 현상

트리거는 `rule_id`의 `approved_at` 존재만 확인한다. `control_execution.command_json`이 승인된 `control_rule.action_json`과 같은지, 또는 그 승인본에서 파생됐는지는 확인하지 않는다. 승인 후 `action_json` 변경도 금지하지 않는다. 승인된 규칙 A를 참조하면서 전혀 다른 명령 B를 실행 테이블에 넣을 수 있다.

## 영향

사람이 승인한 것은 규칙의 존재일 뿐 실제 송신 명령이 아니다. 서비스 코드 오류가 있으면 승인하지 않은 AI 출력이나 다른 명령을 승인된 규칙에 붙여 송신할 수 있어 핵심 주장인 사람 승인 게이트가 내용 수준에서 성립하지 않는다.

## 재현

```sql
-- 승인된 action_json = {"value":0}
INSERT INTO control_execution(..., rule_id, command_json)
VALUES (..., 'approved_rule', '{"value":1}');
-- 현재 성공
```

## 제안

승인 시 불변 스냅샷/해시를 만들고 실행 레코드가 그 승인본을 참조하도록 하거나, RULE 실행 명령을 DB에 중복 입력하지 않고 승인된 action에서만 도출하도록 계약한다.

---

## Claude 처리 기록

| 일시 | 상태 | 내용 |
|---|---|---|
| 2026-08-03 | 확인 | 승인 `action_json={"value":0}` 인 규칙을 참조하면서 `command_json={"value":1}` 삽입 성공, 승인 후 `action_json` 변경 성공 — 둘 다 재현 |
| 2026-08-03 | 수정완료 | 트리거 2개 추가 — `trg_exec_command_matches_approved`(실행 명령이 승인된 `action_json`과 일치해야 함), `trg_rule_action_immutable_after_approval`(승인 후 명령 변조 금지). 회귀 테스트 3종 추가 |
| 2026-08-03 | — | 지적대로 **사람이 승인한 것은 규칙의 존재가 아니라 그 명령**이다. F-017 수정이 존재 수준에 머물렀던 것을 내용 수준으로 끌어올렸다 || | | |
