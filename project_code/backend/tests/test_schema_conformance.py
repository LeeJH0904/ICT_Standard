"""
backend/tests/test_schema_conformance.py — DB 스키마 설계서 §6.2 (표준 유래
제약 동작 테스트 98종)을 pytest로 이식한 것이다(개발 착수 지시서 §3.7).

정본은 `project_docs/db/verify.py` — 이 파일은 그 케이스 목록을 **같은
내용으로 다시** 만든다(같은 명세서를 두 번 타이핑해 같은 판정이 나오는지가
교차 검증이다, CLAUDE.md §6.2와 같은 원칙). `project_code/`는 `project_docs/`
를 import하지 않으므로(CLAUDE.md §2.2) 케이스를 공유 모듈로 빼지 않고
독립적으로 다시 적는다. 대상 스키마는 `project_code/backend/schema.sql`
(`project_docs/db/schema.sql`과 동기, F-153).

CLAUDE.md §3.2 — 테스트 함수명에 조항 번호를 넣는다. 98건을 손으로 각각
def 하는 대신, 아래 케이스 표에서 **실제 개별 pytest 함수를 생성**한다 —
`pytest --collect-only`에 98개의 개별 이름(조항 번호 포함)이 그대로 뜬다.
"""
from __future__ import annotations

import re
import sqlite3
import uuid
from pathlib import Path

SCHEMA_PATH = Path(__file__).resolve().parent.parent / "schema.sql"
NOW = "2026-08-01T09:00:00+09:00"


def _u() -> str:
    return str(uuid.uuid4())


def _fresh() -> sqlite3.Connection:
    con = sqlite3.connect(":memory:")
    con.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
    con.execute("PRAGMA foreign_keys=ON")
    return con


def _seed(con: sqlite3.Connection) -> dict[str, str]:
    ids: dict[str, str] = {}
    ids['user'] = _u()
    con.execute("INSERT INTO user_info(id,created_at,updated_at,name,group_id,group_role)"
                " VALUES(?,?,?,'관리자','g1','ADMIN')", (ids['user'], NOW, NOW))
    ids['farm'] = _u()
    con.execute("INSERT INTO farm_info(id,created_at,updated_at,name,owner_id,"
                "location,location_type,location_unit,area_value,area_error,area_unit)"
                " VALUES(?,?,?,'테스트농장',?,'37.4,127.1','GPS','deg',1000,1,'m2')",
                (ids['farm'], NOW, NOW, ids['user']))
    ids['gh'] = _u()
    con.execute("INSERT INTO greenhouse_info(id,created_at,updated_at,name,"
                "width_value,height_value,length_value,gh_type,medium_type,irrigation_type,heating_type,"
                "crop,crop_season,usage_state) VALUES(?,?,?,'1호온실',6,3,30,'단동','토경','점적','온풍',"
                "'토마토','2026춘작','사용중')", (ids['gh'], NOW, NOW))
    ids['dev'] = _u()
    con.execute("INSERT INTO device_info(id,created_at,updated_at,device_name,device_kind,model_name,manufacturer)"
                " VALUES(?,?,?,'온습도센서','SENSOR','DHT22','Aosong')", (ids['dev'], NOW, NOW))
    ids['inst'] = _u()
    con.execute("INSERT INTO device_install_info(id,created_at,updated_at,device_name,"
                "installed_at,install_location,install_loc_unit,device_info_id,siap_node_id,siap_device_id,siap_subtype,"
                "unit,lower_limit,upper_limit,precision_val)"
                " VALUES(?,?,?,'중앙온습도',?,'중앙 상단','m',?,3,1,1,'℃',-40,80,0.1)",
                (ids['inst'], NOW, NOW, NOW, ids['dev']))
    ids['esd'] = _u()
    con.execute("INSERT INTO env_state_data(id,measured_at,location,location_unit)"
                " VALUES(?,?,'중앙 상단','m')", (ids['esd'], NOW))
    con.execute("INSERT INTO env_measurement(id,subtype,value,unit,error_range,lower_limit,upper_limit)"
                " VALUES(?,'TEMPERATURE',25.3,'℃',0.1,-40,80)", (ids['esd'],))
    ids['dsd'] = _u()
    con.execute("INSERT INTO device_state_data(id,reported_at,subtype)"
                " VALUES(?,?,'IRRIGATION_VALVE')", (ids['dsd'], NOW))
    con.execute("INSERT INTO dsd_irrigation_valve(id,open_level,valid_range) VALUES(?,100,'0-100')", (ids['dsd'],))
    con.commit()
    return ids


# ═══════════════════════════════════════════════════════════════
#  케이스 표 — (이름, 조항, 함수, expect_fail)
# ═══════════════════════════════════════════════════════════════
_CASES: list[tuple[str, str, "callable", bool]] = []


def _case(name, clause, fn, expect_fail=True):
    _CASES.append((name, clause, fn, expect_fail))


# ── 1369-P1 식별자/시간 불변 ────────────────────────────────
_case("farm_info.id UPDATE 차단", "7.2.2.2", lambda c, i: c.execute("UPDATE farm_info SET id=? WHERE id=?", (_u(), i['farm'])))
_case("greenhouse_info.id UPDATE 차단", "7.2.2.3", lambda c, i: c.execute("UPDATE greenhouse_info SET id=? WHERE id=?", (_u(), i['gh'])))
_case("device_info.id UPDATE 차단", "7.2.2.4", lambda c, i: c.execute("UPDATE device_info SET id=? WHERE id=?", (_u(), i['dev'])))
_case("device_install_info.id UPDATE 차단", "7.2.2.5", lambda c, i: c.execute("UPDATE device_install_info SET id=? WHERE id=?", (_u(), i['inst'])))
_case("user_info.id UPDATE 차단", "7.2.2.6", lambda c, i: c.execute("UPDATE user_info SET id=? WHERE id=?", (_u(), i['user'])))
_case("farm_info.created_at UPDATE 차단", "7.2.2.2", lambda c, i: c.execute("UPDATE farm_info SET created_at='2020-01-01' WHERE id=?", (i['farm'],)))
_case("device_info.model_name UPDATE 차단", "7.2.2.4", lambda c, i: c.execute("UPDATE device_info SET model_name='X' WHERE id=?", (i['dev'],)))
_case("device_info.model_name 전역 유일성 (중복 차단)", "6.2.4",
      lambda c, i: c.execute("INSERT INTO device_info(id,created_at,updated_at,device_name,device_kind,model_name,manufacturer)"
                             " VALUES(?,?,?,'다른센서','SENSOR','DHT22','다른제조사')", (_u(), NOW, NOW)))
