# F-135 · Message Identifier가 0을 건너뜀

| 항목 | 값 |
|---|---|
| 심각도 | 치명 |
| 분류 | 코드버그 |
| 대상 | `project_code/siap/build.py:39` · `project_code/firmware/core/node_state.c:50` · `CLAUDE.md` §3.5 |
| 발견일 | 2026-08-09 |
| 상태 | 수정완료 |

## 근거

TTAK.KO-10.0943 7.2.2 — “Message Identifier는 … '0'에서 '65535'까지 사용할 수 있다. 일련번호는 데이터 전송 시마다 +1을 하며 만료되면 0부터 다시 시작한다.”

## 현상

Python `MsgIdAllocator.next()`와 C `_next_msg_id()`는 모두 `0xFFFF` 다음 값을 `1`로 만든다. `CLAUDE.md` §3.5와 펌웨어 설계서 §9도 이를 “표준 미규정”이라고 적었지만 원문은 0 사용과 만료 후 0 재시작을 명시한다. 골든 B04·B05도 `0xFFFF→0x0000`을 정답으로 둔다.

## 영향

두 실제 발번기가 골든과 표준이 요구하는 순환을 구현하지 않는다. C·Python이 같은 잘못된 정책을 공유하므로 참조 구현의 표준 준수 주장이 무너진다.

## 재현

```text
alloc = MsgIdAllocator(); alloc._next = 0xFFFF
alloc.next() -> 0xFFFF
alloc.next() -> 0x0001   # 표준 기대 0x0000
```

## 제안

표준대로 0을 유효한 순번으로 사용하고, C·Python 발번기와 관련 정본·경계 테스트를 함께 맞춘다.

---

## Claude 처리 기록

| 일시 | 상태 | 내용 |
|---|---|---|
| 2026-08-09 | 확인 | 0943 원문(`표준 문서 md 파일/.../TTAK.KO-10.0943.md:523`)을 직접 대조 — "Message Identifier는 … '0'에서 '65535'까지 사용할 수 있다. 일련번호는 데이터 전송 시마다 +1을 하며 만료되면 0부터 다시 시작한다"를 확인. `node_state.c::_next_msg_id()`(1부터 시작, 0xFFFF 다음 1로 복귀)와 `build.py::MsgIdAllocator`(동일 정책)가 표준 문구와 직접 어긋남을 확인. `pending.kind==SIAP_KIND_NONE`이 이미 "비어 있음" 판정을 전담하고 있어 `msg_id==0`을 센티널로 참조하는 코드가 실제로 없음을 `node_state.c/.h` 전수 grep으로 확인 — "0은 미할당 표시로 예약"이 근거 없는 자체 결정이었음을 확인 |
| 2026-08-09 | 수정완료 | `node_state.c::_next_msg_id()`에서 0 건너뛰기 분기 제거(uint16_t 덧셈이 0xFFFF+1을 자연스럽게 0으로 감음), `siap_node_init()`의 초기값을 1→0으로 변경. `node_state.h`의 필드 주석 정정. `build.py::MsgIdAllocator`도 동일하게 초기값 0, `(v+1)&0xFFFF`로 수정. `CLAUDE.md` §3.5의 "노드의 Message Identifier 초기값" 행 삭제(표준이 실제로 규정하므로 "표준 미규정" 표에 있을 항목이 아니었다), 펌웨어 설계서 §9에서도 동일 행 삭제 + §6.4에 표준 문구 그대로 따른다는 설명 추가 + §0 요약 "아홉"→"여덟" 동기화. 회귀 테스트 추가: `test_node_state.c::test_msg_id_wraps_to_zero_not_one_F135`(C, 0xFFFF 발번 후 next_msg_id==0 확인) + 기존 "최초 Message Identifier" 검사를 1→0 기대로 정정, `test_build.py::test_msg_id_allocator_starts_at_0_and_wraps_to_0_f135`(Python, 동일 검증). 결함 주입(옛 정책으로 되돌림) 후 두 신규 테스트가 각각 정확히 실패함을 확인(C: 90/91, 새 테스트 재통과 후 91/91)하고 원복. 회귀: `test_bitpack` 41/41 · `test_siap_frame` 143/143 · `test_status_codes` 53/53 · `test_golden` 253/253 · `test_node_state` 91/91(+2) · `pytest siap/tests/` 재통과 |
