"""backend/tests/test_greenhouse_location.py — F-258 회귀. 온실 위치 API.

위경도 저장/조회 HTTP 경로와 입력 검증(빈값·비숫자·NaN·무한대·범위초과 거부),
404, LIVE/DEMO_FIXTURE 구분을 확인한다(제안 §8-1·§8-9).
"""
from __future__ import annotations

import pytest

from _asgi_client import call

from backend import db, repository
from backend.api import create_app
from contracts.fake_link import FakeFrameBuilder, FakeSiapLink


@pytest.fixture()
def app(tmp_path):
    db.init_db(tmp_path / "gh.db", seed=True).close()
    link = FakeSiapLink()
    link.start("simulate")
    return create_app(db_path=tmp_path / "gh.db", link=link,
                      builder=FakeFrameBuilder(gcg_id=1),
                      run_mode="simulate", proto_mode="strict")


def test_list_greenhouses_has_demo_location_f258(app):
    r = call(app, "GET", "/api/v1/greenhouses")
    assert r.status_code == 200
    items = r.json()["items"]
    demo = next(g for g in items if g["id"] == "demo-gh-1")
    assert (demo["kma_nx"], demo["kma_ny"]) == (60, 127)
    assert demo["coordinate_source"] == "DEMO_FIXTURE"


def test_set_location_valid_recomputes_grid_f258(app):
    # 부산 좌표 → 격자 (98,76) 재계산
    r = call(app, "PUT", "/api/v1/greenhouses/demo-gh-1/location",
             json={"latitude": 35.1796, "longitude": 129.0756},
             headers={"X-User-Id": "demo-user-1"})
    assert r.status_code == 200
    body = r.json()
    assert (body["kma_nx"], body["kma_ny"]) == (98, 76)
    assert body["coordinate_source"] == "MANUAL"


@pytest.mark.parametrize("payload", [
    {"latitude": 91, "longitude": 126},          # 위도 범위 초과
    {"latitude": 37, "longitude": 181},          # 경도 범위 초과
    {"latitude": "nan", "longitude": 126},       # 숫자로 보이는 문자열
    {"latitude": None, "longitude": 126},        # null
    {"latitude": 37},                            # 필드 누락
    {"latitude": 37, "longitude": 126, "kma_nx": 1},  # 초과 필드(파생값 직접입력 금지)
])
def test_set_location_invalid_rejected_400_f258(app, payload):
    r = call(app, "PUT", "/api/v1/greenhouses/demo-gh-1/location",
             json=payload, headers={"X-User-Id": "demo-user-1"})
    assert r.status_code == 400


def test_set_location_nan_infinity_rejected_f258(app):
    # JSON 은 NaN/Infinity 를 표준 허용하지 않으므로 매우 큰 값으로 범위를 뚫어본다.
    r = call(app, "PUT", "/api/v1/greenhouses/demo-gh-1/location",
             json={"latitude": 1e400, "longitude": 126},
             headers={"X-User-Id": "demo-user-1"})
    assert r.status_code == 400


def test_set_location_unknown_greenhouse_404_f258(app):
    r = call(app, "PUT", "/api/v1/greenhouses/no-such-gh/location",
             json={"latitude": 37.5, "longitude": 127.0},
             headers={"X-User-Id": "demo-user-1"})
    assert r.status_code == 404


def test_set_location_unknown_user_400_f258(app):
    r = call(app, "PUT", "/api/v1/greenhouses/demo-gh-1/location",
             json={"latitude": 37.5, "longitude": 127.0},
             headers={"X-User-Id": "ghost-user"})
    assert r.status_code == 400


def test_set_location_preserved_on_invalid_f258(app):
    # 잘못된 입력이 기존 저장값을 훼손하지 않는다(원자성).
    before = call(app, "GET", "/api/v1/greenhouses").json()["items"]
    demo_before = next(g for g in before if g["id"] == "demo-gh-1")
    call(app, "PUT", "/api/v1/greenhouses/demo-gh-1/location",
         json={"latitude": 999, "longitude": 999}, headers={"X-User-Id": "demo-user-1"})
    after = call(app, "GET", "/api/v1/greenhouses").json()["items"]
    demo_after = next(g for g in after if g["id"] == "demo-gh-1")
    assert (demo_after["kma_nx"], demo_after["kma_ny"]) == (demo_before["kma_nx"], demo_before["kma_ny"])
