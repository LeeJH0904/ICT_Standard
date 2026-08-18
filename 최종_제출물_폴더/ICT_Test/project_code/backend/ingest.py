"""
backend/ingest.py — ★ Frame 소비 지점. 프로토콜 계층과 서비스 계층의 유일한 경계.

`handle(frame)` 위쪽에 로직을 두지 않는다 — Frame이 어디서 왔는지(하드웨어냐
replay 냐 simulate 냐) 이 계층은 모른다. `contracts/frame.py`의 `Frame` 외에는
아무것도 참조하지 않고, `siap/` 내부 심볼(codec·link·registry)을 import 하지
않는다. 표준 해석(위반 판정)은 이미 프로토콜 계층이 끝냈다 — 여기는 그 결과를
테이블에 적을 뿐 다시 판정하지 않는다.

Frame → 테이블 매핑:
  REQ_SET_DEVICE_PROPERTY /
  REQ_SET_NODE_DEVICE_PROPERTY_ALL → device_install_info + device_install (기능 1)
                        노드가 디바이스 구성을 게이트웨이에 선언하는 통로는 이 두
                        메시지다(표 7-2·LAYOUT 상 DEVICE_PROPERTY×N). REQ_SET_CONNECTION
                        (8.1.1)의 LAYOUT은 (0,0)이라 디바이스 구성을 실을 수 없다.
  NOTI_DEVICE_VALUE  → env_state_data+env_measurement+env_measure (FMS, 센서)
                        또는 device_state_data+dsd_*+device_state (액추에이터)
  NOTI_ERROR         → alert                                      (FCS)
  NOTI_DISCONNECT    → alert                                      (FCS)
  모든 프레임         → frame_log (+ 위반 시 frame_violation)

위반 프레임은 `kind=None`이고 구조화된 필드(`device_main_infos`·`node_property`
등)가 전부 비어 있다(codec.decode_frame 보장). 따라서 위반 프레임은 `frame_log`+
`frame_violation`만 기록하고 비즈니스 테이블은 건드리지 않는다.

`handle(frame, conn)`은 DB 반영만 하고 회신 Frame을 만들지 않는다(반환값 없음) —
`siap/link.py`의 `on_frame` 훅은 부수효과 전용이고, 회신 구성은 프로토콜 계층의
책임이다. `bind(conn)`으로 그 훅에 맞는 단일 인자 콜백을 만든다.
"""
from __future__ import annotations

import json
import sqlite3
from typing import Callable

try:                    # 패키지로 import될 때
    from contracts.frame import DevType, Frame, MsgKind, Subtype
except ImportError:     # 스크립트로 직접 실행되거나 project_code 가 sys.path 밖일 때
    import pathlib
    import sys
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
    from contracts.frame import DevType, Frame, MsgKind, Subtype

try:
    from backend import repository
except ImportError:
    import pathlib
    import sys
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
    from backend import repository

#: 0943 NEC(표 7-12) → 1369-P1 alert.severity(INFO/WARN/CRITICAL) 매핑.
#: 0943은 NEC에 심각도 등급을 두지 않는다(표준 미규정 구현 결정) — 전원·배터리
#: 계열(장치가 곧 통신 불능이 되는 원인)을 CRITICAL로, 그 외(SW/HW 타이머·수신
#: 오류 등 일시적 이상)를 WARN으로 본다.
_NEC_SEVERITY: dict[int, str] = {
    0x05: "CRITICAL",   # ERROR_PWR
    0x06: "CRITICAL",   # ERROR_BATTERY
    0x07: "CRITICAL",   # ERROR_BATTERY_LOW
    0x08: "CRITICAL",   # ERROR_BATTERY_OFF
}


def _nec_severity(nec: int) -> str:
    return _NEC_SEVERITY.get(nec, "WARN")


