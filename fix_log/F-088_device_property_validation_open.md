# F-088 · DeviceProperty 요청의 선택자·값 계약이 열려 있음

| 항목 | 값 |
|---|---|
| 심각도 | 오류 |
| 분류 | 문서불일치 |
| 대상 | `project_docs/api/openapi.json` `DevicePropertySelector` · `DevicePropertyPatch` |
| 발견일 | 2026-08-07 |
| 상태 | 수정완료 |

## 근거

0943 표 7-15는 `Period`를 14bit, `Lower Value`·`Upper Value`를 32bit `USER DEPENDENT`로 정의한다. 프로젝트 정본 `CLAUDE.md` §3.5는 USER DEPENDENT 필드가 `DEVICE_MAIN_INFO.Value Type`을 따르고 32bit 범위 밖 값은 거부한다고 결정했다.

OpenAPI 설명은 선택자가 `install_id` 개별 또는 `greenhouse_id + install_location` 구역 일괄이라고 선언하고, 둘 다 없으면 400이라고 적는다.

## 현상

- `DevicePropertySelector`에는 `required`·`oneOf`가 없어 `{}`와 개별·구역 선택자를 동시에 넣은 객체가 모두 스키마상 유효하다.
- `DevicePropertyPatch`에는 `minProperties`가 없어 변경값이 하나도 없는 `{}`가 유효하다.
- 두 임계값은 제한 없는 `number`라 32bit 표현 범위 밖 값과 대상 장치의 INT/UINT/FLOAT 타입 불일치를 계약에서 거부하지 않는다.

`additionalProperties: false`는 알려지지 않은 필드만 막을 뿐 위 세 반례를 막지 못한다.

## 영향

API 설명과 실제 요청 계약이 다르며, 유효 대상을 정할 수 없거나 SIAP 인코더가 표현할 수 없는 요청이 전송 단계까지 내려간다. 구역 일괄 적용에서는 대상별 값 타입이 다르면 부분 적용 의미도 미정이다.

## 제안

선택자 XOR, 최소 한 개 변경 필드, 대상별 `Value Type` 범위 검사를 명시한다. 구역 대상 중 하나라도 실패할 때 전량 거부인지 부분 적용인지도 응답 계약으로 결정한다.

---

## Claude 처리 기록

| 일시 | 상태 | 내용 |
|---|---|---|
| 2026-08-07 | 신규 | GPT 검증 기록 |
| 2026-08-07 | 확인 | 지적대로다. 설명문이 강제하는 것은 없다. `additionalProperties: false` 는 모르는 필드만 막을 뿐 `{}` · 상충 선택자 · 빈 변경 · 범위 밖 임계값 네 반례를 모두 통과시켰다. |
| 2026-08-07 | 수정완료 | `DevicePropertySelector` 에 **`oneOf`**(개별 `install_id` XOR 구역 `greenhouse_id`+`install_location`) + `minProperties: 1`, `DevicePropertyPatch` 에 **`minProperties: 1`** 과 임계값의 **float32 표현 범위**(±3.4028235e38) 경계를 넣었다. 대상별 `Value Type`(INT/UINT/FLOAT) 일치 검사는 스키마로 표현할 수 없으므로 **서버 검증 + `INVALID_DATA_TYPE` 응답**으로 계약에 적었다 — `CLAUDE.md` §3.5 의 "32bit 범위 초과는 거부한다(F-044)"와 같은 판정이다. 구역 일괄에서 하나라도 실패하면 **전량 거부**(422)로 결정했다: 부분 적용은 화면이 어느 장치가 적용됐는지 되물을 수단이 없다. `api_verify.py` **60/60** |
