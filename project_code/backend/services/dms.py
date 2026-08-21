"""
backend/services/dms.py — TTAK.KO-10.0937 6.2 DMS(데이터관리서비스).

"공공데이터(Public Data)서비스로부터 필요한 외부 데이터를 수집하여
데이터베이스에 기록하는 서비스"(0937 6.2). 노드·디바이스 속성 설정은
여기 없다 — 그건 6.1 EMS의 일이다(F-079, `ems.py` 참조).

담당 조항: 6.2 전부 · A.2-2·3·4 (0937_요구사항_대조표.md §4.1)
진입점: fetch_public_data · get_source · list_records
"""
from __future__ import annotations

import json
import os
import sqlite3
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

try:                    # F-025 와 같은 원칙
    from backend import repository
except ImportError:
    import pathlib
    import sys
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent.parent))
    from backend import repository

FIXTURES_DIR = Path(__file__).resolve().parent.parent.parent / "fixtures"
MOCK_PATH = FIXTURES_DIR / "kma_forecast_mock.json"

#: 기상청 API 키. 부재 시 fixtures 목업으로 자동 폴백한다(CLAUDE.md §7).
API_KEY_ENV = "KMA_API_KEY"

_KMA_URL = ("https://apihub.kma.go.kr/api/typ02/openApi/VilageFcstInfoService_2.0"
            "/getVilageFcst")

#: 기상청 단기예보(getVilageFcst) 발표시각 — 하루 8회(활용가이드). 3시간 간격.
_VILAGE_BASE_TIMES = ("0200", "0500", "0800", "1100", "1400", "1700", "2000", "2300")

#: 발표시각 이후 API 자료 제공까지의 지연(활용가이드 "발표시각 + 10분"). 아직
#: 제공되지 않은 회차를 요청하면 NO_DATA 가 나므로 이 지연을 지나야 유효하다.
_VILAGE_PROVIDE_DELAY = timedelta(minutes=10)

#: 한국 표준시(KST, UTC+9). 발표회차 계산은 반드시 KST 기준이다.
_KST = timezone(timedelta(hours=9))


def select_vilage_base_datetime(now_kst: datetime) -> tuple[str, str]:
    """단기예보 `base_date`·`base_time` 선택(F-258 제안 §5). 순수 함수 —
    네트워크·환경변수와 무관하며 오직 KST 현재 시각에만 의존한다.

    발표시각 목록과 API 제공 지연(발표 + 10분)을 반영해 **이미 이용 가능한
    가장 최신 회차**를 고른다. 자정 직후처럼 오늘 회차가 아직 없으면 전날
    2300 회차로 넘어간다 — 월·연 경계도 `date` 연산이 처리한다.

    반환: (`YYYYMMDD`, `HHMM`)."""
    if now_kst.tzinfo is None:
        raise ValueError("now_kst 는 타임존을 가져야 한다(KST 기준)")
    now = now_kst.astimezone(_KST)
    today = now.date()
    for base_time in reversed(_VILAGE_BASE_TIMES):
        hh, mm = int(base_time[:2]), int(base_time[2:])
        announced = datetime(today.year, today.month, today.day, hh, mm, tzinfo=_KST)
        if now >= announced + _VILAGE_PROVIDE_DELAY:
            return today.strftime("%Y%m%d"), base_time
    # 오늘 첫 회차(0200)도 아직 제공 전 → 전날 마지막 회차(2300)
    yesterday = today - timedelta(days=1)
    return yesterday.strftime("%Y%m%d"), _VILAGE_BASE_TIMES[-1]


def _kma_request_url(kma_key: str, *, nx: int, ny: int,
                      base_date: str, base_time: str,
                      num_of_rows: int = 100, page_no: int = 1) -> str:
    """`getVilageFcst` 요청 URL(F-258 제안 §5). 공식 필수 요청값 8개를
    `urlencode` 로 구성한다 — 키·값을 문자열 연결하지 않는다. `nx`·`ny` 는
    일반 위경도가 아니라 `kma_grid.latlon_to_kma_grid()` 가 계산한 격자다."""
    params = {
        "authKey": kma_key,
        "dataType": "JSON",
        "pageNo": page_no,
        "numOfRows": num_of_rows,
        "base_date": base_date,
        "base_time": base_time,
        "nx": nx,
        "ny": ny,
    }
    return f"{_KMA_URL}?{urllib.parse.urlencode(params)}"


