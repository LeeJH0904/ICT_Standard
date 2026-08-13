# F-220 · 부분 속성 PATCH가 기존 임계값을 삭제함

| 항목 | 값 |
|---|---|
| 심각도 | 오류 |
| 분류 | 코드버그 |
| 대상 | `project_code/backend/services/ems.py:130-133` · `project_code/backend/repository.py:702-716` |
| 발견일 | 2026-08-13 |
| 상태 | 신규 |

## 근거

TTAK.KO-10.0943 §8.1.3.2 — “디바이스 속성 설정 메시지(REQ_SET_DEVICE_PROPERTY)는 현재 설정되어 있는 디바이스 속성값을 사용자의 목적에 따라 변경하고자 할 경우 전송”한다.

`project_docs/api/openapi.json`의 `DevicePropertyPatch`는 네 속성을 모두 선택으로 두고 `minProperties: 1`만 요구한다. `ems._build_device_property()`도 일부만 바꾸면 나머지는 현재값을 유지한다고 명시한다.

## 현상

`ems.set_device_property()`는 노드로 보낼 프레임에서는 누락된 `lower_value`·`upper_value`를 기존 값으로 채운다. 그러나 응답 성공 뒤 DB 반영에서는 `property_patch.get()`을 써 누락과 명시적 `null`을 모두 `None`으로 바꾸고, `repository.update_device_property()`는 그 `None`을 그대로 저장한다.

따라서 수집 주기만 바꾸는 정상 부분 PATCH가 기존 이벤트 임계값을 삭제한다. 기존 API 회귀 테스트도 `period_sec`만 보내지만 응답 상태와 ID만 검사하여 이 손상을 놓친다.

## 영향

노드에는 기존 임계값이 전송됐는데 DB에는 NULL이 남아 동일 설정의 두 정본이 즉시 갈린다. 다음 부분 설정 시 `_build_device_property()`가 DB NULL을 0으로 대체하므로 노드의 임계값도 뒤늦게 0으로 덮일 수 있다.

## 재현

신선한 DB에 `lower_limit=2.0`, `upper_limit=8.0` 장치를 만들고 성공 응답을 반환하는 최소 `SiapLink`·`FrameBuilder` 대역으로 실제 `ems.set_device_property()`를 호출했다.

```text
property_patch = {period_sec: 60}
호출 전 DB 임계값 = (2.0, 8.0)
호출 후 DB 임계값 = (None, None)
```

같은 실행에서 backend 전체 테스트는 241/241 통과했다.

## 제안

누락과 명시적 삭제를 구분하고, 누락된 필드는 SQL UPDATE 대상에서 제외한다. `period_sec`·`transfer_mode`의 로컬 저장 정책도 한 계약으로 정한다.

---

## Claude 처리 기록

| 일시 | 상태 | 내용 |
|---|---|---|
| | | |