_case("device_state_data.reported_at UPDATE 차단", "7.2.3.2", lambda c, i: c.execute("UPDATE device_state_data SET reported_at='2020-01-01' WHERE id=?", (i['dsd'],)))
_case("env_state_data.measured_at UPDATE 차단", "7.2.3.3", lambda c, i: c.execute("UPDATE env_state_data SET measured_at='2020-01-01' WHERE id=?", (i['esd'],)))
_case("greenhouse_info.name UPDATE 허용", "7.2.2.3", lambda c, i: c.execute("UPDATE greenhouse_info SET name='2호온실' WHERE id=?", (i['gh'],)), False)

# ── 관계 유일성 ────────────────────────────────────────────
def _dup_own(c, i):
    c.execute("INSERT INTO greenhouse_own VALUES(?,?)", (i['farm'], i['gh']))
    c.execute("INSERT INTO greenhouse_own VALUES(?,?)", (i['farm'], i['gh']))
_case("온실소유 중복 차단", "7.2.2.7", _dup_own)

def _dup_mng(c, i):
    c.execute("INSERT INTO greenhouse_manage VALUES(?,?)", (i['gh'], i['user']))
    c.execute("INSERT INTO greenhouse_manage VALUES(?,?)", (i['gh'], i['user']))
_case("온실관리 중복 차단", "7.2.2.8", _dup_mng)

def _dup_inst(c, i):
    c.execute("INSERT INTO device_install VALUES(?,?)", (i['gh'], i['inst']))
    c.execute("INSERT INTO device_install VALUES(?,?)", (i['gh'], i['inst']))
_case("장치설치 중복 차단", "7.2.2.9", _dup_inst)

def _dup_dmng(c, i):
    c.execute("INSERT INTO device_manage VALUES(?,?)", (i['user'], i['inst']))
    c.execute("INSERT INTO device_manage VALUES(?,?)", (i['user'], i['inst']))
_case("장치관리 중복 차단", "7.2.2.10", _dup_dmng)

def _dup_ds(c, i):
    c.execute("INSERT INTO device_state VALUES(?,?,?)", (_u(), i['inst'], i['dsd']))
    c.execute("INSERT INTO device_state VALUES(?,?,?)", (_u(), i['inst'], i['dsd']))
_case("장치상태 관계 중복 차단", "7.2.4.2", _dup_ds)

def _dup_em(c, i):
    c.execute("INSERT INTO env_measure VALUES(?,?,?)", (_u(), i['inst'], i['esd']))
    c.execute("INSERT INTO env_measure VALUES(?,?,?)", (_u(), i['inst'], i['esd']))
_case("환경측정 관계 중복 차단", "7.2.4.3", _dup_em)

def _dup_ge(c, i):
    c.execute("INSERT INTO greenhouse_env VALUES(?,?,?)", (_u(), i['gh'], i['esd']))
    c.execute("INSERT INTO greenhouse_env VALUES(?,?,?)", (_u(), i['gh'], i['esd']))
_case("온실환경 관계 중복 차단", "7.2.4.4", _dup_ge)

def _dup_oe(c, i):
    c.execute("INSERT INTO operating_env VALUES(?,?)", (i['dsd'], i['esd']))
    c.execute("INSERT INTO operating_env VALUES(?,?)", (i['dsd'], i['esd']))
_case("작동환경 관계 중복 차단", "7.2.3.4", _dup_oe)

# ── 관계 FK 불변 ───────────────────────────────────────────
def _upd_rel(c, i):
    c.execute("INSERT INTO env_measure VALUES(?,?,?)", ('r1', i['inst'], i['esd']))
    c.execute("UPDATE env_measure SET install_id=? WHERE id='r1'", (i['inst'],))
_case("환경측정 FK UPDATE 차단", "7.2.4.3", _upd_rel)

# ── 참조 무결성 ────────────────────────────────────────────
_case("존재하지 않는 장치정보 참조 차단", "7.2.2.5",
      # F-158 이후: 컬럼 추가로 조용히 깨지지 않도록 위치 지정 대신 컬럼명을 명시한다 (F-024 원칙)
      lambda c, i: c.execute("INSERT INTO device_install_info(id,created_at,updated_at,device_name,installed_at,"
                             "install_location,install_loc_unit,device_info_id,siap_node_id,siap_device_id,siap_subtype,"
                             "unit,lower_limit,upper_limit,precision_val)"
                             " VALUES(?,?,?,'X',?,NULL,NULL,'NO_SUCH',9,9,1,NULL,NULL,NULL,NULL)", (_u(), NOW, NOW, NOW)))
_case("측정형 데이터 timestamp NOT NULL", "6.3.2",
      lambda c, i: c.execute("INSERT INTO env_state_data VALUES(?,NULL,NULL,NULL)", (_u(),)))

# ── 측정값 CHECK ───────────────────────────────────────────
_case("미정의 환경 subtype 차단", "6.3.3.1",
      lambda c, i: (c.execute("INSERT INTO env_state_data(id,measured_at) VALUES('e2',?)", (NOW,)),
                    c.execute("INSERT INTO env_measurement(id,subtype,value,unit,error_range,lower_limit,upper_limit)"
                              " VALUES('e2','LUX',100,'lx',0,0,1)")))
_case("감우 측정값 단독 허용", "그림 7-3",
      lambda c, i: (c.execute("INSERT INTO env_state_data(id,measured_at) VALUES('e4',?)", (NOW,)),
                    c.execute("INSERT INTO env_measurement(id,subtype,value) VALUES('e4','RAIN_DETECTION',1)")), False)
_case("미정의 장치 subtype 차단", "6.3.4.1",
      lambda c, i: c.execute("INSERT INTO device_state_data VALUES(?,?,'SHADING_SCREEN')", (_u(), NOW)))

