-- =============================================================================
--  스마트 온실 데이터 스키마
--  TTAK.KO-10.1369-Part1 7.2 논리적 모델 직역
--  + TTAK.KO-10.0937 서비스 계층 요구 테이블
--  + TTAK.KO-10.0943 연동 지점
--  DBMS: SQLite 3
-- =============================================================================
--  식별자 표기: ITU-T X.667 (UUID)  — 1369-P1 6.1
--  시간 표기  : ISO 8601 TEXT       — 1369-P1 6.1
-- =============================================================================

PRAGMA foreign_keys = ON;

-- =============================================================================
--  A. 설정형 데이터  (1369-Part1 6.2 / 7.2.2)
-- =============================================================================

-- F-184: 6.1 "시간을 다루는 일관된 형식의 표기가 지정되어야 한다" — 이
--        구현은 ISO 8601(설계서 §1-3)로 결정했다. F-166은 이 최소 GLOB
--        형식 검사(연-월-일로 시작)를 `device_install_info.installed_at`
--        하나에만 걸었다 — 나머지 시간 컬럼(created_at·updated_at 등)은
--        검사가 없어 `INSERT INTO user_info(...) VALUES(...,'not-a-time',
--        'also-not-time',...)`가 그대로 통과했다(재현 확인). 6.1은 특정
--        컬럼이 아니라 "시간을 다루는" 모든 표기에 적용되므로, 이 참조
--        구현이 시간으로 관리하는 모든 TEXT 컬럼에 같은 최소 검사를 건다.
--        시각·오프셋 세부 형식까지는 강제하지 않는다(F-166과 같은 이유 —
--        과한 정규식은 그 자체가 새 표준 미규정 해석이 된다). 매크로로
--        중복을 줄이지 않는 이유: SQLite는 CHECK 안에서 매크로·함수를
--        쓸 수 없다(표현식만 허용) — 컬럼마다 그대로 반복해 적는다.

-- A-1. 농장 정보 — 6.2.2 / 7.2.2.2
CREATE TABLE farm_info (
    id            TEXT PRIMARY KEY,                    -- 식별자 (불변)
    created_at    TEXT NOT NULL,                       -- 생성시간 (불변)
    updated_at    TEXT NOT NULL,
    name          TEXT NOT NULL,                       -- 이름
    owner_id      TEXT NOT NULL,                       -- 소유자 (FK → user_info)
    location      TEXT,                                -- 위치
    location_type TEXT,                                --   값의 타입 (GPS/GPX/ADDRESS)
    location_unit TEXT,                                --   단위
    area_value    REAL,                                -- 면적 값
    area_error    REAL,                                --   오차범위
    area_unit     TEXT,                                --   단위
    FOREIGN KEY (owner_id) REFERENCES user_info(id),
    CHECK (created_at GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]*'),   -- F-184
    CHECK (updated_at GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]*')    -- F-184
);

-- A-2. 온실 정보 — 6.2.3 / 7.2.2.3
CREATE TABLE greenhouse_info (
    id             TEXT PRIMARY KEY,
    created_at     TEXT NOT NULL,
    updated_at     TEXT NOT NULL,
    name           TEXT NOT NULL,
    location       TEXT,
    location_type  TEXT,
    location_unit  TEXT,
    width_value    REAL,  width_error  REAL,  width_unit  TEXT,   -- 폭
    height_value   REAL,  height_error REAL,  height_unit TEXT,   -- 높이
    length_value   REAL,  length_error REAL,  length_unit TEXT,   -- 길이
    gh_type        TEXT,                                          -- 유형
    medium_type    TEXT,                                          -- 배지종류
    irrigation_type TEXT,                                         -- 관수유형
    heating_type   TEXT,                                          -- 난방형태
    crop           TEXT,                                          -- 생육작물 (6.2.3 본문)
    crop_season    TEXT,                                          -- 작기정보
    usage_state    TEXT,                                          -- 활용상태
    -- F-258: 기상청 단기예보(getVilageFcst) 는 일반 위경도가 아니라 동네예보
    --        격자(nx,ny)를 요구한다. 온실별 WGS84 위경도와 그로부터 계산한
    --        격자를 저장해 온실마다 자기 위치의 예보를 수집한다. 전역 최신
    --        레코드를 위치 무관하게 쓰던 문제를 닫는다.
    latitude       REAL,                                          -- WGS84 위도
    longitude      REAL,                                          -- WGS84 경도
    kma_nx         INTEGER,                                       -- 기상청 격자 X (위경도 파생, 내부값)
    kma_ny         INTEGER,                                       -- 기상청 격자 Y (위경도 파생, 내부값)
    coordinate_source TEXT,                                       -- 좌표 출처 (MANUAL·DEMO_FIXTURE)
    coordinates_updated_at TEXT,                                  -- 좌표 확정·변경 시각
    CHECK (created_at GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]*'),   -- F-184
    CHECK (updated_at GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]*'),   -- F-184
    -- F-258: 위경도 범위·격자 정수·출처·시각 형식을 DDL 로 강제한다 —
    --        브라우저 입력을 그대로 신뢰하지 않는다(제안 §2·§3).
    CHECK (latitude  IS NULL OR (latitude  BETWEEN -90.0  AND 90.0)),
    CHECK (longitude IS NULL OR (longitude BETWEEN -180.0 AND 180.0)),
    CHECK (kma_nx IS NULL OR (typeof(kma_nx) = 'integer' AND kma_nx > 0)),
    CHECK (kma_ny IS NULL OR (typeof(kma_ny) = 'integer' AND kma_ny > 0)),
    CHECK (coordinate_source IS NULL OR coordinate_source IN ('MANUAL','DEMO_FIXTURE')),
    CHECK (coordinates_updated_at IS NULL OR coordinates_updated_at GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]*'),
    -- 위경도·격자는 함께 확정된다 — 넷 다 있거나 넷 다 없다(부분 저장 금지, 제안 §3)
    CHECK ((latitude IS NULL) = (longitude IS NULL)
       AND (latitude IS NULL) = (kma_nx IS NULL)
       AND (latitude IS NULL) = (kma_ny IS NULL))
);

-- A-3. 장치 정보 — 6.2.4 / 7.2.2.4
CREATE TABLE device_info (
    id            TEXT PRIMARY KEY,
    created_at    TEXT NOT NULL,
    updated_at    TEXT NOT NULL,
    device_name   TEXT NOT NULL,                       -- 장치이름
    device_kind   TEXT NOT NULL,                       -- 장치종류
    -- F-159: "모델명은 장치를 고유하게 식별하는 속성으로... 모든 스마트 온실
    --        서비스에서 장치를 고유하게 식별"(6.2.4) — UNIQUE로 강제한다.
    --        NOT NULL만으로는 같은 model_name 을 가진 행이 여러 개 존재할
    --        수 있어 "전역 식별"이 문서상 주장일 뿐 DDL로 보장되지 않았다.
    model_name    TEXT NOT NULL UNIQUE,                 -- 모델명 (불변, 전역 식별)
    manufacturer  TEXT,                                -- 제조사
    -- F-185: 6.2.4 "장치정보에는 장치코드, 장치이름, 장치종류, 장치모델,
    --        장치제조사, 장치특성 등이 포함되어야 한다" — 장치특성을 저장할
    --        컬럼이 없었다. manufacturer 와 같은 자격(nullable, 0943
    --        REQ_SET_CONNECTION 이 나르지 않는 속성)으로 추가한다 — 이
    --        참조 구현의 동적 등록 경로(REQ_SET_CONNECTION)는 채우지
    --        않는다(0943 미규정 속성). 자유 텍스트로 둔다 — 1369-P1은
    --        장치특성의 세부 구조를 규정하지 않는다.
    device_characteristics TEXT,                       -- 장치특성 (F-185)
    CHECK (created_at GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]*'),   -- F-184
    CHECK (updated_at GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]*')    -- F-184
);

