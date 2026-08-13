import sqlite3, uuid, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent   # F-024: 실행 위치 무관

# F-045 — 한국어 Windows 기본 콘솔은 CP949 다. 표현 불가 문자 하나로 검증이
#         중단되면 재현성이 깨진다. 출력 문자는 CP949 안에서 고르는 것이 원칙이고
#         (meta_verify.py 가 강제), 이 가드는 중단만은 막는 2중 방어다.
if sys.stdout.encoding and sys.stdout.encoding.lower().replace("-", "") != "utf8":
    try: sys.stdout.reconfigure(errors="replace")
    except Exception: pass
NOW = "2026-08-01T09:00:00+09:00"
U = lambda: str(uuid.uuid4())

def fresh():
    con = sqlite3.connect(":memory:")
    con.executescript(open(HERE / "schema.sql", encoding="utf-8").read())
    con.execute("PRAGMA foreign_keys=ON")
    return con

def seed(con):
    ids = {}
    ids['user'] = U(); con.execute("INSERT INTO user_info(id,created_at,updated_at,name,group_id,group_role)"
        " VALUES(?,?,?,'관리자','g1','ADMIN')",(ids['user'],NOW,NOW))
    ids['farm'] = U(); con.execute("INSERT INTO farm_info(id,created_at,updated_at,name,owner_id,"
        "location,location_type,location_unit,area_value,area_error,area_unit)"
        " VALUES(?,?,?,'테스트농장',?,'37.4,127.1','GPS','deg',1000,1,'m2')",(ids['farm'],NOW,NOW,ids['user']))
    ids['gh']   = U(); con.execute("INSERT INTO greenhouse_info(id,created_at,updated_at,name,"
        "width_value,height_value,length_value,gh_type,medium_type,irrigation_type,heating_type,"
        "crop,crop_season,usage_state) VALUES(?,?,?,'1호온실',6,3,30,'단동','토경','점적','온풍',"
        "'토마토','2026춘작','사용중')",(ids['gh'],NOW,NOW))
    ids['dev']  = U(); con.execute("INSERT INTO device_info(id,created_at,updated_at,device_name,device_kind,model_name,manufacturer)"
        " VALUES(?,?,?,'온습도센서','SENSOR','DHT22','Aosong')",(ids['dev'],NOW,NOW))
    ids['inst'] = U(); con.execute("INSERT INTO device_install_info(id,created_at,updated_at,device_name,"
        "installed_at,install_location,install_loc_unit,device_info_id,siap_node_id,siap_device_id,siap_subtype,"
        "unit,lower_limit,upper_limit,precision_val)"
        " VALUES(?,?,?,'중앙온습도',?,'중앙 상단','m',?,3,1,1,'℃',-40,80,0.1)",(ids['inst'],NOW,NOW,NOW,ids['dev']))
    ids['esd']  = U(); con.execute("INSERT INTO env_state_data(id,measured_at,location,location_unit)"
        " VALUES(?,?,'중앙 상단','m')",(ids['esd'],NOW))
    con.execute("INSERT INTO env_measurement(id,subtype,value,unit,error_range,lower_limit,upper_limit)"
        " VALUES(?,'TEMPERATURE',25.3,'℃',0.1,-40,80)",(ids['esd'],))
    ids['dsd']  = U(); con.execute("INSERT INTO device_state_data(id,reported_at,subtype)"
        " VALUES(?,?,'IRRIGATION_VALVE')",(ids['dsd'],NOW))
    con.execute("INSERT INTO dsd_irrigation_valve(id,open_level,valid_range) VALUES(?,100,'0-100')",(ids['dsd'],))
    con.commit(); return ids

results = []
def check(name, clause, fn, expect_fail=True):
    """F-024 — 차단 기대 테스트는 sqlite3.IntegrityError 만 성공으로 인정한다.
    모든 Exception을 통과로 보면 SQL 오타·NameError가 제약 통과로 위장된다."""
    con = fresh(); ids = seed(con)
    try:
        fn(con, ids); con.commit()
        ok, msg = (not expect_fail), "허용됨"
    except sqlite3.IntegrityError as e:
        ok, msg = expect_fail, "IntegrityError"
    except Exception as e:
        ok, msg = False, f"!! {type(e).__name__}: {e}"      # 테스트 자체의 결함
    results.append((ok, name, clause, msg)); con.close()

# ── 1369-P1 식별자/시간 불변 ────────────────────────────────
check("farm_info.id UPDATE 차단","7.2.2.2", lambda c,i: c.execute("UPDATE farm_info SET id=? WHERE id=?",(U(),i['farm'])))
check("greenhouse_info.id UPDATE 차단","7.2.2.3", lambda c,i: c.execute("UPDATE greenhouse_info SET id=? WHERE id=?",(U(),i['gh'])))
check("device_info.id UPDATE 차단","7.2.2.4", lambda c,i: c.execute("UPDATE device_info SET id=? WHERE id=?",(U(),i['dev'])))
check("device_install_info.id UPDATE 차단","7.2.2.5", lambda c,i: c.execute("UPDATE device_install_info SET id=? WHERE id=?",(U(),i['inst'])))
check("user_info.id UPDATE 차단","7.2.2.6", lambda c,i: c.execute("UPDATE user_info SET id=? WHERE id=?",(U(),i['user'])))
check("farm_info.created_at UPDATE 차단","7.2.2.2", lambda c,i: c.execute("UPDATE farm_info SET created_at='2020-01-01' WHERE id=?",(i['farm'],)))
check("device_info.model_name UPDATE 차단","7.2.2.4", lambda c,i: c.execute("UPDATE device_info SET model_name='X' WHERE id=?",(i['dev'],)))
check("device_info.model_name 전역 유일성 (중복 차단)","6.2.4",
      lambda c,i: c.execute("INSERT INTO device_info(id,created_at,updated_at,device_name,device_kind,model_name,manufacturer)"
                            " VALUES(?,?,?,'다른센서','SENSOR','DHT22','다른제조사')",(U(),NOW,NOW)))
