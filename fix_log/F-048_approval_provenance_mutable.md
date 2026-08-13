# F-048 · 승인 후 승인자와 승인시각을 변조할 수 있음

| 항목 | 값 |
|---|---|
| 심각도 | 오류 |
| 분류 | 코드버그 |
| 대상 | `project_docs/db/schema.sql:627-649` |
| 발견일 | 2026-08-03 |
| 상태 | 수정완료 |

## 근거

0937 부속서 A §3.2 절차 3 — "사용자는 최종 의사결정 후 제어 조건 조정을 한다."

DB 설계서 §4.3은 승인을 `(condition_expr, action_json, approved_at, approved_by)`의 단일 스냅샷으로 설명한다.

## 현상

승인 후 `action_json`과 `condition_expr` 변경 및 `approved_at=NULL` 철회만 차단한다. `approved_by`는 다른 사용자로 자유롭게 변경할 수 있고, `approved_at`도 NULL이 아닌 다른 시각으로 바꿀 수 있다. CHECK는 두 값이 함께 NULL인지 여부만 검사하므로 이 변조를 허용한다.

## 영향

실제 최종 의사결정을 내린 사용자와 승인 시각을 사후 위조할 수 있다. 승인 감사 기록과 “사람이 최종 결정했다”는 증거가 신뢰성을 잃는다.

## 재현

```sql
-- alice가 승인한 규칙
UPDATE control_rule
SET approved_by='bob', approved_at='1999-01-01T00:00:00'
WHERE id='r';
-- 현재 성공
```

## 제안

승인 상태가 된 뒤에는 `approved_by`와 `approved_at` 모두 기존 값과 달라지는 UPDATE를 차단하고 회귀 테스트를 추가한다.

---

## Claude 처리 기록

| 일시 | 상태 | 내용 |
|---|---|---|
| 2026-08-03 | 확인 | 재현 성공. 승인된 규칙에서 `approved_by` 를 다른 사용자로, `approved_at` 을 1999년으로 바꾸는 UPDATE 가 모두 통과했다. 기존 `trg_rule_approval_irrevocable` 은 `approved_at` 이 **NULL 로 바뀌는 경우만** 막는다 |
| 2026-08-03 | 수정완료 | `trg_rule_approver_immutable`, `trg_rule_approved_at_immutable` 신설. 승인 상태에서 두 값이 기존과 달라지는 UPDATE 를 차단한다. NULL 안전 비교 `IS NOT` 사용 |
| 2026-08-03 | 수정완료 | 회귀 테스트 2종 추가(승인자 사후 변조 차단 / 승인시각 사후 변조 차단). 수정 전 재현 스크립트를 다시 돌려 두 경로 모두 차단됨을 확인 |
| 2026-08-03 | 수정완료 | DB 설계서 §4.3 에 봉인 트리거 7종을 표로 정리하고, **승인자·승인시각이 곧 감사 기록**이라는 근거를 명시했다 |