# ── 0943 연동 범위 ─────────────────────────────────────────
_DII_COLS = ("INSERT INTO device_install_info(id,created_at,updated_at,device_name,installed_at,"
             "install_location,install_loc_unit,device_info_id,siap_node_id,siap_device_id,siap_subtype,"
             "unit,lower_limit,upper_limit,precision_val)")
_case("Node ID 20bit 초과 차단", "0943 7.2.4",
      lambda c, i: c.execute(_DII_COLS + " VALUES(?,?,?,'X',?,NULL,NULL,?,1048576,1,1,NULL,NULL,NULL,NULL)", (_u(), NOW, NOW, NOW, i['dev'])))
_case("Device ID 8bit 초과 차단", "0943 5.1",
      lambda c, i: c.execute(_DII_COLS + " VALUES(?,?,?,'X',?,NULL,NULL,?,5,256,1,NULL,NULL,NULL,NULL)", (_u(), NOW, NOW, NOW, i['dev'])))
_case("(node_id, device_id) 중복 차단", "0943 3.4",
      lambda c, i: c.execute(_DII_COLS + " VALUES(?,?,?,'X',?,NULL,NULL,?,3,1,2,NULL,NULL,NULL,NULL)", (_u(), NOW, NOW, NOW, i['dev'])))
_case("장치설치 설치일자 NOT NULL 차단", "6.2.5",
      lambda c, i: c.execute("INSERT INTO device_install_info(id,created_at,updated_at,device_name,device_info_id)"
                             " VALUES(?,?,?,'X',?)", (_u(), NOW, NOW, i['dev'])))
# F-162: NOT NULL 만으로는 빈 문자열이 통과한다 — CHECK(installed_at <> '') 를
# 실제로 넣어봐서 확인한다("컬럼이 있다"와 "값이 온다"는 다르다, F-158 재발 방지).
_case("장치설치 설치일자 빈 문자열 차단", "6.2.5",
      lambda c, i: c.execute(_DII_COLS + " VALUES(?,?,?,'X','',NULL,NULL,?,NULL,NULL,NULL,NULL,NULL,NULL,NULL)",
                             (_u(), NOW, NOW, i['dev'])))
# F-166: 빈 문자열이 아니어도 임의 문자열('not-a-date')은 CHECK(installed_at <> '')
# 만으로는 통과한다 — GLOB 최소 형식 검사를 실제로 넣어봐서 확인한다.
_case("장치설치 설치일자 형식(ISO 8601) 위반 차단", "6.1",
      lambda c, i: c.execute(_DII_COLS + " VALUES(?,?,?,'X','not-a-date',NULL,NULL,?,NULL,NULL,NULL,NULL,NULL,NULL,NULL)",
                             (_u(), NOW, NOW, i['dev'])))
_case("장치설치 설치일자 ISO 8601 오프셋 표기 허용", "6.1",
      lambda c, i: c.execute(_DII_COLS + " VALUES(?,?,?,'X','2026-08-01T09:00:00+09:00',NULL,NULL,?,NULL,NULL,NULL,NULL,NULL,NULL,NULL)",
                             (_u(), NOW, NOW, i['dev'])), False)

# F-184: F-166은 이 형식 검사를 installed_at 하나에만 걸었다 — 나머지
# 시간 컬럼(created_at·updated_at 등)은 검사가 없어 아래 INSERT가 그대로
# 통과했다(재현 그대로 고정).
_case("사용자정보 생성시간 형식(ISO 8601) 위반 차단", "6.1",
      lambda c, i: c.execute("INSERT INTO user_info(id,created_at,updated_at,name) VALUES(?,?,?,'U')",
                             (_u(), 'not-a-time', NOW)))
_case("사용자정보 갱신시간 형식(ISO 8601) 위반 차단", "6.1",
      lambda c, i: c.execute("INSERT INTO user_info(id,created_at,updated_at,name) VALUES(?,?,?,'U')",
                             (_u(), NOW, 'also-not-time')))
_case("사용자정보 삭제시간(nullable) 형식(ISO 8601) 위반 차단", "6.1",
      lambda c, i: c.execute("INSERT INTO user_info(id,created_at,updated_at,deleted_at,name) VALUES(?,?,?,?,'U')",
                             (_u(), NOW, NOW, 'not-a-time')))
_case("사용자정보 삭제시간 NULL 허용(미삭제)", "6.1",
      lambda c, i: c.execute("INSERT INTO user_info(id,created_at,updated_at,deleted_at,name) VALUES(?,?,?,NULL,'U')",
                             (_u(), NOW, NOW)), False)
_case("제어실행 승인 규칙 없는 issued_at 형식 위반 차단", "6.1",
      lambda c, i: c.execute("INSERT INTO control_execution(id,origin,issued_by,install_id,issued_at,command_json)"
                             " VALUES(?,'MANUAL',?,?,?,'{}')", (_u(), i['user'], i['inst'], 'not-a-time')))

# ── 0937 승인 게이트 ───────────────────────────────────────
_RULE_COLS = ("INSERT INTO control_rule(id,created_at,origin,generation,draft_text,"
              "condition_expr,action_json,target_install_id,approved_at,approved_by)")
_case("미승인 규칙의 실행명령 차단", "0937 부속서A 3.3",
      lambda c, i: c.execute(_RULE_COLS + " VALUES(?,?,'AI_DRAFT','AI','내일 33도 예상, 관수 20분',"
                             "NULL,'{\"cmd\":\"open\"}',NULL,NULL,NULL)", (_u(), NOW)))
_case("승인자 없는 승인 차단", "0937 6.3",
      lambda c, i: c.execute(_RULE_COLS + " VALUES(?,?,'AI_DRAFT','AI','초안','t>33','{}',?,?,NULL)", (_u(), NOW, i['inst'], NOW)))
_case("승인된 규칙의 실행명령 허용", "0937 부속서A 3.3",
      lambda c, i: c.execute(_RULE_COLS + " VALUES(?,?,'AI_DRAFT','AI','초안','t>33','{\"cmd\":\"open\"}',?,?,?)",
                             (_u(), NOW, i['inst'], NOW, i['user'])), False)
_case("AI 초안 저장 허용 (미승인, 명령 없음)", "0937 6.3",
      lambda c, i: c.execute(_RULE_COLS + " VALUES(?,?,'AI_DRAFT','AI','초안만',NULL,NULL,NULL,NULL,NULL)", (_u(), NOW)), False)
