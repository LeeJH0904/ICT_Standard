# F-202 · F-091 수정 후에도 OpenAPI 거부 제약 수치가 이전 값

| 항목 | 값 |
|---|---|
| 심각도 | 오류 |
| 분류 | 문서불일치 |
| 대상 | `project_docs/api/openapi.json:915` · `project_code/backend/schema.sql:486-495,823-825` |
| 발견일 | 2026-08-12 |
| 상태 | 수정완료 |

## 근거

TTAK.KO-10.0937 부속서 A 3.2 절차 3 — "사용자는 최종 의사결정 후 제어 조건 조정을 한다."

`schema.sql` 실측은 거부자 동시성·사유 동시성·사유 공백 금지·승인과 배타의 CHECK 4종과 `trg_rule_reject_immutable` 트리거 1종이다. 화면 설계서 §6.2도 같은 4·1을 정본으로 명시한다.

## 현상

`openapi.json`의 `rejectRule` 설명은 여전히 "CHECK 3종과 트리거 3종"이라고 적는다. F-091은 이 드리프트를 수정완료로 기록했지만 OpenAPI 설명은 고쳐지지 않았다. `meta_verify.py`도 Markdown 수치만 대조해 이 JSON 설명을 놓치고 109/109로 통과한다.

## 영향

심사자가 실행 계약의 설명을 따르면 실제 승인·거부 봉인 구조와 다른 증거 수를 보게 된다. 수정완료 상태가 실제 산출물 전부의 수정을 보장하지 못하며 메타 검증도 이를 탐지하지 못한다.

## 재현

```powershell
rg -n "CHECK 3종과 트리거 3종" project_docs/api/openapi.json
rg -n "trg_rule_reject_immutable|rejected_at|rejected_by|reject_reason" project_code/backend/schema.sql
python fix_log/meta_verify.py
```

OpenAPI는 3·3을 주장하지만 DDL은 CHECK 4종·트리거 1종이고 메타 검증은 109/109로 통과한다.

---

## Claude 처리 기록

| 일시 | 상태 | 내용 |
|---|---|---|
| 2026-08-12 | 신규→확인 | 재현 확인 — `project_docs/api/openapi.json:915`의 `rejectRule` `description`이 여전히 "CHECK 3종과 트리거 3종"을 주장함을 `rg`로 확인. `project_code/backend/schema.sql`의 `control_rule` DDL을 직접 읽어 거부 워크플로 관련 CHECK가 4개(거부자 동시성 486줄·사유 동시성 490줄·사유 공백 금지 491줄·승인과 배타 495줄, GLOB 형식 검사 3건은 F-184가 넣은 무관한 시간 형식 검사라 제외)이고 트리거는 `trg_rule_reject_immutable` 1개뿐임을 확인 — `project_docs/web/화면_설계서.md:351-352`가 이미 같은 "CHECK 4종(...)과 트리거 1종(...)" 문구로 F-091 때 정정돼 있어, openapi.json 만 그 라운드에서 누락됐음을 확인(판정: 설계서·DDL이 옳고 openapi.json이 틀렸다) |
| 2026-08-12 | 확인→수정완료 | `openapi.json`의 `rejectRule.description`을 화면 설계서 §와 동일한 문구("CHECK 4종(거부자 동시성 · 사유 동시성 · 사유 공백 금지 · 승인과 배타)과 트리거 1종(trg_rule_reject_immutable)")로 교체. 근본 원인(F-091 회귀 검사가 Markdown만 대조하고 JSON 설명 필드는 애초에 스캔 대상이 아니었음)을 닫기 위해 `fix_log/meta_verify.py`에 openapi.json의 `rejectRule.description`을 직접 읽어 같은 CHECK/트리거 수치를 DDL 실측(`_rej_chk`·`_rej_trig`, 기존 F-091 코드가 이미 계산해 둔 값 재사용)과 대조하는 검사를 신설(109→**110**항목) — 이후 이 JSON 문자열이 다시 낡아도 다음 실행에서 잡힌다. **결함 주입 검증**: `rejectRule.description`을 원래 신고문 그대로("CHECK 3종과 트리거 3종")로 되돌린 사본에서 실행 → 신설 검사가 `FAIL ... openapi.json=(CHECK 3, 트리거 3)`으로 즉시 검출, 원복 후 110/110 재통과 확인. JSON 구문 유효성도 `json.load()`로 별도 확인. 검증: `python fix_log/meta_verify.py` **110/110** · `python project_docs/api/api_verify.py` **71/71**(오퍼레이션·경로·매트릭스 수 불변, 설명 문구만 바뀜) |