check("device_state_data.reported_at UPDATE 차단","7.2.3.2", lambda c,i: c.execute("UPDATE device_state_data SET reported_at='2020-01-01' WHERE id=?",(i['dsd'],)))
check("env_state_data.measured_at UPDATE 차단","7.2.3.3", lambda c,i: c.execute("UPDATE env_state_data SET measured_at='2020-01-01' WHERE id=?",(i['esd'],)))
# 수정 가능해야 하는 속성은 통과해야 함
check("greenhouse_info.name UPDATE 허용","7.2.2.3", lambda c,i: c.execute("UPDATE greenhouse_info SET name='2호온실' WHERE id=?",(i['gh'],)), expect_fail=False)

# ── 관계 유일성 ────────────────────────────────────────────
def dup_own(c,i):
    c.execute("INSERT INTO greenhouse_own VALUES(?,?)",(i['farm'],i['gh']))
    c.execute("INSERT INTO greenhouse_own VALUES(?,?)",(i['farm'],i['gh']))
check("온실소유 중복 차단","7.2.2.7", dup_own)
def dup_mng(c,i):
    c.execute("INSERT INTO greenhouse_manage VALUES(?,?)",(i['gh'],i['user']))
    c.execute("INSERT INTO greenhouse_manage VALUES(?,?)",(i['gh'],i['user']))
check("온실관리 중복 차단","7.2.2.8", dup_mng)
def dup_inst(c,i):
    c.execute("INSERT INTO device_install VALUES(?,?)",(i['gh'],i['inst']))
    c.execute("INSERT INTO device_install VALUES(?,?)",(i['gh'],i['inst']))
check("장치설치 중복 차단","7.2.2.9", dup_inst)
def dup_dmng(c,i):
    c.execute("INSERT INTO device_manage VALUES(?,?)",(i['user'],i['inst']))
    c.execute("INSERT INTO device_manage VALUES(?,?)",(i['user'],i['inst']))
check("장치관리 중복 차단","7.2.2.10", dup_dmng)
def dup_ds(c,i):
    c.execute("INSERT INTO device_state VALUES(?,?,?)",(U(),i['inst'],i['dsd']))
    c.execute("INSERT INTO device_state VALUES(?,?,?)",(U(),i['inst'],i['dsd']))
check("장치상태 관계 중복 차단","7.2.4.2", dup_ds)
def dup_em(c,i):
    c.execute("INSERT INTO env_measure VALUES(?,?,?)",(U(),i['inst'],i['esd']))
    c.execute("INSERT INTO env_measure VALUES(?,?,?)",(U(),i['inst'],i['esd']))
check("환경측정 관계 중복 차단","7.2.4.3", dup_em)
def dup_ge(c,i):
    c.execute("INSERT INTO greenhouse_env VALUES(?,?,?)",(U(),i['gh'],i['esd']))
    c.execute("INSERT INTO greenhouse_env VALUES(?,?,?)",(U(),i['gh'],i['esd']))
check("온실환경 관계 중복 차단","7.2.4.4", dup_ge)
def dup_oe(c,i):
    c.execute("INSERT INTO operating_env VALUES(?,?)",(i['dsd'],i['esd']))
    c.execute("INSERT INTO operating_env VALUES(?,?)",(i['dsd'],i['esd']))
check("작동환경 관계 중복 차단","7.2.3.4", dup_oe)

# ── 관계 FK 불변 ───────────────────────────────────────────
def upd_rel(c,i):
    c.execute("INSERT INTO env_measure VALUES(?,?,?)",('r1',i['inst'],i['esd']))
    c.execute("UPDATE env_measure SET install_id=? WHERE id='r1'",(i['inst'],))
check("환경측정 FK UPDATE 차단","7.2.4.3", upd_rel)

# ── 참조 무결성 ────────────────────────────────────────────
check("존재하지 않는 장치정보 참조 차단","7.2.2.5",
      # F-158 이후: 컬럼 추가로 조용히 깨지지 않도록 위치 지정 대신 컬럼명을 명시한다 (F-024 원칙)
      lambda c,i: c.execute("INSERT INTO device_install_info(id,created_at,updated_at,device_name,installed_at,"
                            "install_location,install_loc_unit,device_info_id,siap_node_id,siap_device_id,siap_subtype,"
                            "unit,lower_limit,upper_limit,precision_val)"
                            " VALUES(?,?,?,'X',?,NULL,NULL,'NO_SUCH',9,9,1,NULL,NULL,NULL,NULL)",(U(),NOW,NOW,NOW)))
check("측정형 데이터 timestamp NOT NULL","6.3.2",
      lambda c,i: c.execute("INSERT INTO env_state_data VALUES(?,NULL,NULL,NULL)",(U(),)))

# ── 측정값 CHECK ───────────────────────────────────────────
check("미정의 환경 subtype 차단","6.3.3.1",
      lambda c,i: (c.execute("INSERT INTO env_state_data(id,measured_at) VALUES('e2',?)",(NOW,)),
                   c.execute("INSERT INTO env_measurement(id,subtype,value,unit,error_range,lower_limit,upper_limit)"
                             " VALUES('e2','LUX',100,'lx',0,0,1)")))
check("감우 측정값 단독 허용","그림 7-3",
      lambda c,i: (c.execute("INSERT INTO env_state_data(id,measured_at) VALUES('e4',?)",(NOW,)),
                   c.execute("INSERT INTO env_measurement(id,subtype,value) VALUES('e4','RAIN_DETECTION',1)")), expect_fail=False)
check("미정의 장치 subtype 차단","6.3.4.1",
      lambda c,i: c.execute("INSERT INTO device_state_data VALUES(?,?,'SHADING_SCREEN')",(U(),NOW)))

# ── 0943 연동 범위 ─────────────────────────────────────────
_DII_COLS = ("INSERT INTO device_install_info(id,created_at,updated_at,device_name,installed_at,"
             "install_location,install_loc_unit,device_info_id,siap_node_id,siap_device_id,siap_subtype,"
             "unit,lower_limit,upper_limit,precision_val)")
