"""
backend/repository.py — SQL 담당. `schema.sql`이 정본이고 트리거·CHECK가
거기 있다(CLAUDE.md §4.3) — 이 파일은 그 제약을 재해석하지 않고 그대로
믿는다. ORM 미사용, 전부 파라미터 바인딩(`?`) — 문자열 포매팅으로 SQL을
조립하지 않는다.

쓰기 소유권은 테이블 단위다(아키텍처 설계서 §4.4-a). 이 파일의 함수들은
"어느 스레드가 부르는가"를 모른다 — 소유권은 **호출자**(ingest.py = I/O
스레드, 장차 api.py = API 스레드)가 지킨다. 이 파일은 SQL만 안다.

식별자는 UUID4(TEXT), 시간은 ISO 8601(TEXT) — 1369-P1 6.1, 설계 원칙 §1-3.
"""
from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone

try:                    # F-025 와 같은 원칙 — 패키지로 import될 때
    from backend import models
except ImportError:     # 스크립트로 직접 실행되거나 project_code 가 sys.path 밖일 때
    import pathlib
    import sys
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
    from backend import models


# ═══════════════════════════════════════════════════════════════
#  공용 헬퍼
# ═══════════════════════════════════════════════════════════════

def new_id() -> str:
    """1369-P1 6.1 "식별자의 표기는 ITU-T X.667 권고안을 준용" — UUID4."""
    return str(uuid.uuid4())


def now_iso() -> str:
    """1369-P1 6.1 "시간을 다루는 일관된 형식" — ISO 8601, 초 단위, 로컬 오프셋 포함."""
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def record_config_change(conn: sqlite3.Connection, *, table_name: str, row_id: str, operation: str,
                          changes: dict | None = None, user_id: str | None = None,
                          changed_at: str | None = None) -> str:
    """F-182 — 1369-P1 6.2.1 "설정형 데이터는... 변경(생성, 수정, 삭제)에
    대해 이력이 관리되어야 한다". 시드 로더(`fixtures/seed.sql`)만 이
    테이블을 쓴다고 알려져 있었으나(아키텍처 §4.4-a①), 실제 설정형 데이터
    변경 대부분은 런타임에 `REQ_SET_CONNECTION`으로 일어난다 — 그 경로가
    이 함수를 부르지 않아 동적 등록·재연결의 변경 이력이 항상 0건이었다
    (재현 확인). `user_id`는 nullable — 이 경로(Plug & Play 등록)는 사람이
    아니라 노드가 유발한 변경이라 항상 None이다(사람이 유발한 변경은
    `api.py`가 자기 스레드에서 직접 이 함수를 부르게 될 것이다, 단계 6).
    `version`은 DEFAULT 1을 그대로 쓴다 — 이 참조 구현은 행 단위 버전
    카운터를 별도로 올리지 않는다(표준 미규정, 필요 시 CLAUDE.md §3.5
    갱신 대상)."""
    id_ = new_id()
    changed_at = changed_at or now_iso()
    conn.execute(
        "INSERT INTO config_change_log(id,changed_at,table_name,row_id,operation,changes,user_id)"
        " VALUES(?,?,?,?,?,?,?)",
        (id_, changed_at, table_name, row_id, operation,
         json.dumps(changes, ensure_ascii=False) if changes is not None else None, user_id),
    )
    return id_


def get_by_id(conn: sqlite3.Connection, table: str, id_: str):
    """`id` 단일 PK를 갖는 테이블 전용 범용 조회. 관계 테이블(복합 PK)은
    각자의 전용 함수를 쓴다. `models.TABLE_MODEL`이 테이블↔dataclass 매핑의
    정본이다 — 여기서 새로 만들지 않는다."""
    model = models.TABLE_MODEL[table]
    row = conn.execute(f"SELECT * FROM {table} WHERE id = ?", (id_,)).fetchone()
    return model.from_row(row) if row is not None else None


# ═══════════════════════════════════════════════════════════════
#  A/B — device_info · device_install_info · device_install
#         (SIAP I/O 스레드 소유, 아키텍처 §4.4-a②) — REQ_SET_CONNECTION 결과
# ═══════════════════════════════════════════════════════════════

def get_or_create_device_info(conn: sqlite3.Connection, *, device_kind: str,
                               model_name: str, device_name: str,
                               manufacturer: str | None = None,
                               device_characteristics: str | None = None) -> str:
    """`model_name`은 7.2.2.4상 불변·전역 식별이다 — 이미 등록된 모델이면
    재사용하고, 없으면 새로 만든다. 노드 종류를 분기하지 않는다(CLAUDE.md §1-6):
    `model_name`은 오직 SIAP `Subtype` 코드에서 유도되며 호출자(ingest.py)가
    어느 보드인지는 이 함수에 전달되지도 않는다.

    F-185 — `device_characteristics`는 `manufacturer`와 같은 자격이다:
    0943 DEVICE_PROPERTY(표 7-15, F-198)가 나르지 않는 속성이라 이 참조 구현의
    동적 등록 경로(`ingest.py::_handle_device_property`)는 채우지 않고 항상 `None`을
    넘긴다 — 6.2.4가 요구하는 컬럼 자체는 존재해야 하므로(F-185) 저장할
    수단은 열어 둔다.

    F-182 — 실제로 새 행을 만들 때만(재사용 시에는 아무것도 바뀌지 않으므로
    이력이 아니다) `config_change_log`에 CREATE 1건을 남긴다."""
    row = conn.execute("SELECT id FROM device_info WHERE model_name = ?", (model_name,)).fetchone()
    if row is not None:
        return row["id"]
    id_, now = new_id(), now_iso()
    conn.execute(
        "INSERT INTO device_info(id,created_at,updated_at,device_name,device_kind,model_name,"
        "manufacturer,device_characteristics)"
        " VALUES(?,?,?,?,?,?,?,?)",
        (id_, now, now, device_name, device_kind, model_name, manufacturer, device_characteristics),
    )
    record_config_change(conn, table_name="device_info", row_id=id_, operation="CREATE",
                          changes={"device_kind": device_kind, "model_name": model_name,
                                   "device_name": device_name, "manufacturer": manufacturer,
                                   "device_characteristics": device_characteristics})
    return id_


def find_device_install_by_siap(conn: sqlite3.Connection, siap_node_id: int,
                                 siap_device_id: int) -> sqlite3.Row | None:
    """0943 3.4 "디바이스 ID는 단일 노드에서 유일" — `UNIQUE(siap_node_id,
    siap_device_id)`를 그대로 조회 키로 쓴다."""
    return conn.execute(
        "SELECT * FROM device_install_info WHERE siap_node_id = ? AND siap_device_id = ?",
        (siap_node_id, siap_device_id),
    ).fetchone()


