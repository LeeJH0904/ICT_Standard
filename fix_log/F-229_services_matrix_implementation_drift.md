# F-229 · 0937 대조표가 구현 후에도 존재하지 않는 진입점을 근거로 삼음

| 항목 | 값 |
|---|---|
| 심각도 | 오류 |
| 분류 | 문서불일치 |
| 대상 | `project_docs/services/0937_요구사항_대조표.md:37,282-291` · `project_docs/services/services_verify.py:345-380` |
| 발견일 | 2026-08-13 |
| 상태 | 수정완료 |

## 근거

TTAK.KO-10.0937 §6은 EMS·DMS·MMS·FMS·FCS의 서비스 능력을 요구한다. 표준은 Python 함수 이름을 규정하지 않는다.

개발 착수 지시서 §3 단계 6은 `backend/services/`와 `api.py`의 구현을 대조표에 맞춰 검증하도록 한다.

## 현상

대조표는 단계 7까지 구현된 현재에도 “현재 단계는 구현 전”이라고 선언한다. §4.1은 구현 근거로 5개 모듈의 진입점을 열거하지만 실제 모듈 대조 결과 다음 10개가 없다.

```text
ems: on_node_connect, on_node_property, on_device_property,
     on_node_device_all, on_profile, on_node_disconnect,
     on_node_reboot, on_keep_alive
fms: on_device_value
fcs: on_node_error
```

일부 동작은 `backend/ingest.py`와 현재 서비스의 다른 함수에 구현돼 있다. 그런데 `services_verify.py`는 §4.1 문서 표에서 `ENTRY` 집합을 만든 뒤 같은 문서가 인용한 심벌을 그 집합과 대조한다. 실제 Python 모듈을 import하거나 AST로 읽지 않으므로 위 10개가 모두 없어도 42/42를 통과한다.

## 영향

요구 충족 행의 추적 근거가 실행 코드에 닿지 않는다. 구현을 바꾸거나 삭제해도 설계 검증은 자기 문서만 대조해 계속 통과할 수 있다.

## 재현

```powershell
cd project_code
@'
from importlib import import_module
expected = {
  ems: (on_node_connect, on_node_property, on_device_property, on_node_device_all,
          on_profile, on_node_disconnect, on_node_reboot, on_keep_alive),
  fms: (on_device_value, check_stale_devices, query_env),
  fcs: (execute, on_node_error, query_history),
}
for mod, names in expected.items():
    obj = import_module(fbackend.services.{mod})
    print(mod, [n for n in names if not callable(getattr(obj, n, None))])
'@ | python -
cd ..
python project_docs/services/services_verify.py
# 위 10개 missing 출력 뒤에도 42/42 통과
```

## 제안

표준은 함수명이 아니라 능력을 요구하므로 실제 구현 배치가 맞다. 대조표의 “구현 전” 문구와 §4.1 진입점을 현재 `ingest.py`·서비스 함수로 갱신하고, 검증기는 문서 표가 아닌 실제 모듈에서 호출 가능한 심벌을 독립적으로 읽어야 한다.

---

## Claude 처리 기록

| 일시 | 상태 | 내용 |
|---|---|---|
| 2026-08-14 | 확인 | 실제 `backend.services` 모듈을 import해 §4.1 진입점을 대조한 결과 ems 8개, fms 1개, fcs 1개가 호출 불가능했다. 동작은 `ingest.handle()` 및 현재 서비스 함수에 배치되어 있는데도 `services_verify.py`가 문서 표를 `ENTRY` 정본으로 재사용해 42/42 통과하는 거짓 음성을 재현했다. |
| 2026-08-14 | 수정완료 | 대조표의 “구현 전” 선언과 §4.1·§4.4 진입점/시그니처를 실제 `link`·`ingest`·서비스 함수로 갱신했다. `services_verify.py`는 7개 Python 소스를 AST로 읽어 문서의 함수·클래스 메서드를 독립 대조한다(44/44). 존재하지 않는 `ems.on_node_connect()`를 재주입하자 exit 1로 반전한 뒤 원복했다. |
