# F-151 · Version-only 재동기가 다음 정상 프레임을 삭제

| 항목 | 값 |
|---|---|
| 심각도 | 오류 |
| 분류 | 코드버그 |
| 대상 | `project_code/siap/codec.py:692-745` |
| 발견일 | 2026-08-09 |
| 상태 | 수정완료 |

## 근거

CLAUDE.md §3.5 프레임 재동기 결정 및 F-140 — 위반 프레임 뒤에도 이미 수신한 정상 트래픽을 유실하지 않고 새 프레임 시작점을 찾아야 한다. F-146은 연속 위반 벡터를 분류하기 위해 Python 게이트웨이의 후보 조건을 Version 일치 하나로 완화했다.

## 현상

Version 위반 헤더가 `Payload Length=1`과 payload `0x12`를 가진 뒤 정상 `NOTI_KEEP_ALIVE`가 바로 이어지는 스트림을 넣었다. 첫 위반을 반환한 디코더는 헤더 12바이트만 삭제하고 재동기에 들어간다. 남은 payload의 `0x12`를 Version-only 게이트가 새 헤더 시작으로 승인하면서, 그 1바이트와 다음 정상 헤더의 앞 11바이트가 가짜 헤더로 해석된다. 가짜 `INVALID_FORMAT`을 반환한 뒤 12바이트를 삭제해 정상 프레임은 사라진다.

실측 결과는 `[(90, INVALID_VERSION), (3072, INVALID_FORMAT)]`, 내부 버퍼 `03`, 정상 msg_id 91 미도달이다. 같은 입력에서 런타임으로 F-146 이전 4조건 게이트를 복원하면 `[(90, INVALID_VERSION), (91, 정상)]`이 되어 정상 프레임이 보존된다. 즉 F-146 수정이 만든 회귀다.

## 영향

공격적이거나 손상된 프레임의 payload가 우연히 `0x12`로 끝나기만 해도 바로 뒤 정상 프레임 하나를 잃는다. F-140이 고친 “위반 헤더가 뒤의 정상 프레임을 삭제”하는 결함이 다른 경로로 재발했다.

## 재현

```python
from sim import _wire as w
from siap.codec import Decoder

bad = w.encode_header(w.WireHeader(
    0x99, w.MT_NOTI_KEEP_ALIVE, w.TRANS_UNICAST, 90, 1, 1, 3
)) + b\x12
good = w.build_noti_keep_alive(91, 1, 3)

frames = list(Decoder(node_known=lambda _: True).feed(bad + good))
assert [f.header.msg_id for f in frames] == [90, 3072]  # 91 유실
```

---

## Claude 처리 기록

| 일시 | 상태 | 내용 |
|---|---|---|
| 2026-08-09 | 확인 | 재현 스니펫(Version 위반 헤더 + payload 1byte(`0x12`) + 정상 프레임)을 그대로 실행 — 지적대로 `msg_id=[(90, INVALID_VERSION), (3072, INVALID_FORMAT)]`이 나와 정상 프레임(msg_id=91)이 사라지는 것을 확인. F-146 의 Version 단독 게이트가 위반 프레임의 잔여 payload 바이트를 새 헤더로 오인하는 근본 원인도 확인 |
| 2026-08-09 | 수정완료 | `siap/codec.py::Decoder._resync_check()`에 **등록된 Node ID** 조건을 추가(F-151) — Version 이 맞아도 `node_known(node_id)`가 거짓이면 원칙적으로 거부한다. 다만 Node ID 미등록 자체가 위반 목표인 X02 류를 다시 삼키지 않도록, Node ID 가 미등록이어도 resolve_kind·Transmission Type·element_count 가 전부 자기충족적으로 유효하면 후보로 인정하는 예외를 뒀다(등록 노드 집합이 20bit 공간보다 훨씬 작아 오탐률이 1/256→4조건 수준(약 2⁻²²)으로 낮아진다). `CLAUDE.md` §3.5 결정 표와 `펌웨어_설계서.md` §5.7 갱신. 회귀 테스트 2건 추가(`siap/tests/test_codec.py`): `test_decoder_resync_does_not_mistake_stray_version_byte_for_new_header_f151`(재현 시나리오 그대로), `test_decoder_resync_still_classifies_unregistered_node_after_violation_f151`(X02가 다른 위반 직후 연쇄 주입돼도 유실되지 않음). **결함 주입 검증**: `_resync_check()`를 Version 단독 버전으로 되돌리자 새 테스트가 정확히 재현 증상(`msg_id=[90, 3072]`, 91 유실)으로 실패하는 것을 확인한 뒤 복원, `siap/tests/` 101/101 재통과. **live 통합 검증**: 실제 simulate 링크에서 S4-b 5종 + X02·X04·X08 을 한 세션에 연쇄 주입(몽타주가 같은 스트림에 이어붙는 최악 케이스 가정) — 8/8 전부 목표 판정과 일치, 유실 없음(수정 전에는 X02 가 이 연쇄 조건에서 유실됨을 별도로 확인) |