def upsert_device_install_info(conn: sqlite3.Connection, *, device_info_id: str, device_name: str,
                                siap_node_id: int, siap_device_id: int, siap_subtype: int,
                                installed_at: str | None = None,
                                install_location: str | None = None, install_loc_unit: str | None = None,
                                unit: str | None = None, lower_limit: float | None = None,
                                upper_limit: float | None = None, precision_val: float | None = None) -> str:
    """재연결(REQ_SET_CONNECTION 재수신) 시 같은 (node_id, device_id) 행을
    갱신한다 — `id`·`created_at`은 트리거로 불변이라 건드리지 않는다.

    F-158 — `installed_at`(6.2.5 설치일자)도 최초 설치 시점의 사실이므로
    재연결 UPDATE 에서는 건드리지 않는다(의미상 `created_at`과 같은 부류).
    호출자가 넘기지 않으면 최초 등록 시각(`now_iso()`)을 그대로 쓴다 —
    이 참조 구현에서 "설치"는 곧 "첫 REQ_SET_CONNECTION 등록"이다.

    F-169 — 재연결로 장치 종류(subtype)가 바뀌면 `device_info_id`도 함께
    갱신해야 한다. 이전에는 UPDATE 절에서 이 컬럼이 빠져 있어 `siap_subtype`
    만 새 값으로 바뀌고 `device_info_id`는 예전 모델(예: TEMPERATURE)을
    계속 참조했다 — 이후 값 알림이 새 subtype(예: HUMIDITY)으로 들어와도
    설치 행이 가리키는 `device_info.device_kind`는 예전 것이라 정체성이
    어긋났다(1369-P1 §7.1(6) "장치 설치 정보는 정확히 하나의 장치 기본
    정보를 가진다", §7.2.2.5 "device_info_id는 갱신 가능").

    F-170 — `install_location`·`install_loc_unit`·`unit`은 이전에는 호출자
    (`ingest.py::_handle_device_property`)가 넘길 수단이 없어 항상 `None`으로
    들어왔다. UPDATE가 그 `None`을 그대로 덮어쓰면 서버가 (장차 API 등
    다른 경로로) 관리하던 값을 재연결마다 지운다 — `COALESCE`로 "호출자가
    실제 값을 줬을 때만 갱신"하도록 바꿔 `unit`처럼 한 번 설정된 값이
    이후 정보 없는 재연결에 의해 사라지지 않게 한다.

    F-183 — 이제 호출자는 **최초 등록(CREATE)에서만** 온실 위치를 기본값
    으로 넘기고(`repository.get_greenhouse_location`), 재연결(UPDATE)
    에서는 `None`을 넘긴다 — 그래야 위 F-170의 COALESCE가 그대로 지켜진다.
    호출자가 매 재연결마다 같은 기본값을 계속 넘기면 COALESCE가 매번
    "새 값이 왔다"고 보고 덮어써, 장차 더 구체적인 위치가 다른 경로로
    설정되더라도 재연결 한 번에 다시 온실 기본값으로 되돌아간다 — F-170이
    막으려던 것과 같은 문제가 다른 값으로 재발한다.

    F-182 — 실제 CREATE/UPDATE가 일어날 때만 `config_change_log`에 남긴다."""
    existing = find_device_install_by_siap(conn, siap_node_id, siap_device_id)
    now = now_iso()
    if existing is not None:
        conn.execute(
            "UPDATE device_install_info SET updated_at=?, device_name=?, device_info_id=?, "
            "install_location=COALESCE(?, install_location), "
            "install_loc_unit=COALESCE(?, install_loc_unit), siap_subtype=?, "
            "unit=COALESCE(?, unit), lower_limit=?, upper_limit=?, precision_val=? "
            "WHERE id=?",
            (now, device_name, device_info_id, install_location, install_loc_unit, siap_subtype,
             unit, lower_limit, upper_limit, precision_val, existing["id"]),
        )
        # F-182 — 재연결도 6.2.1의 "수정" 이다. 이 UPDATE가 실제로 무엇을
        # 바꿨는지(예: siap_subtype)를 남긴다 — 재연결 자체가 이력이다.
        record_config_change(conn, table_name="device_install_info", row_id=existing["id"], operation="UPDATE",
                              changes={"device_name": device_name, "device_info_id": device_info_id,
                                       "siap_subtype": siap_subtype})
        return existing["id"]
    id_ = new_id()
    conn.execute(
        "INSERT INTO device_install_info(id,created_at,updated_at,device_name,installed_at,"
        "install_location,install_loc_unit,device_info_id,siap_node_id,siap_device_id,siap_subtype,"
        "unit,lower_limit,upper_limit,precision_val)"
        " VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (id_, now, now, device_name, installed_at or now, install_location, install_loc_unit,
         device_info_id, siap_node_id, siap_device_id, siap_subtype, unit, lower_limit,
         upper_limit, precision_val),
    )
    record_config_change(conn, table_name="device_install_info", row_id=id_, operation="CREATE",
                          changes={"device_name": device_name, "device_info_id": device_info_id,
                                   "siap_node_id": siap_node_id, "siap_device_id": siap_device_id,
                                   "siap_subtype": siap_subtype})
    return id_


def link_device_install(conn: sqlite3.Connection, greenhouse_id: str, install_id: str) -> None:
    """7.1(4) "1개의 장치는 1개의 온실에 설치될 수 있다" — `UNIQUE(install_id)`가
    강제하므로 이미 연결돼 있으면 조용히 건너뛴다(재연결 시 재삽입 금지)."""
    exists = conn.execute(
        "SELECT 1 FROM device_install WHERE greenhouse_id = ? AND install_id = ?",
        (greenhouse_id, install_id),
    ).fetchone()
    if exists is None:
        conn.execute("INSERT INTO device_install(greenhouse_id, install_id) VALUES(?,?)",
                      (greenhouse_id, install_id))


def get_greenhouse_manager_user_id(conn: sqlite3.Connection, greenhouse_id: str) -> str | None:
    """1369-P1 §7.1(3) "온실은 정확히 1명의 사용자가 관리한다"
    (`greenhouse_manage`, `UNIQUE(greenhouse_id)`) — 그 온실의 관리자를
    돌려준다. `link_device_manage()`(F-176)의 호출자가 "이 장치의 관리자는
    누구인가"를 결정하는 데 쓴다. 없으면 None — 시드 누락 등 방어적 상황."""
    row = conn.execute(
        "SELECT user_id FROM greenhouse_manage WHERE greenhouse_id = ?", (greenhouse_id,)
    ).fetchone()
    return row["user_id"] if row is not None else None


