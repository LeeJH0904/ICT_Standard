# F-085 · 검증 화면용 Frame 응답 계약 불완전

| 항목 | 값 |
|---|---|
| 심각도 | 오류 |
| 분류 | 문서불일치 |
| 대상 | `project_docs/web/화면_설계서.md` §5 · `project_docs/api/openapi.json` `Frame` |
| 발견일 | 2026-08-07 |
| 상태 | 수정완료 |

## 근거

0943 표 7-1·7-14·7-15는 필드 비트 폭을 정의한다. 화면 설계서 §5는 각 필드의 비트 폭·오프셋과 바이트 경계 하이라이트를 표시하되, §0·§10에 따라 화면은 비트 언팩이나 표준 판정을 하지 않는다고 선언한다.

## 현상

OpenAPI `Frame`은 `raw_hex`, 고정 `header`, `kind`, `element_count`, `is_valid`, `violations`만 제공한다.

- 페이로드를 포함한 필드 이름·비트 오프셋·폭·값 배열이 없다.
- `judgement`(`normal`/`violation`/`alert`)가 없다.
- `X08`의 별도 알림 이벤트 `Alert`에는 원인 `frame_id`가 없어 정상 Frame과 알림을 화면에서 결속할 수 없다.

골든 벡터의 `fields`와 `judgement`는 정적 테스트 산출물이며 런타임 `getFrame`·SSE 응답 계약에는 포함되지 않는다.

## 영향

화면이 직접 프레임을 해석하면 계층 규칙을 위반하고, 해석하지 않으면 핵심 필드 분해와 F-060의 알림 구분을 표시할 수 없다. 기능 2의 핵심 시각화가 API 계약으로 닫히지 않았다.

## 제안

서버가 프로토콜 계층의 판독 결과를 `FieldSlice(name, bit_offset, bit_width, raw_value)` 형태로 내보내고, 판정 종류와 알림의 원인 프레임 식별자를 응답 계약에 추가한다. 화면은 이 메타데이터만 렌더링한다.

---

## Claude 처리 기록

| 일시 | 상태 | 내용 |
|---|---|---|
| 2026-08-07 | 신규 | GPT 검증 기록 |
| 2026-08-07 | 확인 | 지적대로다. 골든 벡터의 `fields`·`judgement` 는 정적 테스트 산출물이었고 런타임 `getFrame`·SSE 응답에는 없었다. 화면이 직접 언팩하면 §3.4(표준 해석은 프로토콜 계층에만) 위반, 하지 않으면 기능 2 의 핵심 시각화가 불가능한 양자택일이었다. |
| 2026-08-07 | 수정완료 | `FieldSlice(name, bit_offset, bit_width, raw_value, value_repr)` 스키마를 신설하고 `Frame.fields` 를 **`required`** 로 넣었다 — optional 로 두면 서버가 비워도 계약 위반이 아니게 되어 같은 구멍이 남는다. `Frame.judgement`(`normal`/`violation`/`alert`)도 `required` 다. 이 세 값의 분리는 F-060 에서 확정한 것으로, `violations` 가 비었지만 alert 인 정상 NEC 알림을 화면이 구별할 유일한 수단이다. `Alert.frame_id` + `frame_log` FK 를 추가해 알림을 원인 프레임에 결속했고, `alert.kind` 에 `CONTROL_TIMEOUT` 을 넣었다. 화면은 이 메타데이터를 렌더링만 한다 |
