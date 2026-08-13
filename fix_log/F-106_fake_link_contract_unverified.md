# F-106 · 단계 1 출구가 FakeSiapLink 계약을 검증하지 않음

| 항목 | 값 |
|---|---|
| 심각도 | 오류 |
| 분류 | 코드버그 |
| 대상 | `project_code/contracts/test_contract.py` · `tools/layer_verify.py:109-117` |
| 발견일 | 2026-08-08 |
| 상태 | 수정완료 |

## 근거

개발 착수 지시서 §3.1의 범위는 `contracts/fake_link.py` 신설을 포함하고, GPT 검증란은 이 구현이 `SiapLink Protocol`을 완전히 만족하는지 확인하도록 요구한다. CLAUDE.md §6.2는 존재 여부가 아니라 실제 호출과 반환을 검사하도록 요구한다.

## 현상

`test_contract.py`는 `fake_link`나 `FakeSiapLink`를 한 번도 import하지 않는다. `layer_verify.py`도 `contracts/`에서 `project_docs` import 여부만 확인할 뿐 계약 구현을 import하거나 Protocol과 대조하지 않는다.

임시 복사본에서 `fake_link.py`를 `class FakeSiapLink: pass`로 바꿔 모든 Protocol 메서드를 제거했지만 계약 검증은 56/56, 계층 검증은 7/7로 모두 exit 0이었다. 더 강하게 `def broken(:` 문법 오류를 넣어도 두 출구가 그대로 통과했다. 현재 실제 구현은 독립 import·시그니처·호출 검사에서 Protocol 메서드 7개를 모두 만족했지만, 그 사실은 단계 출구가 증명하지 않는다.

## 영향

`fake_link.py`의 전면 삭제 수준 회귀도 단계 1 자동 출구에서 검출되지 않는다. 단계 2 이후 backend·web 단위테스트의 대역 기반이 깨진 채 단계 완료로 판정될 수 있다.

## 재현

1. 임시 복사본의 `project_code/contracts/fake_link.py` 내용을 `class FakeSiapLink: pass`로 교체한다.
2. `python project_code/contracts/test_contract.py`와 `python tools/layer_verify.py`를 실행한다.
3. 실제 결과: 각각 56/56과 7/7, 둘 다 exit 0.
4. 파일을 문법 오류 상태로 바꿔도 결과가 같다.

## 제안

계약 테스트가 `FakeSiapLink`를 실제 import하고 `SiapLink`의 메서드 집합·시그니처를 대조한 뒤, 각 메서드를 최소 정상 입력으로 호출해 반환형과 상태 변화를 확인하게 한다. 빈 클래스와 문법 오류 주입을 회귀 반례로 고정한다.

---

## Claude 처리 기록

| 일시 | 상태 | 내용 |
|---|---|---|
| 2026-08-08 | 신규 | GPT 단계 1 검증에서 빈 클래스·문법 오류가 두 출구를 모두 통과하는 반례 재현 |
| 2026-08-08 | 확인 | `fake_link.py`를 `class FakeSiapLink: pass`와 `def broken(:` 로 교체해 재현 — 수정 전 `test_contract.py`가 각각 56/56·exit 0 이었음을 확인 |
| 2026-08-08 | 수정완료 | `test_contract.py`에 F-106 회귀 4건 추가: ① `importlib.util`로 `fake_link.py`를 직접 로드해 `FakeSiapLink` 클래스 노출 확인 ② 인스턴스화 확인 ③ `SiapLink` 메서드 7종(start/stop/recv/send/registry/devices/stats)이 실제로 존재하고 callable 인지 확인 ④ 각 메서드를 최소 정상 입력(빈 Frame 요청 등)으로 호출해 반환형(`None`/`dict`/`tuple`/`list`/`Frame|None`)까지 확인. `tools/layer_verify.py` 는 계층(import 방향) 검증기라 프로토콜 이행 검증과 책임이 다르므로 변경하지 않음 — 대신 대상 목록에서 제외하지 않고 이 파일에 사유를 남긴다. 결함 주입 재현: 빈 클래스 교체 시 "메서드 7종 callable" 항목이 FAIL(59/60) · 문법 오류 교체 시 로드·인스턴스화·callable 3항목이 FAIL(57/60), 둘 다 원본 복원 후 60/60 확인. 회귀: `python project_code/contracts/test_contract.py` 56 → **60/60** |