_case("미승인 규칙의 대상 확정 차단", "0937 부속서A 3.3",
      lambda c, i: c.execute(_RULE_COLS + " VALUES(?,?,'AI_DRAFT','AI','초안','t>33',NULL,?,NULL,NULL)", (_u(), NOW, i['inst'])))

# ── F-015 회귀: 1:N 카디널리티 (1369-P1 7.1) ───────────────
_I2 = "INSERT INTO device_install_info(id,created_at,updated_at,device_name,installed_at,device_info_id) VALUES('i2','2026-08-01T09:00:00+09:00','2026-08-01T09:00:00+09:00','I2','2026-08-01T09:00:00+09:00',?)"
_S2 = "INSERT INTO device_state_data(id,reported_at,subtype) VALUES('s2','2026-08-01T09:00:00+09:00','FAN')"
_G2 = "INSERT INTO greenhouse_info(id,created_at,updated_at,name) VALUES('g2','2026-08-01T09:00:00+09:00','2026-08-01T09:00:00+09:00','G2')"


def _card(name, clause, sqls):
    def fn(c, i):
        for q in sqls:
            c.execute(q.replace("<DEV>", i['dev']).replace("<INST>", i['inst'])
                      .replace("<GH>", i['gh']).replace("<FARM>", i['farm'])
                      .replace("<USER>", i['user']).replace("<DSD>", i['dsd'])
                      .replace("<ESD>", i['esd']))
    _case(name, clause, fn)


_card("온실 1개가 농장 2곳에 소속 차단", "7.1(1)", [
    "INSERT INTO farm_info(id,created_at,updated_at,name,owner_id) VALUES('f2','2026-08-01T09:00:00+09:00','2026-08-01T09:00:00+09:00','F2','<USER>')",
    "INSERT INTO greenhouse_own VALUES('<FARM>','<GH>')", "INSERT INTO greenhouse_own VALUES('f2','<GH>')"])
_card("온실 1개를 사용자 2명이 관리 차단", "7.1(3)", [
    "INSERT INTO user_info(id,created_at,updated_at,name) VALUES('u2','2026-08-01T09:00:00+09:00','2026-08-01T09:00:00+09:00','U2')",
    "INSERT INTO greenhouse_manage VALUES('<GH>','<USER>')", "INSERT INTO greenhouse_manage VALUES('<GH>','u2')"])
_card("장치 1개가 온실 2곳에 설치 차단", "7.1(4)", [
    _G2, "INSERT INTO device_install VALUES('<GH>','<INST>')", "INSERT INTO device_install VALUES('g2','<INST>')"])
_card("장치 1개를 사용자 2명이 관리 차단", "7.1(7)", [
    "INSERT INTO user_info(id,created_at,updated_at,name) VALUES('u2','2026-08-01T09:00:00+09:00','2026-08-01T09:00:00+09:00','U2')",
    "INSERT INTO device_manage VALUES('<USER>','<INST>')", "INSERT INTO device_manage VALUES('u2','<INST>')"])
_card("장치상태 1건이 설치 2건에 귀속 차단", "7.1(8)", [
    _I2.replace("?", "'<DEV>'"), "INSERT INTO device_state VALUES('r1','<INST>','<DSD>')",
    "INSERT INTO device_state VALUES('r2','i2','<DSD>')"])
_card("환경상태 1건을 장치 2개가 측정 차단", "7.1(9)", [
    _I2.replace("?", "'<DEV>'"), "INSERT INTO env_measure VALUES('r1','<INST>','<ESD>')",
    "INSERT INTO env_measure VALUES('r2','i2','<ESD>')"])
_card("환경상태 1건이 온실 2곳에 귀속 차단", "7.1(5)", [
    _G2, "INSERT INTO greenhouse_env VALUES('r1','<GH>','<ESD>')",
    "INSERT INTO greenhouse_env VALUES('r2','g2','<ESD>')"])
_card("환경상태 1건이 장치상태 2건에 귀속 차단", "7.1(10)", [
    _S2, "INSERT INTO operating_env VALUES('<DSD>','<ESD>')", "INSERT INTO operating_env VALUES('s2','<ESD>')"])

# ── F-016 회귀: 불변성 제약 보강분 ─────────────────────────
_case("device_info.created_at UPDATE 차단", "7.2.2.4",
      lambda c, i: c.execute("UPDATE device_info SET created_at='t2' WHERE id=?", (i['dev'],)))
_case("device_install_info.created_at UPDATE 차단", "7.2.2.5",
      lambda c, i: c.execute("UPDATE device_install_info SET created_at='t2' WHERE id=?", (i['inst'],)))
_case("user_info.created_at UPDATE 차단", "7.2.2.6",
      lambda c, i: c.execute("UPDATE user_info SET created_at='t2' WHERE id=?", (i['user'],)))
for _nm, _cl, _tbl, _cols in [("온실소유", "7.2.2.7", "greenhouse_own", "farm_id"),
                               ("온실관리", "7.2.2.8", "greenhouse_manage", "user_id"),
                               ("장치설치", "7.2.2.9", "device_install", "greenhouse_id"),
                               ("장치관리", "7.2.2.10", "device_manage", "user_id")]:
    def _mk(tbl=_tbl, cols=_cols):
        def fn(c, i):
            a = {"greenhouse_own": (i['farm'], i['gh']), "greenhouse_manage": (i['gh'], i['user']),
                 "device_install": (i['gh'], i['inst']), "device_manage": (i['user'], i['inst'])}[tbl]
            c.execute(f"INSERT INTO {tbl} VALUES(?,?)", a)
            c.execute(f"UPDATE {tbl} SET {cols}='ZZZ'")
        return fn
    _case(f"{_nm} 관계 FK UPDATE 차단", _cl, _mk())


def _oe(c, i):
    c.execute("INSERT INTO device_state_data(id,reported_at,subtype) VALUES('s2','2026-08-01T09:00:00+09:00','FAN')")
    c.execute("INSERT INTO operating_env VALUES(?,?)", (i['dsd'], i['esd']))
    c.execute("UPDATE operating_env SET device_state_id='s2'")
