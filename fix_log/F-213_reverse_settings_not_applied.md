# F-213 · 노드발 설정 성공 회신 뒤 런타임 상태를 반영하지 않음

| 항목 | 값 |
|---|---|
| 심각도 | 오류 |
| 분류 | 코드버그 |
| 대상 | `project_code/siap/link.py:L257` · `project_code/siap/registry.py:L90` |
| 발견일 | 2026-08-12 |
| 상태 | 수정완료 |

## 근거

TTAK.KO-10.0943 §8.1.3.1 — `REQ_SET_NODE_PROPERTY`는 “현재 설정되어 있는 노드 속성값을 ... 변경”하기 위한 메시지이며 Request가 역방향으로 전송될 수 있다.

TTAK.KO-10.0943 §8.1.3.3 — `REQ_SET_NODE_DEVICE_PROPERTY_ALL`은 “현재 설정되어 있는 노드 속성 및 ... 전체 디바이스의 속성값을 ... 변경”하기 위한 메시지이며 역방향 전송이 가능하다.

TTAK.KO-10.0943 §8.1.3.4 — `REQ_SET_MSG_CONTROL_PROFILE`은 “현재 설정되어 있는 프로파일 속성값 ... 을 ... 변경”하기 위한 메시지이며 역방향 전송이 가능하다.

## 현상

`_default_reply()`는 노드발 세 요청에 모두 `RSC.SUCCESS`를 만든다. 그러나 `_apply_registry_effects()`는 `REQ_SET_NODE_PROPERTY`를 처리하지 않고, `REQ_SET_NODE_DEVICE_PROPERTY_ALL`에서는 디바이스 목록만 교체하며 `frame.node_property`를 버린다. `REQ_SET_MSG_FLOW_CONTROL_PROFILE`도 처리하지 않아 `SiapNodeLink._profile`과 이미 생성된 `PendingTable`의 프로파일이 그대로다. `NodeRegistry.update_node()`는 구현되어 있지만 호출되지 않는다.

## 영향

상대 노드는 설정이 적용됐다고 믿지만 게이트웨이의 조회 상태와 재전송·대기 정책은 이전 값으로 남는다. 같은 연결에서 양 끝의 노드 속성·흐름제어 프로파일이 갈린다. 표준의 역방향 설정 절차와 구현이 불일치한다.

## 재현

저장소 루트에서 실행한다.

```python
import sys
sys.path.insert(0, 'project_code')
from contracts.frame import Frame, Header, MsgControlProfile, MsgKind, NodeProperty, Status
from siap.link import SiapNodeLink
h=Header(0x12,0,0,7,0,1,3)
old=NodeProperty(1,1,3,Status.NORMAL,0)
new=NodeProperty(9,1,3,Status.ABNORMAL,5)
link=SiapNodeLink(); link._registry.register(old,())
for req in (
    Frame(h,MsgKind.REQ_SET_NODE_PROPERTY,node_property=new),
    Frame(h,MsgKind.REQ_SET_NODE_DEVICE_PROPERTY_ALL,node_property=new),
    Frame(h,MsgKind.REQ_SET_MSG_FLOW_CONTROL_PROFILE,
          profile=MsgControlProfile(9,4,9,9))):
    res=link._default_reply(req); link._apply_registry_effects(req,res)
    print(req.kind.name,res.rsc.name,link._registry.registry()[3],link._profile)
```

세 줄 모두 `SUCCESS`지만 노드는 계속 `sw_version=1, status=NORMAL, num_devices=0`, 프로파일은 계속 `recv_timeout=2, num_retry=2, ...=60`으로 출력된다.

## 제안

SUCCESS 응답을 확정한 한 경로에서 메시지별 설정 상태를 원자적으로 반영한다. 프로파일 변경은 `SiapNodeLink`와 `PendingTable`이 서로 다른 프로파일을 갖지 않도록 단일 갱신 지점을 둔다.

---

## Claude 처리 기록

| 일시 | 상태 | 내용 |
|---|---|---|
| 2026-08-13 | 확인 | 등록 노드에 역방향 설정 요청 3종을 넣어 `_default_reply()`와 `_apply_registry_effects()`를 연속 호출했다. 세 응답은 모두 SUCCESS였으나 노드는 `sw_version=1/status=NORMAL/num_devices=0`, 링크와 PendingTable 프로파일은 기본값으로 유지돼 미반영을 재현했다. |
| 2026-08-13 | 수정완료 | SUCCESS가 확정된 단일 `_apply_registry_effects()` 경로에서 `REQ_SET_NODE_PROPERTY`는 노드 속성을, `REQ_SET_NODE_DEVICE_PROPERTY_ALL`은 노드와 전체 디바이스를 registry 한 잠금으로, `REQ_SET_MSG_FLOW_CONTROL_PROFILE`은 link와 PendingTable 프로파일을 같은 갱신점에서 반영하도록 수정했다. `send()`의 프로파일 읽기도 잠금으로 직렬화하고 새 pending deadline 적용 테스트를 추가했다. 상태 반영 분기 제거 재주입에서 전용 테스트가 실패했으며 복원 후 관련 94/94, SIAP 전체 108/108을 통과했다. |