def link_device_manage(conn: sqlite3.Connection, user_id: str, install_id: str) -> None:
    """F-176 — 1369-P1 §7.1(7) "설치된 장치들은 1명의 사용자에 의해
    관리된다" / §7.2.2.10. `UNIQUE(install_id)`가 강제하므로 이미 관리자가
    있으면 조용히 건너뛴다(재연결 시 재삽입 금지 — `link_device_install()`
    과 같은 멱등 패턴)."""
    exists = conn.execute(
        "SELECT 1 FROM device_manage WHERE install_id = ?", (install_id,)
    ).fetchone()
    if exists is None:
        conn.execute("INSERT INTO device_manage(user_id, install_id) VALUES(?,?)",
                      (user_id, install_id))


def get_greenhouse_location(conn: sqlite3.Connection, greenhouse_id: str) -> tuple[str | None, str | None]:
    """F-183 — 1369-P1 6.2.5 "장치설치정보에는... 설치위치 등이 포함되어야
    한다" / 7.2.2.5 "설치 위치 속성은 속성값과 단위가 함께 포함되어야
    한다". 이 참조 구현에는 장치별 세부 설치위치를 입력할 별도 수단이
    없다(0943 REQ_SET_CONNECTION은 위치를 나르지 않는다, API 명세서 §3
    쓰기 7건에도 없다) — F-176(장치 관리자 = 소속 온실 관리자)과 같은
    근거로, 그 장치가 설치된 온실 자신의 위치(`greenhouse_info.location`/
    `location_unit`)를 기본값으로 쓴다. 온실 위치도 없으면 (None, None) —
    지어내지 않는다(CLAUDE.md §1-1)."""
    row = conn.execute(
        "SELECT location, location_unit FROM greenhouse_info WHERE id = ?", (greenhouse_id,)
    ).fetchone()
    return (row["location"], row["location_unit"]) if row is not None else (None, None)


def get_default_greenhouse_id(conn: sqlite3.Connection) -> str | None:
    """이 참조 구현은 온실 1개 고정 데모다(`fixtures/seed.sql`, DB 스키마
    설계서 §7.4). 온실이 없으면 None — 호출자가 그 프레임 처리를 건너뛴다.
    여러 개면 가장 먼저 생성된 것을 쓴다(결정적 — created_at 오름차순)."""
    row = conn.execute(
        "SELECT id FROM greenhouse_info ORDER BY created_at ASC LIMIT 1"
    ).fetchone()
    return row["id"] if row is not None else None


# ═══════════════════════════════════════════════════════════════
#  C/D — env_state_data/env_measurement/env_measure/greenhouse_env
#         device_state_data/dsd_*/device_state  (SIAP I/O 스레드 소유)
#         NOTI_DEVICE_VALUE 결과 (FMS)
# ═══════════════════════════════════════════════════════════════

#: 그림 7-3 9개 서브타입 통합(env_measurement CHECK와 동일 집합)
ENV_SUBTYPES = frozenset({
    "TEMPERATURE", "HUMIDITY", "INSOLATION", "CO2", "WIND_DIRECTION",
    "WIND_SPEED", "SOIL_MOISTURE_TENSION", "EC", "PH", "RAIN_DETECTION",
})

#: 장치상태 6종(device_state_data CHECK와 동일 집합)
DEVICE_STATE_SUBTYPES = frozenset({
    "WINDOW_OPENER", "INSULATION_COVER", "IRRIGATION_PUMP",
    "IRRIGATION_VALVE", "FAN", "COOLING_HEATER",
})


def record_env_measurement(conn: sqlite3.Connection, *, install_id: str, greenhouse_id: str,
                            subtype: str, value: float, unit: str | None = None,
                            error_range: float | None = None, lower_limit: float | None = None,
                            upper_limit: float | None = None, measured_at: str | None = None,
                            location: str | None = None, location_unit: str | None = None) -> str:
    """env_state_data + env_measurement + env_measure + greenhouse_env 를
    한 측정 이벤트로 함께 기록한다 — 7.2.4.3/7.2.4.4가 요구하는 두 관계
    (장치↔환경, 온실↔환경) 모두 이 시점에 확정된다."""
    if subtype not in ENV_SUBTYPES:
        raise ValueError(f"미등록 환경 subtype: {subtype}")
    # 그림 7-3: RAIN_DETECTION은 측정값 단독 — 오차범위·유효범위는 CHECK가 거부한다.
    # 여기서 미리 비워 스키마의 이 결정을 그대로 존중한다(6.3.3.8, CLAUDE.md §3.5).
    if subtype == "RAIN_DETECTION":
        error_range = lower_limit = upper_limit = None
    esd_id = new_id()
    measured_at = measured_at or now_iso()
    conn.execute("INSERT INTO env_state_data(id,measured_at,location,location_unit) VALUES(?,?,?,?)",
                 (esd_id, measured_at, location, location_unit))
    conn.execute(
        "INSERT INTO env_measurement(id,subtype,value,unit,error_range,lower_limit,upper_limit)"
        " VALUES(?,?,?,?,?,?,?)",
        (esd_id, subtype, value, unit, error_range, lower_limit, upper_limit),
    )
    conn.execute("INSERT INTO env_measure(id,install_id,env_state_id) VALUES(?,?,?)",
                 (new_id(), install_id, esd_id))
    conn.execute("INSERT INTO greenhouse_env(id,greenhouse_id,env_state_id) VALUES(?,?,?)",
                 (new_id(), greenhouse_id, esd_id))
    return esd_id