_case("작동환경 관계 FK UPDATE 차단", "7.2.3.4", _oe)

for _nm, _cl, _tbl, _a, _b in [("장치상태", "7.2.4.2", "device_state", "inst", "dsd"),
                                ("환경측정", "7.2.4.3", "env_measure", "inst", "esd"),
                                ("온실환경", "7.2.4.4", "greenhouse_env", "gh", "esd")]:
    def _mk2(tbl=_tbl, a=_a, b=_b):
        def fn(c, i):
            c.execute(f"INSERT INTO {tbl} VALUES('r1',?,?)", (i[a], i[b]))
            c.execute(f"UPDATE {tbl} SET id='r9' WHERE id='r1'")
        return fn
    _case(f"{_nm} 관계 식별자 UPDATE 차단", _cl, _mk2())

# ── F-017 회귀: 제어 실행의 권한 출처 ──────────────────────
def _unapproved(c, i):
    c.execute("INSERT INTO control_rule(id,created_at,origin,generation,draft_text) VALUES('r','2026-08-01T09:00:00+09:00','AI_DRAFT','AI','초안')")
    c.execute("INSERT INTO control_execution(id,origin,rule_id,install_id,issued_at,command_json)"
              " VALUES('x','RULE','r',?,'2026-08-01T09:00:00+09:00','{}')", (i['inst'],))
_case("미승인 규칙 기반 제어 실행 차단", "0937 A.3.2", _unapproved)


def _noauth(c, i):
    c.execute("INSERT INTO control_execution(id,origin,install_id,issued_at,command_json)"
              " VALUES('x','RULE',?,'2026-08-01T09:00:00+09:00','{}')", (i['inst'],))
_case("권한 출처 없는 제어 실행 차단", "0937 A.3.2", _noauth)


def _approved_ok(c, i):
    c.execute("INSERT INTO control_rule(id,created_at,origin,generation,draft_text,condition_expr,action_json,target_install_id,approved_at,approved_by)"
              " VALUES('r','2026-08-01T09:00:00+09:00','AI_DRAFT','AI','초안','t>33','{}',?,?,?)", (i['inst'], NOW, i['user']))
    c.execute("INSERT INTO control_execution(id,origin,rule_id,install_id,issued_at,command_json)"
              " VALUES('x','RULE','r',?,'2026-08-01T09:00:00+09:00','{}')", (i['inst'],))
_case("승인된 규칙 기반 제어 실행 허용", "0937 A.3.2", _approved_ok, False)


def _manual_ok(c, i):
    c.execute("INSERT INTO control_execution(id,origin,issued_by,install_id,issued_at,command_json)"
              " VALUES('x','MANUAL',?,?,'2026-08-01T09:00:00+09:00','{}')", (i['user'], i['inst']))
_case("사용자 직접 지시(MANUAL) 허용", "0937 A.1·A.2", _manual_ok, False)


def _revoke(c, i):
    c.execute("INSERT INTO control_rule(id,created_at,origin,generation,draft_text,condition_expr,action_json,target_install_id,approved_at,approved_by)"
              " VALUES('r','2026-08-01T09:00:00+09:00','AI_DRAFT','AI','초안','t>33','{}',?,?,?)", (i['inst'], NOW, i['user']))
    c.execute("UPDATE control_rule SET approved_at=NULL WHERE id='r'")
_case("승인 철회 차단", "0937 6.3", _revoke)

# ── F-030 회귀: 승인 명령과 실행 명령의 결속 ───────────────
def _approved_rule(c, i, action='{"value":0}', cond='t>33', target=None):
    c.execute("INSERT INTO control_rule(id,created_at,origin,generation,draft_text,condition_expr,action_json,target_install_id,approved_at,approved_by)"
              " VALUES('r','2026-08-01T09:00:00+09:00','AI_DRAFT','AI','초안',?,?,?,?,?)",
              (cond, action, target or i['inst'], NOW, i['user']))


def _mismatch(c, i):
    _approved_rule(c, i)
    c.execute("INSERT INTO control_execution(id,origin,rule_id,install_id,issued_at,command_json)"
              ' VALUES(\'x\',\'RULE\',\'r\',?,\'2026-08-01T09:00:00+09:00\',\'{"value":1}\')', (i['inst'],))
_case("승인 내용과 다른 명령 실행 차단", "0937 A.3.2", _mismatch)


def _match_ok(c, i):
    _approved_rule(c, i)
    c.execute("INSERT INTO control_execution(id,origin,rule_id,install_id,issued_at,command_json)"
              ' VALUES(\'x\',\'RULE\',\'r\',?,\'2026-08-01T09:00:00+09:00\',\'{"value":0}\')', (i['inst'],))
_case("승인 내용과 일치하는 명령 허용", "0937 A.3.2", _match_ok, False)


def _tamper(c, i):
    _approved_rule(c, i)
    c.execute('UPDATE control_rule SET action_json=\'{"value":9}\' WHERE id=\'r\'')
_case("승인 후 명령 변조 차단", "0937 6.3", _tamper)

# ── F-039 회귀: 승인 스냅샷의 NULL·조건 변조 우회 ──────────
def _approved_null_action(c, i):
    c.execute("INSERT INTO control_rule(id,created_at,origin,generation,draft_text,condition_expr,action_json,target_install_id,approved_at,approved_by)"
              " VALUES('r','2026-08-01T09:00:00+09:00','AI_DRAFT','AI','초안','t>40',NULL,?,?,?)", (i['inst'], NOW, i['user']))
_case("승인 규칙의 NULL 명령 차단", "0937 A.3.2", _approved_null_action)


def _approved_null_condition(c, i):
    c.execute("INSERT INTO control_rule(id,created_at,origin,generation,draft_text,condition_expr,action_json,target_install_id,approved_at,approved_by)"
              " VALUES('r','2026-08-01T09:00:00+09:00','AI_DRAFT','AI','초안',NULL,'{\"value\":0}',?,?,?)", (i['inst'], NOW, i['user']))
_case("승인 규칙의 NULL 조건식 차단", "0937 A.3.2", _approved_null_condition)


