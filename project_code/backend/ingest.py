"""
backend/ingest.py — ★ Frame 소비 지점. 유일한 경계 (CLAUDE.md §2.2).

`handle(frame)` 위쪽에 로직을 두지 않는다 — Frame이 어디서 왔는지(하드웨어냐
replay 냐 simulate 냐) 이 계층은 모른다. `contracts/frame.py`의 `Frame`
외에는 아무것도 참조하지 않는다 — `siap/` 내부 심볼(codec·link·registry)을
import하지 않는다(CLAUDE.md §2.2). 표준 해석(위반 판정)은 이미 프로토콜
계층이 끝냈다 — 여기는 그 결과를 테이블에 적을 뿐 다시 판정하지 않는다
(CLAUDE.md §3.4).

DB 스키마 설계서 §7 "Frame → 테이블 매핑 규칙":
  REQ_SET_DEVICE_PROPERTY /
  REQ_SET_NODE_DEVICE_PROPERTY_ALL → device_install_info + device_install (기능 1)
                        F-198 — REQ_SET_CONNECTION(8.1.1)이 아니다. 이 두 메시지가
                        표 7-2·`contracts/frame.py::LAYOUT`상 DEVICE_PROPERTY×N을
                        싣는 실제 통로다. REQ_SET_CONNECTION의 LAYOUT은 (0,0)이라
                        `frame.device_properties`가 구조적으로 항상 비어 있다 —
                        예전 버전은 REQ_SET_CONNECTION에 바인딩돼 있어 이 함수가
                        한 번도 실행되지 않는 죽은 코드였다(아래 §3.5 결정 참고).
  NOTI_DEVICE_VALUE  → env_state_data+env_measurement+env_measure (FMS, 센서)
                        또는 device_state_data+dsd_*+device_state (액추에이터)
  NOTI_ERROR         → alert                                      (FCS)
  NOTI_DISCONNECT    → alert                                      (FCS, F-191)
  모든 프레임         → frame_log (+ 위반 시 frame_violation)

구현 결정(표준 미규정 아님 — codec.py의 기존 동작 그대로) — 위반 프레임은
`kind=None`이고 구조화된 필드(`device_main_infos`·`node_property` 등)가
전부 비어 있다(`siap/codec.py::decode_frame`의 `_violation()` 이 항상 그렇게
만든다). 따라서 위반 프레임은 `frame_log`+`frame_violation`만 기록하고
비즈니스 테이블은 건드리지 않는다 — 반영할 구조화된 데이터 자체가 없다.

F-154 — `handle(frame, conn)`은 DB 반영만 하고 회신 Frame을 만들지 않는다
(반환값 없음). `siap/link.py`의 `on_frame` 훅은 이제 부수효과 전용이라
(F-154, 회신은 `_default_reply()`가 계속 만든다 — 표준 해석은 프로토콜
계층에만, CLAUDE.md §3.4) `bind(conn)`으로 그 훅에 맞는 단일 인자 콜백을
만들면 된다. `backend/`가 `siap/build.py`(FrameBuilder 구현)를 몰라도 되는
이유이기도 하다 — 회신 구성은 애초에 이 계층의 책임이 아니다.

F-167 — `bind(conn)`은 스레드 경계가 이미 보장된 호출자(테스트 등) 전용이다.
실제 진입점(`run.py`)은 `bind()`를 직접 쓰지 않는다 — `on_frame`이 호출되는
SIAP I/O 스레드와 다른 스레드에서 연 `conn`을 넘기면 `sqlite3.
ProgrammingError`가 난다(F-160 재현). `run.py`는 대신 DB 경로만 받아 그
스레드 안에서 지연 연결하는 자체 래퍼(`_make_on_frame()`)를 쓴다 — 자세한
이유는 `bind()`의 독스트링 참고.
"""
from __future__ import annotations

import json
import sqlite3
from typing import Callable

try:                    # F-025 — 패키지로 import될 때
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
#: 표준 미규정 구현 결정(CLAUDE.md §3.5 갱신 대상) — 0943은 NEC에 심각도
#: 등급을 두지 않는다. 전원·배터리 계열(장치가 곧 통신 불능이 되는 원인)을
#: CRITICAL로, 그 외(SW/HW 타이머·수신 오류 등 일시적 이상)를 WARN으로 본다.
_NEC_SEVERITY: dict[int, str] = {
    0x05: "CRITICAL",   # ERROR_PWR
    0x06: "CRITICAL",   # ERROR_BATTERY
    0x07: "CRITICAL",   # ERROR_BATTERY_LOW
    0x08: "CRITICAL",   # ERROR_BATTERY_OFF
}