check("Node ID 20bit 초과 차단","0943 7.2.4",
      lambda c,i: c.execute(_DII_COLS + " VALUES(?,?,?,'X',?,NULL,NULL,?,1048576,1,1,NULL,NULL,NULL,NULL)",(U(),NOW,NOW,NOW,i['dev'])))
check("Device ID 8bit 초과 차단","0943 5.1",
      lambda c,i: c.execute(_DII_COLS + " VALUES(?,?,?,'X',?,NULL,NULL,?,5,256,1,NULL,NULL,NULL,NULL)",(U(),NOW,NOW,NOW,i['dev'])))
check("(node_id, device_id) 중복 차단","0943 3.4",
      lambda c,i: c.execute(_DII_COLS + " VALUES(?,?,?,'X',?,NULL,NULL,?,3,1,2,NULL,NULL,NULL,NULL)",(U(),NOW,NOW,NOW,i['dev'])))
check("장치설치 설치일자 NOT NULL 차단","6.2.5",
      lambda c,i: c.execute("INSERT INTO device_install_info(id,created_at,updated_at,device_name,device_info_id)"
                            " VALUES(?,?,?,'X',?)",(U(),NOW,NOW,i['dev'])))
# F-162: NOT NULL 만으로는 빈 문자열이 통과한다 — CHECK(installed_at <> '') 를
# 실제로 넣어봐서 확인한다("컬럼이 있다"와 "값이 온다"는 다르다, F-158 재발 방지).
check("장치설치 설치일자 빈 문자열 차단","6.2.5",
      lambda c,i: c.execute(_DII_COLS + " VALUES(?,?,?,'X','',NULL,NULL,?,NULL,NULL,NULL,NULL,NULL,NULL,NULL)",
                            (U(),NOW,NOW,i['dev'])))
# F-166: 빈 문자열이 아니어도 임의 문자열('not-a-date')은 CHECK(installed_at <> '')
# 만으로는 통과한다 — GLOB 최소 형식 검사를 실제로 넣어봐서 확인한다.
check("장치설치 설치일자 형식(ISO 8601) 위반 차단","6.1",
      lambda c,i: c.execute(_DII_COLS + " VALUES(?,?,?,'X','not-a-date',NULL,NULL,?,NULL,NULL,NULL,NULL,NULL,NULL,NULL)",
                            (U(),NOW,NOW,i['dev'])))
check("장치설치 설치일자 ISO 8601 오프셋 표기 허용","6.1",
      lambda c,i: c.execute(_DII_COLS + " VALUES(?,?,?,'X','2026-08-01T09:00:00+09:00',NULL,NULL,?,NULL,NULL,NULL,NULL,NULL,NULL,NULL)",
                            (U(),NOW,NOW,i['dev'])), expect_fail=False)

# F-184: F-166은 이 형식 검사를 installed_at 하나에만 걸었다 — 나머지
# 시간 컬럼(created_at·updated_at 등)은 검사가 없어 아래 INSERT가 그대로
# 통과했다(재현 그대로 고정).
check("사용자정보 생성시간 형식(ISO 8601) 위반 차단","6.1",
      lambda c,i: c.execute("INSERT INTO user_info(id,created_at,updated_at,name) VALUES(?,?,?,'U')",
                            (U(),'not-a-time',NOW)))
check("사용자정보 갱신시간 형식(ISO 8601) 위반 차단","6.1",
      lambda c,i: c.execute("INSERT INTO user_info(id,created_at,updated_at,name) VALUES(?,?,?,'U')",
                            (U(),NOW,'also-not-time')))
check("사용자정보 삭제시간(nullable) 형식(ISO 8601) 위반 차단","6.1",
      lambda c,i: c.execute("INSERT INTO user_info(id,created_at,updated_at,deleted_at,name) VALUES(?,?,?,?,'U')",
                            (U(),NOW,NOW,'not-a-time')))
check("사용자정보 삭제시간 NULL 허용(미삭제)","6.1",
      lambda c,i: c.execute("INSERT INTO user_info(id,created_at,updated_at,deleted_at,name) VALUES(?,?,?,NULL,'U')",
                            (U(),NOW,NOW)), expect_fail=False)
check("제어실행 승인 규칙 없는 issued_at 형식 위반 차단","6.1",
      lambda c,i: c.execute("INSERT INTO control_execution(id,origin,issued_by,install_id,issued_at,command_json)"
                            " VALUES(?,'MANUAL',?,?,?,'{}')", (U(),i['user'],i['inst'],'not-a-time')))

# ── 0937 승인 게이트 ───────────────────────────────────────
# F-024/F-049: 컬럼명을 명시한다. 위치 지정 INSERT 는 컬럼 추가 시 조용히 깨진다.
RULE_COLS = ("INSERT INTO control_rule(id,created_at,origin,generation,draft_text,"
             "condition_expr,action_json,target_install_id,approved_at,approved_by)")
check("미승인 규칙의 실행명령 차단","0937 부속서A 3.3",
      lambda c,i: c.execute(RULE_COLS + " VALUES(?,?,'AI_DRAFT','AI','내일 33도 예상, 관수 20분',"
                            "NULL,'{\"cmd\":\"open\"}',NULL,NULL,NULL)",(U(),NOW)))
check("승인자 없는 승인 차단","0937 6.3",
      lambda c,i: c.execute(RULE_COLS + " VALUES(?,?,'AI_DRAFT','AI','초안','t>33','{}',?,?,NULL)",(U(),NOW,i['inst'],NOW)))
check("승인된 규칙의 실행명령 허용","0937 부속서A 3.3",
      lambda c,i: c.execute(RULE_COLS + " VALUES(?,?,'AI_DRAFT','AI','초안','t>33','{\"cmd\":\"open\"}',?,?,?)",
                            (U(),NOW,i['inst'],NOW,i['user'])), expect_fail=False)
check("AI 초안 저장 허용 (미승인, 명령 없음)","0937 6.3",
      lambda c,i: c.execute(RULE_COLS + " VALUES(?,?,'AI_DRAFT','AI','초안만',NULL,NULL,NULL,NULL,NULL)",(U(),NOW)), expect_fail=False)