def _approve_update_without_action(c, i):
    c.execute("INSERT INTO control_rule(id,created_at,origin,generation,draft_text) VALUES('r','2026-08-01T09:00:00+09:00','AI_DRAFT','AI','초안')")
    c.execute("UPDATE control_rule SET approved_at=?, approved_by=? WHERE id='r'", (NOW, i['user']))
_case("명령 없는 승인 UPDATE 차단", "0937 A.3.2", _approve_update_without_action)


def _atomic_approval_ok(c, i):
    c.execute("INSERT INTO control_rule(id,created_at,origin,generation,draft_text) VALUES('r','2026-08-01T09:00:00+09:00','AI_DRAFT','AI','초안')")
    c.execute("UPDATE control_rule SET condition_expr='t>33', action_json='{\"value\":0}',"
              " target_install_id=?, approved_at=?, approved_by=? WHERE id='r'", (i['inst'], NOW, i['user']))
    c.execute("INSERT INTO control_execution(id,origin,rule_id,install_id,issued_at,command_json)"
              ' VALUES(\'x\',\'RULE\',\'r\',?,\'2026-08-01T09:00:00+09:00\',\'{"value":0}\')', (i['inst'],))
_case("원자적 승인 UPDATE 후 실행 허용", "0937 A.3.2", _atomic_approval_ok, False)


def _cond_tamper(c, i):
    _approved_rule(c, i)
    c.execute("UPDATE control_rule SET condition_expr='t>0' WHERE id='r'")
_case("승인 후 조건식 변조 차단", "0937 A.3.2", _cond_tamper)


def _null_action_arbitrary_command(c, i):
    c.execute("INSERT INTO control_rule(id,created_at,origin,generation,draft_text,condition_expr,action_json,target_install_id,approved_at,approved_by)"
              " VALUES('r','2026-08-01T09:00:00+09:00','AI_DRAFT','AI','초안','t>40',NULL,?,?,?)", (i['inst'], NOW, i['user']))
    c.execute("INSERT INTO control_execution(id,origin,rule_id,install_id,issued_at,command_json)"
              ' VALUES(\'x\',\'RULE\',\'r\',?,\'2026-08-01T09:00:00+09:00\',\'{"value":1}\')', (i['inst'],))
_case("NULL 승인 경유 임의 명령 실행 차단", "0937 A.3.2", _null_action_arbitrary_command)

# ── F-048 회귀: 승인 출처(누가·언제)의 불변성 ───────────────
def _approver_tamper(c, i):
    _approved_rule(c, i)
    other = _u()
    c.execute("INSERT INTO user_info(id,created_at,updated_at,name) VALUES(?,?,?,'다른사용자')", (other, NOW, NOW))
    c.execute("UPDATE control_rule SET approved_by=? WHERE id='r'", (other,))
_case("승인자 사후 변조 차단", "0937 A.3.2", _approver_tamper)


def _approved_at_tamper(c, i):
    _approved_rule(c, i)
    c.execute("UPDATE control_rule SET approved_at='1999-01-01T00:00:00' WHERE id='r'")
_case("승인시각 사후 변조 차단", "0937 A.3.2", _approved_at_tamper)

# ── F-049 회귀: 승인 대상 장치의 결속 ──────────────────────
def _second_install(c, i):
    other = _u()
    c.execute("INSERT INTO device_install_info(id,created_at,updated_at,device_name,installed_at,"
              "device_info_id,siap_node_id,siap_device_id,siap_subtype)"
              " VALUES(?,?,?,'밸브B',?,?,3,2,133)", (other, NOW, NOW, NOW, i['dev']))
    return other


def _target_mismatch(c, i):
    _approved_rule(c, i)
    other = _second_install(c, i)
    c.execute("INSERT INTO control_execution(id,origin,rule_id,install_id,issued_at,command_json)"
              ' VALUES(\'x\',\'RULE\',\'r\',?,\'2026-08-01T09:00:00+09:00\',\'{"value":0}\')', (other,))
_case("승인 대상과 다른 장치 실행 차단", "0937 6.5", _target_mismatch)


def _target_match_ok(c, i):
    _approved_rule(c, i)
    c.execute("INSERT INTO control_execution(id,origin,rule_id,install_id,issued_at,command_json)"
              ' VALUES(\'x\',\'RULE\',\'r\',?,\'2026-08-01T09:00:00+09:00\',\'{"value":0}\')', (i['inst'],))
_case("승인 대상과 일치하는 장치 실행 허용", "0937 6.5", _target_match_ok, False)


def _exec_target_swap(c, i):
    _approved_rule(c, i)
    other = _second_install(c, i)
    c.execute("INSERT INTO control_execution(id,origin,rule_id,install_id,issued_at,command_json)"
              ' VALUES(\'x\',\'RULE\',\'r\',?,\'2026-08-01T09:00:00+09:00\',\'{"value":0}\')', (i['inst'],))
    c.execute("UPDATE control_execution SET install_id=? WHERE id='x'", (other,))
_case("실행 후 대상 장치 바꿔치기 차단", "0937 6.5", _exec_target_swap)


def _approved_target_tamper(c, i):
    _approved_rule(c, i)
    other = _second_install(c, i)
    c.execute("UPDATE control_rule SET target_install_id=? WHERE id='r'", (other,))
_case("승인 후 대상 장치 변조 차단", "0937 A.3.2", _approved_target_tamper)


def _approve_update_without_target(c, i):
    c.execute("INSERT INTO control_rule(id,created_at,origin,generation,draft_text) VALUES('r','2026-08-01T09:00:00+09:00','AI_DRAFT','AI','초안')")
    c.execute("UPDATE control_rule SET condition_expr='t>33', action_json='{}',"
              " approved_at=?, approved_by=? WHERE id='r'", (NOW, i['user']))
_case("대상 없는 승인 UPDATE 차단", "0937 6.5", _approve_update_without_target)


def _manual_target_free(c, i):
    other = _second_install(c, i)
    c.execute("INSERT INTO control_execution(id,origin,issued_by,install_id,issued_at,command_json)"
              ' VALUES(\'x\',\'MANUAL\',?,?,\'2026-08-01T09:00:00+09:00\',\'{"value":1}\')', (i['user'], other))
_case("MANUAL 실행은 대상 제약 없음", "0937 A.1·A.2", _manual_target_free, False)

