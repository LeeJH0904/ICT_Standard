"""backend/tests/test_kma_grid.py — F-258 회귀. 기상청 격자 변환 순수 함수.

외부 API·네트워크 없이 결정론적으로 검증한다(제안 §4·§8-3). 서울·부산은
기상청 공표 동네예보 격자표와 독립 일치하는 외부 교차검증 앵커이고, 나머지는
변환식의 결정론을 고정하는 회귀 락이다.
"""
from __future__ import annotations

import math

import pytest

from backend.services.kma_grid import (
    latlon_to_kma_grid,
    validate_latlon,
)

# (위도, 경도) -> (nx, ny). 서울·부산은 기상청 공표값과 일치(외부 앵커).
_GOLDEN = {
    "서울시청": (37.5665, 126.9780, 60, 127),   # 공표 (60,127) — 목업 fixture 와도 일치
    "부산시청": (35.1796, 129.0756, 98, 76),    # 공표 (98,76)
    "제주": (33.4996, 126.5312, 53, 38),        # 회귀 락(변환식 결정론)
    "강릉": (37.7519, 128.8761, 92, 132),       # 회귀 락
}


@pytest.mark.parametrize("name", list(_GOLDEN))
def test_latlon_to_kma_grid_golden_f258(name: str) -> None:
    lat, lon, nx, ny = _GOLDEN[name]
    assert latlon_to_kma_grid(lat, lon) == (nx, ny)


def test_grid_is_deterministic_f258() -> None:
    # 같은 입력은 항상 같은 격자 — 무작위성이 없다.
    for _ in range(5):
        assert latlon_to_kma_grid(37.5665, 126.9780) == (60, 127)


@pytest.mark.parametrize("lat,lon", [
    (float("nan"), 126.0),
    (37.0, float("inf")),
    (91.0, 126.0),          # 위도 범위 초과
    (-91.0, 126.0),
    (37.0, 181.0),          # 경도 범위 초과
    (37.0, -181.0),
    (True, 126.0),          # bool 은 숫자가 아니다
])
def test_invalid_latlon_rejected_f258(lat, lon) -> None:
    with pytest.raises(ValueError):
        validate_latlon(lat, lon)
    with pytest.raises(ValueError):
        latlon_to_kma_grid(lat, lon)


@pytest.mark.parametrize("lat,lon", [
    (-89.9, -179.9),        # 극단값(투영 특이점인 정확한 극 -90 은 도메인 밖)
    (89.9, 179.9),
    (0.0, 0.0),
])
def test_boundary_latlon_accepted_f258(lat, lon) -> None:
    validate_latlon(lat, lon)                       # 예외 없음
    nx, ny = latlon_to_kma_grid(lat, lon)
    assert isinstance(nx, int) and isinstance(ny, int)


def test_empty_string_rejected_f258() -> None:
    # 빈 문자열·숫자로 보이는 문자열은 숫자가 아니다.
    for bad in ("", "37.5", "nan"):
        with pytest.raises(ValueError):
            validate_latlon(bad, 126.0)  # type: ignore[arg-type]