def _nec_severity(nec: int) -> str:
    return _NEC_SEVERITY.get(nec, "WARN")


def _serialize_elements(frame: Frame) -> str | None:
    """F-187 — `siap/codec.py`가 이미 디코딩해 준 가변 요소를 `frame_log.
    elements_json`에 그대로 옮긴다(재해석 없음, §3.4 — 표준 해석은 여전히
    프로토콜 계층 하나뿐이다). `api.py`가 조회 시점에 이 값을 필드 분해
    패널(FieldSlice)로 펼친다. 위반 프레임은 두 튜플이 항상 비어 있으므로
    (`_violation()` 보장) 자동으로 `None`이 된다.

    표준 표기(Device ID·Type 등)를 그대로 키로 쓰지 않고 짧은 이름을 쓰는
    이유 — 이 JSON은 저장 전용 내부 표현이고, `표준 표기`로의 매핑은
    `api.py::_PAYLOAD_FIELD_LAYOUT`이 전담한다(중복 없이 한 곳)."""
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
    프로토콜 계층의 회신 로직을 각자 부르는 방식으로 조립한다(단계 6).

    F-178 — 아키텍처 설계서 §4.4 "프레임 1건 = 트랜잭션 1건"(이유: "부분
    반영 방지"). 이전에는 성공 경로 끝에서만 `commit()`을 걸어, 여러 요소
    중 뒤쪽에서 예외가 나면 앞쪽 요소의 INSERT가 열린 트랜잭션에 그대로
    남았다 — 이 함수는 예외를 던지고 끝나지만, 같은 `conn`을 나중에 다른
    프레임에서 `commit()`하면 실패한 프레임의 일부가 함께 영구 저장됐다.
    전체를 `try/except`로 감싸 예외 시 `rollback()`한 뒤 그대로 재전파한다
    — 호출자가 실패를 알아야 하므로 삼키지 않는다."""
    try:
        frame_id = repository.insert_frame_log(
            conn,
            t=frame.t,
            direction="rx",
            raw_hex=frame.raw.hex(),
            version=frame.header.version,
            msg_type=frame.header.msg_type,
            trans_type=frame.header.trans_type,
            msg_id=frame.header.msg_id,
            payload_len=frame.header.payload_len,
            gcg_id=frame.header.gcg_id,
            node_id=frame.header.node_id,
            is_valid=frame.is_valid,
            elements_json=_serialize_elements(frame),
        )

        if not frame.is_valid:
            # 위반 프레임 — codec.py는 이 경우 kind=None, 구조화 필드 전부 비움을
            # 보장한다. 반영할 것이 없으므로 위반 내역만 남기고 격리한다.
            for v in frame.violations:
                repository.insert_frame_violation(
                    conn, frame_id=frame_id, code=v.code, code_name=v.code_name,
                    clause=v.clause, detail=v.detail,
                )
            conn.commit()
            return

        if frame.kind in (MsgKind.REQ_SET_DEVICE_PROPERTY, MsgKind.REQ_SET_NODE_DEVICE_PROPERTY_ALL):
            # F-198 — REQ_SET_CONNECTION이 아니다. LAYOUT[(REQ_SET_CONNECTION)]==(0,0)
            # 이라 그 프레임의 device_properties는 디코더가 만드는 한 항상 빈
            # 튜플이다(위 헤더 §3.5 참고) — 여기 바인딩해 두면 다시 죽은 코드가
            # 된다. 노드가 자신의 디바이스 구성을 게이트웨이에 선언하는 실제
            # 통로는 이 두 메시지다(표 7-2, `NODE_ORIGINATED_REQUESTS`).
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
    """F-154 — `siap/link.py`의 `on_frame: Callable[[Frame], Frame | None]`
    훅에 맞는 단일 인자 콜백을 만든다. `on_frame`은 이제 부수효과 전용이라
    (회신은 `_default_reply()`가 만든다) 반환값을 신경 쓸 필요가 없다.

    `handle()` 자체를 `conn` 없이 두 인자로 남긴 이유는 테스트에서 매 호출마다
    다른(또는 `:memory:`) 연결을 명시적으로 넘기기 위해서다 — 전역 연결
    상태를 두지 않는다(아키텍처 설계서 §4.1 "스레드별 연결" 원칙과 같은 이유).

    F-160 — **`conn`은 반드시 실제로 `on_frame`이 호출될 스레드(SIAP I/O
    스레드)에서 연 연결이어야 한다.** SQLite 연결은 만든 스레드에서만 쓸 수
    있다(`check_same_thread=False` 금지, §4.1) — 메인 스레드에서 연 연결을
    여기 넘기면 첫 프레임 처리에서 `ProgrammingError`로 죽는다. 그래서
    `run.py`는 이 함수를 직접 쓰지 않고, I/O 스레드 안에서 지연 연결하는
    자체 래퍼(`_make_on_frame()`)를 쓴다 — 이 함수는 스레드 경계가 이미
    보장된 호출자(테스트, 단일 스레드 스크립트)를 위해 남아 있다."""
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

    F-198 — 예전 이름은 `_handle_connection`이었고 `REQ_SET_CONNECTION`
    (8.1.1)에 바인딩돼 있었다. 그러나 `contracts/frame.py::LAYOUT
    [MsgKind.REQ_SET_CONNECTION] == (0, 0)`(고정부·가변부 전부 0, SIAP
    메시지 명세서 §2.4 표도 "(없음)")이라 그 프레임의 `frame.device_properties`
    는 디코더가 만드는 한 구조적으로 항상 빈 튜플이다 — 이 함수의 for 루프가
    한 번도 실행되지 않는 죽은 코드였다. 노드가 자신의 디바이스 구성을
    선언하는 실제 통로는 이 두 메시지다 — `contracts/frame.py::
    NODE_ORIGINATED_REQUESTS`가 "노드가 보낼 수 있는 Request"로 명시하고
    `LAYOUT`도 `DEVICE_PROPERTY×N`을 배정한다. 노드가 이 선언을 언제
    보내는가는 0943이 절차를 규정하지 않는 표준 미규정 사항이다 — 이 참조
    구현은 "연결 성공(`RES_SET_CONNECTION` RSC=SUCCESS) 직후, 세션마다
    `REQ_SET_NODE_DEVICE_PROPERTY_ALL` 1회로 전체 구성을 선언한다"로
    결정했다(`CLAUDE.md` §3.5, `sim/virtual_node.py`가 이 결정을 구현한다).
    `REQ_SET_DEVICE_PROPERTY`(부분 집합)로 와도 이 함수는 원소 단위
    upsert라 동일하게 처리된다 — 전체 교체와 부분 갱신을 구분해야 하는
    쪽은 런타임 registry(`siap/registry.py::merge_device_properties`)다.

    노드 종류를 분기하지 않는다(CLAUDE.md §1-6) — `device_info`의 `model_name`
    은 오직 `Subtype` 코드에서 유도된다(`SIAP-0x..`), 어느 보드(Uno/Pro Mini/
    ESP32)가 보냈는지는 이 함수에 아예 전달되지 않는다. 온실은 이 데모의
    고정 시드(§7.4)를 그대로 쓴다 — 온실이 없으면(시드 누락) 조용히
    건너뛴다: 이 함수는 표준을 재해석하지 않으므로 그 상황을 판정하지 않는다.

    F-180 — F-175가 `_handle_device_value()`에 추가한 Type/Subtype 일관성
    검사(표 7-14의 Type은 Subtype과 독립된 1bit 필드라 코덱이 조합 자체를
    거부하지 않는다)를 이 함수에도 그대로 적용한다. 여기서 걸러내지
    않으면 `device_info.device_kind`가 Type(예: ACTUATOR)으로, 이후
    값 알림은 그 subtype이 실제로 속한 종류(예: HUMIDITY→SENSOR)로 들어와
    F-175 가드에 막혀 저장은 안 되지만 등록 정체성 자체가 이미
    모순(1369-P1 §7.1(6)·§7.2.2.5)인 채로 남는다.

    F-176 — 1369-P1 §7.1(7) "설치된 장치들은 1명의 사용자에 의해 관리된다"
    (device_manage, `UNIQUE(install_id)`). 이 참조 구현은 별도의 "장치
    관리자 지정" 입력이 없으므로(§3.5 갱신 대상), 장치가 설치된 온실의
    관리자(`greenhouse_manage`, 1369-P1 §7.1(3)로 이미 N:1 확정)를 그
    장치의 관리자로도 삼는다 — 이 데모는 온실 1개 고정이라 결과가 유일하다.

    F-183 — 1369-P1 §6.2.5 "장치설치정보에는... 설치위치 등이 포함되어야
    한다". 0943 DEVICE_PROPERTY(표 7-15)는 위치를 나르지 않고 이 참조 구현에는
    장치별 세부 위치를 입력할 별도 수단도 없으므로(§3.5 갱신 대상, F-176과
    같은 사정), 그 장치가 설치된 온실 자신의 위치를 기본값으로 쓴다
    (`repository.get_greenhouse_location`). **최초 등록(신규 install
    행)에서만** 이 기본값을 넘긴다 — 재연결(기존 install 행 UPDATE)에서도
    매번 넘기면 `upsert_device_install_info`의 COALESCE(F-170)가 "새 값이
    왔다"고 보고 매 재연결마다 이 기본값으로 덮어써, 장차 더 구체적인
    위치가 다른 경로로 설정되더라도 도로 온실 기본값이 된다."""
    greenhouse_id = repository.get_default_greenhouse_id(conn)
    if greenhouse_id is None:
        return
    manager_user_id = repository.get_greenhouse_manager_user_id(conn, greenhouse_id)  # F-176
    gh_location, gh_loc_unit = repository.get_greenhouse_location(conn, greenhouse_id)  # F-183
    node_id = frame.header.node_id
    for dp in frame.device_properties:
        dmi = dp.main
        name = _subtype_name(dmi.subtype)
        if name is None:
            continue
        if dmi.dev_type is not Subtype(dmi.subtype).dev_type:
            # F-180 — Type이 이 subtype의 정의(Subtype.dev_type)와 어긋나면
            # 등록 자체를 거부한다(F-175와 같은 불변식).
            continue
        model_name = f"SIAP-0x{dmi.subtype:02X}"
        device_info_id = repository.get_or_create_device_info(
            conn,
            device_kind=dmi.dev_type.name,
            model_name=model_name,
            device_name=name,
        )
        # F-183 — 이 (node_id, device_id)가 처음 등록되는 것인지 먼저 본다.
        # 최초 등록일 때만 온실 위치 기본값을 넘긴다(위 독스트링 근거).
        is_new = repository.find_device_install_by_siap(conn, node_id, dmi.device_id) is None
        install_id = repository.upsert_device_install_info(
            conn,
            device_info_id=device_info_id,
            device_name=f"node{node_id}-{name.lower()}-{dmi.device_id}",
            siap_node_id=node_id,
            siap_device_id=dmi.device_id,
            siap_subtype=dmi.subtype,
            install_location=gh_location if is_new else None,
            install_loc_unit=gh_loc_unit if is_new else None,
            unit=None,
            lower_limit=_as_float(dp.lower_limit),
            upper_limit=_as_float(dp.upper_limit),
            precision_val=_as_float(dp.precision),
        )
        repository.link_device_install(conn, greenhouse_id, install_id)
        if manager_user_id is not None:
            repository.link_device_manage(conn, manager_user_id, install_id)  # F-176


def _as_float(v: float | int | None) -> float | None:
    return None if v is None else float(v)


def _handle_device_value(conn: sqlite3.Connection, frame: Frame) -> None:
    """NOTI_DEVICE_VALUE (8.2.1.2) → 센서면 env_*, 액추에이터면 device_state_*.

    각 DEVICE_MAIN_INFO 요소가 가리키는 (node_id, device_id)가 먼저
    REQ_SET_DEVICE_PROPERTY/REQ_SET_NODE_DEVICE_PROPERTY_ALL(F-198)로
    등록돼 있어야 한다 — 없으면(프로토콜상 있을 수 없지만 방어적으로)
    그 요소만 건너뛴다.

    F-156 — 같은 프레임 안에서 장치상태와 환경상태가 함께 관측되면 1369-P1
    7.2.3.4 "작동 환경" 관계(`operating_env`)로 묶는다. `env_state_id`가
    `UNIQUE`라 환경상태 1건은 정확히 하나의 장치상태에만 귀속될 수 있다
    (7.1(10)) — 이 프레임에서 장치상태가 **정확히 1건** 생성됐을 때만 묶는다.
    2건 이상이면 어느 장치상태와 짝지어야 하는지 프레임 자체로는 정할 수
    없어(표준 미규정) 건너뛴다 — 틀리게 짝짓느니 비워 두는 쪽을 택했다
    (CLAUDE.md §3.5 갱신 대상).

    F-170 — 환경 측정 위치는 그 장치의 설치 위치(`install_location`/
    `install_loc_unit`)를 참조하도록 결정돼 있다(1369-P1 §7.2.3.3). 설치
    행이 이미 그 값을 들고 있으므로 그대로 넘긴다.

    F-171/F-177 — 1369-P1 §6.3.2 "센서 유효범위를 벗어난 값은 측정 오류로
    보고 무시해야 하며" — 설치 시 등록된 `lower_limit`/`upper_limit`을 벗어난
    센서 값은 정상 환경 데이터로 저장하지 않고 그 요소만 건너뛴다. 두 경계는
    스키마상 각각 독립적으로 nullable이다(편측 유효범위 — 하한만 있거나
    상한만 있는 센서) — **둘 다 있을 때만** 검사하면(F-171 최초 구현) 한쪽
    경계만 등록된 장치는 그 경계를 넘는 값도 그대로 통과한다. 있는 경계만
    독립적으로 검사한다(F-177).

    F-173 — §7.1(6) "장치 설치 정보는 정확히 하나의 장치 기본 정보를
    가진다" / §7.2.2.5. 설치 행을 찾은 뒤 알림의 `subtype`이 **등록된
    `siap_subtype`과 같은지** 대조한다 — node/device 번호만으로 찾으면,
    SENSOR로 등록된 주소가 ACTUATOR 알림(또는 그 반대)을 보내도 알림이
    주장하는 `dev_type`을 그대로 믿고 저장하게 된다. `ENV_SUBTYPES`와
    `DEVICE_STATE_SUBTYPES`는 서로소이므로 subtype 코드 일치 하나로
    dev_type 불일치까지 함께 걸러진다(F-169가 고친 재연결 UPDATE와는
    별개의 경로 — 재연결 없이 알림만 다른 종류로 와도 걸러야 한다)."""
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
            # F-173 — 알림의 subtype이 등록 정체성과 다르면 신뢰할 수 없다.
            continue
        name = _subtype_name(dmi.subtype)
        if name is None:
            continue
        if dmi.dev_type is not Subtype(dmi.subtype).dev_type:
            # F-175 — 표 7-14의 Type은 Subtype과 별개인 독립 1bit 필드라
            # 코덱이 조합 자체를 거부하지 않는다(값 자체는 정상 디코드된다).
            # subtype이 일치해도 Type이 그 subtype의 정의(Subtype.dev_type,
            # Frame 구조 명세서 §2.3)와 어긋나면 아래 SENSOR/ACTUATOR 분기가
            # 서로 다른 서브타입 집합(ENV_SUBTYPES/DEVICE_STATE_SUBTYPES)을
            # 잘못 골라 record_device_state()/record_env_measurement()가
            # ValueError로 죽는다(재현: HUMIDITY subtype + ACTUATOR Type).
            continue
        value = float(dmi.value)
        if dmi.dev_type is DevType.SENSOR:
            lo, hi = install["lower_limit"], install["upper_limit"]
            if (lo is not None and value < lo) or (hi is not None and value > hi):
                # F-171/F-177 — 유효범위 밖(편측이라도)은 측정 오류.
                # 정상 데이터로 축적하지 않는다.
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
    """NOTI_ERROR (8.2.1.1) → alert. F-060 — 정상 NEC 알림은 위반이 아니다
    (`frame.violations`는 비어 있다, 이미 위에서 확인됨). NOTI_ERROR는
    device_id를 싣지 않으므로(표 7-12, NEC 1byte뿐) `install_id`는 항상
    NULL — 노드 단위 알림이다."""
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
    """NOTI_DISCONNECT (8.2.1.3) → alert (F-191). 0937 6.5-2 "하드웨어 고장,
    네트워크 단절 등 긴급 상황시 사용자 알림"이 명시한 "네트워크 단절" 그
    자체다 — `frame_log`는 원본 프레임 보관용이지 사용자에게 보이는 알림이
    아니므로, 이전에는(F-060 판정과 별개로) 이 메시지가 alert 없이 조용히
    지나갔다. `alert.kind` CHECK(`schema.sql`)가 이미 `DISCONNECT`를
    예정해 두고 있었다 — 스키마가 아니라 이 지점의 결선이 빠져 있었다.
    페이로드가 없어(LAYOUT (0,0), 표 7-2) NEC와 마찬가지로 노드 단위
    알림이다 — `install_id`는 항상 NULL."""
    repository.record_alert(
        conn,
        kind="DISCONNECT",
        severity="CRITICAL",
        message=f"Node {frame.header.node_id} 연결 종료 알림(NOTI_DISCONNECT)",
        install_id=None,
        frame_id=frame_id,
    )
