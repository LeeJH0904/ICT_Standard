# F-153 · DB 스키마 설계서 §8 예시 DDL이 정본 schema.sql보다 낡았다

| 항목 | 값 |
|---|---|
| 심각도 | 위험 |
| 분류 | 문서불일치 |
| 대상 | `project_docs/db/DB_스키마_설계서.md` §8 vs `project_docs/db/schema.sql` |
| 발견일 | 2026-08-10 |
| 상태 | 수정완료 |

## 근거

`CLAUDE.md` §4.3 — *"ORM을 쓰지 않는다. `schema.sql`이 정본이며 트리거·CHECK가 여기 있다."*
`DB_스키마_설계서.md` §6.1 자신도 *"테이블 31개, 트리거 37개, 인덱스 8개"* 를 주장한다.

## 현상

단계 5 착수를 위해 `DB_스키마_설계서.md`를 전문 읽고 `project_docs/db/schema.sql`을 대조하자,
설계서 §8에 박제된 DDL 스니펫이 실제 `schema.sql`보다 오래된 스냅샷임을 확인했다 — F-083·F-085·
F-091·F-092가 `schema.sql`에는 반영되어 있는데 §8 스니펫에는 없다.

- `control_rule`: 설계서 §8은 `generation`·`rejected_at`·`rejected_by`·`reject_reason` 4개 컬럼과
  이를 사용하는 CHECK 6종, 트리거 `trg_rule_reject_immutable` 이 통째로 빠져 있다 (F-083·F-091).
- `alert`: 설계서 §8은 `frame_id` 컬럼과 그 FK·CHECK(`siap_nec IS NULL OR frame_id IS NOT NULL`)가
  빠져 있다 (F-085·F-092). `kind` CHECK 목록도 `CONTROL_TIMEOUT`이 없다.

`project_docs/db/verify.py`(98/98 통과)는 이미 `schema.sql`(정본)을 읽어 실행하므로 검증 자체는
낡은 스니펫의 영향을 받지 않았다 — 코드는 옳고 문서 본문 안의 예시 코드 블록만 갈렸다.

## 영향

심사자가 §8 DDL만 읽고 `control_rule`/`alert`의 실제 제약(거부 게이트·NEC-프레임 결속)을
확인하면 F-083·F-085·F-091·F-092가 반영되지 않은 것으로 오인한다. 단계 5에서 `project_code/
backend/schema.sql`을 이관할 때 §8을 원본으로 삼으면 이 결함들이 구현에 재발한다.

## 재현

```
diff <(sed -n '341,1037p' "project_docs/db/DB_스키마_설계서.md" | sed '1d;$d')  project_docs/db/schema.sql
# control_rule / alert 블록에서 컬럼·CHECK·트리거 차이 확인
```

## 제안

§8 코드 블록을 `project_docs/db/schema.sql` 전문으로 교체(복사)한다. 정본은 계속 `schema.sql`이며,
설계서는 그 사본을 보여주는 역할이다.

---

## Claude 처리 기록

| 일시 | 상태 | 내용 |
|---|---|---|
| 2026-08-10 | 확인 | 단계 5 착수 전 읽기(`CLAUDE.md` §8 세션 시작 절차)에서 자체 발견. `schema.sql`이 정본이라는 `CLAUDE.md` §4.3 규정에 따라 스니펫 쪽이 틀렸다고 판정 |
| 2026-08-10 | 수정완료 | `DB_스키마_설계서.md` §8 코드 블록을 `project_docs/db/schema.sql` 전문으로 교체. `project_code/backend/schema.sql`은 (이관 시) `schema.sql`을 원본으로 삼아 이 결함과 무관 |
