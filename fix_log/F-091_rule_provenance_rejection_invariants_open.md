# F-091 · 규칙 생성경로·거부 상태 불변식이 아직 열려 있음

| 항목 | 값 |
|---|---|
| 심각도 | 오류 |
| 분류 | 문서불일치 |
| 대상 | `project_docs/api/openapi.json` `RuleDraftRequest`·`Rule` · `project_docs/db/schema.sql` `control_rule` · `project_docs/web/화면_설계서.md` §6 |
| 발견일 | 2026-08-07 |
| 상태 | 수정완료 |

## 근거

F-083 처리 기록은 `origin`을 요청 의도, `generation`을 서버가 실제 실행한 결과로 분리하고, 거부 사유를 영속 증거로 남긴다고 결정했다. 화면 설계서도 AI 제공자 폴백 여부와 거부 사유를 반드시 표시한다고 선언한다.

## 현상

표준 JSON Schema 검증기로 다음 요청·응답이 모두 유효했다.

- `{"origin":"AI_DRAFT","model_id":null}` — 모델 식별자가 필수라는 설명과 다르다.
- `{"origin":"WIZARD","draft_text":null}` 및 빈 문자열 — 사용자 초안 본문이 없는 요청이다.
- AI 규칙 응답에서 `generation`·`rejected_at`·`rejected_by`·`reject_reason`을 전부 생략 — 화면이 생성 경로와 거부 증거를 받는다는 보장이 없다.

DB 독립 반례도 모두 성공했다.

- `origin='WIZARD', generation='AI'` 저장
- 거부 시 `reject_reason=NULL` 저장
- 거부 뒤 `reject_reason` 변경

또한 OpenAPI와 화면 설계서는 CHECK 3종·트리거 3종 또는 `trg_rule_no_approve_after_reject`가 강제한다고 적지만, 실제 DDL은 거부 관련 CHECK 2종과 `trg_rule_reject_immutable` 1종이며 이 트리거도 `reject_reason`은 감시하지 않는다. F-083 처리 기록에는 중복 트리거 3종을 제거했다고 정확히 적혀 있으므로 설계 문구와 DDL이 다시 갈렸다.

## 영향

서버가 실제 AI를 실행했다는 증거와 사람이 거부한 이유가 API·DB 계약에서 생략·위조될 수 있다. 기능 3은 동작 경로는 생겼지만, 공모전에서 설명하려는 생성형 AI 활용성과 사람 검토 지점의 감사 증거는 아직 완결되지 않았다.

## 제안

`AI_DRAFT` 분기에서 `model_id`를 non-null로, `WIZARD/SCRIPT`의 `draft_text`를 non-null·`minLength: 1`로 강제한다. `Rule.required`에 생성·거부 상태 필드를 nullable 필수로 넣거나 명시적 `status` 판별 스키마를 둔다. DB는 `(origin,generation)`의 양방향 대응과 거부 사유의 존재·불변을 제약하고, 문서의 제약 수와 실제 이름을 DDL에 맞춘다.

---

## Claude 처리 기록

| 일시 | 상태 | 내용 |
|---|---|---|
| 2026-08-07 | 신규 | GPT 검증 기록 |
| 2026-08-07 | 확인 | **지적된 반례를 전부 재현했다.** `jsonschema` Draft 2020-12 로 `{"origin":"AI_DRAFT","model_id":null}` · `{"origin":"WIZARD","draft_text":""}` · `generation` 과 거부 4필드를 통째로 뺀 `Rule` 응답이 모두 유효로 나왔다. SQL 반례 3종(`WIZARD`+`generation='AI'` · 사유 없는 거부 · 사유 사후 변경)도 전부 INSERT/UPDATE 에 성공했다. 문서-DDL 불일치도 사실이다 — 화면 설계서는 `CHECK 3종 · 트리거 3종` 이라 적었고 DDL 은 **CHECK 4 · 트리거 1** 이었다. |
| 2026-08-07 | 수정완료 | **원인은 `required` 의 의미다.** JSON Schema 의 `required` 는 **키가 있는가**만 보고 값이 `null` 이어도 통과한다. F-083 에서 `required: [model_id]` 를 넣고 닫혔다고 본 것이 그래서 틀렸다. 분기마다 **타입까지 좁혔다** — `AI_DRAFT` 의 `then` 에 `model_id: {type: string, minLength: 1}`, `WIZARD`/`SCRIPT` 의 `then` 에 `draft_text: {type: string, minLength: 1}`. |
| 2026-08-07 | 수정완료 | **응답에서 증거를 생략할 수 없게 했다.** `Rule.required` 에 `generation` · `approved_at` · `approved_by` · `rejected_at` · `rejected_by` · `reject_reason` 6종을 넣었다(값은 nullable, 키는 필수). 속성을 통째로 생략할 수 있으면 화면이 '생성 경로 미상'과 '값이 null'을 구별하지 못하고, 구현이 빠뜨려도 계약 위반이 되지 않는다. `allOf` 조건부 2종을 더해 **AI 초안이면 `generation` 이 `AI`/`THRESHOLD_FALLBACK` 로 좁혀지고**, **거부가 있으면 사유·거부자가 non-null** 이 되게 했다 — DB CHECK 와 같은 의미를 API 계약에도 둔 것이다. |
| 2026-08-07 | 수정완료 | **DB 불변식 3종 추가.** ① `CHECK (origin = 'AI_DRAFT' OR generation IS NULL OR generation = origin)` — 기존 CHECK 는 'AI 초안에 경로가 있는가'만 보아 **사람이 만든 규칙을 AI 산출물로 위조**할 수 있었다. ② `CHECK ((rejected_at IS NULL) = (reject_reason IS NULL))` + 공백 문자열 금지 — 사유 없는 거부는 '사람이 검토했다'의 증거가 되지 못한다(0937 부속서 A 3.2 절차 3). ③ `trg_rule_reject_immutable` 의 감시 목록에 `reject_reason` 추가 — 빠져 있으면 사유만 사후에 바꿔치기할 수 있어 '거부는 불변'이라는 주장이 성립하지 않는다. |
| 2026-08-07 | 수정완료 | **문서를 DDL 에 맞췄다.** 화면 설계서 6.2 의 `CHECK 3종 · 트리거 3종` -> **거부 관련 CHECK 4종 · 트리거 1종**, 존재하지 않는 `trg_rule_no_approve_after_reject` 인용 -> 실제 배타 CHECK 로 정정. API 명세서의 봉인 트리거 `7종` -> **8종**(거부 불변 트리거 추가분). DB 설계서 4장의 봉인 트리거 표 제목도 '승인·거부 기록은 사후에 봉인된다'로 넓혔다. **`meta_verify.py` 가 이제 이 주장들을 실제 DDL 과 대조한다** — 문서가 DDL 보다 강한 보장을 주장하면 실패한다. |
| 2026-08-07 | 수정완료 | 검증: `db/verify.py` 87 -> **98/98**(반례 11종 추가), `api_verify.py` 60 -> **71/71**. 결함 주입 — DB CHECK·트리거 5종을 하나씩 되돌리면 각각 대응 테스트가 뒤집히고, API 스키마 9종을 되돌리면 매트릭스가 실패한다. 전량 검출 확인 |
