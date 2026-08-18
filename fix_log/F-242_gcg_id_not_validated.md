# F-242 · 다른 GCG ID의 연결 요청을 SUCCESS로 승인한다

| 항목 | 값 |
|---|---|
| 심각도 | 오류 |
| 분류 | 코드버그 |
| 대상 | 제출본 `project_code/siap/codec.py:537` · `project_code/siap/link.py:114,319` |
| 발견일 | 2026-08-18 |
| 상태 | 신규 |

## 근거

TTAK.KO-10.0943 7.3.1, 표 7-10 — 요청이 정상 처리되지 않은 경우 상황에 맞는
오류 상태를 응답해야 하며 `INVALID_GCG_ID(0x02)`는 "온실통합제어기 식별자 오류"다.

## 현상

`decode_frame()`은 Version, Message Type/Payload Length, Transmission Type, Node ID를
검사하지만 수신 헤더의 GCG ID가 `SiapNodeLink._gcg_id`와 같은지는 검사하지 않는다.
링크도 디코더에 `node_known`만 전달한다. `_default_reply()`는 위반이 없는
`REQ_SET_CONNECTION`을 무조건 SUCCESS로 회신한다.

로컬 GCG ID가 1인 링크에 `gcg_id=2, node_id=3` 연결 요청을 넣자 위반은 빈 튜플,
응답 RSC는 SUCCESS였다. 더구나 응답 헤더는 요청에서 복사한 GCG ID 2이고,
응답 `NODE_PROPERTY`에는 로컬 GCG ID 1이 들어 한 프레임 안에서도 식별자가 충돌했다.

## 영향

다른 제어기를 향한 요청을 잘못 수락하며, 적합성 화면과 프레임 로그도 이를 정상으로
판정한다. 표 7-10에 선언한 `INVALID_GCG_ID`를 게이트웨이 수신 경로에서 만들 수 없다.

## 재현

```python
from contracts.frame import Header
from siap import codec
from siap.link import SiapNodeLink

h = Header(0x12, 0x0000, 0, 1, 0, 2, 3)
f = codec.decode_frame(codec.encode_header(h), node_known=lambda _: True)
r = SiapNodeLink(gcg_id=1)._default_reply(f)
print(f.violations, r.rsc, r.header.gcg_id, r.node_property.gcg_id)
# () RSC.SUCCESS 2 1
```

## 제안

디코더 또는 링크 수신 경계에 기대 GCG ID 검사를 추가하고, 불일치 Request에는
`INVALID_GCG_ID` Response를 생성한다. 연결 요청을 포함한 정상·불일치 회귀 벡터를 둔다.

---

## 작업자 처리 기록

| 일시 | 상태 | 내용 |
|---|---|---|
|  |  |  |
