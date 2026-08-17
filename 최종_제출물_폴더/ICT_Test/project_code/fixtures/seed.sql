-- =============================================================================
--  데모 시드 데이터 — 농장 1 / 온실 1 / 사용자 1 (고정값). 기동 시 1회 적재된다.
--
--  이 파일이 쓰는 테이블(farm_info·greenhouse_info·user_info·greenhouse_own·
--  greenhouse_manage·control_model·public_data_source)은 이후 어느 스레드도
--  쓰지 않는다. `device_manage`·`config_change_log`는 시드에 두지 않는다 —
--  install_id/device_info_id가 가리킬 행이 시드 시점에는 아직 없고(장치는
--  런타임에 등록된다), 대신 `backend/ingest.py`가 장치 등록 시점에 채운다
--  (관리자는 그 장치가 설치된 온실의 관리자를 그대로 쓴다).
--
--  식별자는 UUID 대신 사람이 읽을 수 있는 고정 문자열을 쓴다(재현성 — 심사자가
--  매 실행 같은 id로 조회·재현할 수 있어야 한다). ITU-T X.667 형식 강제는
--  런타임 발번(UUID4)의 책임이다(1369-P1 6.1).
-- =============================================================================

INSERT INTO user_info (id, created_at, updated_at, deleted_at, name, group_id, group_role)
VALUES ('demo-user-1', '2026-08-01T09:00:00+09:00', '2026-08-01T09:00:00+09:00', NULL,
        '관리자', 'demo-group', 'ADMIN');

INSERT INTO farm_info (id, created_at, updated_at, name, owner_id,
                        location, location_type, location_unit,
                        area_value, area_error, area_unit)
VALUES ('demo-farm-1', '2026-08-01T09:00:00+09:00', '2026-08-01T09:00:00+09:00',
        '데모 농장', 'demo-user-1',
        '37.4,127.1', 'GPS', 'deg', 1000, 1, 'm2');

INSERT INTO greenhouse_info (id, created_at, updated_at, name,
                              location, location_type, location_unit,
                              width_value, width_error, width_unit,
                              height_value, height_error, height_unit,
                              length_value, length_error, length_unit,
                              gh_type, medium_type, irrigation_type, heating_type,
                              crop, crop_season, usage_state)
VALUES ('demo-gh-1', '2026-08-01T09:00:00+09:00', '2026-08-01T09:00:00+09:00',
        '1호 온실',
        '37.4,127.1', 'GPS', 'deg',
        6, 0.1, 'm',
        3, 0.1, 'm',
        30, 0.1, 'm',
        '단동', '토경', '점적', '온풍',
        '토마토', '2026춘작', '사용중');

-- 7.1(1) 온실은 정확히 1개 농장에 속한다 — greenhouse_own UNIQUE(greenhouse_id)
INSERT INTO greenhouse_own (farm_id, greenhouse_id)
VALUES ('demo-farm-1', 'demo-gh-1');

-- 7.1(3) 온실은 정확히 1명의 사용자가 관리한다 — greenhouse_manage UNIQUE(greenhouse_id)
INSERT INTO greenhouse_manage (greenhouse_id, user_id)
VALUES ('demo-gh-1', 'demo-user-1');

-- 시드 반영 기록 — 1369-P1 6.2.1 "변경시간, 수정내용, 변경을 수행한 사용자 정보"
INSERT INTO config_change_log (id, changed_at, table_name, row_id, operation, changes, user_id, version)
VALUES ('demo-log-1', '2026-08-01T09:00:00+09:00', 'farm_info', 'demo-farm-1', 'CREATE',
        '{"seed":"fixtures/seed.sql"}', 'demo-user-1', 1);
INSERT INTO config_change_log (id, changed_at, table_name, row_id, operation, changes, user_id, version)
VALUES ('demo-log-2', '2026-08-01T09:00:00+09:00', 'greenhouse_info', 'demo-gh-1', 'CREATE',
        '{"seed":"fixtures/seed.sql"}', 'demo-user-1', 1);

