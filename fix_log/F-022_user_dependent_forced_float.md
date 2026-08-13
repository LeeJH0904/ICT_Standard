# F-022 · USER DEPENDENT 필드의 무근거 FLOAT 고정

| 항목 | 값 |
|---|---|
| 심각도 | 위험 |
| 분류 | 문서불일치 |
| 대상 | `project_docs/siap/spec_verify.py:38-43`, `project_docs/contracts/frame.py:190-198`, `project_docs/siap/SIAP_메시지_명세서.md` §2.3·§7 |
| 발견일 | 2026-08-03 |
| 상태 | 수정완료 |

## 근거

0943 표 7-15 — `Lower Value`, `Upper Value`, `Lower Limit`, `Upper Limit`, `Precision`의 타입은 모두 "USER DEPENDENT", 길이는 각 32비트이다.

`SIAP_메시지_명세서.md` §7 — FLOAT 표현 결정은 "Value Type = FLOAT"에 대해서만 IEEE-754 single로 기록되어 있다.

## 현상

`spec_verify.py`의 `device_property()`는 위 5개 필드를 `b.wf(v)`로 항상 IEEE-754 FLOAT 패킹한다. `DeviceProperty` 계약도 다섯 필드를 모두 `float`로 고정한다. 그러나 표준의 USER DEPENDENT가 어떤 규칙으로 INT/UNSIGNED INT/FLOAT 중 하나를 선택하는지, `Device Main Info.Value Type`을 따르는지에 대한 해석 결정이 문서에 없다.

## 영향

현재 예시는 FLOAT 센서라 우연히 일치하지만 INT/UNSIGNED INT 디바이스의 경계값·정밀도를 다른 구현체가 다르게 해석할 수 있다. 펌웨어 코덱의 직접 입력 명세로 사용하기에는 결정이 누락되어 있다.

## 재현

`spec_verify.py:42`의 루프는 `DeviceMainInfo.value_type`을 확인하지 않고 다섯 값을 전부 `wf()`로 전달한다. 표 7-15 또는 프로젝트 결정표에는 이 고정을 정당화하는 근거가 없다.

## 제안

USER DEPENDENT의 실제 타입 결정 규칙을 표준 근거 또는 명시적 구현 결정으로 확정한 후 계약·예시·향후 C/Python 코덱에 동일하게 반영한다.

---

## Claude 처리 기록

| 일시 | 상태 | 내용 |
|---|---|---|
| 2026-08-03 | 확인 | 타당. 표 7-15 의 USER DEPENDENT 5필드를 FLOAT 로 고정할 근거가 표준에 없다. 표준 미규정 사항이므로 결정하고 기록해야 한다(CLAUDE.md §3.5) |
| 2026-08-03 | 수정완료 | 5필드는 `DEVICE_MAIN_INFO.Value Type` 을 따르도록 결정했다 — 같은 물리량의 경계·정밀도이므로 타입이 달라질 이유가 없다. `spec_verify.py` · `frame.py` · SIAP 명세서에 반영. 표준 미규정 사항이므로 표준결함 F-034 로 별도 등재 |
| 2026-08-03 | 수정완료 | 계약 테스트 2종 추가 — UINT 디바이스의 경계값이 int 로, FLOAT 디바이스의 경계값이 float 로 유지되는지 검사(`test_contract.py`) |
| 2026-08-03 | 수정완료 | **F-043 정정** — 2차 처리 시 상세 파일의 상태를 `신규` 그대로 두고 처리 기록을 비워 인덱스와 어긋났다. 이 항목으로 보강 |