def record_device_state(conn: sqlite3.Connection, *, install_id: str, subtype: str,
                         value: float, valid_range: str | None = None,
                         reported_at: str | None = None) -> str:
    """device_state_data + 서브타입 테이블 + device_state 관계를 함께 기록한다.

    구현 결정(표준 미규정, CLAUDE.md §3.5) — 0943 DEVICE_MAIN_INFO(표 7-14)는
    디바이스 1개당 값 1개만 나른다. 1369-P1의 장치상태 서브타입 중 2개 이상의
    물리량을 갖는 것(관수펌프의 압력+분사도, 송풍기의 전원+바람세기, 냉난방기의
    전원+온도+바람세기)은 이 프레임 구조로 한 번에 표현할 수 없다 — 주 필드에만
    값을 싣고 나머지는 NULL로 둔다. 전원(on/off) 필드는 NOT NULL이므로 값 != 0
    을 켜짐으로 해석한다. 별도 채널(device_id)로 나누는 것은 계약 확장이라
    CLAUDE.md §5 절차 대상이며 이 단계의 범위가 아니다."""
    if subtype not in DEVICE_STATE_SUBTYPES:
        raise ValueError(f"미등록 장치상태 subtype: {subtype}")
    dsd_id = new_id()
    reported_at = reported_at or now_iso()
    conn.execute("INSERT INTO device_state_data(id,reported_at,subtype) VALUES(?,?,?)",
                 (dsd_id, reported_at, subtype))
    if subtype == "WINDOW_OPENER":
        conn.execute("INSERT INTO dsd_window_opener(id,open_level,valid_range) VALUES(?,?,?)",
                     (dsd_id, value, valid_range))
    elif subtype == "INSULATION_COVER":
        conn.execute("INSERT INTO dsd_insulation_cover(id,angle,valid_range) VALUES(?,?,?)",
                     (dsd_id, value, valid_range))
    elif subtype == "IRRIGATION_PUMP":
        conn.execute(
            "INSERT INTO dsd_irrigation_pump(id,pressure,pressure_valid_range,spray_level,spray_valid_range)"
            " VALUES(?,?,?,NULL,NULL)",
            (dsd_id, value, valid_range),
        )
    elif subtype == "IRRIGATION_VALVE":
        conn.execute("INSERT INTO dsd_irrigation_valve(id,open_level,valid_range) VALUES(?,?,?)",
                     (dsd_id, value, valid_range))
    elif subtype == "FAN":
        conn.execute("INSERT INTO dsd_fan(id,power,wind_level,valid_range) VALUES(?,?,NULL,?)",
                     (dsd_id, 1 if value else 0, valid_range))
    elif subtype == "COOLING_HEATER":
        # F-157 — power 하나만 주 필드로 채운다(FAN과 같은 패턴). 이전에는
        # 같은 value를 power와 temperature 두 필드에 중복 기입해, 관측
        # 근거가 하나인데 두 물리량을 관측한 것처럼 보였다 — 위 §3.5
        # 결정("주 필드에만 값을 싣고 나머지는 NULL") 자체를 어겼다.
        conn.execute("INSERT INTO dsd_cooling_heater(id,power,temperature,wind_level) VALUES(?,?,NULL,NULL)",
                     (dsd_id, 1 if value else 0))
    conn.execute("INSERT INTO device_state(id,install_id,device_state_id) VALUES(?,?,?)",
                 (new_id(), install_id, dsd_id))
    return dsd_id


def record_operating_env(conn: sqlite3.Connection, *, device_state_id: str, env_state_id: str) -> None:
    """작동 환경 — 1369-P1 7.2.3.4 / 7.1(10). "특정한 시간에 온실 내 설치된
    장치의 상태"(장치상태)와 그 시점의 환경상태를 묶는다. `UNIQUE(env_state_id)`
    가 강제하므로 환경상태 1건은 정확히 하나의 장치상태에만 귀속된다 — 호출자
    (ingest.py, F-156)가 그 유일성을 보장한 뒤에만 부른다."""
    conn.execute("INSERT INTO operating_env(device_state_id,env_state_id) VALUES(?,?)",
                 (device_state_id, env_state_id))


# ═══════════════════════════════════════════════════════════════
#  F-6 — alert — NOTI_ERROR/NOTI_DISCONNECT 결과(SIAP I/O 스레드)와
#  CONTROL_TIMEOUT/NO_DATA(API 스레드, F-191)가 함께 쓴다. F-186과 같은
#  원칙 — `SiapLink.send()`가 동기 반환이라 재전송 소진을 API 스레드가
#  그 자리에서 알고, 미수집 판정(`check_stale_devices`)도 조회 시점에
#  API 스레드에서 돈다(전용 스케줄러 스레드를 새로 두지 않는다).
# ═══════════════════════════════════════════════════════════════

def record_alert(conn: sqlite3.Connection, *, kind: str, severity: str, message: str,
                  install_id: str | None = None, siap_nec: int | None = None,
                  frame_id: str | None = None, raised_at: str | None = None) -> str:
    """F-092 CHECK — `siap_nec`가 있으면 `frame_id`도 반드시 있어야 한다.
    호출자(ingest.py)가 NEC 알림을 기록할 때는 항상 `frame_id`를 함께 넘긴다."""
    if siap_nec is not None and frame_id is None:
        raise ValueError("siap_nec 가 있으면 frame_id 가 필수다 (0943 8.2.1.1, F-092)")
    id_ = new_id()
    raised_at = raised_at or now_iso()
    conn.execute(
        "INSERT INTO alert(id,raised_at,kind,severity,install_id,siap_nec,message,frame_id)"
        " VALUES(?,?,?,?,?,?,?,?)",
        (id_, raised_at, kind, severity, install_id, siap_nec, message, frame_id),
    )
    return id_


def list_alerts(conn: sqlite3.Connection, *, limit: int = 100) -> list[models.Alert]:
    rows = conn.execute(
        "SELECT * FROM alert ORDER BY raised_at DESC LIMIT ?", (limit,)
    ).fetchall()
    return [models.Alert.from_row(r) for r in rows]


def list_alerts_page(conn: sqlite3.Connection, *, since: str | None = None, until: str | None = None,
                      unacked: bool | None = None, limit: int = 100,
                      offset: int = 0) -> tuple[list[models.Alert], int]:
    """단계 6 — `GET /api/v1/alerts`(0937 6.4-3 · 6.5-2) 전용. `list_alerts()`
    는 단계 5부터 `list[Alert]`를 돌려주는 계약으로 굳어 있어(기존 회귀
    테스트 3건이 그 계약에 의존한다) 시그니처를 바꾸지 않는다 — 페이지네이션
    (`total` 포함, API 명세서 §4.7)이 필요한 이 호출을 별도 함수로 둔다."""
    where: list[str] = []
    params: list = []
    if since is not None:
        where.append("raised_at >= ?"); params.append(since)
    if until is not None:
        where.append("raised_at < ?"); params.append(until)
    if unacked is True:
        where.append("ack_at IS NULL")
    elif unacked is False:
        where.append("ack_at IS NOT NULL")
    wsql = ("WHERE " + " AND ".join(where)) if where else ""
    total = conn.execute(f"SELECT COUNT(*) AS c FROM alert {wsql}", params).fetchone()["c"]
    rows = conn.execute(
        f"SELECT * FROM alert {wsql} ORDER BY raised_at DESC LIMIT ? OFFSET ?",
        (*params, limit, offset),
    ).fetchall()
    return [models.Alert.from_row(r) for r in rows], total


# ═══════════════════════════════════════════════════════════════
#  G — frame_log · frame_violation  (SIAP I/O 스레드 소유) — 모든 프레임
# ═══════════════════════════════════════════════════════════════

