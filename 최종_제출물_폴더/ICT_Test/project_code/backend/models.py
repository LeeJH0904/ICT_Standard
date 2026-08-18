"""
backend/models.py — 읽기 전용 dataclass. ORM을 쓰지 않는다.

`schema.sql`이 정본이다. 이 파일은 그 행을 담는 그릇일 뿐 제약을 다시 정의하지
않는다 — 스키마 무결성은 DB 제약에만 있다. 모든 dataclass는 `frozen=True`.

각 클래스는 `from_row(row: sqlite3.Row) -> Self`를 갖는다. `sqlite3.Row`는
컬럼명으로 접근한다 — 위치 인덱스로 읽으면 컬럼 추가 시 조용히 깨진다.

테이블 31개 = A5 + B4 + C10 + D3 + E1 + F6 + G2.
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass


# ═══════════════════════════════════════════════════════════════
#  A. 설정형 데이터  (1369-Part1 6.2 / 7.2.2)
# ═══════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class FarmInfo:                                   # A-1 — 6.2.2 / 7.2.2.2
    id: str
    created_at: str
    updated_at: str
    name: str
    owner_id: str
    location: str | None
    location_type: str | None
    location_unit: str | None
    area_value: float | None
    area_error: float | None
    area_unit: str | None

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> "FarmInfo":
        return cls(row["id"], row["created_at"], row["updated_at"], row["name"], row["owner_id"],
                    row["location"], row["location_type"], row["location_unit"],
                    row["area_value"], row["area_error"], row["area_unit"])


@dataclass(frozen=True)
class GreenhouseInfo:                              # A-2 — 6.2.3 / 7.2.2.3
    id: str
    created_at: str
    updated_at: str
    name: str
    location: str | None
    location_type: str | None
    location_unit: str | None
    width_value: float | None
    width_error: float | None
    width_unit: str | None
    height_value: float | None
    height_error: float | None
    height_unit: str | None
    length_value: float | None
    length_error: float | None
    length_unit: str | None
    gh_type: str | None
    medium_type: str | None
    irrigation_type: str | None
    heating_type: str | None
    crop: str | None                                # 생육작물 (1369-P1 6.2.3 본문)
    crop_season: str | None
    usage_state: str | None

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> "GreenhouseInfo":
        return cls(row["id"], row["created_at"], row["updated_at"], row["name"],
                    row["location"], row["location_type"], row["location_unit"],
                    row["width_value"], row["width_error"], row["width_unit"],
                    row["height_value"], row["height_error"], row["height_unit"],
                    row["length_value"], row["length_error"], row["length_unit"],
                    row["gh_type"], row["medium_type"], row["irrigation_type"], row["heating_type"],
                    row["crop"], row["crop_season"], row["usage_state"])


@dataclass(frozen=True)
class DeviceInfo:                                  # A-3 — 6.2.4 / 7.2.2.4
    id: str
    created_at: str
    updated_at: str
    device_name: str
    device_kind: str
    model_name: str                                 # 불변, 전역 식별
    manufacturer: str | None
    device_characteristics: str | None              # 장치특성 (1369-P1 6.2.4)

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> "DeviceInfo":
        return cls(row["id"], row["created_at"], row["updated_at"], row["device_name"],
                    row["device_kind"], row["model_name"], row["manufacturer"],
                    row["device_characteristics"])


@dataclass(frozen=True)
class DeviceInstallInfo:                           # A-4 — 6.2.5 / 7.2.2.5 (+0943 확장)
    id: str
    created_at: str
    updated_at: str
    device_name: str
    installed_at: str                                 # 설치일자 (1369-P1 6.2.5)
    install_location: str | None
    install_loc_unit: str | None
    device_info_id: str
    siap_node_id: int | None
    siap_device_id: int | None
    siap_subtype: int | None
    siap_value_type: int | None
    transfer_mode: str | None
    period_sec: int | None
    unit: str | None
    lower_limit: float | None
    upper_limit: float | None
    precision_val: float | None

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> "DeviceInstallInfo":
        return cls(row["id"], row["created_at"], row["updated_at"], row["device_name"],
                    row["installed_at"], row["install_location"], row["install_loc_unit"],
                    row["device_info_id"], row["siap_node_id"], row["siap_device_id"],
                    row["siap_subtype"],
                    row["siap_value_type"] if "siap_value_type" in row.keys() else None,
                    row["transfer_mode"], row["period_sec"],
                    row["unit"], row["lower_limit"], row["upper_limit"], row["precision_val"])


@dataclass(frozen=True)
class UserInfo:                                    # A-5 — 6.2.6 / 7.2.2.6
    id: str
    created_at: str
    updated_at: str
    deleted_at: str | None
    name: str
    group_id: str | None
    group_role: str | None

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> "UserInfo":
        return cls(row["id"], row["created_at"], row["updated_at"], row["deleted_at"],
                    row["name"], row["group_id"], row["group_role"])


# ═══════════════════════════════════════════════════════════════
#  B. 설정형 데이터 간 관계  (1369-Part1 7.2.2.7 ~ 7.2.2.10)
# ═══════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class GreenhouseOwn:                               # B-1 — 7.2.2.7
    farm_id: str
    greenhouse_id: str

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> "GreenhouseOwn":
        return cls(row["farm_id"], row["greenhouse_id"])


@dataclass(frozen=True)
class GreenhouseManage:                            # B-2 — 7.2.2.8
    greenhouse_id: str
    user_id: str

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> "GreenhouseManage":
        return cls(row["greenhouse_id"], row["user_id"])


@dataclass(frozen=True)
class DeviceInstall:                               # B-3 — 7.2.2.9
    greenhouse_id: str
    install_id: str

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> "DeviceInstall":
        return cls(row["greenhouse_id"], row["install_id"])


@dataclass(frozen=True)
class DeviceManage:                                # B-4 — 7.2.2.10
    user_id: str
    install_id: str

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> "DeviceManage":
        return cls(row["user_id"], row["install_id"])


# ═══════════════════════════════════════════════════════════════
#  C. 측정형 데이터  (1369-Part1 6.3 / 7.2.3)
# ═══════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class DeviceStateData:                             # C-1 — 7.2.3.2
    id: str
    reported_at: str
    subtype: str

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> "DeviceStateData":
        return cls(row["id"], row["reported_at"], row["subtype"])


@dataclass(frozen=True)
class DsdWindowOpener:                             # C-1-a — 6.3.4.2
    id: str
    open_level: float
    valid_range: str | None

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> "DsdWindowOpener":
        return cls(row["id"], row["open_level"], row["valid_range"])


@dataclass(frozen=True)
class DsdInsulationCover:                          # C-1-b — 6.3.4.3
    id: str
    angle: float
    valid_range: str | None

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> "DsdInsulationCover":
        return cls(row["id"], row["angle"], row["valid_range"])


@dataclass(frozen=True)
class DsdIrrigationPump:                           # C-1-c — 6.3.4.5
    id: str
    pressure: float | None
    pressure_valid_range: str | None
    spray_level: float | None
    spray_valid_range: str | None

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> "DsdIrrigationPump":
        return cls(row["id"], row["pressure"], row["pressure_valid_range"],
                    row["spray_level"], row["spray_valid_range"])


@dataclass(frozen=True)
class DsdIrrigationValve:                          # C-1-d — 6.3.4.6
    id: str
    open_level: float
    valid_range: str | None

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> "DsdIrrigationValve":
        return cls(row["id"], row["open_level"], row["valid_range"])


@dataclass(frozen=True)
class DsdFan:                                      # C-1-e — 6.3.4.4
    id: str
    power: int
    wind_level: float | None
    valid_range: str | None

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> "DsdFan":
        return cls(row["id"], row["power"], row["wind_level"], row["valid_range"])


@dataclass(frozen=True)
class DsdCoolingHeater:                            # C-1-f — 6.3.4.7
    id: str
    power: int
    temperature: float | None
    wind_level: float | None

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> "DsdCoolingHeater":
        return cls(row["id"], row["power"], row["temperature"], row["wind_level"])


@dataclass(frozen=True)
class EnvStateData:                                # C-2 — 7.2.3.3
    id: str
    measured_at: str
    location: str | None
    location_unit: str | None

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> "EnvStateData":
        return cls(row["id"], row["measured_at"], row["location"], row["location_unit"])


@dataclass(frozen=True)
class EnvMeasurement:                              # C-2-a — 그림 7-3 9종 통합
    id: str
    subtype: str
    value: float
    unit: str | None
    error_range: float | None
    lower_limit: float | None
    upper_limit: float | None

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> "EnvMeasurement":
        return cls(row["id"], row["subtype"], row["value"], row["unit"],
                    row["error_range"], row["lower_limit"], row["upper_limit"])


@dataclass(frozen=True)
class OperatingEnv:                                # C-3 — 7.2.3.4
    device_state_id: str
    env_state_id: str

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> "OperatingEnv":
        return cls(row["device_state_id"], row["env_state_id"])


# ═══════════════════════════════════════════════════════════════
#  D. 설정형 ↔ 측정형 관계  (1369-Part1 7.2.4)
# ═══════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class DeviceState:                                 # D-1 — 7.2.4.2
    id: str
    install_id: str
    device_state_id: str

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> "DeviceState":
        return cls(row["id"], row["install_id"], row["device_state_id"])


@dataclass(frozen=True)
class EnvMeasure:                                  # D-2 — 7.2.4.3
    id: str
    install_id: str
    env_state_id: str

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> "EnvMeasure":
        return cls(row["id"], row["install_id"], row["env_state_id"])


@dataclass(frozen=True)
class GreenhouseEnv:                               # D-3 — 7.2.4.4
    id: str
    greenhouse_id: str
    env_state_id: str

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> "GreenhouseEnv":
        return cls(row["id"], row["greenhouse_id"], row["env_state_id"])


# ═══════════════════════════════════════════════════════════════
#  E. 설정형 데이터 변경 이력  (1369-Part1 6.2.1)
# ═══════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class ConfigChangeLog:                             # E-1
    id: str
    changed_at: str
    table_name: str
    row_id: str
    operation: str                                  # CREATE / UPDATE / DELETE
    changes: str | None
    user_id: str | None
    version: int

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> "ConfigChangeLog":
        return cls(row["id"], row["changed_at"], row["table_name"], row["row_id"],
                    row["operation"], row["changes"], row["user_id"], row["version"])


# ═══════════════════════════════════════════════════════════════
#  F. 서비스 계층  (TTAK.KO-10.0937)
# ═══════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class PublicDataSource:                            # F-1 — 0937 6.2 DMS
    id: str
    name: str
    provider: str
    registered_at: str
    updated_at: str | None
    source_url: str
    license: str | None
    scope: str | None

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> "PublicDataSource":
        return cls(row["id"], row["name"], row["provider"], row["registered_at"],
                    row["updated_at"], row["source_url"], row["license"], row["scope"])


@dataclass(frozen=True)
class PublicDataRecord:                            # F-2 — 0937 부속서 A 2.3
    id: str
    source_id: str
    fetched_at: str
    period_from: str | None
    period_to: str | None
    region: str | None
    item: str | None
    payload: str

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> "PublicDataRecord":
        return cls(row["id"], row["source_id"], row["fetched_at"], row["period_from"],
                    row["period_to"], row["region"], row["item"], row["payload"])


@dataclass(frozen=True)
class ControlModel:                                # F-3 — 0937 6.3 MMS
    id: str
    created_at: str
    name: str
    input_spec: str
    output_spec: str
    exec_method: str
    protocol: str | None
    data_format: str | None
    period_sec: int | None
    developer: str | None

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> "ControlModel":
        return cls(row["id"], row["created_at"], row["name"], row["input_spec"],
                    row["output_spec"], row["exec_method"], row["protocol"],
                    row["data_format"], row["period_sec"], row["developer"])


@dataclass(frozen=True)
class ControlRule:                                 # F-4 — 0937 6.3 / 부속서 A 3.3
    id: str
    model_id: str | None
    created_at: str
    origin: str                                      # AI_DRAFT / WIZARD / SCRIPT
    generation: str | None                           # AI / THRESHOLD_FALLBACK / WIZARD / SCRIPT
    draft_text: str
    condition_expr: str | None
    action_json: str | None
    target_install_id: str | None                    # 승인된 제어 대상 장치
    approved_at: str | None
    approved_by: str | None
    rejected_at: str | None                          # 거부도 영속 상태다
    rejected_by: str | None
    reject_reason: str | None

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> "ControlRule":
        return cls(row["id"], row["model_id"], row["created_at"], row["origin"], row["generation"],
                    row["draft_text"], row["condition_expr"], row["action_json"],
                    row["target_install_id"], row["approved_at"], row["approved_by"],
                    row["rejected_at"], row["rejected_by"], row["reject_reason"])

    @property
    def is_approved(self) -> bool:
        return self.approved_at is not None

    @property
    def is_rejected(self) -> bool:
        return self.rejected_at is not None


@dataclass(frozen=True)
class ControlExecution:                            # F-5 — 0937 6.5 FCS / 부속서 A 3.3
    id: str
    origin: str                                      # RULE / MANUAL
    rule_id: str | None
    issued_by: str | None
    install_id: str
    issued_at: str
    command_json: str
    siap_msg_id: int | None
    result_rsc: int | None
    responded_at: str | None

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> "ControlExecution":
        return cls(row["id"], row["origin"], row["rule_id"], row["issued_by"], row["install_id"],
                    row["issued_at"], row["command_json"], row["siap_msg_id"],
                    row["result_rsc"], row["responded_at"])


@dataclass(frozen=True)
class Alert:                                       # F-6 — 0937 6.4 FMS / 6.5 FCS
    id: str
    raised_at: str
    kind: str                                        # NO_DATA/NODE_ERROR/DISCONNECT/THRESHOLD/CONTROL_TIMEOUT
    severity: str                                     # INFO/WARN/CRITICAL
    install_id: str | None
    siap_nec: int | None
    message: str
    ack_at: str | None
    frame_id: str | None                              # NEC 알림 결속

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> "Alert":
        return cls(row["id"], row["raised_at"], row["kind"], row["severity"], row["install_id"],
                    row["siap_nec"], row["message"], row["ack_at"], row["frame_id"])


# ═══════════════════════════════════════════════════════════════
#  G. 프레임 로그 및 표준 준수 검증  (기능 2 / TTAK.KO-10.0943 7장)
# ═══════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class FrameLog:                                    # G-1
    id: str
    t: float
    direction: str                                    # rx / tx
    raw_hex: str
    version: int | None
    msg_type: int | None
    trans_type: int | None
    msg_id: int | None
    payload_len: int | None
    gcg_id: int | None
    node_id: int | None
    is_valid: bool
    elements_json: str | None = None   # device_main_infos/device_properties 그대로

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> "FrameLog":
        return cls(row["id"], row["t"], row["direction"], row["raw_hex"],
                    row["version"], row["msg_type"], row["trans_type"], row["msg_id"],
                    row["payload_len"], row["gcg_id"], row["node_id"], bool(row["is_valid"]),
                    row["elements_json"])


@dataclass(frozen=True)
class FrameViolation:                              # G-2 — 화면에 조항 번호를 그대로 표시
    id: str
    frame_id: str
    code: int
    code_name: str
    clause: str
    detail: str | None

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> "FrameViolation":
        return cls(row["id"], row["frame_id"], row["code"], row["code_name"],
                    row["clause"], row["detail"])


# 31개 = A5 + B4 + C10 + D3 + E1 + F6 + G2 — schema.sql 의 테이블명 → dataclass 매핑.
# 정본은 schema.sql 이며 이 표는 매핑일 뿐이다.
TABLE_MODEL: dict[str, type] = {
    "farm_info": FarmInfo,
    "greenhouse_info": GreenhouseInfo,
    "device_info": DeviceInfo,
    "device_install_info": DeviceInstallInfo,
    "user_info": UserInfo,
    "greenhouse_own": GreenhouseOwn,
    "greenhouse_manage": GreenhouseManage,
    "device_install": DeviceInstall,
    "device_manage": DeviceManage,
    "device_state_data": DeviceStateData,
    "dsd_window_opener": DsdWindowOpener,
    "dsd_insulation_cover": DsdInsulationCover,
    "dsd_irrigation_pump": DsdIrrigationPump,
    "dsd_irrigation_valve": DsdIrrigationValve,
    "dsd_fan": DsdFan,
    "dsd_cooling_heater": DsdCoolingHeater,
    "env_state_data": EnvStateData,
    "env_measurement": EnvMeasurement,
    "operating_env": OperatingEnv,
    "device_state": DeviceState,
    "env_measure": EnvMeasure,
    "greenhouse_env": GreenhouseEnv,
    "config_change_log": ConfigChangeLog,
    "public_data_source": PublicDataSource,
    "public_data_record": PublicDataRecord,
    "control_model": ControlModel,
    "control_rule": ControlRule,
    "control_execution": ControlExecution,
    "alert": Alert,
    "frame_log": FrameLog,
    "frame_violation": FrameViolation,
}
