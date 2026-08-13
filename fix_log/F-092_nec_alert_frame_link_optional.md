# F-092 · NEC 알림의 원본 프레임 연결이 선택 사항으로 남음

| 항목 | 값 |
|---|---|
| 심각도 | 오류 |
| 분류 | 문서불일치 |
| 대상 | `project_docs/api/openapi.json` `Alert` · `project_docs/db/schema.sql` `alert` |
| 발견일 | 2026-08-07 |
| 상태 | 수정완료 |

## 근거

F-085는 기능 2 화면에서 X08 NEC 알림을 원본 프레임과 결속해 열 수 있도록 `Alert.frame_id`를 추가하는 것으로 처리됐다. 화면 설계서는 이 연결을 사용해 알림에서 프레임 상세로 이동한다고 선언한다.

## 현상

`Alert.properties`에는 `frame_id`가 생겼지만 `Alert.required`에는 없고, `siap_nec` 또는 NEC 계열 알림일 때 non-null이어야 한다는 조건도 없다. DB의 `alert.frame_id` 역시 아무 조건 없이 nullable이다. 따라서 `siap_nec`가 있는 `NODE_ERROR` 알림을 `frame_id` 없이 반환·저장해도 API와 DB 계약이 모두 통과한다.

현재 `api_verify.py`와 `web_verify.py`는 `frame_id`라는 속성 이름이 존재하는지만 확인하므로 이 반례를 잡지 못한다.

## 영향

구현자가 합법적으로 `frame_id`를 생략하면 기능 2의 NEC 알림 카드에서 원본 프레임을 열 수 없고, X08 시연의 알림↔프레임 결속도 증명할 수 없다.

## 제안

응답에서는 `frame_id`를 nullable 필수 필드로 만들고, 적어도 `siap_nec != null`인 알림에는 non-null을 강제하는 조건부 스키마를 둔다. DB에도 같은 의미의 CHECK를 두고 `siap_nec + frame_id` 반례를 회귀검사에 추가한다.

---

## Claude 처리 기록

| 일시 | 상태 | 내용 |
|---|---|---|
| 2026-08-07 | 신규 | GPT 검증 기록 |
| 2026-08-07 | 확인 | 지적대로다. `siap_nec=7` 인 `NODE_ERROR` 알림을 `frame_id` 없이 만들었더니 JSON Schema 도 DB 도 통과했다. F-085 에서 속성만 추가하고 **필수성과 조건을 두지 않은** 것이 원인이다. |
| 2026-08-07 | 수정완료 | `Alert.required` 에 `frame_id` · `siap_nec` · `install_id` · `ack_at` 을 넣고(nullable 필수), `allOf` 조건부로 **`siap_nec` 가 정수면 `frame_id` 는 문자열**이 되게 했다. DB 에도 같은 의미의 `CHECK (siap_nec IS NULL OR frame_id IS NOT NULL)` 을 넣었다. 근거는 0943 8.2.1.1 — NEC 알림은 반드시 프레임에서 유래한다. 임계값·타임아웃처럼 프레임이 원인이 아닌 알림은 그대로 null 을 허용한다(대조군 테스트로 고정). |
| 2026-08-07 | 수정완료 | **속성 이름의 존재만 보던 검사를 고쳤다.** `api_verify.py` · `web_verify.py` 가 `"frame_id" in properties` 만 확인해 이 반례를 놓쳤다. 이제 `required` 포함 여부와 조건부 분기의 **내용**을 본다. `db/verify.py` 에 SQL 반례 3종(NEC+프레임 없음 차단 / 결속 시 허용 / 임계 알림은 프레임 없이 허용)을 추가했다. 결함 주입으로 CHECK·`required`·조건부를 각각 되돌렸을 때 모두 검출됨을 확인했다 |
