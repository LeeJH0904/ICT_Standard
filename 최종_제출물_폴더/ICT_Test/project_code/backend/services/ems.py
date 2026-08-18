"""
backend/services/ems.py — TTAK.KO-10.0937 6.1 EMS(장치관리서비스).

"클라우드용 센서노드·구동기노드·복합노드·통합제어기·게이트웨이 등의
설치·변경·삭제 및 자동화된 연결을 지원하고, 장치의 상태 및 운영 정보를
수집하는 서비스"(0937 6.1).

담당 조항: 6.1 전부 · A.1-1 · A.2-1 (0937_요구사항_대조표.md §4.1)
진입점: list_nodes · get_node · list_node_devices · set_device_property

노드발 프레임(`REQ_SET_CONNECTION` 등)의 실제 반영은 `backend/ingest.py`가
한다(단계 5부터, F-079) — 이 모듈은 그 로직을 재구현하지 않는다. 여기서는
API가 필요로 하는 조회와, 게이트웨이발 `REQ_SET_DEVICE_PROPERTY` 송신
(`PATCH /device-property`)만 새로 둔다.
"""
from __future__ import annotations

import sqlite3

try:                    # F-025 와 같은 원칙
    from backend import repository
except ImportError:
    import pathlib
    import sys
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent.parent))
    from backend import repository

try:
    from contracts.frame import DeviceMainInfo, DeviceProperty, RSC, Status, TransferMode, ValueType
    from contracts.siap_iface import FrameBuilder, SiapLink
except ImportError:
    import pathlib
    import sys
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent.parent))
    from contracts.frame import DeviceMainInfo, DeviceProperty, RSC, Status, TransferMode, ValueType
    from contracts.siap_iface import FrameBuilder, SiapLink


class DevicePropertyError(Exception):
    """`PATCH /device-property` 거부 — 대상 없음(404) 또는 Value Type
    불일치·응답 없음(422/504). `api.py`가 `status`로 구분해 옮긴다."""

    def __init__(self, message: str, *, status: int, siap_rsc: str | None = None) -> None:
        super().__init__(message)
        self.status = status
        self.siap_rsc = siap_rsc


def list_nodes(conn: sqlite3.Connection, link: SiapLink) -> list[dict]:
    """`GET /api/v1/nodes` — 0943 8.1.1 연결 설정을 마친 노드. `status`는
    `SiapLink.registry()`(in-memory, 표 7-13)가 정본이다. `connected_at`·
    `last_seen_at`는 `NodeProperty`에 없는 필드라 `frame_log`에서 유도한다
    (API 명세서 §5)."""
    return [_node_dict(conn, node_id, prop) for node_id, prop in sorted(link.registry().items())]


def get_node(conn: sqlite3.Connection, link: SiapLink, node_id: int) -> dict | None:
    prop = link.registry().get(node_id)
    return None if prop is None else _node_dict(conn, node_id, prop)


def _node_dict(conn: sqlite3.Connection, node_id: int, prop) -> dict:
    return {
        "node_id": node_id,
        "gcg_id": prop.gcg_id,
        "sw_version": prop.sw_version,
        "status": prop.status.name,
        "device_count": prop.num_devices,
        "connected_at": repository.node_connected_at(conn, node_id),
        "last_seen_at": repository.node_last_seen_at(conn, node_id),
    }


def list_node_devices(conn: sqlite3.Connection, node_id: int):
    """`GET /api/v1/nodes/{id}/devices` — 표 7-15로 등록된 항목이 1369-P1
    7.2.2.5 장치설치정보로 저장된 결과다(API 명세서 §3)."""
    return repository.list_device_installs_by_node(conn, node_id)


def set_device_property(conn: sqlite3.Connection, link: SiapLink, builder: FrameBuilder, *,
                         selector: dict, property_patch: dict, user_id: str,
                         timeout: float | None = None) -> list:
    """`PATCH /api/v1/device-property` — 0937 6.4-2 · 부속서 A 1.3
    (0943 8.1.3.2 REQ_SET_DEVICE_PROPERTY 로 나간다).

    F-088·F-093 — 대상이 여럿이면(구역 일괄) **전량 사전 검증 후에만**
    송신한다. 검증에서 하나라도 걸리면 아무 프레임도 나가지 않는다 —
    부분 적용은 화면이 어느 장치까지 적용됐는지 되물을 수단이 없다."""
    installs = _resolve_selector(conn, selector)
    if not installs:
        raise DevicePropertyError("대상 장치를 찾을 수 없다", status=404)

    plans: list[tuple] = []   # (install, node_id, device_id, DeviceMainInfo)
    for install in installs:
        node_id, device_id = install.siap_node_id, install.siap_device_id
        if node_id is None or device_id is None:
            raise DevicePropertyError(
                f"install_id={install.id} 는 SIAP 연동 정보가 없다(siap_node_id/siap_device_id 없음)",
                status=422, siap_rsc="INVALID_DATA_TYPE",
            )
        dmi = _lookup_current(link, node_id, device_id)
        if dmi is None:
            raise DevicePropertyError(
                f"install_id={install.id} 의 현재 Value Type 을 확인할 수 없다"
                f"(node_id={node_id} 미접속 또는 device_id={device_id} 미등록)",
                status=422, siap_rsc="INVALID_DATA_TYPE",
            )
        _validate_value_type(install.id, dmi.value_type, property_patch)
        plans.append((install, node_id, device_id, dmi))

    # 노드 단위로 묶는다 — 0943 8.1.3.2 는 한 프레임에 그 노드의
    # DEVICE_PROPERTY×N 을 함께 싣는다.
    by_node: dict[int, list[tuple]] = {}
    for plan in plans:
        by_node.setdefault(plan[1], []).append(plan)

    updated_ids: list[str] = []
    for node_id, node_plans in by_node.items():
        props = [_build_device_property(install, dmi, property_patch)
                 for (install, _n, _d, dmi) in node_plans]
        frame = builder.set_device_property(node_id, props)
        resp = link.send(frame, timeout=timeout)
        if resp is None:
            raise DevicePropertyError(f"node_id={node_id} 가 응답 시간 안에 회신하지 않았다", status=504)
        if resp.rsc != RSC.SUCCESS:
            raise DevicePropertyError(
                f"node_id={node_id} 가 거부했다(RSC={resp.rsc.name})", status=422,
                siap_rsc=resp.rsc.name,
            )
        for (install, _n, _d, _dmi) in node_plans:
            repository.update_device_property(
                conn, install.id, property_patch=property_patch, user_id=user_id,
            )
            updated_ids.append(install.id)
    conn.commit()
    return [repository.get_device_install(conn, iid) for iid in updated_ids]


