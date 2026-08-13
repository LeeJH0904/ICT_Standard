# F-017 · 승인 게이트 우회 가능성과 문서의 절대 주장

| 항목 | 값 |
|---|---|
| 심각도 | 위험 |
| 분류 | 문서불일치 |
| 대상 | `project_docs/db/DB_스키마_설계서.md:141-149`, `project_docs/db/schema.sql:347-381` |
| 발견일 | 2026-08-03 |
| 상태 | 수정완료 |

## 근거

0937 부속서 A 3.2 절차 3 — "사용자는 최종 의사결정 후 제어 조건 조정을 한다."

`DB_스키마_설계서.md` §4.3 — "코드 버그로도 우회되지 않는다."

## 현상

`control_rule`의 CHECK는 미승인 행에 `action_json`을 저장하지 못하게 할 뿐이다. `control_execution`은 `rule_id`가 NULL이어도 되고, 미승인 `control_rule`을 참조해도 되며, 독립적인 `command_json`에 임의 명령을 저장할 수 있다. DDL에는 참조 규칙의 `approved_at`을 확인하는 트리거나 승인된 `action_json`과 실행 명령의 일치를 보장하는 제약이 없다.

## 영향

현재 DDL만으로는 "AI 출력이 직접 구동기로 전달되지 않는다"는 경로 전체를 보장할 수 없다. 향후 서비스 코드가 `control_execution` 또는 프레임 빌더를 직접 호출하면 문서가 주장하는 DB 수준의 절대 보장이 무너진다.

## 재현

```sql
INSERT INTO control_rule(id, created_at, origin, draft_text)
VALUES ('r', 't', 'AI_DRAFT', '미승인 초안');

INSERT INTO control_execution(id, rule_id, install_id, issued_at, command_json)
VALUES ('x', 'r', '<유효 install_id>', 't', '{"cmd":"open"}');
-- 성공
```

## 제안

DDL이 보장하는 범위를 정확히 낮춰 서술하고, 실제 제어 송신 경로에서 승인 검증을 강제하는 별도 계약과 회귀 테스트를 설계한다.

---

## Claude 처리 기록

| 일시 | 상태 | 내용 |
|---|---|---|
| 2026-08-03 | 확인 | 미승인 규칙을 참조하는 `control_execution` 삽입, `rule_id=NULL` 삽입 모두 성공함을 재현. 설계서 §4.3의 "코드 버그로도 우회되지 않는다"는 `control_rule` 범위에만 해당하는데 전체 경로를 보장하는 것처럼 서술되어 있었음 |
| 2026-08-03 | 수정완료 | **DDL 강화** — `control_execution`에 `origin`(RULE/MANUAL)과 `issued_by` 추가. CHECK로 권한 출처를 강제하고, `trg_exec_requires_approval` 트리거가 참조 규칙의 `approved_at`을 확인한다. `trg_exec_rule_immutable`(권한 필드 사후 변경 금지), `trg_rule_approval_irrevocable`(승인 철회 금지) 추가 |
| 2026-08-03 | 수정완료 | **문서 정정** — 설계서 §4.3을 3단 구조로 재작성하고, DDL이 보장하는 범위와 보장하지 못하는 범위(DB를 거치지 않는 직접 송신)를 구분해 명시. 서비스 계층에서 `control_execution` 기록을 선행 조건으로 강제한다는 요구를 추가 |
| 2026-08-03 | — | 부수 효과로 `MANUAL` 경로가 생겨 0937 부속서 A 1·2(수동·원격제어)까지 모델이 포괄하게 됨. 회귀 테스트 5종 추가 |
