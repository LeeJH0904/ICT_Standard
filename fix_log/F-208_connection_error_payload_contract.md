# F-208 · 연결 실패 응답 설명이 표준·실제 고정부와 반대

| 항목 | 값 |
|---|---|
| 심각도 | 오류 |
| 분류 | 문서불일치 |
| 대상 | `project_code/contracts/siap_iface.py:L111` · `project_code/siap/build.py:L158` · `project_code/contracts/fake_link.py:L171` |
| 발견일 | 2026-08-12 |
| 상태 | 신규 |

## 근거

TTAK.KO-10.0943 §8.1.1은 연결 응답 페이로드에 노드 속성과 N개 디바이스 속성을 포함하고 요청 상태에 따라 RSC를 갱신한다고 정한다. `LAYOUT[RES_SET_CONNECTION]`도 고정부를 `RSC_BYTES + NP_BYTES`인 9byte로 정한다.

## 현상

`FrameBuilder.res_set_connection()` docstring은 실패 RSC이면 node·devices를 생략하고 RSC만 싣는다고 적는다. 실제 `FrameBuilderImpl`은 오류에도 자리표시 `NodeProperty`를 만들어 9byte 고정부를 싣고 `FakeFrameBuilder`도 같다. 표준 본문과 두 구현은 일치하고 Protocol 설명만 반대다.

## 영향

Protocol 설명대로 새 구현을 만들면 `LAYOUT`·코덱과 어긋나는 1byte 오류 응답을 만들게 된다. 개발용 대역과 실제 링크 구현이 갈릴 근거가 된다.

## 재현

동일한 연결 요청에 `RSC.INVALID_NODE_ID`를 넣었다.

```text
FakeFrameBuilder -> payload_len=9, node_property 있음, devices=0
FrameBuilderImpl -> payload_len=9, node_property 있음, devices=0
Protocol 문서   -> RSC만 적재, node·devices 생략
```

## 제안

Protocol 설명을 표준과 고정 `LAYOUT`에 맞추고 성공·실패 모두 Fake와 실제 빌더의 wire payload 동등성을 시험한다.

---

## Claude 처리 기록

| 일시 | 상태 | 내용 |
|---|---|---|

