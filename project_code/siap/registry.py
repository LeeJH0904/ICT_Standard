"""
siap/registry.py — 노드 세션 (in-memory). TTAK.KO-10.0943 8.1.1 절차의 결과.

`SiapLink.registry()`/`devices()`(contracts/siap_iface.py)가 반환하는 상태의
정본이다. `link.py`가 `REQ_SET_CONNECTION` 처리를 마친 뒤 `register()`를 불러
갱신한다.

`backend/`의 `device_install*` 테이블(1369-P1 대응, 영구 저장)과는 별개다 —
이건 "지금 이 프로세스가 이번 실행에서 본 노드"만 아는 프로토콜 계층 전용
런타임 세션이다. `siap/`는 `backend/`를 import하지 않는다(CLAUDE.md §2.2) —
이 파일은 그 규칙 안에서 성립하는 가장 얇은 조회 테이블이다.
"""
from __future__ import annotations

import threading

try:                    # F-025 — 패키지로 import될 때
    from contracts.frame import DeviceMainInfo, DeviceProperty, NodeProperty
except ImportError:     # 스크립트로 직접 실행되거나 project_code 가 sys.path 밖일 때
    import pathlib
    import sys
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
    from contracts.frame import DeviceMainInfo, DeviceProperty, NodeProperty


class NodeRegistry:
    """스레드 안전한 in-memory 노드 세션 테이블.

    쓰기 주체는 SIAP I/O 스레드(link.py) 하나뿐이다 — 아키텍처 설계서 §4.4의
    "쓰기 소유권은 테이블 단위" 원칙을 이 좁은 테이블에도 그대로 적용한다.
    다른 스레드(API)는 registry()/devices() 로 조회만 한다."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._nodes: dict[int, NodeProperty] = {}
        self._devices: dict[int, tuple[DeviceMainInfo, ...]] = {}
        self._device_properties: dict[int, tuple[DeviceProperty, ...]] = {}

    def is_known(self, node_id: int) -> bool:
        """codec.decode_frame() 의 node_known 콜백으로 그대로 주입된다
        (위반 2 판정, F-060 — codec 은 registry 를 직접 import 하지 않고
        link.py 가 이 메서드를 콜백으로 넘긴다)."""
        with self._lock:
            return node_id in self._nodes

    def register(self, node: NodeProperty,
                 devices: tuple[DeviceProperty, ...] = ()) -> None:
        """REQ_SET_CONNECTION 처리 완료 시 호출한다(8.1.1). DEVICE_PROPERTY×N 에서
        DEVICE_MAIN_INFO 만 추려 devices() 조회용으로도 보관한다."""
        with self._lock:
            self._nodes[node.node_id] = node
            self._device_properties[node.node_id] = tuple(devices)
            self._devices[node.node_id] = tuple(dp.main for dp in devices)

    def unregister(self, node_id: int) -> None:
        """NOTI_DISCONNECT(8.2.1.3) 수신 시 호출한다."""
        with self._lock:
            self._nodes.pop(node_id, None)
            self._devices.pop(node_id, None)
            self._device_properties.pop(node_id, None)

    def merge_device_properties(self, node_id: int, devices: tuple[DeviceProperty, ...],
                                 *, replace: bool) -> None:
        """F-198 — `REQ_SET_NODE_DEVICE_PROPERTY_ALL`(8.1.3.3, 노드→GCG)·
        `REQ_SET_DEVICE_PROPERTY`(8.1.3.2, 노드→GCG) 처리 완료 시 호출한다.
        `register()`는 `REQ_SET_CONNECTION`(8.1.1) 성공 시에만 노드 자체를
        등록할 뿐 — 그 프레임은 페이로드가 없어(`LAYOUT[REQ_SET_CONNECTION]
        == (0, 0)`) 디바이스 구성을 실을 수 없다. 디바이스 구성은 이 두
        메시지로 별도 갱신된다.

        `replace=True`(`..._ALL`) — "ALL"이 뜻하는 대로 전체를 교체한다.
        `replace=False`(`REQ_SET_DEVICE_PROPERTY`) — `device_id` 기준으로
        기존 목록에 병합한다(표에 없는 기존 디바이스는 유지). 미등록 노드는
        조용히 무시한다 — `register()`와 같은 원칙, 그 판정은
        `codec.decode_frame()`의 `INVALID_NODE_ID` 위반이 이미 내렸어야
        한다(CLAUDE.md §3.4)."""
        with self._lock:
            if node_id not in self._nodes:
                return
            if replace:
                merged = {dp.main.device_id: dp for dp in devices}
            else:
                merged = {dp.main.device_id: dp
                          for dp in self._device_properties.get(node_id, ())}
                merged.update({dp.main.device_id: dp for dp in devices})
            ordered = tuple(merged.values())
            self._device_properties[node_id] = ordered
            self._devices[node_id] = tuple(dp.main for dp in ordered)

    def update_node(self, node: NodeProperty) -> None:
        """REQ_SET_NODE_PROPERTY(8.1.3.1 역방향) 등으로 등록된 노드의 속성만
        갱신한다. 미등록 노드는 조용히 무시한다 — 그 판정(INVALID_NODE_ID)은
        codec.decode_frame() 이 이미 내렸어야 한다(표준 해석은 프로토콜
        계층에만, CLAUDE.md §3.4)."""
        with self._lock:
            if node.node_id in self._nodes:
                self._nodes[node.node_id] = node

    def registry(self) -> dict[int, NodeProperty]:
        """SiapLink.registry() 구현. 내부 dict 의 사본을 돌려준다 — 호출자가
        고쳐도 세션 상태가 깨지지 않는다."""
        with self._lock:
            return dict(self._nodes)

    def devices(self, node_id: int) -> tuple[DeviceMainInfo, ...]:
        """SiapLink.devices() 구현."""
        with self._lock:
            return self._devices.get(node_id, ())

    def device_properties(self, node_id: int) -> tuple[DeviceProperty, ...]:
        """DEVICE_PROPERTY 전체(Period·Transfer Mode 포함)가 필요한 호출자용 —
        SiapLink Protocol 밖의 registry.py 전용 확장이다(siap/ 내부에서만 쓴다,
        control.py 가 재전송 프로파일을 고를 때 참조)."""
        with self._lock:
            return self._device_properties.get(node_id, ())

    def __len__(self) -> int:
        with self._lock:
            return len(self._nodes)