def insert_frame_log(conn: sqlite3.Connection, *, t: float, direction: str, raw_hex: str,
                      version: int | None, msg_type: int | None, trans_type: int | None,
                      msg_id: int | None, payload_len: int | None, gcg_id: int | None,
                      node_id: int | None, is_valid: bool,
                      elements_json: str | None = None) -> str:
    id_ = new_id()
    conn.execute(
        "INSERT INTO frame_log(id,t,direction,raw_hex,version,msg_type,trans_type,msg_id,"
        "payload_len,gcg_id,node_id,is_valid,elements_json) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (id_, t, direction, raw_hex, version, msg_type, trans_type, msg_id,
         payload_len, gcg_id, node_id, 1 if is_valid else 0, elements_json),
    )
    return id_


def insert_frame_violation(conn: sqlite3.Connection, *, frame_id: str, code: int,
                            code_name: str, clause: str, detail: str | None = None) -> str:
    id_ = new_id()
    conn.execute(
        "INSERT INTO frame_violation(id,frame_id,code,code_name,clause,detail) VALUES(?,?,?,?,?,?)",
        (id_, frame_id, code, code_name, clause, detail),
    )
    return id_


def list_frame_log(conn: sqlite3.Connection, *, limit: int = 100) -> list[models.FrameLog]:
    rows = conn.execute(
        "SELECT * FROM frame_log ORDER BY t DESC LIMIT ?", (limit,)
    ).fetchall()
    return [models.FrameLog.from_row(r) for r in rows]


def list_frame_violations(conn: sqlite3.Connection, frame_id: str) -> list[models.FrameViolation]:
    rows = conn.execute(
        "SELECT * FROM frame_violation WHERE frame_id = ? ORDER BY id", (frame_id,)
    ).fetchall()
    return [models.FrameViolation.from_row(r) for r in rows]


# ═══════════════════════════════════════════════════════════════
#  단계 6 — API 스레드가 쓰는 테이블(아키텍처 §4.4-a③)과 읽기 전용 조회.
#  이 절 아래는 backend/services/*.py · backend/api.py 가 부르는 SQL이다.
#  쓰기 소유권은 여전히 호출자(API 스레드)가 지킨다 — 이 파일은 SQL만 안다.
# ═══════════════════════════════════════════════════════════════

try:                    # F-025 와 같은 원칙
    from contracts.frame import MsgKind, WIRE_CODE, WIRE_CODE_EXT
except ImportError:
    import pathlib as _pathlib
    import sys as _sys
    _sys.path.insert(0, str(_pathlib.Path(__file__).resolve().parent.parent))
    from contracts.frame import MsgKind, WIRE_CODE, WIRE_CODE_EXT

#: strict·extended 두 모드 모두에서 REQ_SET_CONNECTION 이 쓸 수 있는 wire code.
#: `frame_log.msg_type`은 실제 송신 당시 모드의 원시 코드이므로 둘 다 받는다.
_CONNECT_CODES = tuple({WIRE_CODE[MsgKind.REQ_SET_CONNECTION], WIRE_CODE_EXT[MsgKind.REQ_SET_CONNECTION]})


def _epoch_to_iso(t: float) -> str:
    return datetime.fromtimestamp(t, tz=timezone.utc).astimezone().isoformat(timespec="seconds")


# ── public_data_source / record — 0937 6.2 DMS ────────────────────────────

def list_public_data_sources(conn: sqlite3.Connection) -> list[models.PublicDataSource]:
    """`public_data_source`는 시드 전용(아키텍처 §4.4-a①) — 여기선 조회만."""
    rows = conn.execute("SELECT * FROM public_data_source ORDER BY registered_at").fetchall()
    return [models.PublicDataSource.from_row(r) for r in rows]


def get_public_data_source(conn: sqlite3.Connection, source_id: str) -> models.PublicDataSource | None:
    return get_by_id(conn, "public_data_source", source_id)


def insert_public_data_record(conn: sqlite3.Connection, *, source_id: str, payload: dict,
                               fetched_at: str | None = None, period_from: str | None = None,
                               period_to: str | None = None, region: str | None = None,
                               item: str | None = None) -> str:
    """0937 6.2 DMS 부속서 A 2.3 수집 이력. API 스레드 소유(아키텍처 §4.4-a③)
    — 외부 HTTP 호출이 SIAP I/O 스레드를 막으면 안 된다."""
    id_ = new_id()
    conn.execute(
        "INSERT INTO public_data_record(id,source_id,fetched_at,period_from,period_to,region,item,payload)"
        " VALUES(?,?,?,?,?,?,?,?)",
        (id_, source_id, fetched_at or now_iso(), period_from, period_to, region, item,
         json.dumps(payload, ensure_ascii=False)),
    )
    return id_


def list_public_data_records(conn: sqlite3.Connection, *, source_id: str | None = None,
                              since: str | None = None, until: str | None = None,
                              limit: int = 100, offset: int = 0) -> tuple[list[models.PublicDataRecord], int]:
    where: list[str] = []
    params: list = []
    if source_id is not None:
        where.append("source_id = ?"); params.append(source_id)
    if since is not None:
        where.append("fetched_at >= ?"); params.append(since)
    if until is not None:
        where.append("fetched_at < ?"); params.append(until)
    wsql = ("WHERE " + " AND ".join(where)) if where else ""
    total = conn.execute(f"SELECT COUNT(*) AS c FROM public_data_record {wsql}", params).fetchone()["c"]
    rows = conn.execute(
        f"SELECT * FROM public_data_record {wsql} ORDER BY fetched_at DESC LIMIT ? OFFSET ?",
        (*params, limit, offset),
    ).fetchall()
    return [models.PublicDataRecord.from_row(r) for r in rows], total


# ── control_model — 0937 6.3 MMS (시드 전용, 조회만) ───────────────────────

def get_control_model(conn: sqlite3.Connection, model_id: str) -> models.ControlModel | None:
    return get_by_id(conn, "control_model", model_id)


# ── control_rule — 0937 6.3 MMS / 부속서 A 3.2 (API 스레드 소유, §4.4-a③) ──

def insert_control_rule(conn: sqlite3.Connection, *, origin: str, draft_text: str,
                         model_id: str | None = None, generation: str | None = None,
                         condition_expr: str | None = None, created_at: str | None = None) -> str:
    id_ = new_id()
    conn.execute(
        "INSERT INTO control_rule(id,model_id,created_at,origin,generation,draft_text,"
        "condition_expr,action_json,target_install_id,approved_at,approved_by,"
        "rejected_at,rejected_by,reject_reason)"
        " VALUES(?,?,?,?,?,?,?,NULL,NULL,NULL,NULL,NULL,NULL,NULL)",
        (id_, model_id, created_at or now_iso(), origin, generation, draft_text, condition_expr),
    )
    return id_


def get_control_rule(conn: sqlite3.Connection, rule_id: str) -> models.ControlRule | None:
    return get_by_id(conn, "control_rule", rule_id)