check("미승인 규칙의 대상 확정 차단","0937 부속서A 3.3",
      lambda c,i: c.execute(RULE_COLS + " VALUES(?,?,'AI_DRAFT','AI','초안','t>33',NULL,?,NULL,NULL)",(U(),NOW,i['inst'])))

# ── F-015 회귀: 1:N 카디널리티 (1369-P1 7.1) ───────────────
I2 = "INSERT INTO device_install_info(id,created_at,updated_at,device_name,installed_at,device_info_id) VALUES('i2','2026-08-01T09:00:00+09:00','2026-08-01T09:00:00+09:00','I2','2026-08-01T09:00:00+09:00',?)"
S2 = "INSERT INTO device_state_data(id,reported_at,subtype) VALUES('s2','2026-08-01T09:00:00+09:00','FAN')"
G2 = "INSERT INTO greenhouse_info(id,created_at,updated_at,name) VALUES('g2','2026-08-01T09:00:00+09:00','2026-08-01T09:00:00+09:00','G2')"
def card(name, clause, sqls):
    def fn(c, i):
        for q in sqls: c.execute(q.replace("<DEV>", i['dev']).replace("<INST>", i['inst'])
                                  .replace("<GH>", i['gh']).replace("<FARM>", i['farm'])
                                  .replace("<USER>", i['user']).replace("<DSD>", i['dsd'])
                                  .replace("<ESD>", i['esd']))
    check(name, clause, fn)

card("온실 1개가 농장 2곳에 소속 차단", "7.1(1)", [
  "INSERT INTO farm_info(id,created_at,updated_at,name,owner_id) VALUES('f2','2026-08-01T09:00:00+09:00','2026-08-01T09:00:00+09:00','F2','<USER>')",
  "INSERT INTO greenhouse_own VALUES('<FARM>','<GH>')", "INSERT INTO greenhouse_own VALUES('f2','<GH>')"])
card("온실 1개를 사용자 2명이 관리 차단", "7.1(3)", [
  "INSERT INTO user_info(id,created_at,updated_at,name) VALUES('u2','2026-08-01T09:00:00+09:00','2026-08-01T09:00:00+09:00','U2')",
  "INSERT INTO greenhouse_manage VALUES('<GH>','<USER>')", "INSERT INTO greenhouse_manage VALUES('<GH>','u2')"])
card("장치 1개가 온실 2곳에 설치 차단", "7.1(4)", [
  G2, "INSERT INTO device_install VALUES('<GH>','<INST>')", "INSERT INTO device_install VALUES('g2','<INST>')"])
card("장치 1개를 사용자 2명이 관리 차단", "7.1(7)", [
  "INSERT INTO user_info(id,created_at,updated_at,name) VALUES('u2','2026-08-01T09:00:00+09:00','2026-08-01T09:00:00+09:00','U2')",
  "INSERT INTO device_manage VALUES('<USER>','<INST>')", "INSERT INTO device_manage VALUES('u2','<INST>')"])
card("장치상태 1건이 설치 2건에 귀속 차단", "7.1(8)", [
  I2.replace("?", "'<DEV>'"), "INSERT INTO device_state VALUES('r1','<INST>','<DSD>')",
  "INSERT INTO device_state VALUES('r2','i2','<DSD>')"])
card("환경상태 1건을 장치 2개가 측정 차단", "7.1(9)", [
  I2.replace("?", "'<DEV>'"), "INSERT INTO env_measure VALUES('r1','<INST>','<ESD>')",
  "INSERT INTO env_measure VALUES('r2','i2','<ESD>')"])
card("환경상태 1건이 온실 2곳에 귀속 차단", "7.1(5)", [
  G2, "INSERT INTO greenhouse_env VALUES('r1','<GH>','<ESD>')",
  "INSERT INTO greenhouse_env VALUES('r2','g2','<ESD>')"])
card("환경상태 1건이 장치상태 2건에 귀속 차단", "7.1(10)", [
  S2, "INSERT INTO operating_env VALUES('<DSD>','<ESD>')", "INSERT INTO operating_env VALUES('s2','<ESD>')"])

# ── F-016 회귀: 불변성 제약 보강분 ─────────────────────────
check("device_info.created_at UPDATE 차단", "7.2.2.4",
      lambda c,i: c.execute("UPDATE device_info SET created_at='t2' WHERE id=?", (i['dev'],)))
check("device_install_info.created_at UPDATE 차단", "7.2.2.5",
      lambda c,i: c.execute("UPDATE device_install_info SET created_at='t2' WHERE id=?", (i['inst'],)))
check("user_info.created_at UPDATE 차단", "7.2.2.6",
      lambda c,i: c.execute("UPDATE user_info SET created_at='t2' WHERE id=?", (i['user'],)))
for nm, cl, tbl, cols in [("온실소유","7.2.2.7","greenhouse_own","farm_id"),
                          ("온실관리","7.2.2.8","greenhouse_manage","user_id"),
                          ("장치설치","7.2.2.9","device_install","greenhouse_id"),
                          ("장치관리","7.2.2.10","device_manage","user_id")]:
    def mk(tbl=tbl, cols=cols):
        def fn(c,i):
            a = {"greenhouse_own":(i['farm'],i['gh']), "greenhouse_manage":(i['gh'],i['user']),
                 "device_install":(i['gh'],i['inst']), "device_manage":(i['user'],i['inst'])}[tbl]
            c.execute(f"INSERT INTO {tbl} VALUES(?,?)", a)
            c.execute(f"UPDATE {tbl} SET {cols}='ZZZ'")
        return fn
    check(f"{nm} 관계 FK UPDATE 차단", cl, mk())
def oe(c,i):
    c.execute("INSERT INTO device_state_data(id,reported_at,subtype) VALUES('s2','2026-08-01T09:00:00+09:00','FAN')")
    c.execute("INSERT INTO operating_env VALUES(?,?)", (i['dsd'], i['esd']))
    c.execute("UPDATE operating_env SET device_state_id='s2'")