def _resolve_selector(conn: sqlite3.Connection, selector: dict) -> list:
    """F-093 — `install_id`(개별)과 `greenhouse_id`(구역, 온실 전체가
    기본 의미이며 `install_location`·`subtype`은 좁히는 선택 항목)는 배타다
    — `api.py`가 스키마 단계(`DevicePropertySelector` oneOf)에서 이미
    걸러 보낸다. 여기서는 어느 쪽이 왔는지만 본다."""
    if "install_id" in selector:
        install = repository.get_device_install(conn, selector["install_id"])
        return [install] if install is not None else []
    return repository.list_device_installs_by_selector(
        conn, greenhouse_id=selector.get("greenhouse_id"),
        install_location=selector.get("install_location"),
        subtype=selector.get("subtype"),
    )


def _lookup_current(link: SiapLink, node_id: int, device_id: int) -> DeviceMainInfo | None:
    for dmi in link.devices(node_id):
        if dmi.device_id == device_id:
            return dmi
    return None


def _validate_value_type(install_id: str, value_type: ValueType, patch: dict) -> None:
    """CLAUDE.md §3.5 — 표 7-15 USER DEPENDENT 5필드는 `DEVICE_MAIN_INFO.
    Value Type`을 따른다. `lower_value`/`upper_value`가 그 타입의 32bit
    범위(0943 표 7-14, F-044)를 벗어나면 422(INVALID_DATA_TYPE)."""
    for key in ("lower_value", "upper_value"):
        if key not in patch:
            continue
        v = patch[key]
        if value_type in (ValueType.INT, ValueType.UINT):
            if not float(v).is_integer():
                raise DevicePropertyError(
                    f"install_id={install_id} 의 Value Type 은 {value_type.name} 인데 {key}={v} 는 정수가 아니다",
                    status=422, siap_rsc="INVALID_DATA_TYPE",
                )
            v = int(v)
        if value_type is ValueType.UINT and not (0 <= v <= 2**32 - 1):
            raise DevicePropertyError(
                f"install_id={install_id} 의 Value Type 은 UINT 인데 {key}={v} 를 받았다",
                status=422, siap_rsc="INVALID_DATA_TYPE",
            )
        if value_type is ValueType.INT and not (-2**31 <= v <= 2**31 - 1):
            raise DevicePropertyError(
                f"install_id={install_id}: {key}={v} 가 INT 32bit 범위를 벗어난다",
                status=422, siap_rsc="INVALID_DATA_TYPE",
            )


def _build_device_property(install, dmi: DeviceMainInfo, patch: dict) -> DeviceProperty:
    """DEVICE_PROPERTY(표 7-15)는 필드 8개를 한 번에 싣는다 — PATCH가 그중
    일부만 바꿔도 나머지는 현재값을 그대로 채워 보낸다(부분 필드 전송
    수단이 0943에 없다). `lower_value`/`upper_value`는 패치 값 우선,
    없으면 `device_install_info`에 저장된 값(F-170), 그것도 없으면 0."""
    tm = patch.get("transfer_mode", install.transfer_mode)
    transfer_mode = TransferMode[tm] if tm else TransferMode.PERIODIC
    zero = 0 if dmi.value_type in (ValueType.INT, ValueType.UINT) else 0.0
    lower = patch.get("lower_value", install.lower_limit if install.lower_limit is not None else zero)
    upper = patch.get("upper_value", install.upper_limit if install.upper_limit is not None else zero)
    return DeviceProperty(
        main=dmi,
        transfer_mode=transfer_mode,
        period=patch.get("period_sec", install.period_sec if install.period_sec is not None else 0),
        lower_value=lower, upper_value=upper,
        lower_limit=zero, upper_limit=zero, precision=zero,
        status=Status.NORMAL,
    )