def list_control_rules(conn: sqlite3.Connection, *, approved: bool | None = None,
                        limit: int = 100, offset: int = 0) -> tuple[list[models.ControlRule], int]:
    where = ""
    if approved is True:
        where = "WHERE approved_at IS NOT NULL"
    elif approved is False:
        where = "WHERE approved_at IS NULL"
    total = conn.execute(f"SELECT COUNT(*) AS c FROM control_rule {where}").fetchone()["c"]
    rows = conn.execute(
        f"SELECT * FROM control_rule {where} ORDER BY created_at DESC LIMIT ? OFFSET ?",
        (limit, offset),
    ).fetchall()
    return [models.ControlRule.from_row(r) for r in rows], total


def approve_control_rule(conn: sqlite3.Connection, rule_id: str, *, condition_expr: str,
                          action_json: str, target_install_id: str, approved_by: str,
                          approved_at: str | None = None) -> None:
    """단일 UPDATE로 승인 스냅샷 5필드를 동시에 채운다(API 명세서 §4.2) —
    `schema.sql`의 CHECK·트리거가 부분 상태·재승인·변조를 막는다. 실패하면
    `sqlite3.IntegrityError`를 그대로 던진다 — 호출자(services/mms.py)가
    `constraint` 이름을 메시지에서 뽑아 Problem 으로 옮긴다."""
    conn.execute(
        "UPDATE control_rule SET condition_expr=?, action_json=?, target_install_id=?,"
        " approved_at=?, approved_by=? WHERE id=?",
        (condition_expr, action_json, target_install_id, approved_at or now_iso(),
         approved_by, rule_id),
    )


def reject_control_rule(conn: sqlite3.Connection, rule_id: str, *, reason: str,
                         rejected_by: str, rejected_at: str | None = None) -> None:
    conn.execute(
        "UPDATE control_rule SET rejected_at=?, rejected_by=?, reject_reason=? WHERE id=?",
        (rejected_at or now_iso(), rejected_by, reason, rule_id),
    )


# ── control_execution — 0937 6.5 FCS (교차 소유, §4.4-a④ · F-186) ─────────

def insert_control_execution(conn: sqlite3.Connection, *, origin: str, install_id: str,
                              command: dict, rule_id: str | None = None,
                              issued_by: str | None = None, issued_at: str | None = None) -> str:
    """INSERT는 API 스레드가 한다 — 기록이 송신의 선행 조건이다(아키텍처 §3.2).
    미승인 규칙이면 `trg_exec_requires_approval` 등이 `sqlite3.IntegrityError`
    로 막는다 — 여기서 삼키지 않고 그대로 전파한다."""
    id_ = new_id()
    conn.execute(
        "INSERT INTO control_execution(id,origin,rule_id,issued_by,install_id,issued_at,"
        "command_json,siap_msg_id,result_rsc,responded_at)"
        " VALUES(?,?,?,?,?,?,?,NULL,NULL,NULL)",
        (id_, origin, rule_id, issued_by, install_id, issued_at or now_iso(),
         json.dumps(command, ensure_ascii=False)),
    )
    return id_


def update_execution_result(conn: sqlite3.Connection, exec_id: str, *,
                             siap_msg_id: int | None, result_rsc: int | None,
                             responded_at: str | None) -> None:
    """F-186 — `SiapLink.send()`가 응답을 동기 반환하므로 API 스레드가 이
    UPDATE도 (같은 커넥션으로) 직접 수행한다(아키텍처 §4.4-a④ 정정)."""
    conn.execute(
        "UPDATE control_execution SET siap_msg_id=?, result_rsc=?, responded_at=? WHERE id=?",
        (siap_msg_id, result_rsc, responded_at, exec_id),
    )


def get_control_execution(conn: sqlite3.Connection, exec_id: str) -> models.ControlExecution | None:
    return get_by_id(conn, "control_execution", exec_id)


def list_control_executions(conn: sqlite3.Connection, *, origin: str | None = None,
                             install_id: str | None = None, since: str | None = None,
                             until: str | None = None, limit: int = 100,
                             offset: int = 0) -> tuple[list[models.ControlExecution], int]:
    where: list[str] = []
    params: list = []
    if origin is not None:
        where.append("origin = ?"); params.append(origin)
    if install_id is not None:
        where.append("install_id = ?"); params.append(install_id)
    if since is not None:
        where.append("issued_at >= ?"); params.append(since)
    if until is not None:
        where.append("issued_at < ?"); params.append(until)
    wsql = ("WHERE " + " AND ".join(where)) if where else ""
    total = conn.execute(f"SELECT COUNT(*) AS c FROM control_execution {wsql}", params).fetchone()["c"]
    rows = conn.execute(
        f"SELECT * FROM control_execution {wsql} ORDER BY issued_at DESC LIMIT ? OFFSET ?",
        (*params, limit, offset),
    ).fetchall()
    return [models.ControlExecution.from_row(r) for r in rows], total


# ── 사용자 실재 확인 — API 명세서 §2.1 (X-User-Id 는 인증이 아니라 실재 확인) ──

def user_exists(conn: sqlite3.Connection, user_id: str) -> bool:
    return conn.execute("SELECT 1 FROM user_info WHERE id = ?", (user_id,)).fetchone() is not None


# ── device_install_info 조회 — `/nodes/{id}/devices`, `/device-property` ──

def get_device_install(conn: sqlite3.Connection, install_id: str) -> models.DeviceInstallInfo | None:
    return get_by_id(conn, "device_install_info", install_id)


def list_device_installs_by_node(conn: sqlite3.Connection, siap_node_id: int) -> list[models.DeviceInstallInfo]:
    rows = conn.execute(
        "SELECT * FROM device_install_info WHERE siap_node_id = ? ORDER BY siap_device_id",
        (siap_node_id,),
    ).fetchall()
    return [models.DeviceInstallInfo.from_row(r) for r in rows]


def list_device_installs_by_selector(conn: sqlite3.Connection, *, greenhouse_id: str | None = None,
                                      install_location: str | None = None,
                                      subtype: int | None = None) -> list[models.DeviceInstallInfo]:
    """0937 6.4-2 구역 일괄 선택 — `PATCH /device-property`(API 명세서 F-093).
    구역의 기본 의미는 온실 전체이며 `install_location`·`subtype`은 좁히는
    선택 항목이다."""
    where: list[str] = []
    params: list = []
    joins = ""
    if greenhouse_id is not None:
        joins = "JOIN device_install di ON di.install_id = device_install_info.id"
        where.append("di.greenhouse_id = ?"); params.append(greenhouse_id)
    if install_location is not None:
        where.append("device_install_info.install_location = ?"); params.append(install_location)
    if subtype is not None:
        where.append("device_install_info.siap_subtype = ?"); params.append(subtype)
    wsql = ("WHERE " + " AND ".join(where)) if where else ""
    rows = conn.execute(
        f"SELECT device_install_info.* FROM device_install_info {joins} {wsql}", params,
    ).fetchall()
    return [models.DeviceInstallInfo.from_row(r) for r in rows]


