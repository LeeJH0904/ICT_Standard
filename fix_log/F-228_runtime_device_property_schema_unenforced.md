# F-228 · 런타임 설정 API가 OpenAPI 입력 제약을 적용하지 않음

| 항목 | 값 |
|---|---|
| 심각도 | 오류 |
| 분류 | 코드버그 |
| 대상 | `project_code/backend/api.py:451-465` · `project_code/backend/services/ems.py:189-204` · `project_docs/api/openapi.json:2798-2831` |
| 발견일 | 2026-08-13 |
| 상태 | 신규 |

## 근거

TTAK.KO-10.0943 표 7-15 — `DEVICE_PROPERTY.Period`는 14 bit `UNSIGNED INT`다.

`openapi.json`의 `DevicePropertyPatch`는 `additionalProperties: false`, `minProperties: 1`, `period_sec` 범위 0~16383을 계약한다.

## 현상

라우트는 요청 본문을 타입 없는 `dict`로 받고 `selector`·`property`가 객체인지, `property`가 비지 않았는지만 검사한다. 속성 키 집합과 `period_sec` 범위는 검사하지 않는다. 서비스 빌더도 알 수 없는 키는 무시하고 `period_sec`는 그대로 `DeviceProperty.period`에 넣는다.

실제 ASGI HTTP 요청에서 OpenAPI가 금지한 두 입력을 각각 전송한 결과 모두 HTTP 200이었다.

```text
property={value: 1}            -> 200
property={period_sec: 16384}  -> 200
python project_docs/api/api_verify.py -> 71/71 통과
```

`api_verify.py`는 JSON Schema 자체에 위 반례를 넣어 거부됨을 확인하지만 실행 라우트에는 같은 입력을 넣지 않아 계약과 구현의 분기를 놓친다.

## 영향

클라이언트는 적용되지 않은 `value`를 성공으로 오인한다. 14 bit를 넘는 Period는 fake link에서는 성공하고 실제 SIAP 인코더 경로에서는 뒤늦게 실패할 수 있어 simulate와 실물 동작도 갈린다.

## 재현

```python
from pathlib import Path
from tempfile import TemporaryDirectory
from tools.gate_e2e import call, _fresh_app, _register_install
from test_api import _register_link_device
from contracts.frame import DevType

with TemporaryDirectory() as td:
    app, db_path, link, builder = _fresh_app(Path(td))
    install_id = _register_install(db_path, 3, 1, 0x01, builder)
    _register_link_device(link, 3, 1, DevType.SENSOR, 0x01)
    for prop in ({value: 1}, {period_sec: 16384}):
        r = call(app, PATCH, /api/v1/device-property,
                 json={selector: {install_id: install_id}, property: prop},
                 headers={X-User-Id: demo-user-1})
        print(prop, r.status_code)
# 둘 다 200
```

## 제안

OpenAPI와 같은 닫힌 요청 모델을 런타임 라우트에 적용하고, `api_verify.py` 또는 별도 live 검증기가 스키마 음성 벡터를 실제 HTTP에도 전송해 같은 판정을 요구하게 한다.

---

## Claude 처리 기록

| 일시 | 상태 | 내용 |
|---|---|---|

