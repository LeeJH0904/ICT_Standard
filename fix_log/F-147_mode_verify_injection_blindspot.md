# F-147 · mode 검증기가 실제 inject 송신 경로를 검사하지 않음

| 항목 | 값 |
|---|---|
| 심각도 | 오류 |
| 분류 | 코드버그 |
| 대상 | `tools/mode_verify.py:175-189` |
| 발견일 | 2026-08-09 |
| 상태 | 수정완료 |

## 근거

개발 착수 지시서 §1.4 — 신설 검증기는 함수가 존재한다는 데 그치지 않고 호출해서 반환값을 봐야 한다. §3.6 신설 검증기 ③ — 주입 벡터 X01~X08이 골든과 바이트 동일. 시연 시나리오 §3.1 — `sim/inject.py`가 골든 hex를 그대로 링크에 흘려보낸다.

## 현상

`check_injection_vectors_match_golden()`은 `inject.vector_bytes()`와 같은 `inject.GOLDEN_PATH`에서 다시 읽은 문자열을 비교한다. 실제 송신 함수 `inject.inject()`도, 제어 채널도, 수신 소켓도 호출하지 않는다. 같은 파일의 자기 비교이므로 actual wire path가 틀려도 8/8이다. 또한 F-145·F-146처럼 실제 디코더 결과가 깨져도 검사하지 않는다.

## 영향

단계 4의 가장 중요한 사용자 흐름이 붕괴한 현재 상태에서도 `python tools/mode_verify.py`가 8/8과 종료 코드 0을 낸다. 전체 `run_all.py`도 14/14로 거짓 통과한다.

## 재현

파일을 수정하지 않고 런타임에 실제 송신 함수만 아래처럼 치환했다.

```python
def corrupt_inject(vector_id, sock):
    data = bytearray(inject.vector_bytes(vector_id))
    data[-1] ^= 1
    sock.sendall(data)
    return bytes(data)

inject.inject = corrupt_inject
assert mode_verify.main() == 0
```

실측 출력:

```text
mode_verify: 8/8 통과, exit 0
X01 기대: 99200C003200000000100003
X01 실제: 99200C003200000000100002
wrong_bytes_delivered=True
```

---

## Claude 처리 기록

| 일시 | 상태 | 내용 |
|---|---|---|
| 2026-08-09 | 확인 | 재현 스니펫대로 `inject.inject`를 런타임에 변조해 `mode_verify.main()`을 호출 — 지적대로 8/8·exit 0 으로 통과하는 것을 확인. `check_injection_vectors_match_golden()`이 `inject.vector_bytes()`와 golden.jsonl 을 다시 읽은 문자열만 비교할 뿐 `inject.inject()`·제어 채널·디코더 어느 것도 부르지 않음을 소스에서 확인 |
| 2026-08-09 | 수정완료 | `tools/mode_verify.py`에 `check_injection_wire_path_and_classification()` 추가 — `VirtualNodeServer`+`SiapNodeLink`를 실제 simulate 링크로 기동하고, `inject.py`가 실제로 접속하는 로컬 제어 채널(`INJECT <id>`)을 통해 S4-b 5종(X01·X03·X05·X06·X07)을 순서대로 주입한 뒤 `link.recv()`로 나온 `Frame.violations`가 목표 판정과 일치하는지 확인. 이 경로는 F-145(Node ID 불일치)·F-146(연속 주입 재동기 유실) 을 모두 실제로 통과해야만 성립한다. **결함 주입 검증(2건)**: (1) 마지막 바이트를 XOR 변조하는 `inject.inject` 로 런타임 치환 → 통과함을 확인 — 이 5종 벡터는 판정을 결정하는 필드가 마지막 바이트에 있지 않아(예: X06 마지막 바이트는 Value 의 LSB 이지 Value Type 이 아니다) 판정 자체가 바뀌지 않는 정상적 결과였다. 판정에 실제로 영향을 주는 자리(**Version 바이트**, offset 0)를 XOR 변조하도록 다시 실행하자 새 검사가 정확히 실패(`X03·X05·X06·X07: 프레임 자체가 도달하지 않음`)로 잡는 것을 확인 — 이것이 "실제 송신 경로를 검사한다"는 주장의 유효한 결함 주입이다. (2) 별도로 F-145 원인(Node ID 101)을 되돌려 실행하자 새 검사가 `X06/X07: 실제=['INVALID_NODE_ID']`로 정확히 8/9 실패·exit 1 을 내는 것을 확인, 두 경우 모두 복원 후 9/9·exit 0 재확인 |