check("작동환경 관계 FK UPDATE 차단", "7.2.3.4", oe)
for nm, cl, tbl, a, b in [("장치상태","7.2.4.2","device_state","inst","dsd"),
                          ("환경측정","7.2.4.3","env_measure","inst","esd"),
                          ("온실환경","7.2.4.4","greenhouse_env","gh","esd")]:
    def mk(tbl=tbl,a=a,b=b):
        def fn(c,i):
            c.execute(f"INSERT INTO {tbl} VALUES('r1',?,?)", (i[a], i[b]))
            c.execute(f"UPDATE {tbl} SET id='r9' WHERE id='r1'")
        return fn
    check(f"{nm} 관계 식별자 UPDATE 차단", cl, mk())

# ── F-017 회귀: 제어 실행의 권한 출처 ──────────────────────
def unapproved(c,i):
    c.execute("INSERT INTO control_rule(id,created_at,origin,generation,draft_text) VALUES('r','2026-08-01T09:00:00+09:00','AI_DRAFT','AI','초안')")
    c.execute("INSERT INTO control_execution(id,origin,rule_id,install_id,issued_at,command_json)"
              " VALUES('x','RULE','r',?,'2026-08-01T09:00:00+09:00','{}')", (i['inst'],))
check("미승인 규칙 기반 제어 실행 차단", "0937 A.3.2", unapproved)
def noauth(c,i):
    c.execute("INSERT INTO control_execution(id,origin,install_id,issued_at,command_json)"
              " VALUES('x','RULE',?,'2026-08-01T09:00:00+09:00','{}')", (i['inst'],))
check("권한 출처 없는 제어 실행 차단", "0937 A.3.2", noauth)
def approved_ok(c,i):
    c.execute("INSERT INTO control_rule(id,created_at,origin,generation,draft_text,condition_expr,action_json,target_install_id,approved_at,approved_by)"
              " VALUES('r','2026-08-01T09:00:00+09:00','AI_DRAFT','AI','초안','t>33','{}',?,?,?)", (i['inst'], NOW, i['user']))
    c.execute("INSERT INTO control_execution(id,origin,rule_id,install_id,issued_at,command_json)"
              " VALUES('x','RULE','r',?,'2026-08-01T09:00:00+09:00','{}')", (i['inst'],))
check("승인된 규칙 기반 제어 실행 허용", "0937 A.3.2", approved_ok, expect_fail=False)
def manual_ok(c,i):
    c.execute("INSERT INTO control_execution(id,origin,issued_by,install_id,issued_at,command_json)"
              " VALUES('x','MANUAL',?,?,'2026-08-01T09:00:00+09:00','{}')", (i['user'], i['inst']))
check("사용자 직접 지시(MANUAL) 허용", "0937 A.1·A.2", manual_ok, expect_fail=False)
def revoke(c,i):
    c.execute("INSERT INTO control_rule(id,created_at,origin,generation,draft_text,condition_expr,action_json,target_install_id,approved_at,approved_by)"
              " VALUES('r','2026-08-01T09:00:00+09:00','AI_DRAFT','AI','초안','t>33','{}',?,?,?)", (i['inst'], NOW, i['user']))
    c.execute("UPDATE control_rule SET approved_at=NULL WHERE id='r'")
check("승인 철회 차단", "0937 6.3", revoke)

# ── F-030 회귀: 승인 명령과 실행 명령의 결속 ───────────────
def approved_rule(c, i, action='{"value":0}', cond='t>33', target=None):
    c.execute("INSERT INTO control_rule(id,created_at,origin,generation,draft_text,condition_expr,action_json,target_install_id,approved_at,approved_by)"
              " VALUES('r','2026-08-01T09:00:00+09:00','AI_DRAFT','AI','초안',?,?,?,?,?)",
              (cond, action, target or i['inst'], NOW, i['user']))
def mismatch(c,i):
    approved_rule(c,i)
    c.execute("INSERT INTO control_execution(id,origin,rule_id,install_id,issued_at,command_json)"
              ' VALUES(\'x\',\'RULE\',\'r\',?,\'2026-08-01T09:00:00+09:00\',\'{"value":1}\')', (i['inst'],))
check("승인 내용과 다른 명령 실행 차단", "0937 A.3.2", mismatch)
def match_ok(c,i):
    approved_rule(c,i)
    c.execute("INSERT INTO control_execution(id,origin,rule_id,install_id,issued_at,command_json)"
              ' VALUES(\'x\',\'RULE\',\'r\',?,\'2026-08-01T09:00:00+09:00\',\'{"value":0}\')', (i['inst'],))
check("승인 내용과 일치하는 명령 허용", "0937 A.3.2", match_ok, expect_fail=False)
def tamper(c,i):
    approved_rule(c,i)
    c.execute('UPDATE control_rule SET action_json=\'{"value":9}\' WHERE id=\'r\'')
check("승인 후 명령 변조 차단", "0937 6.3", tamper)

# ── F-039 회귀: 승인 스냅샷의 NULL·조건 변조 우회 ──────────
def approved_null_action(c,i):
    """승인 상태 + action_json NULL 자체를 금지한다."""
    c.execute("INSERT INTO control_rule(id,created_at,origin,generation,draft_text,condition_expr,action_json,target_install_id,approved_at,approved_by)"
              " VALUES('r','2026-08-01T09:00:00+09:00','AI_DRAFT','AI','초안','t>40',NULL,?,?,?)", (i['inst'], NOW, i['user']))
check("승인 규칙의 NULL 명령 차단", "0937 A.3.2", approved_null_action)

def approved_null_condition(c,i):
    c.execute("INSERT INTO control_rule(id,created_at,origin,generation,draft_text,condition_expr,action_json,target_install_id,approved_at,approved_by)"
              " VALUES('r','2026-08-01T09:00:00+09:00','AI_DRAFT','AI','초안',NULL,'{\"value\":0}',?,?,?)", (i['inst'], NOW, i['user']))
check("승인 규칙의 NULL 조건식 차단", "0937 A.3.2", approved_null_condition)

