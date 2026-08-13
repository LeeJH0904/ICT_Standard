# F-068 · B03의 Num. of Devices와 DEVICE_PROPERTY 개수가 다름

| 항목 | 값 |
|---|---|
| 심각도 | 오류 |
| 분류 | 코드버그 |
| 대상 | `project_docs/contracts/vectors/golden_layout.py:273-287`, `golden.jsonl` B03 |
| 발견일 | 2026-08-05 |
| 상태 | 수정완료 |

## 근거

0943 표 7-13 — `Num. of Devices`는 "노드에 연결된 디바이스 수"다.

0943 7.3.3.4 — "노드 속성과 해당 노드에 연결된 N개 디바이스의 속성 정보"를 포함한다. 표 7-16은 `DEVICE_PROPERTY`를 `N*240`bit로 정의한다.

## 현상

B03은 지원 상한 N=16의 `RES_SET_CONNECTION`을 표현하며, 실제로 `DEVICE_PROPERTY`와 서로 다른 Device ID를 16개 담고 `n=16`, Payload Length=489, 총 501byte로 기록한다.

하지만 고정부에는 기존 `NP_3DEV`를 재사용해 `NODE_PROPERTY.Num. of Devices=3`을 넣었다. 즉 같은 페이로드가 디바이스 수를 3과 16으로 동시에 주장한다. 현재 28개 골든 검사는 가변부 길이에서 `n=16`만 산출하고 NODE_PROPERTY의 수와 대조하지 않아 통과한다.

## 영향

세 구현이 이 벡터를 정답으로 사용하면 연결 응답에서 노드의 장치 수와 실제 장치 속성 목록이 불일치해도 정상으로 받아들일 수 있다. B03이 펌웨어 수신 버퍼와 Timeout의 기준 벡터라는 F-064 수정 목적도 약화된다.

## 재현

```text
B03.n                                      = 16
B03 fields의 Device ID 개수                = 16 (1..16)
B03 fields의 Num. of Devices               = 3
golden_verify.py                            = 28/28, exit 0
```

## 제안

B03 전용 `NODE_PROPERTY`를 N=16으로 만들고, 검증기에 `COMBINED_PROPERTY`의 `Num. of Devices == DEVICE_PROPERTY 개수` 불변식을 추가한다.

---

## Claude 처리 기록

| 일시 | 상태 | 내용 |
|---|---|---|
| 2026-08-05 | 확인 | 재현 성공. B03 은 `Num. of Devices=3` 인데 `DEVICE_PROPERTY` 를 16건 담고 `n=16` 이다. **같은 페이로드가 디바이스 수를 두 값으로 주장한다.** 원인은 `NP_3DEV` 상수를 생각 없이 재사용한 것 |
| 2026-08-05 | 확인 | **B03 만이 아니었다.** 전 벡터를 훑으니 `N22`(3 vs 1) · `N27`(3 vs 1) · `N30`(3 vs 1) · `B03`(3 vs 16) 네 건이 어긋났고, `B01` 도 디바이스 0건을 보내면서 `Num. of Devices=3` 이었다. 지적은 B03 만 짚었으나 원인이 같아 전부 고쳤다 |
| 2026-08-05 | 수정완료 | `NP(ndev)` 헬퍼를 만들어 벡터마다 개수를 명시하도록 바꿨다 — N22·N27·N30 은 1, B01 은 0, B03 은 16. **B01 은 오히려 경계값으로서 더 나아졌다**: '디바이스 0대인 노드의 연결 응답' 이 되어 N=0 허용의 의미가 자기모순 없이 성립한다 |
| 2026-08-05 | 수정완료 | **`siap/spec_verify.py` 의 예시도 같은 결함이 있었다** — `RES_SET_CONNECTION_1dev` 가 `DEVICE_PROPERTY` 1건에 `Num. of Devices=3` 이었다. 1 로 정정하고 `spec_examples.json` 을 재생성했다 |
| 2026-08-05 | 수정완료 | 불변식을 **양쪽에** 넣었다. 생성기 자체 점검과 `golden_verify.py` 검사 — 가변 요소가 `DEVICE_PROPERTY` 인 메시지(표 7-16 COMBINED_PROPERTY)에서 `Num. of Devices == N` 이어야 한다. 5건이 대상이다 |
| 2026-08-05 | 수정완료 | **독립 인코더 교차 검증이 이 수정을 잡아냈다.** 골든만 고치고 `spec_verify` 를 안 고쳤을 때 N27 과 `RES_SET_CONNECTION_1dev` 의 페이로드 바이트가 어긋나 즉시 FAIL 했다 — 두 번 타이핑한 것을 대조하는 장치가 실제로 작동한다. B03 의 ndev 를 3 으로 되돌린 변형에서도 검출 확인(28/29, exit 1) |
