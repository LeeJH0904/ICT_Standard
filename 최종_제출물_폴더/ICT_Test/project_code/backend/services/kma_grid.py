"""
backend/services/kma_grid.py — WGS84 위경도 → 기상청 동네예보 격자(nx, ny) 변환.

네트워크·DB·외부 API 와 무관한 순수 함수뿐이다(F-258 제안 §4). 기상청
동네예보 활용가이드의 Lambert Conformal Conic 격자 변환식과 반올림 규칙을
그대로 옮긴다 — `getVilageFcst` 요청의 `nx`·`ny` 는 일반 위경도가 아니라 이
격자 좌표다.

상수는 기상청 활용가이드 표준값이다(격자 간격 5km, 표준위도 30°·60°,
기준점 경도 126°·위도 38°, 기준 격자 (43, 136)).
"""
from __future__ import annotations

import math

# --- 기상청 동네예보 격자 표준 상수 (활용가이드) ------------------------------
_RE = 6371.00877        # 지구 반경 (km)
_GRID = 5.0             # 격자 간격 (km)
_SLAT1 = 30.0           # 투영 표준위도 1 (deg)
_SLAT2 = 60.0           # 투영 표준위도 2 (deg)
_OLON = 126.0           # 기준점 경도 (deg)
_OLAT = 38.0            # 기준점 위도 (deg)
_XO = 43               # 기준점 X 격자 좌표
_YO = 136              # 기준점 Y 격자 좌표

_DEGRAD = math.pi / 180.0

# WGS84 위경도 유효 범위(F-258 제안 §2). 격자 변환식 자체는 전 지구에서 정의되나
# 스마트온실 데모의 입력 검증 경계로 사용한다.
LAT_MIN, LAT_MAX = -90.0, 90.0
LON_MIN, LON_MAX = -180.0, 180.0


def _projection_params() -> tuple[float, float, float]:
    """투영 상수 sn·sf·ro 를 미리 계산한다(위경도와 무관, 격자·기준점에만 의존)."""
    slat1 = _SLAT1 * _DEGRAD
    slat2 = _SLAT2 * _DEGRAD
    olat = _OLAT * _DEGRAD
    re = _RE / _GRID

    sn = math.tan(math.pi * 0.25 + slat2 * 0.5) / math.tan(math.pi * 0.25 + slat1 * 0.5)
    sn = math.log(math.cos(slat1) / math.cos(slat2)) / math.log(sn)
    sf = math.tan(math.pi * 0.25 + slat1 * 0.5)
    sf = (sf ** sn) * math.cos(slat1) / sn
    ro = math.tan(math.pi * 0.25 + olat * 0.5)
    ro = re * sf / (ro ** sn)
    return sn, sf, ro


def validate_latlon(latitude: float, longitude: float) -> None:
    """WGS84 위경도 검증(F-258 제안 §2). NaN·무한대·범위 초과는 `ValueError`.

    브라우저 입력값을 그대로 쓰지 않는다 — 저장·요청 전에 이 함수를 통과해야 한다."""
    for name, value in (("latitude", latitude), ("longitude", longitude)):
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            raise ValueError(f"{name} 는 숫자여야 한다: {value!r}")
        if math.isnan(value) or math.isinf(value):
            raise ValueError(f"{name} 가 NaN·무한대다: {value!r}")
    if not (LAT_MIN <= latitude <= LAT_MAX):
        raise ValueError(f"latitude 범위 초과({LAT_MIN}..{LAT_MAX}): {latitude}")
    if not (LON_MIN <= longitude <= LON_MAX):
        raise ValueError(f"longitude 범위 초과({LON_MIN}..{LON_MAX}): {longitude}")


def latlon_to_kma_grid(latitude: float, longitude: float) -> tuple[int, int]:
    """WGS84 위경도 → 기상청 동네예보 격자 (nx, ny). 결정론적 순수 함수.

    기상청 활용가이드의 dfs_xy_conv(lat, lon) 와 동일한 식·반올림(+0.5 후 절삭)이다.
    범위를 벗어나면 `validate_latlon` 이 `ValueError` 를 던진다 — 임의 좌표를
    만들지 않는다(F-258 제안 §2)."""
    validate_latlon(latitude, longitude)
    sn, sf, ro = _projection_params()

    ra = math.tan(math.pi * 0.25 + latitude * _DEGRAD * 0.5)
    ra = _RE / _GRID * sf / (ra ** sn)
    theta = longitude * _DEGRAD - _OLON * _DEGRAD
    if theta > math.pi:
        theta -= 2.0 * math.pi
    if theta < -math.pi:
        theta += 2.0 * math.pi
    theta *= sn

    nx = int(ra * math.sin(theta) + _XO + 0.5)
    ny = int(ro - ra * math.cos(theta) + _YO + 0.5)
    return nx, ny