def _serialize_elements(frame: Frame) -> str | None:
    """`siap/codec.py`가 이미 디코딩해 준 가변 요소를 `frame_log.elements_json`에
    그대로 옮긴다(재해석 없음 — 표준 해석은 프로토콜 계층 하나뿐이다). `api.py`가
    조회 시점에 이 값을 필드 분해 패널로 펼친다. 위반 프레임은 두 튜플이 항상 비어
    있으므로 자동으로 `None`이 된다.

    짧은 이름을 키로 쓰는 이유 — 이 JSON은 저장 전용 내부 표현이고, 표준 표기로의
    매핑은 `api.py`가 전담한다(중복 없이 한 곳)."""
    if frame.device_properties:
        items = [
            {"kind": "DP", "device_id": dp.main.device_id, "dev_type": int(dp.main.dev_type),
             "subtype": dp.main.subtype, "value_type": int(dp.main.value_type),
             "value": dp.main.value, "transfer_mode": int(dp.transfer_mode), "period": dp.period,
             "lower_value": dp.lower_value, "upper_value": dp.upper_value,
             "lower_limit": dp.lower_limit, "upper_limit": dp.upper_limit,
             "precision": dp.precision, "status": int(dp.status)}
            for dp in frame.device_properties
        ]
    elif frame.device_main_infos:
        items = [
            {"kind": "DMI", "device_id": dmi.device_id, "dev_type": int(dmi.dev_type),
             "subtype": dmi.subtype, "value_type": int(dmi.value_type), "value": dmi.value}
            for dmi in frame.device_main_infos
        ]
    else:
        return None
    return json.dumps(items, ensure_ascii=False)


def handle(frame: Frame, conn: sqlite3.Connection) -> None:
    """유일한 진입점. 수신(rx) 프레임 1건을 DB에 반영하고 커밋한다.

    반환값 없음 — `backend/`는 회신 프레임을 만들지 않는다(그건 프로토콜
    계층의 책임, `siap/build.py`·`siap/link.py`). `run.py`가 이 함수와
    프로토콜 계층의 회신 로직을 각자 부르는 방식으로 조립한다.

    "프레임 1건 = 트랜잭션 1건"(부분 반영 방지). 전체를 `try/except`로 감싸 예외
    시 `rollback()`한 뒤 그대로 재전파한다 — 여러 요소 중 뒤쪽에서 예외가 나도
    앞쪽 요소가 열린 트랜잭션에 남지 않게 하고, 호출자가 실패를 알게 한다."""
    try:
        header = frame.header
        frame_id = repository.insert_frame_log(
            conn,
            t=frame.t,
            direction="rx",
            raw_hex=frame.raw.hex(),
            version=header.version if header is not None else None,
            msg_type=header.msg_type if header is not None else None,
            trans_type=header.trans_type if header is not None else None,
            msg_id=header.msg_id if header is not None else None,
            payload_len=header.payload_len if header is not None else None,
            gcg_id=header.gcg_id if header is not None else None,
            node_id=header.node_id if header is not None else None,
            is_valid=frame.is_valid,
            elements_json=_serialize_elements(frame),
        )

        if not frame.is_valid:
            # 위반 프레임은 구조화 필드가 일부 해석됐더라도 비즈니스 데이터로
            # 반영하지 않는다. 위반 내역과 원본만 남기고 격리한다.
            for v in frame.violations:
                repository.insert_frame_violation(
                    conn, frame_id=frame_id, code=v.code, code_name=v.code_name,
                    clause=v.clause, detail=v.detail,
                )
            conn.commit()
            return

        if frame.kind in (MsgKind.REQ_SET_DEVICE_PROPERTY, MsgKind.REQ_SET_NODE_DEVICE_PROPERTY_ALL):
            # 노드가 자신의 디바이스 구성을 게이트웨이에 선언하는 통로는 이 두
            # 메시지다(표 7-2, NODE_ORIGINATED_REQUESTS). REQ_SET_CONNECTION 의
            # LAYOUT 은 (0,0)이라 device_properties 를 실을 수 없다.
            _handle_device_property(conn, frame)
        elif frame.kind is MsgKind.NOTI_DEVICE_VALUE:
            _handle_device_value(conn, frame)
        elif frame.kind is MsgKind.NOTI_ERROR:
            _handle_error(conn, frame, frame_id)
        elif frame.kind is MsgKind.NOTI_DISCONNECT:
            _handle_disconnect(conn, frame, frame_id)
        # 그 외(REBOOT/KEEP_ALIVE, RES_*, ACK 등)는 frame_log 만으로 충분하다.

        conn.commit()
    except Exception:
        conn.rollback()
        raise