-- =============================================================================
--  public_data_source · control_model (시드 전용, 조회 전용 참조).
--  0937 6.2-3/6.3-1 — 이 참조 구현은 등록을 시드로 하고 런타임 등록 API는 두지
--  않는다. backend/services/dms.py·mms.py가 이 두 시드를 조회한다.
-- =============================================================================

-- F-1. 공공데이터 출처 — 0937 6.2 DMS "명칭·제공기관·등록일·갱신일 등 메타정보"
--      기상청 단기예보 조회서비스(VilageFcstInfoService_2.0). API 키
--      (환경변수 KMA_API_KEY) 부재 시 dms.py 가 fixtures/kma_forecast_mock.json
--      으로 자동 폴백한다.
INSERT INTO public_data_source (id, name, provider, registered_at, updated_at, source_url, license, scope)
VALUES ('demo-pds-kma', '단기예보 조회서비스', '기상청',
        '2026-08-01T09:00:00+09:00', NULL,
        'https://apihub.kma.go.kr/api/typ02/openApi/VilageFcstInfoService_2.0',
        '공공누리 제1유형', '단기예보(기온·강수확률·습도)');

-- F-3. 제어 모델 메타정보 — 0937 6.3 MMS "모델 명칭·입력값·출력값·실행방법·개발자".
--      threshold: 내장 규칙(외부 호출 없음, 오프라인 기본 경로).
--      llm_draft: 생성형 AI 초안 — 제공자 부재 시 mms.run_model() 이 threshold 로
--      자동 폴백한다(THRESHOLD_FALLBACK).
--      output_spec.recommend_action 이 권장 조치 문구의 정본이고(0937 6.3-2 "출력값"),
--      input_spec.crop_tmax_c 가 임계값의 정본이다(6.3-3 "입력값") — 작물·장치가
--      다른 모델을 추가할 때 이 두 값만 바뀌고 backend/ 코드는 바뀌지 않는다.
INSERT INTO control_model (id, created_at, name, input_spec, output_spec, exec_method,
                            protocol, data_format, period_sec, developer)
VALUES ('demo-model-threshold-tmax', '2026-08-01T09:00:00+09:00',
        '고온 예보 관수 임계값 모델',
        '{"forecast_tmax_c":"number","crop_tmax_c":"number"}',
        '{"condition_expr":"string","action":"ControlAction","recommend_action":"관수 장치 가동"}',
        'threshold', NULL, 'json', NULL, '참조 구현팀');
INSERT INTO control_model (id, created_at, name, input_spec, output_spec, exec_method,
                            protocol, data_format, period_sec, developer)
VALUES ('demo-model-llm-irrigation', '2026-08-01T09:00:00+09:00',
        '생성형 AI 관수 규칙 초안 모델',
        '{"forecast_tmax_c":"number","crop_tmax_c":"number","greenhouse_id":"string"}',
        '{"condition_expr":"string","action":"ControlAction","recommend_action":"관수 장치 가동"}',
        'llm_draft', 'https', 'json', NULL, '참조 구현팀');

INSERT INTO config_change_log (id, changed_at, table_name, row_id, operation, changes, user_id, version)
VALUES ('demo-log-3', '2026-08-01T09:00:00+09:00', 'public_data_source', 'demo-pds-kma', 'CREATE',
        '{"seed":"fixtures/seed.sql"}', NULL, 1);
INSERT INTO config_change_log (id, changed_at, table_name, row_id, operation, changes, user_id, version)
VALUES ('demo-log-4', '2026-08-01T09:00:00+09:00', 'control_model', 'demo-model-threshold-tmax', 'CREATE',
        '{"seed":"fixtures/seed.sql"}', NULL, 1);
INSERT INTO config_change_log (id, changed_at, table_name, row_id, operation, changes, user_id, version)
VALUES ('demo-log-5', '2026-08-01T09:00:00+09:00', 'control_model', 'demo-model-llm-irrigation', 'CREATE',
        '{"seed":"fixtures/seed.sql"}', NULL, 1);