def approve_update_without_action(c,i):
    """미승인 규칙을 명령 없이 승인 상태로 UPDATE 하는 경로도 막힌다."""
    c.execute("INSERT INTO control_rule(id,created_at,origin,generation,draft_text) VALUES('r','2026-08-01T09:00:00+09:00','AI_DRAFT','AI','초안')")
    c.execute("UPDATE control_rule SET approved_at=?, approved_by=? WHERE id='r'", (NOW, i['user']))
check("명령 없는 승인 UPDATE 차단", "0937 A.3.2", approve_update_without_action)

def atomic_approval_ok(c,i):
    """정상 경로 — 조건·명령·승인자를 한 번에 채우는 단일 UPDATE."""
    c.execute("INSERT INTO control_rule(id,created_at,origin,generation,draft_text) VALUES('r','2026-08-01T09:00:00+09:00','AI_DRAFT','AI','초안')")
    c.execute("UPDATE control_rule SET condition_expr='t>33', action_json='{\"value\":0}',"
              " target_install_id=?, approved_at=?, approved_by=? WHERE id='r'", (i['inst'], NOW, i['user']))
    c.execute("INSERT INTO control_execution(id,origin,rule_id,install_id,issued_at,command_json)"
              ' VALUES(\'x\',\'RULE\',\'r\',?,\'2026-08-01T09:00:00+09:00\',\'{"value":0}\')', (i['inst'],))
check("원자적 승인 UPDATE 후 실행 허용", "0937 A.3.2", atomic_approval_ok, expect_fail=False)

def cond_tamper(c,i):
    approved_rule(c,i)
    c.execute("UPDATE control_rule SET condition_expr='t>0' WHERE id='r'")
check("승인 후 조건식 변조 차단", "0937 A.3.2", cond_tamper)

def null_action_arbitrary_command(c,i):
    """F-039 원 시나리오 — NULL 승인이 막히므로 규칙 생성 단계에서 실패한다.
    설령 통과하더라도 trg_exec_command_matches_approved 가 IS NOT 로 차단한다."""
    c.execute("INSERT INTO control_rule(id,created_at,origin,generation,draft_text,condition_expr,action_json,target_install_id,approved_at,approved_by)"
              " VALUES('r','2026-08-01T09:00:00+09:00','AI_DRAFT','AI','초안','t>40',NULL,?,?,?)", (i['inst'], NOW, i['user']))
    c.execute("INSERT INTO control_execution(id,origin,rule_id,install_id,issued_at,command_json)"
              ' VALUES(\'x\',\'RULE\',\'r\',?,\'2026-08-01T09:00:00+09:00\',\'{"value":1}\')', (i['inst'],))
check("NULL 승인 경유 임의 명령 실행 차단", "0937 A.3.2", null_action_arbitrary_command)

# ── F-048 회귀: 승인 출처(누가·언제)의 불변성 ───────────────
def approver_tamper(c,i):
    approved_rule(c,i)
    other = U()
    c.execute("INSERT INTO user_info(id,created_at,updated_at,name) VALUES(?,?,?,'다른사용자')",(other,NOW,NOW))
    c.execute("UPDATE control_rule SET approved_by=? WHERE id='r'", (other,))
check("승인자 사후 변조 차단", "0937 A.3.2", approver_tamper)

def approved_at_tamper(c,i):
    approved_rule(c,i)
    c.execute("UPDATE control_rule SET approved_at='1999-01-01T00:00:00' WHERE id='r'")
check("승인시각 사후 변조 차단", "0937 A.3.2", approved_at_tamper)

# ── F-049 회귀: 승인 대상 장치의 결속 ──────────────────────
def second_install(c, i):
    """같은 노드의 두 번째 구동기. 승인 대상이 아닌 장치를 만든다."""
    other = U()
    c.execute("INSERT INTO device_install_info(id,created_at,updated_at,device_name,installed_at,"
              "device_info_id,siap_node_id,siap_device_id,siap_subtype)"
              " VALUES(?,?,?,'밸브B',?,?,3,2,133)", (other, NOW, NOW, NOW, i['dev']))
    return other

def target_mismatch(c,i):
    approved_rule(c,i)                       # target = i['inst']
    other = second_install(c,i)
    c.execute("INSERT INTO control_execution(id,origin,rule_id,install_id,issued_at,command_json)"
              ' VALUES(\'x\',\'RULE\',\'r\',?,\'2026-08-01T09:00:00+09:00\',\'{"value":0}\')', (other,))
check("승인 대상과 다른 장치 실행 차단", "0937 6.5", target_mismatch)

def target_match_ok(c,i):
    approved_rule(c,i)
    c.execute("INSERT INTO control_execution(id,origin,rule_id,install_id,issued_at,command_json)"
              ' VALUES(\'x\',\'RULE\',\'r\',?,\'2026-08-01T09:00:00+09:00\',\'{"value":0}\')', (i['inst'],))
check("승인 대상과 일치하는 장치 실행 허용", "0937 6.5", target_match_ok, expect_fail=False)

def exec_target_swap(c,i):
    approved_rule(c,i)
    other = second_install(c,i)
    c.execute("INSERT INTO control_execution(id,origin,rule_id,install_id,issued_at,command_json)"
              ' VALUES(\'x\',\'RULE\',\'r\',?,\'2026-08-01T09:00:00+09:00\',\'{"value":0}\')', (i['inst'],))
    c.execute("UPDATE control_execution SET install_id=? WHERE id='x'", (other,))
check("실행 후 대상 장치 바꿔치기 차단", "0937 6.5", exec_target_swap)

def approved_target_tamper(c,i):
    approved_rule(c,i)
    other = second_install(c,i)
    c.execute("UPDATE control_rule SET target_install_id=? WHERE id='r'", (other,))
check("승인 후 대상 장치 변조 차단", "0937 A.3.2", approved_target_tamper)

def approve_update_without_target(c,i):
    c.execute("INSERT INTO control_rule(id,created_at,origin,generation,draft_text) VALUES('r','2026-08-01T09:00:00+09:00','AI_DRAFT','AI','초안')")
    c.execute("UPDATE control_rule SET condition_expr='t>33', action_json='{}',"
              " approved_at=?, approved_by=? WHERE id='r'", (NOW, i['user']))