# ── F-032 회귀: 표준 커버리지 ──────────────────────────────
def _crop(c, i):
    c.execute("UPDATE greenhouse_info SET crop='토마토' WHERE id=?", (i['gh'],))
_case("온실 생육작물 컬럼 존재", "6.2.3", _crop, False)
# F-185: 6.2.4 "장치정보에는... 장치특성 등이 포함되어야 한다" — 저장할
# 컬럼이 없었다. manufacturer 와 같은 자격(nullable)으로 추가했다.
def _device_characteristics(c, i):
    c.execute("UPDATE device_info SET device_characteristics='IP65 방수' WHERE id=?", (i['dev'],))
_case("장치정보 장치특성 컬럼 존재", "6.2.4", _device_characteristics, False)


def _rain_unit(c, i):
    c.execute("INSERT INTO env_state_data(id,measured_at) VALUES('e2',?)", (NOW,))
    c.execute("INSERT INTO env_measurement(id,subtype,value,unit) VALUES('e2','RAIN_DETECTION',1,'ON/OFF')")
_case("감우 단위 저장 허용", "6.3.3.8", _rain_unit, False)


def _rain_range(c, i):
    c.execute("INSERT INTO env_state_data(id,measured_at) VALUES('e3',?)", (NOW,))
    c.execute("INSERT INTO env_measurement(id,subtype,value,unit,error_range,lower_limit,upper_limit)"
              " VALUES('e3','RAIN_DETECTION',1,'ON/OFF',0.1,0,1)")
_case("감우 오차·유효범위 차단", "그림 7-3", _rain_range)

# ── F-083 회귀: 규칙 거부도 영속 상태다 (0937 부속서 A 3.2 절차 3) ──
_REJ = ("INSERT INTO control_rule(id,created_at,origin,generation,draft_text,"
        "rejected_at,rejected_by,reject_reason)")

_case("거부자 없는 거부 차단", "0937 부속서A 3.2",
      lambda c, i: c.execute(_REJ + " VALUES(?,?,'AI_DRAFT','AI','초안',?,NULL,'부적절')", (_u(), NOW, NOW)))
_case("거부 저장 허용 (사유 포함)", "0937 부속서A 3.2",
      lambda c, i: c.execute(_REJ + " VALUES(?,?,'AI_DRAFT','AI','초안',?,?,'임계값 과도')",
                             (_u(), NOW, NOW, i['user'])), False)
_case("동시 상태 차단 - 승인 내용 + 거부 표시", "0937 부속서A 3.2",
      lambda c, i: c.execute(
          "INSERT INTO control_rule(id,created_at,origin,generation,draft_text,condition_expr,"
          "action_json,target_install_id,approved_at,approved_by,rejected_at,rejected_by)"
          " VALUES(?,?,'AI_DRAFT','AI','초안','t>33','{}',?,?,?,?,?)",
          (_u(), NOW, i['inst'], NOW, i['user'], NOW, i['user'])))
_case("동시 상태 차단 - 거부 내용 + 승인 표시", "0937 부속서A 3.2",
      lambda c, i: c.execute(
          "INSERT INTO control_rule(id,created_at,origin,generation,draft_text,"
          "approved_at,approved_by,rejected_at,rejected_by)"
          " VALUES(?,?,'AI_DRAFT','AI','초안',?,?,?,?)",
          (_u(), NOW, NOW, i['user'], NOW, i['user'])))
_case("AI 초안인데 생성 경로 없음 차단", "0937 6.3",
      lambda c, i: c.execute("INSERT INTO control_rule(id,created_at,origin,draft_text)"
                             " VALUES(?,?,'AI_DRAFT','초안')", (_u(), NOW)))
_case("AI 초안 + THRESHOLD 폴백 허용", "0937 6.3",
      lambda c, i: c.execute("INSERT INTO control_rule(id,created_at,origin,generation,draft_text)"
                             " VALUES(?,?,'AI_DRAFT','THRESHOLD_FALLBACK','초안')",
                             (_u(), NOW)), False)
_case("정의되지 않은 생성 경로 차단", "0937 6.3",
      lambda c, i: c.execute("INSERT INTO control_rule(id,created_at,origin,generation,draft_text)"
                             " VALUES(?,?,'WIZARD','GPT','초안')", (_u(), NOW)))
_case("거부된 규칙의 실행명령 차단 (미승인 제약 경유)", "0937 부속서A 3.2",
      lambda c, i: c.execute(
          "INSERT INTO control_rule(id,created_at,origin,generation,draft_text,action_json,"
          "rejected_at,rejected_by) VALUES(?,?,'AI_DRAFT','AI','초안','{\"cmd\":\"open\"}',?,?)",
          (_u(), NOW, NOW, i['user'])))


def _rej_then(sql, *args):
    def fn(c, i):
        rid = _u()
        c.execute(_REJ + " VALUES(?,?,'AI_DRAFT','AI','초안',?,?,'사유')", (rid, NOW, NOW, i['user']))
        c.execute(sql, tuple(a if a != "<RID>" else rid
                              for a in (x.replace("<USER>", i['user']) if isinstance(x, str) else x
                                        for x in args)))
    return fn


_case("거부 뒤 승인 차단", "0937 부속서A 3.2",
      _rej_then("UPDATE control_rule SET approved_at=?, approved_by=? WHERE id=?",
                NOW, "<USER>", "<RID>"))
_case("거부 사실 변경 차단 (불변)", "0937 부속서A 3.2",
      _rej_then("UPDATE control_rule SET rejected_at=? WHERE id=?", "2099-01-01", "<RID>"))


def _app_then_rej(c, i):
    rid = _u()
    c.execute("INSERT INTO control_rule(id,created_at,origin,generation,draft_text,condition_expr,"
              "action_json,target_install_id,approved_at,approved_by)"
              " VALUES(?,?,'AI_DRAFT','AI','초안','t>33','{}',?,?,?)",
              (rid, NOW, i['inst'], NOW, i['user']))
    c.execute("UPDATE control_rule SET rejected_at=?, rejected_by=?, reject_reason=? WHERE id=?",
              (NOW, i['user'], '대상 장치가 다름', rid))
_case("승인 뒤 거부 차단", "0937 부속서A 3.2", _app_then_rej)