-- A-4. 장치설치 정보 — 6.2.5 / 7.2.2.5
--      ※ siap_* 컬럼은 0943 연동을 위한 확장 (1369-P1 미규정, docs에 명시)
CREATE TABLE device_install_info (
    id              TEXT PRIMARY KEY,
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL,
    device_name     TEXT NOT NULL,                     -- 장치이름
    -- F-158: 6.2.5 "장치설치정보에는 장치식별자, 장치이름, 설치온실, 설치일자,
    --        설치위치 등이 포함되어야 한다" — 설치일자가 누락돼 있었다.
    --        설치온실은 이 표에 없다(관계 엔티티 device_install 이 이미
    --        표현한다 — §5 불일치 판정 #1과 같은 근거로 FK 중복을 피한다).
    -- F-162: NOT NULL만으로는 빈 문자열('')이 통과한다 — "설치일자가
    --        실제로 있다"는 6.2.5 요구를 DDL로 보장하려면 값이 있어야 한다.
    -- F-166: 빈 문자열이 아니어도 'not-a-date' 같은 임의 문자열은 막지 못한다.
    --        6.1 "시간을 다루는 일관된 형식의 표기가 지정되어야 한다" — 이
    --        구현은 ISO 8601(설계서 §1-3)로 결정했다. SQLite에 정규식이 없어
    --        GLOB으로 최소 조건(YYYY-MM-DD 로 시작)만 강제한다 — 시각·오프셋
    --        세부 형식까지 DDL로 강제하지 않는다(과한 정규식은 그 자체가
    --        새 표준 미규정 해석이 된다). 나머지는 API 계층(F-166,
    --        api_verify.py)이 RFC 3339 전체를 검사한다.
    installed_at    TEXT NOT NULL,                     -- 설치일자 (6.2.5)
    install_location TEXT,                             -- 설치위치
    install_loc_unit TEXT,                             --   단위
    device_info_id  TEXT NOT NULL,                     -- 장치정보 식별자 (FK)
    -- ↓ 0943 연동 확장
    siap_node_id    INTEGER,                           -- 0943 Node ID (20bit)
    siap_device_id  INTEGER,                           -- 0943 Device ID (8bit)
    siap_subtype    INTEGER,                           -- 0943 Subtype (8bit)
    siap_value_type INTEGER,                           -- 0943 표 7-14 Value Type (2bit)
    transfer_mode   TEXT,                              -- 0943 표 7-15 Transfer Mode 이름
    period_sec      INTEGER,                           -- 0943 표 7-15 Period (14bit, sec)
    -- ↓ 1369-P1 6.3.2 "단위·유효범위·오차범위가 관리되어야 한다"
    unit            TEXT,
    lower_limit     REAL,
    upper_limit     REAL,
    precision_val   REAL,
    FOREIGN KEY (device_info_id) REFERENCES device_info(id),
    UNIQUE (siap_node_id, siap_device_id),
    CHECK (siap_node_id   IS NULL OR (siap_node_id   BETWEEN 0 AND 1048575)),
    CHECK (siap_device_id IS NULL OR (siap_device_id BETWEEN 0 AND 255)),
    CHECK (siap_subtype   IS NULL OR (siap_subtype   BETWEEN 0 AND 255)),
    CHECK (siap_value_type IS NULL OR (siap_value_type BETWEEN 0 AND 2)),
    CHECK (transfer_mode IS NULL OR transfer_mode IN ('PERIODIC','EVENT','BOTH')),
    CHECK (period_sec IS NULL OR period_sec BETWEEN 0 AND 16383),
    CHECK (installed_at <> ''),                          -- F-162
    CHECK (installed_at GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]*'), -- F-166
    CHECK (created_at GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]*'),   -- F-184
    CHECK (updated_at GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]*')    -- F-184
);

-- A-5. 사용자 정보 — 6.2.6 / 7.2.2.6
CREATE TABLE user_info (
    id          TEXT PRIMARY KEY,
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL,
    deleted_at  TEXT,                                  -- 삭제시간 (7.2.2.6)
    name        TEXT NOT NULL,
    group_id    TEXT,                                  -- 소속 그룹 식별자
    group_role  TEXT,                                  -- 그룹 내 권한
    CHECK (created_at GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]*'),   -- F-184
    CHECK (updated_at GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]*'),   -- F-184
    -- F-184: deleted_at 은 nullable(삭제되지 않은 사용자가 정상) — 있을 때만 형식을 본다.
    CHECK (deleted_at IS NULL OR deleted_at GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]*')
);

-- =============================================================================
--  B. 설정형 데이터 간 관계  (1369-Part1 7.2.2.7 ~ 7.2.2.10)
--     공통 제약: "구성 식별자가 모두 일치하는 2개 이상의 관계 데이터가 존재할 수 없다"
-- =============================================================================

-- B-1. 온실 소유 — 7.2.2.7  (농장 ↔ 온실)
CREATE TABLE greenhouse_own (
    farm_id       TEXT NOT NULL,
    greenhouse_id TEXT NOT NULL,
    PRIMARY KEY (farm_id, greenhouse_id),
    FOREIGN KEY (farm_id)       REFERENCES farm_info(id),
    FOREIGN KEY (greenhouse_id) REFERENCES greenhouse_info(id),
    -- 7.1(1) "특정한 1개의 온실은 1개의 농장에만 포함된다"
    UNIQUE (greenhouse_id)
);

-- B-2. 온실 관리 — 7.2.2.8  (온실 ↔ 사용자)
CREATE TABLE greenhouse_manage (
    greenhouse_id TEXT NOT NULL,
    user_id       TEXT NOT NULL,
    PRIMARY KEY (greenhouse_id, user_id),
    FOREIGN KEY (greenhouse_id) REFERENCES greenhouse_info(id),
    FOREIGN KEY (user_id)       REFERENCES user_info(id),
    -- 7.1(3) N:1 — 1개의 온실은 1명의 사용자가 관리한다
    UNIQUE (greenhouse_id)
);

-- B-3. 장치 설치 — 7.2.2.9  (온실 ↔ 장치설치정보)
CREATE TABLE device_install (
    greenhouse_id TEXT NOT NULL,
    install_id    TEXT NOT NULL,
    PRIMARY KEY (greenhouse_id, install_id),
    FOREIGN KEY (greenhouse_id) REFERENCES greenhouse_info(id),
    FOREIGN KEY (install_id)    REFERENCES device_install_info(id),
    -- 7.1(4) "1개의 장치는 1개의 온실에 설치될 수 있다"
    UNIQUE (install_id)
);

-- B-4. 장치 관리 — 7.2.2.10  (사용자 ↔ 장치설치정보)
CREATE TABLE device_manage (
    user_id    TEXT NOT NULL,
    install_id TEXT NOT NULL,
    PRIMARY KEY (user_id, install_id),
    FOREIGN KEY (user_id)    REFERENCES user_info(id),
    FOREIGN KEY (install_id) REFERENCES device_install_info(id),
    -- 7.1(7) "설치된 장치들은 1명의 사용자에 의해 관리된다"
    UNIQUE (install_id)
);

-- =============================================================================
--  C. 측정형 데이터  (1369-Part1 6.3 / 7.2.3)
-- =============================================================================

-- C-1. 장치상태 데이터 (공통) — 7.2.3.2 / 그림 7-3
CREATE TABLE device_state_data (
    id           TEXT PRIMARY KEY,
    reported_at  TEXT NOT NULL,                        -- 상태보고시간 (불변)
    subtype      TEXT NOT NULL,                        -- 서브타입 판별자
    CHECK (subtype IN ('WINDOW_OPENER','INSULATION_COVER','IRRIGATION_PUMP',
                       'IRRIGATION_VALVE','FAN','COOLING_HEATER')),
    CHECK (reported_at GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]*')  -- F-184
);

-- C-1-a. 창 개폐기 — 6.3.4.2 / 그림 7-3
CREATE TABLE dsd_window_opener (
    id            TEXT PRIMARY KEY,
    open_level    REAL NOT NULL,                       -- 개폐정도
    valid_range   TEXT,                                -- 유효범위
    FOREIGN KEY (id) REFERENCES device_state_data(id) ON DELETE CASCADE
);

-- C-1-b. 보온 덮개 — 6.3.4.3 / 그림 7-3
CREATE TABLE dsd_insulation_cover (
    id            TEXT PRIMARY KEY,
    angle         REAL NOT NULL,                       -- 각도
    valid_range   TEXT,
    FOREIGN KEY (id) REFERENCES device_state_data(id) ON DELETE CASCADE
);

-- C-1-c. 관수펌프 — 6.3.4.5 / 그림 7-3
CREATE TABLE dsd_irrigation_pump (
    id                  TEXT PRIMARY KEY,
    pressure            REAL,                          -- 압력
    pressure_valid_range TEXT,                         -- 압력 유효범위
    spray_level         REAL,                          -- 분사도
    spray_valid_range   TEXT,                          -- 분사도 유효범위
    FOREIGN KEY (id) REFERENCES device_state_data(id) ON DELETE CASCADE
);

-- C-1-d. 관수밸브 — 6.3.4.6 / 그림 7-3
CREATE TABLE dsd_irrigation_valve (
    id            TEXT PRIMARY KEY,
    open_level    REAL NOT NULL,                       -- 개폐정도
    valid_range   TEXT,
    FOREIGN KEY (id) REFERENCES device_state_data(id) ON DELETE CASCADE
);

-- C-1-e. 송풍기 — 6.3.4.4 / 그림 7-3
CREATE TABLE dsd_fan (
    id            TEXT PRIMARY KEY,
    power         INTEGER NOT NULL,                    -- 전원 (0/1)
    wind_level    REAL,                                -- 바람세기
    valid_range   TEXT,
    FOREIGN KEY (id) REFERENCES device_state_data(id) ON DELETE CASCADE,
    CHECK (power IN (0,1))
);

-- C-1-f. 냉난방기 — 6.3.4.7 / 그림 7-3
CREATE TABLE dsd_cooling_heater (
    id            TEXT PRIMARY KEY,
    power         INTEGER NOT NULL,                    -- 전원 (0/1)
    temperature   REAL,                                -- 온도 (설정온도)
    wind_level    REAL,                                -- 바람세기
    FOREIGN KEY (id) REFERENCES device_state_data(id) ON DELETE CASCADE,
    CHECK (power IN (0,1))
);

-- C-2. 환경상태 데이터 (공통) — 7.2.3.3 / 그림 7-3
CREATE TABLE env_state_data (
    id            TEXT PRIMARY KEY,
    measured_at   TEXT NOT NULL,                       -- 측정시간 (불변)
    location      TEXT,                                -- 측정위치
    location_unit TEXT,
    CHECK (measured_at GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]*')  -- F-184
);

-- C-2-a. 환경 측정치 — 6.3.3의 10개 서브타입 통합
--        9종은 (측정값·단위·오차범위·유효범위) 구조 동일, 감우만 측정값(+단위) 단독
CREATE TABLE env_measurement (
    id          TEXT PRIMARY KEY,
    subtype     TEXT NOT NULL,
    value       REAL NOT NULL,                         -- 측정값
    unit        TEXT,                                  -- 측정값 단위
    error_range REAL,                                  -- 오차범위
    lower_limit REAL,                                  -- 유효범위 하한
    upper_limit REAL,                                  -- 유효범위 상한
    FOREIGN KEY (id) REFERENCES env_state_data(id) ON DELETE CASCADE,
    CHECK (subtype IN ('TEMPERATURE','HUMIDITY','INSOLATION','CO2','WIND_DIRECTION',
                       'WIND_SPEED','SOIL_MOISTURE_TENSION','EC','PH','RAIN_DETECTION')),
    -- 감우: 그림 7-3은 '측정값' 단독으로 표기하나, 본문 6.3.3.8은
    --       "주로 사용하는 감우 데이터의 단위가 관리되어야 한다"를 요구한다.
    --       본문을 우선해 단위를 허용하고, 오차범위·유효범위만 금지한다.
    CHECK (subtype <> 'RAIN_DETECTION'
           OR (error_range IS NULL AND lower_limit IS NULL AND upper_limit IS NULL))
);

-- C-3. 작동 환경 — 7.2.3.4  (장치상태 ↔ 환경상태)
CREATE TABLE operating_env (
    device_state_id TEXT NOT NULL,
    env_state_id    TEXT NOT NULL,
    PRIMARY KEY (device_state_id, env_state_id),
    FOREIGN KEY (device_state_id) REFERENCES device_state_data(id),
    FOREIGN KEY (env_state_id)    REFERENCES env_state_data(id),
    -- 7.1(10) 1:N — 1개의 환경상태는 1개의 장치상태에 귀속
    UNIQUE (env_state_id)
);

-- =============================================================================
--  D. 설정형 ↔ 측정형 관계  (1369-Part1 7.2.4)
-- =============================================================================

-- D-1. 장치상태 — 7.2.4.2  (장치설치정보 ↔ 장치상태데이터)
CREATE TABLE device_state (
    id              TEXT PRIMARY KEY,
    install_id      TEXT NOT NULL,
    device_state_id TEXT NOT NULL,
    FOREIGN KEY (install_id)      REFERENCES device_install_info(id),
    FOREIGN KEY (device_state_id) REFERENCES device_state_data(id),
    UNIQUE (install_id, device_state_id),
    -- 7.1(8) "1개의 설치된 장치는 N개의 장치상태를 가진다" (1:N)
    UNIQUE (device_state_id)
);

-- D-2. 환경측정 — 7.2.4.3  (장치설치정보 ↔ 환경상태데이터)
CREATE TABLE env_measure (
    id           TEXT PRIMARY KEY,
    install_id   TEXT NOT NULL,
    env_state_id TEXT NOT NULL,
    FOREIGN KEY (install_id)   REFERENCES device_install_info(id),
    FOREIGN KEY (env_state_id) REFERENCES env_state_data(id),
    UNIQUE (install_id, env_state_id),
    -- 7.1(9) "1개의 장치는 N개의 환경상태 데이터를 측정할 수 있다" (1:N)
    UNIQUE (env_state_id)
);

-- D-3. 온실환경 — 7.2.4.4  (온실정보 ↔ 환경상태데이터)
CREATE TABLE greenhouse_env (
    id            TEXT PRIMARY KEY,
    greenhouse_id TEXT NOT NULL,
    env_state_id  TEXT NOT NULL,
    FOREIGN KEY (greenhouse_id) REFERENCES greenhouse_info(id),
    FOREIGN KEY (env_state_id)  REFERENCES env_state_data(id),
    UNIQUE (greenhouse_id, env_state_id),
    -- 7.1(5) "1개의 온실은 여러 개의 환경상태 데이터로 구성될 수 있다" (1:N)
    UNIQUE (env_state_id)
);

-- =============================================================================
--  E. 설정형 데이터 변경 이력  (1369-Part1 6.2.1)
--     "변경시간, 수정내용, 변경을 수행한 사용자 정보를 포함하는 것이 권고된다"
-- =============================================================================
CREATE TABLE config_change_log (
    id          TEXT PRIMARY KEY,
    changed_at  TEXT NOT NULL,
    table_name  TEXT NOT NULL,
    row_id      TEXT NOT NULL,
    operation   TEXT NOT NULL,
    changes     TEXT,                                  -- 수정내용 (JSON)
    user_id     TEXT,
    version     INTEGER NOT NULL DEFAULT 1,            -- 버전별 데이터 관리
    FOREIGN KEY (user_id) REFERENCES user_info(id),
    CHECK (operation IN ('CREATE','UPDATE','DELETE')),
    CHECK (changed_at GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]*')  -- F-184
);

-- =============================================================================
--  F. 서비스 계층  (TTAK.KO-10.0937)
-- =============================================================================

-- F-1. 공공데이터 메타정보 — 0937 6.2 DMS / 부속서 A 2.3
--      "명칭, 제공기관, 등록일, 갱신일 등 메타 정보를 관리할 수 있어야 한다"
CREATE TABLE public_data_source (
    id            TEXT PRIMARY KEY,
    name          TEXT NOT NULL,                       -- 공공데이터 명칭
    provider      TEXT NOT NULL,                       -- 제공기관
    registered_at TEXT NOT NULL,                       -- 등록일
    updated_at    TEXT,                                -- 갱신일
    source_url    TEXT NOT NULL,
    license       TEXT,
    scope         TEXT,                                -- 사용 범위
    CHECK (registered_at GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]*'),  -- F-184
    CHECK (updated_at IS NULL OR updated_at GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]*')
);

-- F-2. 공공데이터 수집 이력 — 0937 부속서 A 2.3
--      "기간, 지역, 품목 등 검색조건을 지정하여 조회할 수 있다"
CREATE TABLE public_data_record (
    id           TEXT PRIMARY KEY,
    source_id    TEXT NOT NULL,
    fetched_at   TEXT NOT NULL,
    period_from  TEXT,
    period_to    TEXT,
    region       TEXT,
    item         TEXT,
    payload      TEXT NOT NULL,                        -- 원본 응답 (JSON)
    -- F-258: 어느 온실·격자·발표회차의 예보인지, 실데이터인지 폴백인지를
    --        payload 파싱에 의존하지 않고 명시 추적한다(제안 §3). 조회 API 가
    --        이 값들을 노출해 초안이 어떤 위치·회차를 근거로 삼았는지 보인다.
    greenhouse_id TEXT,                                 -- 대상 온실
    base_date    TEXT,                                  -- 실제 요청 발표일자 (YYYYMMDD)
    base_time    TEXT,                                  -- 실제 요청 발표시각 (HHMM)
    nx           INTEGER,                               -- 실제 요청 격자 X
    ny           INTEGER,                               -- 실제 요청 격자 Y
    data_origin  TEXT NOT NULL DEFAULT 'FALLBACK',      -- LIVE·FALLBACK·DEMO_FIXTURE
    -- F-259: 예보 대상일·최고기온(TMX)을 payload 파싱 없이 명시 컬럼으로 둔다.
    --        화면(web)이 기상청 응답 스키마(category='TMX' 등)를 다시 해석하지
    --        않도록 서비스 계층(dms)이 수집 시 뽑아 저장한다 — LIVE 뿐 아니라
    --        DEMO_FIXTURE·FALLBACK 도 payload 에 예보가 있으므로 항상 채운다
    --        (nx/ny/base_* 는 '실제 요청' 이라 폴백에서 NULL 이지만, 이 둘은
    --        '실제로 초안에 쓰인 예보값' 이라 origin 과 무관하게 존재한다).
    forecast_date TEXT,                                 -- 예보 대상일 (YYYYMMDD, TMX 항목)
    forecast_tmax_c REAL,                               -- 예보 최고기온 TMX (°C)
    FOREIGN KEY (source_id) REFERENCES public_data_source(id),
    FOREIGN KEY (greenhouse_id) REFERENCES greenhouse_info(id),
    CHECK (data_origin IN ('LIVE','FALLBACK','DEMO_FIXTURE')),
    CHECK (base_date IS NULL OR base_date GLOB '[0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9]'),
    CHECK (base_time IS NULL OR base_time GLOB '[0-9][0-9][0-9][0-9]'),
    CHECK (forecast_date IS NULL OR forecast_date GLOB '[0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9]'),
    CHECK (fetched_at GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]*'),   -- F-184
    -- F-184: period_from/period_to 는 날짜 단독(YYYY-MM-DD)도 유효한 값이다 —
    --        GLOB 은 접두 검사라 시각이 없어도 그대로 통과한다.
    CHECK (period_from IS NULL OR period_from GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]*'),
    CHECK (period_to   IS NULL OR period_to   GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]*')
);

-- F-3. 제어 모델 메타정보 — 0937 6.3 MMS
--      "모델 명칭, 입력값, 출력값, 모델 실행 방법(통신 프로토콜/데이터 형식/작동 주기),
--       개발자 등 모델의 메타 정보를 등록·수정할 수 있어야 한다"
CREATE TABLE control_model (
    id             TEXT PRIMARY KEY,
    created_at     TEXT NOT NULL,
    name           TEXT NOT NULL,                      -- 모델 명칭
    input_spec     TEXT NOT NULL,                      -- 입력값
    output_spec    TEXT NOT NULL,                      -- 출력값
    exec_method    TEXT NOT NULL,                      -- 모델 실행 방법
    protocol       TEXT,                               --   통신 프로토콜
    data_format    TEXT,                               --   데이터 형식
    period_sec     INTEGER,                            --   작동 주기
    developer      TEXT,                                -- 개발자
    CHECK (created_at GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]*')  -- F-184
);

-- F-4. 제어 규칙 + 승인 게이트 — 0937 6.3 MMS / 부속서 A 3.3
--      "제어 명령을 위자드 선택 방식, 스크립트 입력 방식 등으로 직접 만들어서 등록"
--      AI 초안은 approved_at 이 NULL 인 동안 절대 구동기로 나가지 않는다.
CREATE TABLE control_rule (
    id            TEXT PRIMARY KEY,
    model_id      TEXT,
    created_at    TEXT NOT NULL,
    origin        TEXT NOT NULL,                       -- AI_DRAFT / WIZARD / SCRIPT
    -- F-083: 초안이 실제로 어느 경로로 만들어졌는가. origin 은 요청자의 의도이고
    --        generation 은 서버가 실행한 결과다 — AI 제공자 부재로 threshold 로
    --        폴백했으면 둘이 갈린다. 이 구분이 없으면 'AI 를 썼다'가 증명되지 않는다.
    generation    TEXT,                                -- AI / THRESHOLD_FALLBACK / WIZARD / SCRIPT
    draft_text    TEXT NOT NULL,                       -- AI 초안 (자연어)
    condition_expr TEXT,                               -- 승인된 조건식
    action_json   TEXT,                                -- 승인된 제어 명령
    target_install_id TEXT,                            -- F-049: 승인된 제어 대상 장치
    approved_at   TEXT,                                -- ★ 승인 게이트
    approved_by   TEXT,
    -- F-083: 거부도 영속 상태다. 0937 부속서 A 3.2 절차 3 "사용자는 최종 의사결정 후
    --        제어 조건 조정을 한다" — '조정'에는 반려가 포함된다. 거부 사실이 남지
    --        않으면 초안 생성 직후와 거부 후가 구별되지 않아 '사람 검토 지점'이
    --        기록으로 증명되지 않는다.
    rejected_at   TEXT,
    rejected_by   TEXT,
    reject_reason TEXT,
    -- F-259: 이 초안이 어느 공공데이터 레코드(온실·격자·발표회차·예보값)를
    --        근거로 만들어졌는지 결속한다. 초안 카드가 표와 같은 예보 메타데이터를
    --        보이려면 근거가 필요하다(제안 §3). AI_DRAFT 로 DMS 예보를 쓴 경우에만
    --        채워지고 WIZARD·SCRIPT 는 NULL 이다 — 승인 게이트(action_json·
    --        approved_at 계열 CHECK)와 무관한 순수 출처 추적 컬럼이다.
    public_data_record_id TEXT,                          -- 초안 근거 예보 레코드 (F-259)
    FOREIGN KEY (model_id)    REFERENCES control_model(id),
    FOREIGN KEY (approved_by) REFERENCES user_info(id),
    FOREIGN KEY (rejected_by) REFERENCES user_info(id),
    FOREIGN KEY (target_install_id) REFERENCES device_install_info(id),
    FOREIGN KEY (public_data_record_id) REFERENCES public_data_record(id),
    CHECK (origin IN ('AI_DRAFT','WIZARD','SCRIPT')),
    CHECK (generation IS NULL OR generation IN ('AI','THRESHOLD_FALLBACK','WIZARD','SCRIPT')),
    -- F-083: AI 초안 요청은 서버가 모델을 돌린 결과를 남겨야 한다.
    --        IS NOT NULL 을 먼저 둔다 — SQL 3치 논리에서 `NULL IN (...)` 은 FALSE 가
    --        아니라 NULL 이고, SQLite 는 NULL 로 평가된 CHECK 를 통과로 취급한다.
    --        F-039 와 같은 부류의 함정이다.
    CHECK (origin <> 'AI_DRAFT'
           OR (generation IS NOT NULL
               AND generation IN ('AI','THRESHOLD_FALLBACK'))),
    -- F-091: 반대 방향도 막는다. 위 CHECK 는 'AI 초안에 경로가 있는가'만 보므로
    --        origin='WIZARD' 인데 generation='AI' 인 행이 통과했다 — 사람이 만든
    --        규칙을 AI 산출물로 위조할 수 있다는 뜻이다. AI 가 아닌 경로는
    --        생성 경로가 없거나(NULL) origin 과 같아야 한다.
    CHECK (origin = 'AI_DRAFT'
           OR generation IS NULL
           OR generation = origin),
    -- 승인 시각과 승인자는 동시에 존재해야 한다
    CHECK ((approved_at IS NULL) = (approved_by IS NULL)),
    -- 승인되지 않은 규칙은 실행 가능한 명령도, 확정된 대상도 가질 수 없다 (F-049)
    CHECK (approved_at IS NOT NULL
           OR (action_json IS NULL AND target_install_id IS NULL)),
    -- F-039 / F-049: 승인된 규칙은 (조건식, 명령, 대상)이 모두 채워진 완결된 스냅샷이어야 한다.
    --        0937 부속서 A 3.2 절차 3 — 사람이 승인하는 것은 '규칙의 존재'가 아니라
    --        '이 조건에서 이 장치에 이 명령을 낸다'는 내용 전체다.
    --        NULL action 을 승인 상태로 남기면 trg_exec_command_matches_approved 의
    --        비교가 SQL NULL 이 되어 임의 명령이 통과한다(F-039).
    --        대상을 컬럼으로 승격하지 않으면 같은 명령으로 다른 장치를 켤 수 있다(F-049).
    CHECK (approved_at IS NULL
           OR (action_json IS NOT NULL AND condition_expr IS NOT NULL
               AND target_install_id IS NOT NULL)),
    -- F-083: 거부 시각과 거부자는 동시에 존재해야 한다 (승인과 같은 규칙)
    CHECK ((rejected_at IS NULL) = (rejected_by IS NULL)),
    -- F-091: 사유 없는 거부는 '사람이 검토했다'의 증거가 되지 못한다.
    --        0937 부속서 A 3.2 절차 3 '최종 의사결정 후 제어 조건 조정' — 조정의
    --        근거가 남지 않으면 승인 게이트가 형식만 남는다. 공백 문자열도 막는다.
    CHECK ((rejected_at IS NULL) = (reject_reason IS NULL)),
    CHECK (reject_reason IS NULL OR length(trim(reject_reason)) > 0),
    -- F-083: 승인과 거부는 배타다. 이 CHECK 가 유일하게 그것을 막는다 -
    --   승인 스냅샷이 완결된 규칙에 거부 표시만 얹으면 다른 제약은 전부 통과한다.
    --   결함 주입으로 확인했다.
    CHECK (approved_at IS NULL OR rejected_at IS NULL),
    -- ※ '거부된 규칙은 명령·대상을 가질 수 없다' 는 별도 CHECK 로 두지 않는다.
    --   거부는 곧 미승인이고, 위의 미승인 제약이 이미 action_json·target 을 막는다.
    --   결함 주입에서 독립 반례가 나오지 않아 제거했다.
    -- F-184: created_at 은 항상 있고(NOT NULL), approved_at/rejected_at 은
    --        nullable(미승인·미거부가 정상) — 있을 때만 형식을 본다.
    CHECK (created_at GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]*'),
    CHECK (approved_at IS NULL OR approved_at GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]*'),
    CHECK (rejected_at IS NULL OR rejected_at GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]*'),
    CHECK (1)
);
-- 승인은 (condition_expr, action_json, target_install_id, approved_at, approved_by)를
-- 한 번에 채우는 단일 UPDATE 로만 가능하다. 승인 후에는 다섯 필드 모두 불변이다(아래 트리거).

-- F-5. 제어 실행 이력 — 0937 6.5 FCS / 부속서 A 3.3
--      "제어 명령, 구동 시간 등 제어 이력 정보를 조회할 수 있어야 한다"
--      ★ 모든 제어 실행은 사람의 권한에 근거해야 한다.
--        origin='RULE'   → 승인된 control_rule 참조 (자동제어, 부속서 A 3)
--        origin='MANUAL' → 사용자가 직접 지시 (수동·원격제어, 부속서 A 1·2)
--        승인 여부는 trg_exec_requires_approval 트리거가 강제한다.
CREATE TABLE control_execution (
    id            TEXT PRIMARY KEY,
    origin        TEXT NOT NULL,                       -- RULE / MANUAL
    rule_id       TEXT,
    issued_by     TEXT,                                -- MANUAL 일 때 지시한 사용자
    install_id    TEXT NOT NULL,
    issued_at     TEXT NOT NULL,
    command_json  TEXT NOT NULL,
    siap_msg_id   INTEGER,                             -- 0943 Message Identifier
    result_rsc    INTEGER,                             -- 0943 RSC
    responded_at  TEXT,
    FOREIGN KEY (rule_id)    REFERENCES control_rule(id),
    FOREIGN KEY (issued_by)  REFERENCES user_info(id),
    FOREIGN KEY (install_id) REFERENCES device_install_info(id),
    CHECK (origin IN ('RULE','MANUAL')),
    -- 권한 출처가 반드시 하나 존재한다
    CHECK ((origin = 'RULE'   AND rule_id   IS NOT NULL AND issued_by IS NULL)
        OR (origin = 'MANUAL' AND issued_by IS NOT NULL AND rule_id   IS NULL)),
    CHECK (siap_msg_id IS NULL OR (siap_msg_id BETWEEN 0 AND 65535)),
    CHECK (result_rsc  IS NULL OR (result_rsc  BETWEEN 0 AND 255)),
    CHECK (issued_at GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]*'),   -- F-184
    CHECK (responded_at IS NULL OR responded_at GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]*')
);

-- F-6. 알림 — 0937 6.4 FMS / 6.5 FCS
--      "정해진 시간에 데이터가 수집되지 않는 경우 알림"
--      "하드웨어 고장, 네트워크 단절 등 긴급 상황시 사용자 알림"
CREATE TABLE alert (
    id          TEXT PRIMARY KEY,
    raised_at   TEXT NOT NULL,
    kind        TEXT NOT NULL,                         -- NO_DATA / NODE_ERROR / DISCONNECT / THRESHOLD / CONTROL_TIMEOUT
    severity    TEXT NOT NULL,
    install_id  TEXT,
    siap_nec    INTEGER,                               -- 0943 NEC (해당 시)
    message     TEXT NOT NULL,
    ack_at      TEXT,
    -- F-085: 알림을 유발한 프레임. NEC 알림(0943 8.2.1.1)을 화면에서 원본 프레임과
    --        결속하려면 필요하다. 임계값·타임아웃처럼 프레임이 원인이 아니면 NULL
    frame_id    TEXT,
    FOREIGN KEY (install_id) REFERENCES device_install_info(id),
    FOREIGN KEY (frame_id)   REFERENCES frame_log(id),
    CHECK (kind IN ('NO_DATA','NODE_ERROR','DISCONNECT','THRESHOLD','CONTROL_TIMEOUT')),
    CHECK (severity IN ('INFO','WARN','CRITICAL')),
    CHECK (siap_nec IS NULL OR (siap_nec BETWEEN 0 AND 255)),
    -- F-092: NEC 알림은 반드시 프레임에서 유래한다(0943 8.2.1.1 NOTI_ERROR).
    --        frame_id 를 비워 두면 기능 2 의 알림 카드에서 원본 프레임을 열 수 없고
    --        X08 시연의 알림<->프레임 결속을 증명할 수단이 사라진다.
    CHECK (siap_nec IS NULL OR frame_id IS NOT NULL),
    CHECK (raised_at GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]*'),   -- F-184
    CHECK (ack_at IS NULL OR ack_at GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]*')
);

-- =============================================================================
--  G. 프레임 로그 및 표준 준수 검증  (기능 2 / TTAK.KO-10.0943 7장)
-- =============================================================================

-- G-1. 수신·송신 프레임 로그
CREATE TABLE frame_log (
    id           TEXT PRIMARY KEY,
    t            REAL NOT NULL,                        -- 수신 시각 (epoch)
    direction    TEXT NOT NULL,                        -- rx / tx
    raw_hex      TEXT NOT NULL,                        -- 원본 바이트
    version      INTEGER,
    msg_type     INTEGER,
    trans_type   INTEGER,
    msg_id       INTEGER,
    payload_len  INTEGER,
    gcg_id       INTEGER,
    node_id      INTEGER,
    is_valid     INTEGER NOT NULL DEFAULT 1,
    -- F-187: 이미 디코딩된 가변 요소(DEVICE_MAIN_INFO/DEVICE_PROPERTY)를
    --        조회 시점 렌더링용으로 그대로 보관한다. siap/codec.py 가 만든
    --        구조화 값을 옮겨 적을 뿐 여기서 다시 해석(비트 재파싱)하지
    --        않는다 — 표준 해석은 여전히 프로토콜 계층 하나뿐이다(§3.4).
    elements_json TEXT,
    CHECK (direction IN ('rx','tx')),
    CHECK (is_valid IN (0,1))
);

-- G-2. 표준 위반 내역 — 화면에 조항 번호를 그대로 표시
CREATE TABLE frame_violation (
    id         TEXT PRIMARY KEY,
    frame_id   TEXT NOT NULL,
    code       INTEGER NOT NULL,                       -- RSC 또는 NEC 값
    code_name  TEXT NOT NULL,                          -- 'INVALID_FORMAT'
    clause     TEXT NOT NULL,                          -- '7.3.1'  ← 화면 표시
    detail     TEXT,
    FOREIGN KEY (frame_id) REFERENCES frame_log(id) ON DELETE CASCADE
);

-- =============================================================================
--  H. 식별자 불변 제약  (1369-Part1 7.2.2.x / 7.2.3.x)
--     "식별자는 데이터의 생명주기 동안 수정될 수 없다"
--     SQLite에는 컬럼 단위 불변 제약이 없으므로 트리거로 강제한다.
-- =============================================================================

CREATE TRIGGER trg_farm_info_pk_immutable
BEFORE UPDATE OF id ON farm_info
WHEN OLD.id <> NEW.id
BEGIN SELECT RAISE(ABORT, '1369-P1 7.2.2.2: farm_info.id is immutable'); END;

CREATE TRIGGER trg_greenhouse_info_pk_immutable
BEFORE UPDATE OF id ON greenhouse_info
WHEN OLD.id <> NEW.id
BEGIN SELECT RAISE(ABORT, '1369-P1 7.2.2.3: greenhouse_info.id is immutable'); END;

CREATE TRIGGER trg_device_info_pk_immutable
BEFORE UPDATE OF id ON device_info
WHEN OLD.id <> NEW.id
BEGIN SELECT RAISE(ABORT, '1369-P1 7.2.2.4: device_info.id is immutable'); END;

CREATE TRIGGER trg_device_install_pk_immutable
BEFORE UPDATE OF id ON device_install_info
WHEN OLD.id <> NEW.id
BEGIN SELECT RAISE(ABORT, '1369-P1 7.2.2.5: device_install_info.id is immutable'); END;

CREATE TRIGGER trg_user_info_pk_immutable
BEFORE UPDATE OF id ON user_info
WHEN OLD.id <> NEW.id
BEGIN SELECT RAISE(ABORT, '1369-P1 7.2.2.6: user_info.id is immutable'); END;

CREATE TRIGGER trg_dsd_pk_immutable
BEFORE UPDATE OF id ON device_state_data
WHEN OLD.id <> NEW.id
BEGIN SELECT RAISE(ABORT, '1369-P1 7.2.3.2: device_state_data.id is immutable'); END;

CREATE TRIGGER trg_esd_pk_immutable
BEFORE UPDATE OF id ON env_state_data
WHEN OLD.id <> NEW.id
BEGIN SELECT RAISE(ABORT, '1369-P1 7.2.3.3: env_state_data.id is immutable'); END;

-- 생성시간 불변 — 7.2.2.2 "생성시간은 ... 생명주기 동안 수정될 수 없다"
CREATE TRIGGER trg_farm_created_immutable
BEFORE UPDATE OF created_at ON farm_info
WHEN OLD.created_at <> NEW.created_at
BEGIN SELECT RAISE(ABORT, '1369-P1 7.2.2.2: farm_info.created_at is immutable'); END;

CREATE TRIGGER trg_gh_created_immutable
BEFORE UPDATE OF created_at ON greenhouse_info
WHEN OLD.created_at <> NEW.created_at
BEGIN SELECT RAISE(ABORT, '1369-P1 7.2.2.3: greenhouse_info.created_at is immutable'); END;

-- 상태보고시간 / 측정시간 불변 — 7.2.3.2 / 7.2.3.3
CREATE TRIGGER trg_dsd_time_immutable
BEFORE UPDATE OF reported_at ON device_state_data
WHEN OLD.reported_at <> NEW.reported_at
BEGIN SELECT RAISE(ABORT, '1369-P1 7.2.3.2: reported_at is immutable'); END;

CREATE TRIGGER trg_esd_time_immutable
BEFORE UPDATE OF measured_at ON env_state_data
WHEN OLD.measured_at <> NEW.measured_at
BEGIN SELECT RAISE(ABORT, '1369-P1 7.2.3.3: measured_at is immutable'); END;

-- 모델명 불변 — 7.2.2.4 "모델명은 데이터의 생명주기 동안 수정될 수 없다"
CREATE TRIGGER trg_device_model_immutable
BEFORE UPDATE OF model_name ON device_info
WHEN OLD.model_name <> NEW.model_name
BEGIN SELECT RAISE(ABORT, '1369-P1 7.2.2.4: model_name is immutable'); END;

-- 관계 엔티티 FK 불변 — 7.2.2.7~10, 7.2.4.2~4
CREATE TRIGGER trg_device_state_fk_immutable
BEFORE UPDATE OF install_id, device_state_id ON device_state
BEGIN SELECT RAISE(ABORT, '1369-P1 7.2.4.2: relation FKs are immutable'); END;

CREATE TRIGGER trg_env_measure_fk_immutable
BEFORE UPDATE OF install_id, env_state_id ON env_measure
BEGIN SELECT RAISE(ABORT, '1369-P1 7.2.4.3: relation FKs are immutable'); END;

CREATE TRIGGER trg_greenhouse_env_fk_immutable
BEFORE UPDATE OF greenhouse_id, env_state_id ON greenhouse_env
BEGIN SELECT RAISE(ABORT, '1369-P1 7.2.4.4: relation FKs are immutable'); END;

-- ── F-016 보강: 생성시간 불변 (7.2.2.4 ~ 7.2.2.6) ──────────────────────────
CREATE TRIGGER trg_device_created_immutable
BEFORE UPDATE OF created_at ON device_info
WHEN OLD.created_at <> NEW.created_at
BEGIN SELECT RAISE(ABORT, '1369-P1 7.2.2.4: created_at is immutable'); END;

CREATE TRIGGER trg_install_created_immutable
BEFORE UPDATE OF created_at ON device_install_info
WHEN OLD.created_at <> NEW.created_at
BEGIN SELECT RAISE(ABORT, '1369-P1 7.2.2.5: created_at is immutable'); END;

CREATE TRIGGER trg_user_created_immutable
BEFORE UPDATE OF created_at ON user_info
WHEN OLD.created_at <> NEW.created_at
BEGIN SELECT RAISE(ABORT, '1369-P1 7.2.2.6: created_at is immutable'); END;

-- ── F-016 보강: 설정형 관계 FK 불변 (7.2.2.7 ~ 7.2.2.10) ────────────────────
CREATE TRIGGER trg_gh_own_fk_immutable
BEFORE UPDATE OF farm_id, greenhouse_id ON greenhouse_own
BEGIN SELECT RAISE(ABORT, '1369-P1 7.2.2.7: relation FKs are immutable'); END;

CREATE TRIGGER trg_gh_manage_fk_immutable
BEFORE UPDATE OF greenhouse_id, user_id ON greenhouse_manage
BEGIN SELECT RAISE(ABORT, '1369-P1 7.2.2.8: relation FKs are immutable'); END;

CREATE TRIGGER trg_dev_install_fk_immutable
BEFORE UPDATE OF greenhouse_id, install_id ON device_install
BEGIN SELECT RAISE(ABORT, '1369-P1 7.2.2.9: relation FKs are immutable'); END;

CREATE TRIGGER trg_dev_manage_fk_immutable
BEFORE UPDATE OF user_id, install_id ON device_manage
BEGIN SELECT RAISE(ABORT, '1369-P1 7.2.2.10: relation FKs are immutable'); END;

-- ── F-016 보강: 작동환경 FK 불변 (7.2.3.4) ─────────────────────────────────
CREATE TRIGGER trg_operating_env_fk_immutable
BEFORE UPDATE OF device_state_id, env_state_id ON operating_env
BEGIN SELECT RAISE(ABORT, '1369-P1 7.2.3.4: relation FKs are immutable'); END;

-- ── F-016 보강: 관계 엔티티 식별자 불변 (7.2.4.2 ~ 7.2.4.4) ────────────────
CREATE TRIGGER trg_device_state_pk_immutable
BEFORE UPDATE OF id ON device_state
WHEN OLD.id <> NEW.id
BEGIN SELECT RAISE(ABORT, '1369-P1 7.2.4.2: relation id is immutable'); END;

CREATE TRIGGER trg_env_measure_pk_immutable
BEFORE UPDATE OF id ON env_measure
WHEN OLD.id <> NEW.id
BEGIN SELECT RAISE(ABORT, '1369-P1 7.2.4.3: relation id is immutable'); END;

CREATE TRIGGER trg_greenhouse_env_pk_immutable
BEFORE UPDATE OF id ON greenhouse_env
WHEN OLD.id <> NEW.id
BEGIN SELECT RAISE(ABORT, '1369-P1 7.2.4.4: relation id is immutable'); END;

-- ── F-017: 제어 실행은 승인된 규칙에만 근거한다 ────────────────────────────
--    0937 부속서 A 3.2 절차 3 "사용자는 최종 의사결정 후 제어 조건 조정을 한다"
CREATE TRIGGER trg_exec_requires_approval
BEFORE INSERT ON control_execution
WHEN NEW.origin = 'RULE'
 AND (SELECT approved_at FROM control_rule WHERE id = NEW.rule_id) IS NULL
BEGIN SELECT RAISE(ABORT, '0937 A.3.2: control_execution requires an approved rule'); END;

-- F-030: 실행 명령은 승인된 action_json 과 일치해야 한다
--        사람이 승인한 것은 '규칙의 존재'가 아니라 '그 명령'이다.
-- F-039: `<>` 는 한쪽이 NULL 이면 결과가 SQL NULL 이라 WHEN 이 참이 되지 않는다.
--        NULL 안전 비교 `IS NOT` 을 쓴다. rule_id 가 없으면 서브쿼리가 NULL 이므로
--        command_json(NOT NULL) 과 항상 불일치 → 차단된다.
CREATE TRIGGER trg_exec_command_matches_approved
BEFORE INSERT ON control_execution
WHEN NEW.origin = 'RULE'
 AND NEW.command_json IS NOT (SELECT action_json FROM control_rule WHERE id = NEW.rule_id)
BEGIN SELECT RAISE(ABORT, '0937 A.3.2: command_json must equal the approved action_json'); END;

-- F-030: 승인 후 명령 변조 금지
CREATE TRIGGER trg_rule_action_immutable_after_approval
BEFORE UPDATE OF action_json ON control_rule
WHEN OLD.approved_at IS NOT NULL
BEGIN SELECT RAISE(ABORT, '0937 6.3: approved action_json is immutable'); END;

-- F-039: 승인 후 조건식 변조 금지
--        조건만 넓히면 승인한 명령이 승인하지 않은 상황에서 실행된다.
--        승인 대상은 (조건, 명령, 대상) 전체이므로 조건도 같은 강도로 봉인한다.
CREATE TRIGGER trg_rule_condition_immutable_after_approval
BEFORE UPDATE OF condition_expr ON control_rule
WHEN OLD.approved_at IS NOT NULL
BEGIN SELECT RAISE(ABORT, '0937 A.3.2: approved condition_expr is immutable'); END;

-- F-049: 제어의 '어느 장치를' 을 DB가 강제한다.
--        0937 6.5 "사용자가 지정한 명령을 구동기가 실행하도록 제어 명령을 전달"
--        command_json 만 대조하면 같은 명령으로 다른 구동기를 켤 수 있다.
CREATE TRIGGER trg_exec_target_matches_approved
BEFORE INSERT ON control_execution
WHEN NEW.origin = 'RULE'
 AND NEW.install_id IS NOT (SELECT target_install_id FROM control_rule WHERE id = NEW.rule_id)
BEGIN SELECT RAISE(ABORT, '0937 6.5: install_id must equal the approved target_install_id'); END;

-- F-049: 승인 후 대상 장치 변조 금지
CREATE TRIGGER trg_rule_target_immutable_after_approval
BEFORE UPDATE OF target_install_id ON control_rule
WHEN OLD.approved_at IS NOT NULL
BEGIN SELECT RAISE(ABORT, '0937 A.3.2: approved target_install_id is immutable'); END;

-- F-049: install_id 를 권한 불변 필드에 포함한다. 삽입 후 대상만 바꿔치기할 수 없다.
CREATE TRIGGER trg_exec_rule_immutable
BEFORE UPDATE OF origin, rule_id, issued_by, command_json, install_id ON control_execution
BEGIN SELECT RAISE(ABORT, 'control_execution authority fields are immutable'); END;

-- 승인 철회 방지 — 승인된 규칙은 미승인으로 되돌릴 수 없다
CREATE TRIGGER trg_rule_approval_irrevocable
BEFORE UPDATE OF approved_at ON control_rule
WHEN OLD.approved_at IS NOT NULL AND NEW.approved_at IS NULL
BEGIN SELECT RAISE(ABORT, '0937 6.3: approval cannot be revoked; create a new rule'); END;

-- F-048: 승인 출처(누가·언제)는 승인 후 위조할 수 없다.
--        철회 금지만으로는 부족하다 — 다른 사용자로 바꾸거나 시각을 앞당길 수 있었다.
--        이 둘이 감사 기록이자 "사람이 최종 결정했다"는 증거 자체다.
CREATE TRIGGER trg_rule_approver_immutable
BEFORE UPDATE OF approved_by ON control_rule
WHEN OLD.approved_by IS NOT NULL AND NEW.approved_by IS NOT OLD.approved_by
BEGIN SELECT RAISE(ABORT, '0937 A.3.2: approved_by is immutable once approved'); END;

CREATE TRIGGER trg_rule_approved_at_immutable
BEFORE UPDATE OF approved_at ON control_rule
WHEN OLD.approved_at IS NOT NULL AND NEW.approved_at IS NOT OLD.approved_at
BEGIN SELECT RAISE(ABORT, '0937 A.3.2: approved_at is immutable once approved'); END;

-- F-083: 거부 사실은 불변이다. 거부한 뒤 뒤집을 수 있으면 '사람 검토 지점'이
--        기록이 아니라 상태가 된다. 되살리려면 새 규칙을 만든다.
--
--   ※ '거부 -> 승인' · '승인 -> 거부' 전이를 막는 별도 트리거는 두지 않는다.
--     내용 제약 두 개(승인은 action·cond·target 필수 / 거부는 action·target 금지)와
--     approved_at·rejected_at 불변 트리거가 이미 모든 UPDATE 경로를 덮으며,
--     결함 주입으로 확인했다. 독립 반례가 없는 트리거를 남기면 'DDL 객체 N종'이라는
--     근거 수치만 부풀고 무엇이 실제로 지탱하는지가 흐려진다.
-- F-091: reject_reason 을 감시 목록에 넣는다. 빠져 있으면 거부 사유만 사후에
--        바꿔치기할 수 있어 '거부는 불변'이라는 주장이 성립하지 않는다.
CREATE TRIGGER trg_rule_reject_immutable
BEFORE UPDATE OF rejected_at, rejected_by, reject_reason ON control_rule
WHEN OLD.rejected_at IS NOT NULL
BEGIN SELECT RAISE(ABORT, '0937 A.3.2: rejection is immutable; create a new rule'); END;

-- =============================================================================
--  I. 인덱스
-- =============================================================================
CREATE INDEX idx_esd_measured   ON env_state_data(measured_at);
CREATE INDEX idx_dsd_reported   ON device_state_data(reported_at);
CREATE INDEX idx_em_subtype     ON env_measurement(subtype);
CREATE INDEX idx_frame_t        ON frame_log(t);
CREATE INDEX idx_frame_valid    ON frame_log(is_valid);
CREATE INDEX idx_install_siap   ON device_install_info(siap_node_id, siap_device_id);
CREATE INDEX idx_exec_issued    ON control_execution(issued_at);
CREATE INDEX idx_alert_raised   ON alert(raised_at);