check("대상 없는 승인 UPDATE 차단", "0937 6.5", approve_update_without_target)

def manual_target_free(c,i):
    """MANUAL 실행은 사용자 지시가 권한 출처이므로 규칙 대상에 묶이지 않는다."""
    other = second_install(c,i)
    c.execute("INSERT INTO control_execution(id,origin,issued_by,install_id,issued_at,command_json)"
              ' VALUES(\'x\',\'MANUAL\',?,?,\'2026-08-01T09:00:00+09:00\',\'{"value":1}\')', (i['user'], other))
check("MANUAL 실행은 대상 제약 없음", "0937 A.1·A.2", manual_target_free, expect_fail=False)

# ── F-032 회귀: 표준 커버리지 ──────────────────────────────
def crop(c,i):
    c.execute("UPDATE greenhouse_info SET crop='토마토' WHERE id=?", (i['gh'],))
check("온실 생육작물 컬럼 존재", "6.2.3", crop, expect_fail=False)
# F-185: 6.2.4 "장치정보에는... 장치특성 등이 포함되어야 한다" — 저장할
# 컬럼이 없었다. manufacturer 와 같은 자격(nullable)으로 추가했다.
def device_characteristics(c,i):
    c.execute("UPDATE device_info SET device_characteristics='IP65 방수' WHERE id=?", (i['dev'],))
check("장치정보 장치특성 컬럼 존재", "6.2.4", device_characteristics, expect_fail=False)
def rain_unit(c,i):
    c.execute("INSERT INTO env_state_data(id,measured_at) VALUES('e2',?)", (NOW,))
    c.execute("INSERT INTO env_measurement(id,subtype,value,unit) VALUES('e2','RAIN_DETECTION',1,'ON/OFF')")
check("감우 단위 저장 허용", "6.3.3.8", rain_unit, expect_fail=False)
def rain_range(c,i):
    c.execute("INSERT INTO env_state_data(id,measured_at) VALUES('e3',?)", (NOW,))
    c.execute("INSERT INTO env_measurement(id,subtype,value,unit,error_range,lower_limit,upper_limit)"
              " VALUES('e3','RAIN_DETECTION',1,'ON/OFF',0.1,0,1)")
check("감우 오차·유효범위 차단", "그림 7-3", rain_range)

# ── F-083 회귀: 규칙 거부도 영속 상태다 (0937 부속서 A 3.2 절차 3) ──
REJ = ("INSERT INTO control_rule(id,created_at,origin,generation,draft_text,"
       "rejected_at,rejected_by,reject_reason)")
def _mk(c, i, rid="rj1"):
    c.execute("INSERT INTO control_rule(id,created_at,origin,generation,draft_text)"
              " VALUES(?,?,'AI_DRAFT','AI','초안')", (rid, NOW))
    return rid

check("거부자 없는 거부 차단", "0937 부속서A 3.2",
      lambda c,i: c.execute(REJ + " VALUES(?,?,'AI_DRAFT','AI','초안',?,NULL,'부적절')", (U(),NOW,NOW)))
check("거부 저장 허용 (사유 포함)", "0937 부속서A 3.2",
      lambda c,i: c.execute(REJ + " VALUES(?,?,'AI_DRAFT','AI','초안',?,?,'임계값 과도')",
                            (U(),NOW,NOW,i['user'])), expect_fail=False)
# 승인·거부 동시 상태는 내용 제약만으로도 불가능하다 - 배타 CHECK 는 그 함의를
# 명시한 것이며 단독 반례가 없다(schema.sql 주석). 두 방향을 각각 확인한다.
check("동시 상태 차단 - 승인 내용 + 거부 표시", "0937 부속서A 3.2",
      lambda c,i: c.execute(
          "INSERT INTO control_rule(id,created_at,origin,generation,draft_text,condition_expr,"
          "action_json,target_install_id,approved_at,approved_by,rejected_at,rejected_by)"
          " VALUES(?,?,'AI_DRAFT','AI','초안','t>33','{}',?,?,?,?,?)",
          (U(),NOW,i['inst'],NOW,i['user'],NOW,i['user'])))
check("동시 상태 차단 - 거부 내용 + 승인 표시", "0937 부속서A 3.2",
      lambda c,i: c.execute(
          "INSERT INTO control_rule(id,created_at,origin,generation,draft_text,"
          "approved_at,approved_by,rejected_at,rejected_by)"
          " VALUES(?,?,'AI_DRAFT','AI','초안',?,?,?,?)",
          (U(),NOW,NOW,i['user'],NOW,i['user'])))
# generation - origin 은 요청자 의도, generation 은 서버 실행 결과다 (F-083)
check("AI 초안인데 생성 경로 없음 차단", "0937 6.3",
      lambda c,i: c.execute("INSERT INTO control_rule(id,created_at,origin,draft_text)"
                            " VALUES(?,?,'AI_DRAFT','초안')", (U(),NOW)))
check("AI 초안 + THRESHOLD 폴백 허용", "0937 6.3",
      lambda c,i: c.execute("INSERT INTO control_rule(id,created_at,origin,generation,draft_text)"
                            " VALUES(?,?,'AI_DRAFT','THRESHOLD_FALLBACK','초안')",
                            (U(),NOW)), expect_fail=False)
check("정의되지 않은 생성 경로 차단", "0937 6.3",
      lambda c,i: c.execute("INSERT INTO control_rule(id,created_at,origin,generation,draft_text)"
                            " VALUES(?,?,'WIZARD','GPT','초안')", (U(),NOW)))
check("거부된 규칙의 실행명령 차단 (미승인 제약 경유)", "0937 부속서A 3.2",
      lambda c,i: c.execute(
          "INSERT INTO control_rule(id,created_at,origin,generation,draft_text,action_json,"
          "rejected_at,rejected_by) VALUES(?,?,'AI_DRAFT','AI','초안','{\"cmd\":\"open\"}',?,?)",
          (U(),NOW,NOW,i['user'])))