def bind(conn: sqlite3.Connection) -> Callable[[Frame], None]:
    """`siap/link.py`의 `on_frame` 훅에 맞는 단일 인자 콜백을 만든다. `on_frame`은
    부수효과 전용이라 반환값을 신경 쓸 필요가 없다.

    **`conn`은 반드시 `on_frame`이 호출될 스레드(SIAP I/O 스레드)에서 연 연결이어야
    한다** — SQLite 연결은 만든 스레드에서만 쓸 수 있다(`check_same_thread=False`
    금지). 그래서 실제 진입점(`run.py`)은 이 함수를 직접 쓰지 않고 I/O 스레드 안에서
    지연 연결하는 자체 래퍼를 쓴다 — 이 함수는 스레드 경계가 이미 보장된 호출자
    (테스트, 단일 스레드 스크립트)를 위해 남아 있다."""
    def _on_frame(frame: Frame) -> None:
        handle(frame, conn)
    return _on_frame


def _subtype_name(code: int) -> str | None:
    """SIAP Subtype 코드 → 이름. `env_measurement`/`device_state_data`의
    CHECK 목록과 `Subtype` enum 멤버 이름이 1:1 대응한다(둘 다 1369-P1
    6.3.3/6.3.4에서 나온다). 등록되지 않은 코드는 None — 정상 경로에서는
    `siap/codec.py`가 이미 INVALID_DATA_SUBTYPE 위반으로 걸러 여기 오지
    않는다(방어적 가드일 뿐 정상 흐름의 일부가 아니다)."""
    try:
        return Subtype(code).name
    except ValueError:
        return None


def _handle_device_property(conn: sqlite3.Connection, frame: Frame) -> None:
    """REQ_SET_DEVICE_PROPERTY / REQ_SET_NODE_DEVICE_PROPERTY_ALL (8.1.3.2/.3,
    노드→GCG) → device_info + device_install_info + device_install.

    노드가 자신의 디바이스 구성을 선언하는 통로는 이 두 메시지다 —
    NODE_ORIGINATED_REQUESTS 가 "노드가 보낼 수 있는 Request"로 명시하고 LAYOUT 도
    DEVICE_PROPERTY×N 을 배정한다(REQ_SET_CONNECTION 의 LAYOUT 은 (0,0)이라 구성을
    실을 수 없다). 노드가 이 선언을 언제 보내는가는 0943 미규정이라, 이 참조 구현은
    "연결 성공(RES_SET_CONNECTION RSC=SUCCESS) 직후, 세션마다
    REQ_SET_NODE_DEVICE_PROPERTY_ALL 1회로 전체 구성을 선언한다"로 결정했다.
    REQ_SET_DEVICE_PROPERTY(부분 집합)로 와도 원소 단위 upsert 라 동일하게 처리된다.

    노드 종류를 분기하지 않는다 — `device_info.model_name`은 오직 Subtype 코드에서
    유도되며(`SIAP-0x..`), 어느 보드(Uno/Pro Mini/ESP32)가 보냈는지는 이 함수에
    전달되지 않는다. 온실은 이 데모의 고정 시드를 그대로 쓴다 — 없으면 조용히 건너뛴다.

    Type/Subtype 일관성 검사(표 7-14의 Type은 Subtype과 독립된 1bit 필드라 코덱이
    조합 자체를 거부하지 않는다)를 여기서도 적용한다 — 어긋나면 등록 정체성이
    모순(1369-P1 7.1(6)·7.2.2.5)이 되므로 걸러낸다.

    장치 관리자: 1369-P1 7.1(7) "설치된 장치들은 1명의 사용자에 의해 관리된다"
    (device_manage). 별도의 "장치 관리자 지정" 입력이 없으므로, 장치가 설치된 온실의
    관리자(greenhouse_manage, 7.1(3)로 N:1 확정)를 그 장치의 관리자로도 삼는다 —
    이 데모는 온실 1개 고정이라 결과가 유일하다.

    설치위치: 1369-P1 6.2.5 "장치설치정보에는... 설치위치 등이 포함되어야 한다".
    0943 DEVICE_PROPERTY(표 7-15)는 위치를 나르지 않고 별도 입력 수단도 없으므로,
    그 장치가 설치된 온실 자신의 위치를 기본값으로 쓴다. **최초 등록에서만** 이
    기본값을 넘긴다 — 재연결마다 넘기면 upsert 의 COALESCE 가 매번 이 기본값으로
    덮어써, 장차 더 구체적인 위치가 다른 경로로 설정되더라도 도로 온실 기본값이 된다."""
    greenhouse_id = repository.get_default_greenhouse_id(conn)
    if greenhouse_id is None:
        return
    manager_user_id = repository.get_greenhouse_manager_user_id(conn, greenhouse_id)
    gh_location, gh_loc_unit = repository.get_greenhouse_location(conn, greenhouse_id)
    node_id = frame.header.node_id
    for dp in frame.device_properties:
        dmi = dp.main
        name = _subtype_name(dmi.subtype)
        if name is None:
            continue
        if dmi.dev_type is not Subtype(dmi.subtype).dev_type:
            # Type 이 이 subtype 의 정의(Subtype.dev_type)와 어긋나면 등록을 거부한다.
            continue
        model_name = f"SIAP-0x{dmi.subtype:02X}"
        device_info_id = repository.get_or_create_device_info(
            conn,
            device_kind=dmi.dev_type.name,
            model_name=model_name,
            device_name=name,
        )
        # 이 (node_id, device_id)가 처음 등록되는 것인지 먼저 본다 — 최초 등록일
        # 때만 온실 위치 기본값을 넘긴다(위 독스트링 근거).
        is_new = repository.find_device_install_by_siap(conn, node_id, dmi.device_id) is None
        install_id = repository.upsert_device_install_info(
            conn,
            device_info_id=device_info_id,
            # 노드 ID 는 화면 전체 표기(0x..)와 맞춰 16진수로 이름에 넣는다.
            # subtype 종류명은 device_info 에 별도로 남으므로 라벨에서는 뺀다(중복 방지).
            device_name=f"node0x{node_id:X}-{dmi.device_id}",
            siap_node_id=node_id,
            siap_device_id=dmi.device_id,
            siap_subtype=dmi.subtype,
            siap_value_type=int(dmi.value_type),
            transfer_mode=dp.transfer_mode.name,
            period_sec=dp.period,
            install_location=gh_location if is_new else None,
            install_loc_unit=gh_loc_unit if is_new else None,
            unit=None,
            lower_limit=_as_float(dp.lower_limit),
            upper_limit=_as_float(dp.upper_limit),
            precision_val=_as_float(dp.precision),
        )
        repository.link_device_install(conn, greenhouse_id, install_id)
        if manager_user_id is not None:
            repository.link_device_manage(conn, manager_user_id, install_id)


