# F-163 · ingest 회신 책임 설계가 이전 계약으로 남음

| 항목 | 값 |
|---|---|
| 심각도 | 오류 |
| 분류 | 문서불일치 |
| 대상 | 아키텍처 설계서 §3.1 · Frame 구조 명세서 §5.1 · `contracts/siap_iface.py:48` |
| 발견일 | 2026-08-10 |
| 상태 | 수정완료 |

## 근거

CLAUDE.md §3.4 — 표준 해석은 프로토콜 계층에만 존재한다. F-154 구현도 이 원칙에 따라 회신은 `siap/link.py::_default_reply()`, ingest는 DB 부수효과로 분리했다.

## 현상

아키텍처 §3.1은 여전히 `handle(frame) -> Frame | None`, `reply = ingest.handle(frame)`, 회신은 ingest 반환값이라는 의사코드를 정본으로 둔다. Frame 구조 명세서와 `siap_iface.py`도 즉시 회신 빌더가 `ingest.handle()`의 반환값이라고 적는다. 실제 `backend/ingest.handle(frame, conn) -> None` 및 `link._dispatch()`와 반대다.

## 영향

후속 단계가 설계 문서를 따르면 F-154 이전 구조를 다시 구현하거나 서비스 계층이 0943 회신 종류를 재해석한다. 표준 원칙상 구현의 책임 분리가 옳고 설계·계약 문구가 틀렸다.

---

## Claude 처리 기록

| 일시 | 상태 | 내용 |
|---|---|---|
| 2026-08-10 | 확인 | 세 대상을 직접 대조 — 아키텍처 설계서 §3.1(`def handle(frame) -> Frame \| None`, `reply = ingest.handle(frame)`), §3.1-b, §12 결정 9번(`회신은 ingest.handle() 반환값`), §4.2 표(`I/O → DB \| I/O 스레드가 직접 ingest.handle() 호출`), Frame 구조 명세서 §5.1(2)(`ingest.handle()의 반환값이 된다`), `contracts/siap_iface.py:48`(`FrameBuilder` 독스트링) 전부가 F-154 이전 계약을 그대로 서술함을 확인. 실제 `siap/link.py::_dispatch()`/`_default_reply()`/`backend/ingest.py::handle(frame, conn) -> None` 과 반대다 |
| 2026-08-10 | 수정완료 | 다섯 지점 전부 F-154 실제 구현에 맞춰 재작성 — 아키텍처 §3.1 다이어그램·`handle()` 의사코드(`-> None`, DB 반영 전용)·`_default_reply()` 의사코드 신설·§3.1-a 자기대기 문구·§3.1-b `_io_loop`/`_dispatch()`·§4.2 표·§12 결정 9번(F-154·당시 시점 함께 표기)을 갱신. Frame 구조 명세서 §5.1(2) 헤더를 `_default_reply()` 반환값으로 정정하고 F-154 배경을 서술. `contracts/siap_iface.py`의 `FrameBuilder` 독스트링(2)항과 F-040 주석을 같은 근거로 갱신 — `contracts/`이지만 `Protocol`의 메서드 시그니처·`Frame` 구조는 전혀 바꾸지 않은 주석 정정이라 §5 계약 변경 절차(골든벡터 재생성 등) 대상은 아니라고 판단했다(구조 변경 없음, 사용자가 이미 F-154·F-163 처리를 승인) |
| 2026-08-10 | 확산 반영 | 재작성 중 §3.1 `handle()` 의사코드에서 `ems.on_node_property` 등 3종 호출을 실수로 누락해 `services_verify.py`의 F-079 회귀 검사(1건)가 즉시 깨졌다 — `handle()`에 8.1.3.1~3 세 분기를 복원하며 "회신 RSC는 아직 SUCCESS로 하드코딩돼 있고 ems 판정을 반영하는 배치는 단계 6에서 다시 본다"는 미해결 지점을 주석으로 남겼다(새 버그를 감추지 않고 명시). Frame 구조 명세서 분량 증가(11,000→13,043자)로 `개발_착수_지시서.md`의 분류 표기 인용도 갱신(F-090류 즉시 드리프트) |
| 2026-08-10 | 회귀테스트 | 문서·주석 정정이라 별도 자동 회귀는 없다 — 대신 코드 자체가 바뀌지 않았음을 `python contracts/test_contract.py` **62/62** · `pytest siap/tests/ backend/tests/` **251/251**(불변)로 확인했고, 문서 갱신 자체는 `python project_docs/services/services_verify.py` **42/42**(F-079 회귀 포함) · `python project_docs/dev/dev_verify.py` **76/76**으로 확인했다 |
