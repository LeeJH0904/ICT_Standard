# F-110 · FakeSiapLink 검증이 Protocol 시그니처와 Iterator 계약을 보지 않음

| 항목 | 값 |
|---|---|
| 심각도 | 오류 |
| 분류 | 코드버그 |
| 대상 | `project_code/contracts/test_contract.py:226-282` |
| 발견일 | 2026-08-08 |
| 상태 | 수정완료 |

## 근거

`project_code/contracts/siap_iface.py:20-40`은 `start(..., **opts)`, `recv() -> Iterator[Frame]`, `send(frame, timeout=None)`을 `SiapLink Protocol`의 일부로 정의한다. Frame 구조 명세서 §5도 같은 시그니처를 정본으로 제시한다.

F-106은 빈 클래스·문법 오류를 막기 위해 실제 호출과 반환형 검사를 추가했다. 이 건은 그 두 기존 반례가 아니라, 메서드가 존재하지만 Protocol 시그니처가 호환되지 않는 구현을 주입한 결과다.

## 현상

현재 F-106 회귀는 `start(simulate, proto_mode=strict)`만 호출해 `**opts` 수용 여부를 보지 않고, `send(req)`만 호출해 `timeout` 인자를 보지 않는다. `recv()` 결과는 곧바로 `list(...)`로 변환하므로 iterator가 아닌 일반 iterable도 통과한다.

`start`에서 `**opts`를 제거하고, `send`에서 `timeout`을 제거하며, `recv()`가 `[]`을 반환하는 가짜 클래스를 `fake_link.py` 로더에 메모리 주입했다. 이 구현은 서비스 예시의 `send(frame, timeout=2.0)`에서 `TypeError`가 나고 Protocol 반환형도 어기지만, 실제 `test_contract.py`는 60/60, exit 0이었다.

현재 저장소의 진짜 `FakeSiapLink`는 독립 시그니처 대조와 `start(..., host=...)`·`send(..., timeout=...)`·iterator 검사를 모두 통과했다. 결함은 현재 구현이 아니라 자동 출구의 회귀 검출력이다.

## 영향

빈 클래스보다 덜 노골적인 시그니처 회귀가 단계 1 출구를 통과하고, 이후 backend·web이 Protocol 정본대로 선택 인자를 넘기는 순간 실패한다. “Protocol을 전부 만족한다”는 GPT 검증 항목을 60/60 결과가 증명하지 못한다.

## 재현

1. 메서드 7종은 모두 갖되 `start(self, run_mode, *, proto_mode=strict)`, `send(self, frame)`, `recv(self): return []`인 가짜 클래스를 주입한다.
2. `python project_code/contracts/test_contract.py`와 동일한 실행 경로를 돌린다.
3. 실제 결과: 60/60, exit 0.
4. `inspect.signature` 대조에서는 `**opts`·`timeout` 누락이 보이고, `iter(recv_result) is recv_result`도 false다.

## 제안

`inspect.signature`로 Protocol과 구현의 파라미터 이름·kind·기본값 호환성을 대조한다. 호출 검사에도 임의 `**opts`와 `timeout`을 넣고, `recv()` 반환값은 `collections.abc.Iterator` 또는 `iter(x) is x`로 확인한다.

---

## Claude 처리 기록

| 일시 | 상태 | 내용 |
|---|---|---|
| 2026-08-08 | 신규 | GPT 단계 1 재검증에서 시그니처·Iterator 위반 Fake가 실제 계약 출구 60/60을 통과하는 반례 재현 |
| 2026-08-08 | 확인 | 메서드 7종은 모두 갖되 `start(self, run_mode, *, proto_mode="strict")`(opts 없음)·`send(self, frame)`(timeout 없음)·`recv(self): return []`인 Fake를 실제 `fake_link.py`에 주입해 `test_contract.py` 실행 — 수정 전 60/60·exit 0 통과함을 확인 |
| 2026-08-08 | 수정완료 | `test_contract.py`에 F-110 회귀 2건 추가. ① `_sig_compat(proto_fn, impl_fn)` — `inspect.signature`로 Protocol(`_m.SiapLink`)이 요구하는 파라미터 이름·kind·기본값 유무를 구현(`FakeSiapLink`)이 전부 갖는지 7종 전부 대조(빠진 것만 문제 삼음, 구현이 더 갖는 건 허용) ② 실제 호출 검사 — `start("simulate", proto_mode="strict", host=..., port=...)`로 `**opts` 실수용 확인, `send(frame, timeout=2.0)`로 `timeout` 실수용 확인, `recv()` 결과가 `isinstance(x, collections.abc.Iterator)` 또는 `iter(x) is x`를 만족하는지 확인(`list(...)`로 감싸면 통과하던 기존 F-106 체크의 사각지대). 결함 주입 재현: 위 3종 시그니처 결손 Fake 주입 시 시그니처 대조 항목이 `opts(VAR_KEYWORD) 없음`·`timeout(POSITIONAL_OR_KEYWORD) 없음`으로, 호출 검사 항목이 `TypeError`(2건)·`recv() 가 Iterator 계약을 만족하지 않음: list`로 각각 FAIL(60/62) — 원본 복원 후 62/62 확인. 회귀: `python project_code/contracts/test_contract.py` 60 → **62/62** |
