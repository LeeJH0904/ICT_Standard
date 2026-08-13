# F-146 · S4-b 연속 위반 주입에서 X03·X05 판정 유실

| 항목 | 값 |
|---|---|
| 심각도 | 치명 |
| 분류 | 코드버그 |
| 대상 | `project_code/siap/codec.py:677-730` · `project_code/siap/link.py:175-202` · `project_docs/demo/시연_시나리오.md:75-100` |
| 발견일 | 2026-08-09 |
| 상태 | 수정완료 |

## 근거

시연 시나리오 §3.1 — 위반 프레임 주입 5종을 순차 실행하며 순서는 X01→X03→X05→X06→X07이다. 0943 표 7-10은 X01·X03·X05의 기대 코드를 각각 `INVALID_VERSION`·`INVALID_FORMAT`·`INVALID_TRANSMISSION_TYPE`으로 정의한다.

표준 원문은 프레임 경계·재동기를 규정하지 않는다(F-069). 따라서 이 부분은 프로젝트가 스스로 정한 `T_gap=20ms`·4조건 재동기 규칙이 시연 계약을 만족해야 한다. 현재 구현은 그렇지 않다.

## 현상

`Decoder`는 위반 프레임을 반환한 뒤 `_resync=True`로 들어간다. 재동기 중에는 Version·메시지 종류·Transmission Type·`element_count`가 모두 유효한 헤더만 새 시작으로 인정하므로, 바로 뒤의 X03(의도적으로 잘못된 Payload Length)은 시작 후보가 될 수 없다. `on_gap()` 훅은 정의돼 있지만 `project_code/**/*.py` 실행 경로에서 호출이 0건이다.

실제 S4-b 순서를 한 TCP 세션에서 0.3초 간격으로 주입한 결과 msg_id 50(X01), 55(X06), 56(X07)만 관측됐고 52(X03), 54(X05)는 사라졌다. 관측된 X06·X07도 F-145 때문에 목표 판정이 아니다.

## 영향

영상 컷의 핵심인 5종 순차 실행에서 올바른 결과는 X01 한 종뿐이다. 제출 소스와 시연이 같은 기능을 구현해야 한다는 공고문 「진위·창작성」 조건과 기능 2 재현성이 무너진다.

## 재현

```text
simulate 링크를 1회 기동하고 정상 등록 큐를 비운 뒤 아래를 같은 연결로 실행한다.

for vid in ['X01', 'X03', 'X05', 'X06', 'X07']:
    inject.inject(vid, virtual_node_connection)
    time.sleep(0.3)

관측 msg_id: [50, 55, 56]
기대 msg_id: [50, 52, 54, 55, 56]
결과: 3/5만 Frame으로 도달, 기대 판정은 1/5
```

---

## Claude 처리 기록

| 일시 | 상태 | 내용 |
|---|---|---|
| 2026-08-09 | 확인 | `siap/codec.py::Decoder._resync_check()` 의 4조건(Version+resolve_kind+Transmission Type+element_count)을 추적: 위반 프레임 하나를 낸 직후에는 항상 재동기 모드로 들어가는데(F-140), 뒤이은 X03(Payload Length 위반)·X05(Transmission Type 위반) 은 각자의 위반 자체가 곧 4조건 중 하나를 깨므로 재동기 게이트에서 "노이즈"로 오인돼 1byte 씩 삼켜진다는 근본 원인을 소스에서 확인. `INVALID_FORMAT`·`INVALID_TRANSMISSION_TYPE` 처럼 헤더 해석 실패로 나타나는 위반은 재동기 모드 중에는 원리적으로 영원히 분류될 수 없는 구조였다 |
| 2026-08-09 | 수정완료 | `_resync_check()` 를 Version 일치만 보도록 완화(F-146) — resolve_kind·Transmission Type·element_count 판정은 `decode_frame()` 자신에게 맡긴다. 펌웨어(C) 는 UART 노이즈 복구가 목적이라 4조건을 그대로 유지 — §5.7 원문이 이미 "상대 구현이 다른 규칙을 쓸 수 있다"고 전제하므로 게이트웨이·펌웨어 간 규칙 분리는 모순이 아니다. `CLAUDE.md` §3.5 결정 표와 `펌웨어_설계서.md` §5.7 에 이 분리와 근거를 기록. 회귀 테스트 `test_decoder_classifies_sequential_injected_violations_f146`(`siap/tests/test_codec.py`) 추가 — 실제 golden X01·X03·X05 hex 를 이어 붙여 먹이고 msg_id 50·52·54 가 각각 `INVALID_VERSION`·`INVALID_FORMAT`·`INVALID_TRANSMISSION_TYPE`로 개별 분류되는지 확인. **결함 주입 검증**: `_resync_check()` 를 원래의 4조건 버전으로 되돌리자 새 테스트가 정확히 실측 재현과 같은 증상(`msg_id=[50]`만 도달, 52·54 소실)으로 실패하는 것을 확인한 뒤 복원, `siap/tests/` 99/99 재통과. **live 통합 검증**: 실제 simulate 링크에서 시연 시나리오 §3.1 순서(X01→X03→X05→X06→X07, 0.3초 간격) 그대로 주입 → `msg_id 50=INVALID_VERSION, 52=INVALID_FORMAT, 54=INVALID_TRANSMISSION_TYPE, 55=INVALID_DATA_TYPE, 56=INVALID_DATA_SUBTYPE` 5/5 전부 목표 판정과 일치 |
