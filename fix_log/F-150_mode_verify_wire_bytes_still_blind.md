# F-150 · F-147 수정 후에도 실제 송신 바이트 변조를 통과

| 항목 | 값 |
|---|---|
| 심각도 | 오류 |
| 분류 | 코드버그 |
| 대상 | `tools/mode_verify.py:175-191` · `tools/mode_verify.py:209-276` |
| 발견일 | 2026-08-09 |
| 상태 | 수정완료 |

## 근거

개발 착수 지시서 §3.6 신설 검증기 ③ — “주입 벡터 `X01`~`X08` 이 골든과 바이트 동일”. 시연 시나리오 §3.1 — “`sim/inject.py` 가 골든 벡터의 hex 를 그대로 링크에 흘려보낸다” 및 “영상 속 hex 와 제출 `golden.jsonl` 의 hex 가 같아야 한다”.

## 현상

F-147 수정으로 실제 simulate 링크를 거치는 검사가 추가됐지만, 그 검사는 S4-b 5종의 `Frame.violations` 코드만 대조한다. 실제 소켓에 전달된 바이트는 캡처해 골든과 비교하지 않으며 X02·X04·X08은 live 경로에서 검사하지 않는다. 별도의 바이트 검사는 여전히 `inject.vector_bytes()`를 같은 골든 파일과 비교할 뿐 실제 `inject()` 반환값·송신값을 보지 않는다.

런타임에서 `inject.inject()`가 모든 벡터의 마지막 바이트를 XOR 1 하도록 바꾼 뒤 `mode_verify.main()`을 실행했다. 실제 X01은 기대 `99200C003200000000100003` 대신 `99200C003200000000100002`가 전달되지만, 마지막 바이트가 S4-b 판정 필드가 아니어서 새 live 검사까지 모두 통과하고 검증기는 `9/9 통과`, exit 0을 냈다.

## 영향

F-147의 수정완료 주장이 성립하지 않는다. 영상·제출 벡터의 정확한 hex가 갈리는 구현을 단계 4 출구와 전체 `run_all.py`가 녹색으로 통과시킨다.

## 재현

```python
from sim import inject
from tools import mode_verify

inject.inject = lambda vid, sock: (
    lambda data: (sock.sendall(data), data)[1]
)(inject.vector_bytes(vid)[:-1] + bytes([inject.vector_bytes(vid)[-1] ^ 1]))

assert mode_verify.main() == 0  # 실제 결과: 9/9 통과
```

---

## Claude 처리 기록

| 일시 | 상태 | 내용 |
|---|---|---|
| 2026-08-09 | 확인 | 재현 스니펫대로 `inject.inject`를 마지막 바이트 XOR 변조로 치환해 `mode_verify.main()`을 재실행 — 지적대로 9/9·exit 0 으로 통과하는 것을 확인. F-147 이 추가한 live 검사는 `Frame.violations` 코드만 보고, X02·X04·X08 은 그 검사 대상에도 없다는 것을 소스에서 확인 |
| 2026-08-09 | 수정완료 | `tools/mode_verify.py`에 `check_injection_actual_wire_bytes()` 추가 — X01~X08 전량에 대해 `VirtualNodeServer`/디코더를 거치지 않는 맨 TCP 소켓을 만들고, `inject.inject()`가 실제로 그 소켓에 쓴 바이트를 서버 쪽에서 직접 캡처해 golden.jsonl 원본 hex와 정확히 일치하는지 확인(반환값·실제 수신값 둘 다 대조). `main()`에 등록. **결함 주입 검증**: 재현 스니펫과 동일하게 `inject.inject`를 마지막 바이트 XOR 변조로 런타임 치환 → 새 검사가 정확히 실패(`X01: inject() 반환=...002 실제 수신=...002 기대=...003`)로 잡는 것을 확인, 원상태 재실행 시 10/10·exit 0 재확인 |

