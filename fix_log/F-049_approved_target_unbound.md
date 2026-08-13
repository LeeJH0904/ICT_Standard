# F-049 · 승인 명령과 실제 실행 대상 장치가 결속되지 않음

| 항목 | 값 |
|---|---|
| 심각도 | 치명 |
| 분류 | 코드버그 |
| 대상 | `project_docs/db/schema.sql:399-418,616-643` |
| 발견일 | 2026-08-03 |
| 상태 | 수정완료 |

## 근거

0937 §6.5 — "사용자가 지정한 명령을 구동기가 실행하도록 제어 명령을 전달"

0937 부속서 A §3.2 절차 3·5 — 사용자가 최종 의사결정 후 제어 조건을 조정하고, 이후 클라우드 서비스가 구동기노드에 구동 명령을 전달한다.

## 현상

F-030 수정은 `command_json == action_json`만 비교한다. 실행 대상인 `control_execution.install_id`는 `control_rule`의 승인 스냅샷과 연결되지 않는다. 승인 JSON이 장치 A를 명시해도 같은 JSON을 유지한 채 실행 레코드의 `install_id`를 B로 넣을 수 있다. 또한 `trg_exec_rule_immutable`의 UPDATE 차단 목록에 `install_id`가 없어 삽입 후 대상 변경도 가능하다.

## 영향

사람이 승인한 값은 유지하면서 전혀 다른 구동기를 작동시킬 수 있다. 사람 승인 게이트가 제어의 핵심 요소인 “어느 장치를” 보장하지 못하므로 핵심 안전 주장이 내용 수준에서 다시 우회된다.

## 재현

```sql
-- 승인 action_json = {"install_id":"A","value":0}
INSERT INTO control_execution(
  id, origin, rule_id, install_id, issued_at, command_json
) VALUES (
  'x', 'RULE', 'r', 'B', 't', '{"install_id":"A","value":0}'
);
-- 현재 성공

UPDATE control_execution SET install_id='A' WHERE id='x';
-- 사후 대상 변경도 성공
```

## 제안

승인 스냅샷에 정규화된 대상 식별자를 별도 컬럼으로 포함하고 RULE 실행의 `install_id`가 그 값과 같음을 DB에서 강제한다. 실행 레코드의 `install_id`도 권한 불변 필드에 포함한다.

---

## Claude 처리 기록

| 일시 | 상태 | 내용 |
|---|---|---|
| 2026-08-03 | 확인 | 재현 성공. 승인 `action_json` 이 장치 A 를 명시해도 `install_id='B'` 인 실행 레코드가 통과했고, 삽입 후 `install_id` 변경도 통과했다. `command_json` 동등 비교만으로는 '어느 장치를' 이 전혀 강제되지 않는다 |
| 2026-08-03 | 수정완료 | `control_rule.target_install_id` 컬럼 신설(FK → `device_install_info`). **JSON 문자열이 아니라 정규화된 컬럼이어야** DB 가 파싱 없이 대조할 수 있다. 승인 CHECK 에 포함해 승인 상태면 NOT NULL, 미승인이면 NULL 을 강제한다 |
| 2026-08-03 | 수정완료 | `trg_exec_target_matches_approved` 신설 — RULE 실행의 `install_id` 가 승인 대상과 다르면 차단(NULL 안전 `IS NOT`). `trg_rule_target_immutable_after_approval` 로 승인 후 대상 변조도 봉인 |
| 2026-08-03 | 수정완료 | `trg_exec_rule_immutable` 의 UPDATE 감시 목록에 `install_id` 추가. 삽입 후 대상 바꿔치기가 막힌다 |
| 2026-08-03 | 수정완료 | 회귀 테스트 7종 추가 — 대상 불일치 차단 / 일치 허용 / 실행 후 바꿔치기 차단 / 승인 후 대상 변조 차단 / 대상 없는 승인 UPDATE 차단 / 미승인 규칙의 대상 확정 차단 / **MANUAL 실행은 대상 제약 없음**(권한 출처가 사용자 지시이므로 규칙 대상에 묶이지 않는다). DB 제약 테스트 67 → 76종 |
| 2026-08-03 | 수정완료 | **부수 정정** — `verify.py` 의 위치 지정 `INSERT INTO control_rule VALUES(...)` 4건을 컬럼 명시로 바꿨다. F-024 때와 같은 이유로, 컬럼이 늘면 조용히 깨진다 |