def get_source(conn: sqlite3.Connection, source_id: str):
    """0937 6.2-2 — `public_data_source`는 시드 전용(아키텍처 §4.4-a①,
    등록 API는 §5-2 후속 과제) — 조회만 한다."""
    return repository.get_public_data_source(conn, source_id)


def default_source(conn: sqlite3.Connection):
    """이 참조 구현은 출처 1개(기상청 단기예보) 고정 데모다 — 등록 API가
    없으므로 시드의 첫 출처를 기본으로 쓴다."""
    sources = repository.list_public_data_sources(conn)
    return sources[0] if sources else None


def list_records(conn: sqlite3.Connection, **kwargs):
    """0937 부속서 A 2.3 — "기간, 지역, 품목 등 검색조건을 지정하여 조회"."""
    return repository.list_public_data_records(conn, **kwargs)


def _load_mock() -> dict:
    return json.loads(MOCK_PATH.read_text(encoding="utf-8"))


def _derive_region_item(payload: dict) -> tuple[str | None, str | None]:
    """표시용 `구역`·`항목`을 응답 payload 에서 뽑는다(기상청 단기예보 스키마 —
    실데이터·목업 동일 구조). 구조가 달라 파싱에 실패하면 (None, None) 을
    돌려 컬럼을 비운다."""
    try:
        items = payload["response"]["body"]["items"]["item"]
        first = items[0]
        region = f"격자 {first['nx']},{first['ny']}"
        cats: list[str] = []
        for it in items:
            c = it.get("category")
            if c and c not in cats:
                cats.append(c)
        return region, ("·".join(cats) if cats else None)
    except (KeyError, IndexError, TypeError):
        return None, None


def _extract_forecast(payload: dict) -> tuple[str | None, float | None]:
    """수집한 payload(실데이터·목업 동일 구조)에서 **예보 대상일**과
    **최고기온 TMX**를 뽑는다(F-259 제안 §1). 기상청 단기예보 스키마
    (category='TMX' → 최고기온, fcstDate → 예보 대상일) 해석은 여기(서비스
    계층)에만 둔다 — 화면(web)이 이 스키마를 다시 해석하지 않도록 명시
    컬럼으로 저장하기 위한 것이다(CLAUDE.md §3.4 대칭).
    구조가 달라 파싱에 실패하면 (None, None) — 컬럼을 비운다."""
    try:
        items = payload["response"]["body"]["items"]["item"]
    except (KeyError, TypeError):
        return None, None
    if not isinstance(items, list):
        return None, None
    for it in items:
        if it.get("category") == "TMX":
            fcst_date = it.get("fcstDate")
            if not (isinstance(fcst_date, str) and fcst_date.isdigit() and len(fcst_date) == 8):
                fcst_date = None
            try:
                tmax = float(it["fcstValue"])
            except (KeyError, TypeError, ValueError):
                tmax = None
            return fcst_date, tmax
    return None, None


#: 단기예보 한 페이지 요청 건수(F-260). 기상청 공식 요청 예시가 numOfRows=1000
#: 이며, 한 회차 항목은 첫 100건에 TMX(최고기온)가 없을 수 있다(2026-08-21
#: 실측: totalCount=798, 첫 100건에 TMX 부재). 큰 페이지로 요청하되, 자료량이
#: 이보다 많아지면 아래 totalCount 순회가 나머지 페이지를 마저 수집한다.
_VILAGE_PAGE_ROWS = 1000

#: 페이지 순회 안전 상한 — totalCount 나 응답이 비정상일 때 무한 루프를 막는다.
_VILAGE_MAX_PAGES = 20