def update_device_property(conn: sqlite3.Connection, install_id: str, *,
                            unit: str | None = None, lower_limit: float | None = None,
                            upper_limit: float | None = None) -> None:
    """`PATCH /device-property`의 임계값(Lower/Upper Value, 표 7-15) 저장.
    `COALESCE`는 `unit`에만 건다 — `lower_limit`/`upper_limit`은 이 참조
    구현에서 이벤트 임계값 자체가 요청의 목적이라 넘긴 값(None 포함, 예:
    상한만 지정)을 그대로 반영한다(`upsert_device_install_info`의 F-170과는
    반대 방향 — 그쪽은 재연결이 값을 지우면 안 되고, 이쪽은 사용자가 값을
    지우려는 의도를 존중해야 한다)."""
    conn.execute(
        "UPDATE device_install_info SET updated_at=?, unit=COALESCE(?, unit),"
        " lower_limit=?, upper_limit=? WHERE id=?",
        (now_iso(), unit, lower_limit, upper_limit, install_id),
    )


# ── 환경상태 조회 — 0937 6.4 FMS `GET /telemetry` ──────────────────────────

def list_telemetry(conn: sqlite3.Connection, *, install_id: str | None = None,
                    subtype: str | None = None, since: str | None = None,
                    until: str | None = None, limit: int = 100,
                    offset: int = 0) -> tuple[list[sqlite3.Row], int]:
    """1369-P1 6.3.3 환경상태 + 7.2.4.3 환경측정 관계. `install_id`는 LEFT
    JOIN 결과라 없을 수 있다(스키마상 nullable 관계는 아니지만 이 조회는
    방어적으로 남겨 둔다)."""
    where: list[str] = []
    params: list = []
    if install_id is not None:
        where.append("em.install_id = ?"); params.append(install_id)
    if subtype is not None:
        where.append("m.subtype = ?"); params.append(subtype)
    if since is not None:
        where.append("s.measured_at >= ?"); params.append(since)
    if until is not None:
        where.append("s.measured_at < ?"); params.append(until)
    wsql = ("WHERE " + " AND ".join(where)) if where else ""
    base = (
        "FROM env_state_data s JOIN env_measurement m ON m.id = s.id "
        "LEFT JOIN env_measure em ON em.env_state_id = s.id " + wsql
    )
    total = conn.execute(f"SELECT COUNT(*) AS c {base}", params).fetchone()["c"]
    rows = conn.execute(
        f"SELECT s.id, s.measured_at, s.location, s.location_unit, m.subtype, m.value,"
        f" m.unit, m.error_range, m.lower_limit, m.upper_limit, em.install_id {base}"
        f" ORDER BY s.measured_at DESC LIMIT ? OFFSET ?",
        (*params, limit, offset),
    ).fetchall()
    return rows, total


#: 서브타입 → (서브타입 테이블, `DeviceState.attributes`로 노출할 컬럼).
#: `record_device_state()`가 쓰는 테이블 집합을 조회 방향으로 미러링한 것 —
#: CLAUDE.md §1-6이 금지하는 하드코딩은 board/MCU 분기다(0937 대조표 §4.3
#: "종류는 Subtype 레지스트리 조회로만 해석"). SQLite 테이블명은 리터럴일
#: 수밖에 없고, 이 집합은 이미 위 DEVICE_STATE_SUBTYPES·schema.sql CHECK와
#: 동일한 6종이다 — 새 MCU 보드 추가는 이 표를 건드리지 않는다.
_DSD_ATTRS: dict[str, tuple[str, tuple[str, ...]]] = {
    "WINDOW_OPENER": ("dsd_window_opener", ("open_level", "valid_range")),
    "INSULATION_COVER": ("dsd_insulation_cover", ("angle", "valid_range")),
    "IRRIGATION_PUMP": ("dsd_irrigation_pump",
                         ("pressure", "pressure_valid_range", "spray_level", "spray_valid_range")),
    "IRRIGATION_VALVE": ("dsd_irrigation_valve", ("open_level", "valid_range")),
    "FAN": ("dsd_fan", ("power", "wind_level", "valid_range")),
    "COOLING_HEATER": ("dsd_cooling_heater", ("power", "temperature", "wind_level")),
}


def list_device_states(conn: sqlite3.Connection, *, install_id: str | None = None,
                        subtype: str | None = None, since: str | None = None,
                        until: str | None = None, limit: int = 100,
                        offset: int = 0) -> tuple[list[sqlite3.Row], int]:
    where: list[str] = []
    params: list = []
    if install_id is not None:
        where.append("ds.install_id = ?"); params.append(install_id)
    if subtype is not None:
        where.append("d.subtype = ?"); params.append(subtype)
    if since is not None:
        where.append("d.reported_at >= ?"); params.append(since)
    if until is not None:
        where.append("d.reported_at < ?"); params.append(until)
    wsql = ("WHERE " + " AND ".join(where)) if where else ""
    base = "FROM device_state_data d LEFT JOIN device_state ds ON ds.device_state_id = d.id " + wsql
    total = conn.execute(f"SELECT COUNT(*) AS c {base}", params).fetchone()["c"]
    rows = conn.execute(
        f"SELECT d.id, d.reported_at, d.subtype, ds.install_id {base}"
        f" ORDER BY d.reported_at DESC LIMIT ? OFFSET ?",
        (*params, limit, offset),
    ).fetchall()
    return rows, total


def device_state_attributes(conn: sqlite3.Connection, dsd_id: str, subtype: str) -> dict:
    entry = _DSD_ATTRS.get(subtype)
    if entry is None:
        return {}
    table, cols = entry
    row = conn.execute(f"SELECT * FROM {table} WHERE id = ?", (dsd_id,)).fetchone()
    if row is None:
        return {}
    return {c: row[c] for c in cols}


# ── frame_log 조회 확장 — `GET /frames`, `/frames/violations`, `/frames/{id}` ─