# ── F-091 / F-092 — 생성경로 위조 · 거부 증거 · 알림 결속 ──────────────────
_case("사람 규칙을 AI 산출물로 위조 차단", "0937 6.3",
      lambda c, i: c.execute("INSERT INTO control_rule(id,created_at,origin,generation,draft_text)"
                             " VALUES(?,?,'WIZARD','AI','초안')", (_u(), NOW)))
_case("생성 경로가 origin 과 어긋남 차단", "0937 6.3",
      lambda c, i: c.execute("INSERT INTO control_rule(id,created_at,origin,generation,draft_text)"
                             " VALUES(?,?,'SCRIPT','WIZARD','초안')", (_u(), NOW)))
_case("위자드 규칙 + 같은 생성 경로 허용", "0937 6.3",
      lambda c, i: c.execute("INSERT INTO control_rule(id,created_at,origin,generation,draft_text)"
                             " VALUES(?,?,'WIZARD','WIZARD','초안')", (_u(), NOW)), False)
_case("생성 경로 미기재 허용 (AI 아닌 경우)", "0937 6.3",
      lambda c, i: c.execute("INSERT INTO control_rule(id,created_at,origin,draft_text)"
                             " VALUES(?,?,'WIZARD','초안')", (_u(), NOW)), False)
_case("사유 없는 거부 차단", "0937 부속서A 3.2",
      lambda c, i: c.execute(
          "INSERT INTO control_rule(id,created_at,origin,generation,draft_text,rejected_at,rejected_by)"
          " VALUES(?,?,'AI_DRAFT','AI','초안',?,?)", (_u(), NOW, NOW, i['user'])))
_case("공백뿐인 거부 사유 차단", "0937 부속서A 3.2",
      lambda c, i: c.execute(
          "INSERT INTO control_rule(id,created_at,origin,generation,draft_text,rejected_at,rejected_by,reject_reason)"
          " VALUES(?,?,'AI_DRAFT','AI','초안',?,?,'   ')", (_u(), NOW, NOW, i['user'])))
_case("거부 없이 사유만 차단", "0937 부속서A 3.2",
      lambda c, i: c.execute(
          "INSERT INTO control_rule(id,created_at,origin,generation,draft_text,reject_reason)"
          " VALUES(?,?,'AI_DRAFT','AI','초안','사유')", (_u(), NOW)))
_case("거부 사유 사후 변경 차단 (불변)", "0937 부속서A 3.2",
      _rej_then("UPDATE control_rule SET reject_reason=? WHERE id=?", "다른 사유", "<RID>"))

_case("NEC 알림인데 원본 프레임 없음 차단", "0943 8.2.1.1",
      lambda c, i: c.execute("INSERT INTO alert(id,raised_at,kind,severity,siap_nec,message)"
                             " VALUES(?,?,'NODE_ERROR','WARN',7,'배터리 부족')", (_u(), NOW)))


def _nec_with_frame(c, i):
    fid = _u()
    c.execute("INSERT INTO frame_log(id,t,direction,raw_hex,is_valid)"
              " VALUES(?,?, 'rx','0102','1')", (fid, 1786000000.0))
    c.execute("INSERT INTO alert(id,raised_at,kind,severity,siap_nec,message,frame_id)"
              " VALUES(?,?,'NODE_ERROR','WARN',7,'배터리 부족',?)", (_u(), NOW, fid))
_case("NEC 알림 + 원본 프레임 결속 허용", "0943 8.2.1.1", _nec_with_frame, False)
_case("임계 알림은 프레임 없이 허용", "0937 부속서A 1.3",
      lambda c, i: c.execute("INSERT INTO alert(id,raised_at,kind,severity,message)"
                             " VALUES(?,?,'THRESHOLD','WARN','상한 초과')", (_u(), NOW)),
      False)


# ═══════════════════════════════════════════════════════════════
#  케이스 → 실제 pytest 함수 생성 (CLAUDE.md §3.2 — 함수명에 조항 번호)
# ═══════════════════════════════════════════════════════════════

def _slug(name: str, clause: str) -> str:
    c = re.sub(r"[^0-9A-Za-z가-힣]+", "_", clause).strip("_")
    n = re.sub(r"[^0-9A-Za-z가-힣]+", "_", name).strip("_")
    return f"test_{n}_{c}"


def _make_test(name: str, clause: str, fn, expect_fail: bool):
    def _t() -> None:
        con = _fresh()
        ids = _seed(con)
        try:
            fn(con, ids)
            con.commit()
            ok, reason = (not expect_fail), "허용됨"
        except sqlite3.IntegrityError:
            ok, reason = expect_fail, "IntegrityError"
        except Exception as e:                                   # noqa: BLE001 — 테스트 자체의 결함까지 잡는다 (F-024)
            ok, reason = False, f"{type(e).__name__}: {e}"
        finally:
            con.close()
        assert ok, f"{name} ({clause}) 기대와 다른 결과: {reason}"
    return _t


_seen: set[str] = set()
for _name, _clause, _fn, _expect_fail in _CASES:
    _fname = _slug(_name, _clause)
    _base, _n = _fname, 2
    while _fname in _seen:
        _fname = f"{_base}_{_n}"
        _n += 1
    _seen.add(_fname)
    _test = _make_test(_name, _clause, _fn, _expect_fail)
    _test.__name__ = _fname
    _test.__doc__ = f"{_name} — {_clause}"
    globals()[_fname] = _test


def test_case_count_matches_design_doc_109():
    """DB 스키마 설계서 §6.2 — "109종 109/109 통과"(당시 98종 — F-158·F-159
    로 설치일자 NOT NULL·model_name UNIQUE 검사 2건 추가, 이어서 F-162로
    설치일자 빈 문자열 차단 검사 1건, F-166으로 설치일자 형식(ISO 8601)
    검사 2건 추가, 당시 103종 — F-184로 시간 형식(ISO 8601) 검사를
    installed_at 하나에서 created_at·updated_at·issued_at 등 나머지
    시간 컬럼으로 넓히며 5건 추가, 당시 108종 — F-185로 장치정보
    장치특성 컬럼 존재 검사 1건 추가). 이 파일의 케이스 수가 어긋나면
    설계서 수치가 낡았거나 이식이 누락된 것이다(F-094류 재발 방지)."""
    assert len(_CASES) == 109