def _rej_then(sql, *args):
    def fn(c, i):
        rid = U()
        c.execute(REJ + " VALUES(?,?,'AI_DRAFT','AI','초안',?,?,'사유')", (rid,NOW,NOW,i['user']))
        c.execute(sql, tuple(a if a != "<RID>" else rid
                             for a in (x.replace("<USER>", i['user']) if isinstance(x,str) else x
                                       for x in args)))
    return fn
check("거부 뒤 승인 차단", "0937 부속서A 3.2",
      _rej_then("UPDATE control_rule SET approved_at=?, approved_by=? WHERE id=?",
                NOW, "<USER>", "<RID>"))
check("거부 사실 변경 차단 (불변)", "0937 부속서A 3.2",
      _rej_then("UPDATE control_rule SET rejected_at=? WHERE id=?", "2099-01-01", "<RID>"))

def _app_then_rej(c, i):
    rid = U()
    c.execute("INSERT INTO control_rule(id,created_at,origin,generation,draft_text,condition_expr,"
              "action_json,target_install_id,approved_at,approved_by)"
              " VALUES(?,?,'AI_DRAFT','AI','초안','t>33','{}',?,?,?)",
              (rid,NOW,i['inst'],NOW,i['user']))
    # F-091: 사유를 함께 넣는다. 비워 두면 배타 CHECK 가 아니라 사유 동시성 CHECK 에
    #        먼저 걸려 이 테스트가 무엇을 증명하는지 흐려진다.
    c.execute("UPDATE control_rule SET rejected_at=?, rejected_by=?, reject_reason=? WHERE id=?",
              (NOW, i['user'], '대상 장치가 다름', rid))
check("승인 뒤 거부 차단", "0937 부속서A 3.2", _app_then_rej)


# ── F-091 / F-092 — 생성경로 위조 · 거부 증거 · 알림 결속 ──────────────────
# 지적된 반례를 그대로 테스트로 고정한다. 다섯 건 모두 지적 시점에 '허용됨'이었다.
check("사람 규칙을 AI 산출물로 위조 차단", "0937 6.3",
      lambda c,i: c.execute("INSERT INTO control_rule(id,created_at,origin,generation,draft_text)"
                            " VALUES(?,?,'WIZARD','AI','초안')", (U(),NOW)))
check("생성 경로가 origin 과 어긋남 차단", "0937 6.3",
      lambda c,i: c.execute("INSERT INTO control_rule(id,created_at,origin,generation,draft_text)"
                            " VALUES(?,?,'SCRIPT','WIZARD','초안')", (U(),NOW)))
check("위자드 규칙 + 같은 생성 경로 허용", "0937 6.3",
      lambda c,i: c.execute("INSERT INTO control_rule(id,created_at,origin,generation,draft_text)"
                            " VALUES(?,?,'WIZARD','WIZARD','초안')", (U(),NOW)), expect_fail=False)
check("생성 경로 미기재 허용 (AI 아닌 경우)", "0937 6.3",
      lambda c,i: c.execute("INSERT INTO control_rule(id,created_at,origin,draft_text)"
                            " VALUES(?,?,'WIZARD','초안')", (U(),NOW)), expect_fail=False)
check("사유 없는 거부 차단", "0937 부속서A 3.2",
      lambda c,i: c.execute(
          "INSERT INTO control_rule(id,created_at,origin,generation,draft_text,rejected_at,rejected_by)"
          " VALUES(?,?,'AI_DRAFT','AI','초안',?,?)", (U(),NOW,NOW,i['user'])))
check("공백뿐인 거부 사유 차단", "0937 부속서A 3.2",
      lambda c,i: c.execute(
          "INSERT INTO control_rule(id,created_at,origin,generation,draft_text,rejected_at,rejected_by,reject_reason)"
          " VALUES(?,?,'AI_DRAFT','AI','초안',?,?,'   ')", (U(),NOW,NOW,i['user'])))
check("거부 없이 사유만 차단", "0937 부속서A 3.2",
      lambda c,i: c.execute(
          "INSERT INTO control_rule(id,created_at,origin,generation,draft_text,reject_reason)"
          " VALUES(?,?,'AI_DRAFT','AI','초안','사유')", (U(),NOW)))
check("거부 사유 사후 변경 차단 (불변)", "0937 부속서A 3.2",
      _rej_then("UPDATE control_rule SET reject_reason=? WHERE id=?", "다른 사유", "<RID>"))

check("NEC 알림인데 원본 프레임 없음 차단", "0943 8.2.1.1",
      lambda c,i: c.execute("INSERT INTO alert(id,raised_at,kind,severity,siap_nec,message)"
                            " VALUES(?,?,'NODE_ERROR','WARN',7,'배터리 부족')", (U(),NOW)))
def _nec_with_frame(c, i):
    fid = U()
    c.execute("INSERT INTO frame_log(id,t,direction,raw_hex,is_valid)"
              " VALUES(?,?, 'rx','0102','1')", (fid, 1786000000.0))
    c.execute("INSERT INTO alert(id,raised_at,kind,severity,siap_nec,message,frame_id)"
              " VALUES(?,?,'NODE_ERROR','WARN',7,'배터리 부족',?)", (U(),NOW,fid))
check("NEC 알림 + 원본 프레임 결속 허용", "0943 8.2.1.1", _nec_with_frame, expect_fail=False)
check("임계 알림은 프레임 없이 허용", "0937 부속서A 1.3",
      lambda c,i: c.execute("INSERT INTO alert(id,raised_at,kind,severity,message)"
                            " VALUES(?,?,'THRESHOLD','WARN','상한 초과')", (U(),NOW)),
      expect_fail=False)

# ── 출력 ───────────────────────────────────────────────────
w = max(len(n) for _,n,_,_ in results)
print("\n[2차 검증] 표준 유래 제약 동작 테스트\n")
for ok,name,clause,msg in results:
    print(f"  {'PASS' if ok else 'FAIL'}  {name:<{w}}  {clause:<18} ({msg})")
p = sum(1 for ok,*_ in results if ok)
print(f"\n  {p}/{len(results)} 통과")
sys.exit(0 if p==len(results) else 1)