def _as_float(v: float | int | None) -> float | None:
    return None if v is None else float(v)


def _handle_device_value(conn: sqlite3.Connection, frame: Frame) -> None:
    """NOTI_DEVICE_VALUE (8.2.1.2) → 센서면 env_*, 액추에이터면 device_state_*.

    각 DEVICE_MAIN_INFO 요소가 가리키는 (node_id, device_id)가 먼저
    REQ_SET_DEVICE_PROPERTY/REQ_SET_NODE_DEVICE_PROPERTY_ALL로
    등록돼 있어야 한다 — 없으면(프로토콜상 있을 수 없지만 방어적으로)
    그 요소만 건너뛴다.

    같은 프레임 안에서 장치상태와 환경상태가 함께 관측되면 1369-P1 7.2.3.4
    "작동 환경" 관계(`operating_env`)로 묶는다. `env_state_id`가 `UNIQUE`라 환경상태
    1건은 정확히 하나의 장치상태에만 귀속되므로(7.1(10)), 이 프레임에서 장치상태가
    **정확히 1건** 생성됐을 때만 묶는다 — 2건 이상이면 어느 장치상태와 짝지어야
    하는지 프레임 자체로는 정할 수 없어(표준 미규정) 틀리게 짝짓느니 비워 둔다.

    환경 측정 위치는 그 장치의 설치 위치를 참조한다(1369-P1 7.2.3.3) — 설치 행이
    이미 그 값을 들고 있으므로 그대로 넘긴다.

    1369-P1 6.3.2 "센서 유효범위를 벗어난 값은 측정 오류로 보고 무시해야 하며" —
    설치 시 등록된 `lower_limit`/`upper_limit`을 벗어난 센서 값은 저장하지 않고 그
    요소만 건너뛴다. 두 경계는 각각 독립적으로 nullable(편측 유효범위)이라, 있는
    경계만 독립적으로 검사한다.

    설치 행을 찾은 뒤 알림의 `subtype`이 **등록된 `siap_subtype`과 같은지** 대조한다
    (1369-P1 7.1(6)·7.2.2.5) — node/device 번호만으로 찾으면 SENSOR로 등록된 주소가
    ACTUATOR 알림을 보내도 그대로 믿고 저장하게 된다. `ENV_SUBTYPES`와
    `DEVICE_STATE_SUBTYPES`는 서로소이므로 subtype 코드 일치 하나로 dev_type 불일치도
    함께 걸러진다."""
    node_id = frame.header.node_id
    greenhouse_id = repository.get_default_greenhouse_id(conn)
    if greenhouse_id is None:
        return
    env_state_ids: list[str] = []
    device_state_ids: list[str] = []
    for dmi in frame.device_main_infos:
        install = repository.find_device_install_by_siap(conn, node_id, dmi.device_id)
        if install is None:
            continue
        if install["siap_subtype"] != dmi.subtype:
            # 알림의 subtype 이 등록 정체성과 다르면 신뢰할 수 없다.
            continue
        name = _subtype_name(dmi.subtype)
        if name is None:
            continue
        if dmi.dev_type is not Subtype(dmi.subtype).dev_type:
            # 표 7-14의 Type 은 Subtype 과 별개인 독립 1bit 필드라 코덱이 조합
            # 자체를 거부하지 않는다. subtype 이 일치해도 Type 이 그 subtype 의
            # 정의(Subtype.dev_type)와 어긋나면 아래 SENSOR/ACTUATOR 분기가 서로
            # 다른 서브타입 집합을 잘못 골라 죽으므로, 여기서 걸러낸다.
            continue
        value = float(dmi.value)
        if dmi.dev_type is DevType.SENSOR:
            lo, hi = install["lower_limit"], install["upper_limit"]
            if (lo is not None and value < lo) or (hi is not None and value > hi):
                # 유효범위 밖(편측이라도)은 측정 오류 — 정상 데이터로 축적하지 않는다.
                continue
            esd_id = repository.record_env_measurement(
                conn,
                install_id=install["id"],
                greenhouse_id=greenhouse_id,
                subtype=name,
                value=value,
                unit=install["unit"],
                error_range=install["precision_val"],
                lower_limit=install["lower_limit"],
                upper_limit=install["upper_limit"],
                location=install["install_location"],
                location_unit=install["install_loc_unit"],
            )
            env_state_ids.append(esd_id)
        else:
            valid_range = None
            if install["lower_limit"] is not None and install["upper_limit"] is not None:
                valid_range = f"{install['lower_limit']}-{install['upper_limit']}"
            dsd_id = repository.record_device_state(
                conn, install_id=install["id"], subtype=name, value=value, valid_range=valid_range,
            )
            device_state_ids.append(dsd_id)

    if len(device_state_ids) == 1 and env_state_ids:
        for esd_id in env_state_ids:
            repository.record_operating_env(
                conn, device_state_id=device_state_ids[0], env_state_id=esd_id)


