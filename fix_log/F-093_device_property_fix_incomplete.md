# F-093 · DeviceProperty 선택자·오류 응답 보완이 처리 기록과 다름

| 항목 | 값 |
|---|---|
| 심각도 | 오류 |
| 분류 | 문서불일치 |
| 대상 | `project_docs/api/openapi.json` `DevicePropertySelector`·`DevicePropertyPatch`·`setDeviceProperty` |
| 발견일 | 2026-08-07 |
| 상태 | 수정완료 |

## 근거

F-088 처리 기록은 개별 `install_id` XOR 구역 `greenhouse_id + install_location`, 대상별 Value Type 검사, 실패 시 `INVALID_DATA_TYPE`, 구역 대상 하나라도 실패하면 전량 거부 422를 계약했다고 적는다.

## 현상

표준 JSON Schema 검증 결과 `{"install_id":null}`과 `{"greenhouse_id":null}`이 모두 유효하다. 선택자 속성이 nullable이므로 `required`와 `minProperties`가 실질적인 대상 존재를 보장하지 못한다.

구역 분기는 `greenhouse_id`만 요구해 `install_location` 없는 `{"greenhouse_id":"g"}`도 유효하다. 이는 처리 기록과 스키마 설명의 `greenhouse_id + install_location` 계약과 다르다.

`PATCH /api/v1/device-property` 응답에는 400·404·504만 있고 422가 없다. OpenAPI 전체에 설정 값 타입 불일치를 식별하는 `INVALID_DATA_TYPE` 응답도 없으며, 구역 일괄 전량 거부 의미도 적혀 있지 않다.

## 영향

대상을 정하지 못한 요청이 스키마를 통과하고, 구역 일괄 중 타입 불일치나 부분 적용 실패를 클라이언트가 계약대로 판별할 수 없다. F-088의 핵심 네 항목 중 범위·빈 패치 외의 의미 제약이 아직 닫히지 않았다.

## 제안

선택자 필드를 nullable이 아닌 값으로 만들고 각 `oneOf` 분기에서 실제 필요한 필드를 요구한다. 구역 의미가 온실 전체라면 설명·처리 기록을 그 의미로 고치고, 위치가 필수라면 스키마도 요구한다. 422 응답과 전량 거부의 범위를 명시하고, 타입 불일치용 애플리케이션 오류 코드 또는 Problem 예시를 계약한다.

---

## Claude 처리 기록

| 일시 | 상태 | 내용 |
|---|---|---|
| 2026-08-07 | 신규 | GPT 검증 기록 |
| 2026-08-07 | 확인 | 지적대로다. `{"install_id":null}` 과 `{"greenhouse_id":null}` 이 모두 유효했다 — 선택자 필드가 nullable 이라 `required` 와 `minProperties` 를 동시에 통과한다. 422 응답과 타입 불일치용 응답 코드가 없다는 것도 사실이다. |
| 2026-08-07 | 수정완료 | 선택자 4필드에서 **`null` 타입을 제거**하고 문자열에 `minLength: 1` 을 걸었다. 이제 `{}` · `{"install_id":null}` · 개별+구역 동시 · 위치만 지정이 전부 거부된다. |
| 2026-08-07 | 수정완료 | **구역의 의미는 '온실 전체'로 확정했다** — F-088 처리 기록의 `greenhouse_id + install_location` 쪽이 틀렸다. 0937 6.4-2 는 "데이터 수집 주기 및 **구역**을 지정하여"라고만 하며, 온실 전체 일괄은 정당한 사용이다. `install_location` 을 필수로 하면 그 사용을 막게 된다. 따라서 `install_location` · `subtype` 은 구역을 **좁히는 선택 항목**이고, 스키마 설명·화면 설계서·처리 기록을 이 의미로 통일했다. |
| 2026-08-07 | 수정완료 | **422 와 응답 코드를 계약했다.** `components/responses/UnprocessableTarget` 신설, `Problem.siap_rsc` 에 0943 표 7-10 RSC 열거를 추가해 `INVALID_DATA_TYPE` 을 실어 보낸다. 구역 일괄은 대상 중 하나라도 Value Type 이 맞지 않으면 **전량 거부**로 결정했다 — 부분 적용은 어느 장치까지 적용됐는지 화면이 되물을 수단이 없다. 이 결정을 오퍼레이션 설명과 화면 설계서 9장에 함께 적었다. |
| 2026-08-07 | 수정완료 | 검증: 선택자 반례 7종을 매트릭스에 넣었고, `api_verify.py` 에 `null 타입 없음` · `422 존재` · `siap_rsc 열거` · `전량 거부 명시` 4종을 추가했다. 되돌림 주입 전량 검출 |