def list_frames(conn: sqlite3.Connection, *, direction: str | None = None,
                 valid: bool | None = None, node_id: int | None = None,
                 since: float | None = None, until: float | None = None,
                 limit: int = 100, offset: int = 0) -> tuple[list[models.FrameLog], int]:
    where: list[str] = []
    params: list = []
    if direction is not None:
        where.append("direction = ?"); params.append(direction)
    if valid is not None:
        where.append("is_valid = ?"); params.append(1 if valid else 0)
    if node_id is not None:
        where.append("node_id = ?"); params.append(node_id)
    if since is not None:
        where.append("t >= ?"); params.append(since)
    if until is not None:
        where.append("t < ?"); params.append(until)
    wsql = ("WHERE " + " AND ".join(where)) if where else ""
    total = conn.execute(f"SELECT COUNT(*) AS c FROM frame_log {wsql}", params).fetchone()["c"]
    rows = conn.execute(
        f"SELECT * FROM frame_log {wsql} ORDER BY t DESC LIMIT ? OFFSET ?",
        (*params, limit, offset),
    ).fetchall()
    return [models.FrameLog.from_row(r) for r in rows], total


def list_violation_frames(conn: sqlite3.Connection, *, code: int | None = None,
                           clause: str | None = None, since: float | None = None,
                           until: float | None = None, limit: int = 100,
                           offset: int = 0) -> tuple[list[models.FrameLog], int]:
    """`GET /frames/violations` — 위반 코드·조항으로 좁힌 격리 프레임(0943 7.3.1)."""
    where = ["f.is_valid = 0"]
    params: list = []
    if since is not None:
        where.append("f.t >= ?"); params.append(since)
    if until is not None:
        where.append("f.t < ?"); params.append(until)
    if code is not None:
        where.append("v.code = ?"); params.append(code)
    if clause is not None:
        where.append("v.clause = ?"); params.append(clause)
    wsql = "WHERE " + " AND ".join(where)
    base = f"FROM frame_log f JOIN frame_violation v ON v.frame_id = f.id {wsql}"
    total = conn.execute(f"SELECT COUNT(DISTINCT f.id) AS c {base}", params).fetchone()["c"]
    rows = conn.execute(
        f"SELECT DISTINCT f.* {base} ORDER BY f.t DESC LIMIT ? OFFSET ?",
        (*params, limit, offset),
    ).fetchall()
    return [models.FrameLog.from_row(r) for r in rows], total


def get_frame(conn: sqlite3.Connection, frame_id: str) -> models.FrameLog | None:
    return get_by_id(conn, "frame_log", frame_id)


def frame_judgement(conn: sqlite3.Connection, frame: models.FrameLog) -> str:
    """F-060·F-085 — `violations`가 비어도 alert 일 수 있다(정상 NEC 알림).
    is_valid=0 이면 언제나 violation. is_valid=1 이면 이 프레임을 원인으로
    삼은 `alert` 행이 있는지로 가른다(`alert.frame_id`, F-092)."""
    if not frame.is_valid:
        return "violation"
    row = conn.execute("SELECT 1 FROM alert WHERE frame_id = ? LIMIT 1", (frame.id,)).fetchone()
    return "alert" if row is not None else "normal"


# ── 노드 연결·최근수신 시각 — `GET /nodes` (in-memory registry 보강) ───────

def node_connected_at(conn: sqlite3.Connection, node_id: int) -> str | None:
    """0943 8.1.1 연결 설정 완료 시각 — 그 노드의 첫 정상 REQ_SET_CONNECTION
    수신시각을 ISO 8601 로 돌려준다. `NodeProperty`(contracts/frame.py)엔
    시각 필드가 없어 `SiapLink.registry()`만으로는 알 수 없다 — DB가 유일한
    출처다."""
    placeholders = ",".join("?" for _ in _CONNECT_CODES)
    row = conn.execute(
        f"SELECT MIN(t) AS t0 FROM frame_log WHERE node_id = ? AND direction = 'rx'"
        f" AND is_valid = 1 AND msg_type IN ({placeholders})",
        (node_id, *_CONNECT_CODES),
    ).fetchone()
    return _epoch_to_iso(row["t0"]) if row and row["t0"] is not None else None


def node_last_seen_at(conn: sqlite3.Connection, node_id: int) -> str | None:
    row = conn.execute(
        "SELECT MAX(t) AS t1 FROM frame_log WHERE node_id = ? AND direction = 'rx' AND is_valid = 1",
        (node_id,),
    ).fetchone()
    return _epoch_to_iso(row["t1"]) if row and row["t1"] is not None else None


# ── DB 제약 위반 → 사람이 읽을 트리거 이름 (API 명세서 §4.5 `constraint`) ────

#: `RAISE(ABORT, '메시지')`의 메시지는 트리거의 SQL 이름이 아니라 자유
#: 문자열이다 — sqlite3 예외에는 트리거 이름이 실리지 않으므로, `schema.sql`
#: 의 각 트리거가 실제로 내는 메시지 원문을 그대로 키로 매핑한다. 새 트리거를
#: 추가하면서 이 표를 잊으면 `constraint`가 `None`으로 빠질 뿐 예외 자체는
#: 그대로 전파되므로(§11.5 "근거 없이 기각하지 않는다"와 같은 정직성 원칙),
#: 조용히 틀린 이름을 보고하는 것보다 안전하다.
_TRIGGER_MESSAGES: dict[str, str] = {
    "0937 A.3.2: control_execution requires an approved rule": "trg_exec_requires_approval",
    "0937 A.3.2: command_json must equal the approved action_json": "trg_exec_command_matches_approved",
    "0937 6.5: install_id must equal the approved target_install_id": "trg_exec_target_matches_approved",
    "control_execution authority fields are immutable": "trg_exec_rule_immutable",
    "0937 6.3: approved action_json is immutable": "trg_rule_action_immutable_after_approval",
    "0937 A.3.2: approved condition_expr is immutable": "trg_rule_condition_immutable_after_approval",
    "0937 A.3.2: approved target_install_id is immutable": "trg_rule_target_immutable_after_approval",
    "0937 6.3: approval cannot be revoked; create a new rule": "trg_rule_approval_irrevocable",
    "0937 A.3.2: approved_by is immutable once approved": "trg_rule_approver_immutable",
    "0937 A.3.2: approved_at is immutable once approved": "trg_rule_approved_at_immutable",
    "0937 A.3.2: rejection is immutable; create a new rule": "trg_rule_reject_immutable",
}


def constraint_name_from_error(e: Exception) -> str | None:
    """`sqlite3.IntegrityError`(CHECK) 또는 `sqlite3.OperationalError`(트리거의
    `RAISE(ABORT,...)`가 실제로 이 타입으로 온다) 메시지에서 제약/트리거
    이름을 뽑는다. 매핑에 없으면(CHECK 제약 위반은 이름이 아니라 컬럼·조건
    이 그대로 메시지에 실린다) `None` — 호출자는 원본 메시지를 `detail`로는
    그대로 보존한다."""
    msg = str(e)
    for needle, name in _TRIGGER_MESSAGES.items():
        if needle in msg:
            return name
    return None
