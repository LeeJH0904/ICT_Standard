# F-083 · 기능 3 규칙 생애주기가 API와 연결되지 않음

| 항목 | 값 |
|---|---|
| 심각도 | 치명 |
| 분류 | 문서불일치 |
| 대상 | `project_docs/web/화면_설계서.md` §6 · `project_docs/api/openapi.json` `/api/v1/rules` |
| 발견일 | 2026-08-07 |
| 상태 | 수정완료 |

## 근거

0937 6.3은 모델 실행 방법에 따라 모델을 구동하고 출력값을 수신할 수 있어야 한다고 요구한다. 부속서 A 3.2 절차 3은 사용자가 최종 의사결정 후 제어 조건을 조정하도록 한다.

화면 설계서 §6은 `공공데이터 → AI 초안 생성 → 사람 승인/거부 → 실행`을 기능 3의 흐름으로 선언한다. 그러나 OpenAPI의 `createRuleDraft`는 `origin`과 **클라이언트가 이미 작성한 `draft_text`**를 받아 `control_rule`에 저장할 뿐이다. 서비스 대조표에서 신설한 `mms.run_model(model_id, inputs)`을 호출하는 오퍼레이션이나 입력 데이터 계약은 없다.

## 현상

- 브라우저가 공공데이터를 선택해 AI 모델을 실행할 HTTP 경로가 없다.
- `threshold` 폴백인지 생성형 AI인지 화면에 표시하겠다고 했지만 `Rule` 응답에는 생성 경로가 없다.
- 화면과 발표 시나리오는 승인 **거부** 상태를 요구하지만 API·DB에는 거부 오퍼레이션이나 상태가 없다.

승인·실행 API는 존재하지만, 그 앞의 초안 생성과 거부 단계가 화면 계약과 연결되지 않았다.

## 영향

핵심 기능 3이 설계대로 구현될 수 없다. 클라이언트가 작성한 문장을 `AI_DRAFT`로 저장하면 실제 AI 실행 증거가 사라져 공모전의 생성형 AI 활용 주장도 무너진다.

## 제안

모델 입력과 공공데이터 참조를 받아 `mms.run_model()`을 호출하고 생성 경로를 응답하는 서버 오퍼레이션을 정의한다. 거부가 단순 취소인지 영속 상태인지 결정하고 화면·API·DB·시연 문구를 한 의미로 통일한다.

---

## Claude 처리 기록

| 일시 | 상태 | 내용 |
|---|---|---|
| 2026-08-07 | 신규 | GPT 검증 기록 |
| 2026-08-07 | 확인 | 지적대로다. `createRuleDraft` 는 클라이언트가 만든 `draft_text` 를 그대로 `origin='AI_DRAFT'` 로 저장할 뿐이어서, 저장된 행만 보면 서버가 모델을 돌렸는지 사용자가 문장을 타이핑했는지 구별되지 않는다. 거부는 화면·시연 문구에만 있고 API·DB 어디에도 없었다. |
| 2026-08-07 | 수정완료 | **① 초안 생성을 서버 실행으로 바꿨다.** `RuleDraftRequest` 를 `origin` + `model_id` + `inputs` 로 재정의하고, `if/then` 으로 `origin='AI_DRAFT'` 일 때 `draft_text` 를 **금지**했다 — 클라이언트가 문장을 보낼 수 없으면 서버가 `mms.run_model()` 을 부르는 것 외에 초안을 만들 방법이 없다. **② 생성 경로를 응답과 DB에 남겼다.** `control_rule.generation`(`AI`/`THRESHOLD_FALLBACK`/`WIZARD`/`SCRIPT`) 신설 — `origin` 은 요청자의 의도이고 `generation` 은 서버가 실행한 결과다. AI 제공자 부재로 폴백하면 둘이 갈리며, 이 구분이 없으면 "AI 를 썼다"가 증명되지 않는다. **③ 거부를 영속 상태로 결정**(사용자 확인 2026-08-07). `rejected_at`·`rejected_by`·`reject_reason` 3열 + `POST /api/v1/rules/{ruleId}/reject` + `RejectRequest` + `trg_rule_reject_immutable`. 근거는 0937 부속서 A 3.2 절차 3 의 '조정' — 반려가 포함되며, 거부 사실이 남지 않으면 초안 직후와 거부 후가 구별되지 않아 '사람 검토 지점'이 기록으로 증명되지 않는다. |
| 2026-08-07 | 수정완료 | **수정 도중 같은 부류의 2차 결함을 발견해 함께 고쳤다.** 새로 넣은 `CHECK (origin <> 'AI_DRAFT' OR generation IN ('AI','THRESHOLD_FALLBACK'))` 이 `generation` 을 생략한 INSERT 를 통과시켰다. 원인은 **SQL 3치 논리** — `NULL IN (...)` 은 FALSE 가 아니라 NULL 이고 SQLite 는 NULL 로 평가된 CHECK 를 통과로 취급한다. **F-039 와 같은 부류다.** `generation IS NOT NULL AND ...` 을 앞에 두어 닫았다. 결함 주입으로 재확인: 이 절을 되돌리면 `AI 초안인데 생성 경로 없음 차단` 이 FAIL 로 뒤집힌다. |
| 2026-08-07 | 수정완료 | **중복 제약 3건을 제거했다.** 결함 주입 중 `trg_rule_no_approve_after_reject` · `trg_rule_no_reject_after_approve` · '거부 내용' CHECK 가 각각 독립 반례를 갖지 못함이 드러났다 — 셋 다 배타 CHECK 와 미승인 제약이 이미 덮는다. 근거 없이 남기면 "제약 39개"가 실제 보장보다 부풀려진다. 트리거 39 → **37**, 배타 CHECK 는 반례가 있는 load-bearing 제약이 되었다. `schema/verify.py` **87/87**, 주입 5종 전량 검출 |
