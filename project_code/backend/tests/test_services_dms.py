"""backend/tests/test_services_dms.py — F-258 회귀. DMS 기상청 예보 수집.

네트워크 없이 검증한다 — 실 API 호출부(`_fetch_kma_live`)는 monkeypatch 로
대체하고 발표회차 선택·URL 구성·응답 검증·온실별 격자 결속·출처 판정을
직접 확인한다(제안 §8).
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest

from backend import db, repository
from backend.services import dms
from backend.services.kma_grid import latlon_to_kma_grid

_KST = timezone(timedelta(hours=9))


@pytest.fixture()
def conn(tmp_path):
    con = db.init_db(tmp_path / "dms.db", seed=True)
    yield con
    con.close()


def _mock_payload(nx: int, ny: int, *, tmax: str = "34", result: str = "00", items=True) -> dict:
    body_items = []
    if items:
        body_items = [
            {"baseDate": "20260821", "baseTime": "0500", "category": "TMX",
             "fcstDate": "20260822", "fcstTime": "1500", "fcstValue": tmax, "nx": nx, "ny": ny},
            {"baseDate": "20260821", "baseTime": "0500", "category": "REH",
             "fcstDate": "20260822", "fcstTime": "1500", "fcstValue": "55", "nx": nx, "ny": ny},
        ]
    return {"response": {"header": {"resultCode": result, "resultMsg": "x"},
                         "body": {"items": {"item": body_items}}}}


# --- §8-4 발표회차 선택 -------------------------------------------------------
@pytest.mark.parametrize("dt,expect", [
    (datetime(2026, 8, 21, 2, 5, tzinfo=_KST), ("20260820", "2300")),    # 첫 회차 제공 전
    (datetime(2026, 8, 21, 2, 15, tzinfo=_KST), ("20260821", "0200")),   # 0200 제공 직후
    (datetime(2026, 8, 21, 0, 3, tzinfo=_KST), ("20260820", "2300")),    # 자정 직후
    (datetime(2026, 3, 1, 1, 0, tzinfo=_KST), ("20260228", "2300")),     # 월 경계
    (datetime(2026, 1, 1, 0, 5, tzinfo=_KST), ("20251231", "2300")),     # 연 경계
    (datetime(2026, 8, 21, 14, 11, tzinfo=_KST), ("20260821", "1400")),  # 제공 직후
    (datetime(2026, 8, 21, 14, 9, tzinfo=_KST), ("20260821", "1100")),   # 제공 직전
])
def test_select_vilage_base_datetime_f258(dt, expect):
    assert dms.select_vilage_base_datetime(dt) == expect


def test_base_datetime_requires_tz_f258():
    with pytest.raises(ValueError):
        dms.select_vilage_base_datetime(datetime(2026, 8, 21, 5, 0))


def test_utc_input_converted_to_kst_f258():
    # UTC 2026-08-21 17:00 = KST 2026-08-22 02:00 → 첫 회차(0200) 제공 전이라 전날 2300
    utc = datetime(2026, 8, 21, 17, 0, tzinfo=timezone.utc)
    assert dms.select_vilage_base_datetime(utc) == ("20260821", "2300")


# --- §8-5 요청 URL 8인자 · 인증키 노출 없음 ----------------------------------
def test_request_url_has_all_eight_params_f258():
    import urllib.parse as up
    url = dms._kma_request_url("AUTHVALUE-1", nx=60, ny=127, base_date="20260821", base_time="0500")
    q = dict(up.parse_qsl(up.urlsplit(url).query))
    assert set(q) == {"authKey", "dataType", "pageNo", "numOfRows", "base_date", "base_time", "nx", "ny"}
    assert q["nx"] == "60" and q["ny"] == "127"
    assert q["base_date"] == "20260821" and q["base_time"] == "0500"


def test_auth_key_not_logged_f258(conn, monkeypatch, caplog):
    monkeypatch.setenv(dms.API_KEY_ENV, "AUTHVALUE-abc-1")
    monkeypatch.setattr(dms, "_fetch_kma_live", lambda *a, **k: _mock_payload(60, 127))
    with caplog.at_level("DEBUG"):
        dms.fetch_public_data(conn, greenhouse_id="demo-gh-1")
    assert "AUTHVALUE-abc-1" not in caplog.text


# --- §8-6 실데이터 성공 판정 -------------------------------------------------
@pytest.mark.parametrize("payload,ok", [
    (_mock_payload(60, 127), True),
    (_mock_payload(60, 127, result="03"), False),        # resultCode != 00
    (_mock_payload(60, 127, items=False), False),        # 빈 items
    (_mock_payload(99, 99), False),                       # 격자 불일치
    ({"response": {"header": {"resultCode": "00"}, "body": {}}}, False),  # 구조 결손
])
def test_validate_kma_response_f258(payload, ok):
    assert dms._validate_kma_response(payload, nx=60, ny=127) is ok


def test_validate_rejects_missing_tmax_f258():
    payload = _mock_payload(60, 127)
    payload["response"]["body"]["items"]["item"] = [
        {"category": "REH", "fcstValue": "55", "nx": 60, "ny": 127}]  # TMX 없음
    assert dms._validate_kma_response(payload, nx=60, ny=127) is False


# --- §8-9 출처 판정 LIVE / FALLBACK / DEMO_FIXTURE ---------------------------
def test_no_key_is_demo_fixture_f258(conn):
    record, fallback = dms.fetch_public_data(conn, greenhouse_id="demo-gh-1")
    assert record.data_origin == "DEMO_FIXTURE"
    assert fallback is True


def test_key_and_valid_response_is_live_f258(conn, monkeypatch):
    monkeypatch.setenv(dms.API_KEY_ENV, "K")
    captured = {}

    def fake(kma_key, *, nx, ny, base_date, base_time, **k):
        captured.update(nx=nx, ny=ny, base_date=base_date, base_time=base_time)
        return _mock_payload(nx, ny)

    monkeypatch.setattr(dms, "_fetch_kma_live", fake)
    record, fallback = dms.fetch_public_data(conn, greenhouse_id="demo-gh-1")
    assert record.data_origin == "LIVE"
    assert fallback is False
    assert (record.nx, record.ny) == (60, 127)          # 온실 격자로 요청·기록
    assert captured["nx"] == 60 and captured["ny"] == 127


def test_key_but_invalid_response_is_fallback_f258(conn, monkeypatch):
    monkeypatch.setenv(dms.API_KEY_ENV, "K")
    monkeypatch.setattr(dms, "_fetch_kma_live", lambda *a, **k: _mock_payload(60, 127, result="99"))
    record, fallback = dms.fetch_public_data(conn, greenhouse_id="demo-gh-1")
    assert record.data_origin == "FALLBACK"
    assert record.nx is None and record.base_date is None    # 성립 안 된 요청은 회차 기록 안 함
    assert fallback is True


def test_key_but_no_grid_is_fallback_f258(conn, monkeypatch):
    # 위치 미설정 온실: 키가 있어도 실 요청을 성립시키지 않는다.
    conn.execute("INSERT INTO greenhouse_info(id,created_at,updated_at,name) "
                 "VALUES('gh-noloc','2026-08-01T00:00:00+09:00','2026-08-01T00:00:00+09:00','무위치')")
    conn.commit()
    monkeypatch.setenv(dms.API_KEY_ENV, "K")
    called = []
    monkeypatch.setattr(dms, "_fetch_kma_live", lambda *a, **k: called.append(1) or _mock_payload(1, 1))
    record, fallback = dms.fetch_public_data(conn, greenhouse_id="gh-noloc")
    assert record.data_origin == "FALLBACK"
    assert not called                                    # 실 API 호출 자체가 없다


# --- §8-7 두 온실의 서로 다른 격자로 각각 요청 -------------------------------
def test_two_greenhouses_use_own_grid_f258(conn, monkeypatch):
    nx2, ny2 = latlon_to_kma_grid(35.1796, 129.0756)     # 부산 (98,76)
    repository.set_greenhouse_location(conn, "demo-gh-1",
                                        latitude=35.1796, longitude=129.0756,
                                        kma_nx=nx2, kma_ny=ny2, source="MANUAL", user_id="demo-user-1")
    conn.execute("INSERT INTO greenhouse_info(id,created_at,updated_at,name,latitude,longitude,kma_nx,kma_ny,"
                 "coordinate_source,coordinates_updated_at) VALUES('gh2','2026-08-01T00:00:00+09:00',"
                 "'2026-08-01T00:00:00+09:00','2호',37.5665,126.9780,60,127,'MANUAL','2026-08-01T00:00:00+09:00')")
    conn.commit()
    monkeypatch.setenv(dms.API_KEY_ENV, "K")
    seen = []
    monkeypatch.setattr(dms, "_fetch_kma_live",
                        lambda kma_key, *, nx, ny, **k: seen.append((nx, ny)) or _mock_payload(nx, ny))
    r1, _ = dms.fetch_public_data(conn, greenhouse_id="demo-gh-1")
    r2, _ = dms.fetch_public_data(conn, greenhouse_id="gh2")
    assert (r1.nx, r1.ny) == (98, 76)
    assert (r2.nx, r2.ny) == (60, 127)
    assert seen == [(98, 76), (60, 127)]                 # 서로 다른 격자로 각각 호출


# --- §8-2 위경도 저장 원자성 · 이력 -----------------------------------------
def test_set_location_atomic_and_logged_f258(conn):
    before = conn.execute("SELECT COUNT(*) c FROM config_change_log").fetchone()["c"]
    nx, ny = latlon_to_kma_grid(35.1796, 129.0756)
    ok = repository.set_greenhouse_location(conn, "demo-gh-1",
                                            latitude=35.1796, longitude=129.0756,
                                            kma_nx=nx, kma_ny=ny, source="MANUAL", user_id="demo-user-1")
    conn.commit()
    assert ok is True
    row = conn.execute("SELECT latitude,longitude,kma_nx,kma_ny,coordinate_source "
                       "FROM greenhouse_info WHERE id='demo-gh-1'").fetchone()
    assert (row["kma_nx"], row["kma_ny"]) == (nx, ny)
    assert row["coordinate_source"] == "MANUAL"
    after = conn.execute("SELECT COUNT(*) c FROM config_change_log").fetchone()["c"]
    assert after == before + 1                           # 변경 이력 1건


def test_set_location_missing_greenhouse_f258(conn):
    ok = repository.set_greenhouse_location(conn, "no-such-gh",
                                            latitude=37.5, longitude=127.0,
                                            kma_nx=60, kma_ny=127)
    assert ok is False


# --- F-259 예보 대상일·TMX 를 명시 필드로 추출·저장 --------------------------
def test_extract_forecast_reads_tmx_date_and_value_f259():
    date, tmax = dms._extract_forecast(_mock_payload(60, 127, tmax="34"))
    assert date == "20260822" and tmax == 34.0


@pytest.mark.parametrize("payload", [
    {"response": {"body": {}}},                                    # 구조 결손
    _mock_payload(60, 127, items=False),                          # 빈 items
])
def test_extract_forecast_missing_returns_none_f259(payload):
    assert dms._extract_forecast(payload) == (None, None)


def test_demo_fixture_stores_forecast_but_not_request_grid_f259(conn):
    """키 부재(DEMO_FIXTURE)에서도 예보 대상일·TMX 는 payload 에서 뽑아 저장한다
    — 이 값이 '실제 초안에 쓰인 예보'다. 반면 nx/ny·base_* 는 '실제 요청'이라
    폴백에서 NULL 로 남는다(제안 §2 라벨 분리). 화면이 위치 결속을 증명하되
    실행되지 않은 LIVE 요청을 꾸며내지 않는다."""
    record, fallback = dms.fetch_public_data(conn, greenhouse_id="demo-gh-1")
    assert record.data_origin == "DEMO_FIXTURE" and fallback is True
    # 예보 명시 필드는 채워진다(목업 TMX = 34, 대상일 20260812).
    assert record.forecast_tmax_c == 34.0
    assert record.forecast_date == "20260812"
    # 실제 요청 격자·발표회차는 요청이 성립 안 됐으므로 NULL 이다.
    assert record.nx is None and record.ny is None
    assert record.base_date is None and record.base_time is None


def test_live_stores_forecast_and_request_grid_f259(conn, monkeypatch):
    monkeypatch.setenv(dms.API_KEY_ENV, "K")
    monkeypatch.setattr(dms, "_fetch_kma_live",
                        lambda kma_key, *, nx, ny, **k: _mock_payload(nx, ny, tmax="34"))
    record, fallback = dms.fetch_public_data(conn, greenhouse_id="demo-gh-1")
    assert record.data_origin == "LIVE" and fallback is False
    assert record.forecast_tmax_c == 34.0 and record.forecast_date == "20260822"
    assert (record.nx, record.ny) == (60, 127)               # 요청 격자도 함께 기록