def _handle_error(conn: sqlite3.Connection, frame: Frame, frame_id: str) -> None:
    """NOTI_ERROR (8.2.1.1) → alert. 정상 NEC 알림은 위반이 아니다(`frame.violations`
    는 비어 있다). NOTI_ERROR는 device_id를 싣지 않으므로(표 7-12, NEC 1byte뿐)
    `install_id`는 항상 NULL — 노드 단위 알림이다."""
    nec = int(frame.nec)
    repository.record_alert(
        conn,
        kind="NODE_ERROR",
        severity=_nec_severity(nec),
        message=f"NEC=0x{nec:02X}",
        install_id=None,
        siap_nec=nec,
        frame_id=frame_id,
    )


def _handle_disconnect(conn: sqlite3.Connection, frame: Frame, frame_id: str) -> None:
    """NOTI_DISCONNECT (8.2.1.3) → alert. 0937 6.5-2 "하드웨어 고장, 네트워크 단절
    등 긴급 상황시 사용자 알림"이 명시한 "네트워크 단절" 그 자체다. 페이로드가 없어
    (LAYOUT (0,0), 표 7-2) NEC와 마찬가지로 노드 단위 알림이다 — `install_id`는
    항상 NULL."""
    repository.record_alert(
        conn,
        kind="DISCONNECT",
        severity="CRITICAL",
        message=f"Node {frame.header.node_id} 연결 종료 알림(NOTI_DISCONNECT)",
        install_id=None,
        frame_id=frame_id,
    )
