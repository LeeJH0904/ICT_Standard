# F-195 · 서비스 검증기가 실행 불가능한 호출 흔적만으로 통과함

| 항목 | 값 |
|---|---|
| 심각도 | 오류 |
| 분류 | 코드버그 |
| 대상 | `tools/services_verify.py::_call_sites` · `_record_alert_kinds` |
| 발견일 | 2026-08-11 |
| 상태 | 수정완료 |

## 근거

TTAK.KO-10.0937 6.4·6.5는 미수집과 긴급 상황에서 사용자·관리자 알림 기능이 실제로 제공될 수 있어야 한다. F-191은 함수·문서 존재가 아니라 운영 경로의 실제 결선을 검사해야 한다는 결함이었다.

## 현상

신설 검증기는 AST에 `check_stale_devices()` 호출 한 번과 `record_alert(kind=...)` 네 문자열이 등장하는지만 센다. 도달 가능성, 호출 대상의 실제 정의, 라우트·I/O 경로 연결은 확인하지 않는다.

입력을 다음 가상 운영 파일 하나로 메모리에서 교체했다.

```python
if False:
    check_stale_devices()
    record_alert(kind="NODE_ERROR")
    record_alert(kind="DISCONNECT")
    record_alert(kind="CONTROL_TIMEOUT")
    record_alert(kind="NO_DATA")
```

모든 호출은 실행 불가능하지만 다음처럼 통과했다.

```text
[OK] check_stale_devices() 운영 코드 호출 1건
[OK] alert.kind 4종 전부 실제 record_alert() 호출에 등장
[PASS] tools/services_verify.py
DEAD_CODE_MUTANT_EXIT=0
```

## 영향

F-191의 현재 결선과 회귀 테스트는 통과하지만, 실제 호출을 제거하고 dead code나 무관한 더미 호출만 남겨도 단계 6 전체 스윕이 거짓 통과할 수 있다.

## 재현

실제 파일을 수정하지 않고 `_iter_backend_py()`가 위 AST를 반환하는 가상 Path 하나를 내도록 메모리에서 바꾼 뒤 `services_verify.main()`을 호출했다. 종료 코드는 0이었다.

---

## Claude 처리 기록

| 일시 | 상태 | 내용 |
|---|---|---|
| 2026-08-11 | 확인 | 재현 성공 — `ast.walk(tree)`는 `if False:` 블록 내부도 그냥 방문해, 실행 불가능한 4개 호출이 전부 "운영 코드 호출"로 잡혔다. `_call_sites`·`_record_alert_kinds` 둘 다 같은 결함(순회 방식 자체의 문제)이었다. |
| 2026-08-11 | 수정완료 | `_dead_node_ids()` 신설 — 상수 조건 `if`(거짓 분기 또는 참 분기의 반대쪽)와 `return`/`raise`/`continue`/`break` 뒤에 남은 후속 문장을 죽은 코드로 표시한다(`Try`의 `body`/`handlers`/`orelse`/`finalbody`도 재귀). `_call_sites`·`_record_alert_kinds`가 `ast.walk()` 결과에서 죽은 노드를 제외한 `_live_calls()`만 쓰도록 교체. **명시적 한계**: 완전한 호출 그래프(도달가능성) 분석이 아니다 — "아무도 안 부르는 함수 전체"류는 여전히 놓칠 수 있고, 이 검증기 파일 자체의 독스트링에 그 경계를 적었다(과설계 방지, §4.3 검증기 비례성). **결함 주입 검증**: (1) F-195 재현 스니펫 그대로(`if False:` 안에 4개 호출)를 별도 스크립트로 `_dead_node_ids`/`_live_calls`에 직접 넣어 살아있는 호출 0건 확인. (2) 실제 `api.py`의 두 `check_stale_devices()` 호출부를 `if False:`로 감싸는 결함을 주입 → 검증기가 정확히 `[FAIL]`(check_stale_devices 배선 없음)로 잡음, 원상복구 후 재확인. 검증: `python tools/services_verify.py` 실제 코드 기준 **PASS** 유지 · `pytest siap/tests/ backend/tests/` **340/340**(영향 없음, 소스 변경 없이 검증기만 수정) |