def _payload_items(payload: dict) -> list:
    """응답 payload 의 `items.item` 리스트를 안전하게 꺼낸다 — 구조가 다르거나
    단일 객체면 빈 리스트를 돌린다(F-260 페이지 병합용)."""
    try:
        items = payload["response"]["body"]["items"]["item"]
    except (KeyError, TypeError):
        return []
    return items if isinstance(items, list) else []


def _payload_total_count(payload: dict) -> int | None:
    """응답 payload 의 `totalCount`(전체 자료 건수). 없거나 숫자가 아니면 None —
    호출자는 페이지 순회를 중단한다(F-260)."""
    try:
        return int(payload["response"]["body"]["totalCount"])
    except (KeyError, TypeError, ValueError):
        return None


def _fetch_kma_page(kma_key: str, *, nx: int, ny: int, base_date: str, base_time: str,
                     page_no: int, timeout: float = 3.0) -> dict:
    """단기예보 한 페이지 조회(F-260). `_fetch_kma_live` 가 totalCount 만큼
    순회하며 호출한다. 필수 요청값 8개를 `urlencode` 로 구성한다."""
    url = _kma_request_url(kma_key, nx=nx, ny=ny, base_date=base_date, base_time=base_time,
                           num_of_rows=_VILAGE_PAGE_ROWS, page_no=page_no)
    req = urllib.request.Request(url, headers={"User-Agent": "siap-reference/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:      # noqa: S310 — 고정 기상청 URL
        return json.loads(resp.read().decode("utf-8"))


def _fetch_kma_live(kma_key: str, *, nx: int, ny: int, base_date: str, base_time: str,
                     timeout: float = 3.0) -> dict:
    """실제 기상청 단기예보 조회서비스 호출(F-258·F-260). 오프라인 기본 경로가
    아니므로(CLAUDE.md §7 "네트워크 필수 의존 금지") `KMA_API_KEY`가 있고
    온실 격자가 저장돼 있을 때만 시도되며, 실패·검증불통과면 호출자가
    목업으로 폴백한다.

    F-260 — 단기예보 한 회차는 수백 건이고 TMX(최고기온)가 첫 페이지 뒤에
    올 수 있다. `numOfRows` 한 페이지만 받으면 정상 응답인데도 TMX 를 찾지
    못해 FALLBACK 으로 오판정했다. `totalCount` 만큼 페이지를 순회해 전체
    item 을 첫 페이지 구조에 합쳐 돌려준다."""
    first = _fetch_kma_page(kma_key, nx=nx, ny=ny, base_date=base_date,
                            base_time=base_time, page_no=1, timeout=timeout)
    items = list(_payload_items(first))
    total = _payload_total_count(first)
    page_no = 1
    while total is not None and len(items) < total and page_no < _VILAGE_MAX_PAGES:
        page_no += 1
        nxt = _fetch_kma_page(kma_key, nx=nx, ny=ny, base_date=base_date,
                              base_time=base_time, page_no=page_no, timeout=timeout)
        more = _payload_items(nxt)
        if not more:                    # 더 줄 게 없으면(빈 페이지) 중단 — 상한과 무관
            break
        items.extend(more)
    try:                                # 합친 item 을 첫 페이지 구조에 다시 싣는다
        first["response"]["body"]["items"]["item"] = items
    except (KeyError, TypeError):
        pass
    return first


def _validate_kma_response(payload: dict, *, nx: int, ny: int) -> bool:
    """실데이터 성공 판정(F-258 제안 §5). HTTP 200 만으로 성공으로 보지
    않는다 — `resultCode == '00'`, items 존재, 요청 격자 일치, TMX(최고기온)
    존재까지 확인해야 LIVE 로 기록한다. 하나라도 어긋나면 목업 폴백."""
    try:
        header = payload["response"]["header"]
        if header.get("resultCode") != "00":
            return False
        items = payload["response"]["body"]["items"]["item"]
    except (KeyError, TypeError):
        return False
    if not isinstance(items, list) or not items:
        return False
    if not any(it.get("nx") == nx and it.get("ny") == ny for it in items):
        return False
    for it in items:                                  # TMX 존재 + 숫자
        if it.get("category") == "TMX":
            try:
                float(it["fcstValue"])
                return True
            except (KeyError, TypeError, ValueError):
                return False
    return False


def fetch_public_data(conn: sqlite3.Connection, *, source_id: str | None = None,
                       greenhouse_id: str | None = None,
                       region: str | None = None, item: str | None = None,
                       now_kst: datetime | None = None) -> tuple[object, bool]:
    """0937 6.2-1 — "공개된 공공데이터서비스로부터 데이터를 수집". 6.3-3/6.3-4가
    요구하는 "사전 획득 방식" 입력이 되는 지점이다 — `mms.run_model()`이
    이 결과의 `payload`를 읽는다.

    F-258 — 대상 온실(`greenhouse_id`)에 저장된 격자로 그 온실 위치의 예보를
    수집한다. 격자가 없거나 키가 없으면 실 API 요청을 성립시키지 않고
    목업으로 폴백한다 — 위치와 무관한 전역 예보를 쓰지 않는다.

    반환: (PublicDataRecord, fallback). `fallback=True`면 목업을 썼다(=LIVE 아님).
    `record.data_origin` ∈ {LIVE, FALLBACK, DEMO_FIXTURE} 가 정확한 출처다 —
    키 부재는 DEMO_FIXTURE, 키가 있으나 실패·격자부재는 FALLBACK.

    API 스레드 소유(아키텍처 §4.4-a③) — 외부 HTTP 호출이 SIAP I/O 스레드를
    막으면 안 된다."""
    source = get_source(conn, source_id) if source_id else default_source(conn)
    if source is None:
        raise LookupError("public_data_source 가 비어 있다 — fixtures/seed.sql 을 확인하라")

    grid = repository.get_greenhouse_grid(conn, greenhouse_id) if greenhouse_id else None
    kma_key = os.environ.get(API_KEY_ENV)
    now = now_kst or datetime.now(_KST)
    base_date, base_time = select_vilage_base_datetime(now)

    payload: dict | None = None
    req_nx = req_ny = None
    data_origin = "DEMO_FIXTURE" if not kma_key else "FALLBACK"
    if kma_key and grid is not None:
        req_nx, req_ny = grid
        try:
            live = _fetch_kma_live(kma_key, nx=req_nx, ny=req_ny,
                                    base_date=base_date, base_time=base_time)
            if _validate_kma_response(live, nx=req_nx, ny=req_ny):
                payload = live
                data_origin = "LIVE"
            # 검증 불통과: payload 는 None 으로 두고 아래에서 목업 폴백(FALLBACK 유지)
        except (urllib.error.URLError, TimeoutError, ValueError, OSError):
            payload = None      # 조용히 삼키지 않는다 — 목업으로 대체하되 예외는 버린다(폴백이 곧 처리다)
    if payload is None:
        payload = _load_mock()
        # 실측 요청이 성립하지 않았으므로 발표회차·격자는 기록하지 않는다(추정 금지)
        req_nx = req_ny = None
        base_date = base_time = None

    if region is None and item is None:
        region, item = _derive_region_item(payload)

    # F-259 — 예보 대상일·TMX 는 '실제 초안에 쓰인 예보값' 이라 origin 과 무관하게
    # (LIVE·FALLBACK·DEMO_FIXTURE 전부) payload 에서 뽑아 명시 저장한다. nx/ny·
    # base_* 는 '실제 요청' 이라 위에서 폴백 시 None 으로 지웠지만, 이 둘은 다르다.
    forecast_date, forecast_tmax_c = _extract_forecast(payload)

    record_id = repository.insert_public_data_record(
        conn, source_id=source.id, payload=payload, region=region, item=item,
        greenhouse_id=greenhouse_id, base_date=base_date, base_time=base_time,
        nx=req_nx, ny=req_ny, data_origin=data_origin,
        forecast_date=forecast_date, forecast_tmax_c=forecast_tmax_c,
    )
    conn.commit()
    record = repository.get_by_id(conn, "public_data_record", record_id)
    return record, data_origin != "LIVE"
