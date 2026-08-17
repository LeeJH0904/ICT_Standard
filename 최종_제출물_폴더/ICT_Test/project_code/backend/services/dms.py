"""
backend/services/dms.py — TTAK.KO-10.0937 6.2 DMS(데이터관리서비스).

"공공데이터(Public Data)서비스로부터 필요한 외부 데이터를 수집하여
데이터베이스에 기록하는 서비스"(0937 6.2). 노드·디바이스 속성 설정은
여기 없다 — 그건 6.1 EMS의 일이다(`ems.py` 참조).

담당 조항: 6.2 전부 · A.2-2·3·4
진입점: fetch_public_data · get_source · list_records
"""
from __future__ import annotations

import json
import os
import sqlite3
import urllib.error
import urllib.request
from pathlib import Path

try:                    # 패키지로 import될 때
    from backend import repository
except ImportError:
    import pathlib
    import sys
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent.parent))
    from backend import repository

FIXTURES_DIR = Path(__file__).resolve().parent.parent.parent / "fixtures"
MOCK_PATH = FIXTURES_DIR / "kma_forecast_mock.json"

#: 기상청 API 키. 부재 시 fixtures 목업으로 자동 폴백한다.
API_KEY_ENV = "KMA_API_KEY"

_KMA_URL = ("https://apihub.kma.go.kr/api/typ02/openApi/VilageFcstInfoService_2.0"
            "/getVilageFcst")


def get_source(conn: sqlite3.Connection, source_id: str):
    """0937 6.2-2 — `public_data_source`는 시드 전용 — 조회만 한다."""
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


def _fetch_kma_live(kma_key: str, *, timeout: float = 3.0) -> dict:
    """실제 기상청 단기예보 조회서비스 호출. 오프라인 기본 경로가 아니므로
    `KMA_API_KEY`가 있을 때만
    시도되고, 실패하면 호출자가 목업으로 폴백한다."""
    url = f"{_KMA_URL}?authKey={kma_key}&dataType=JSON&numOfRows=100&pageNo=1"
    req = urllib.request.Request(url, headers={"User-Agent": "siap-reference/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:      # noqa: S310 — 고정 기상청 URL
        return json.loads(resp.read().decode("utf-8"))


def fetch_public_data(conn: sqlite3.Connection, *, source_id: str | None = None,
                       region: str | None = None, item: str | None = None) -> tuple[object, bool]:
    """0937 6.2-1 — "공개된 공공데이터서비스로부터 데이터를 수집". 6.3-3/6.3-4가
    요구하는 "사전 획득 방식" 입력이 되는 지점이다 — `mms.run_model()`이
    이 결과의 `payload`를 읽는다.

    반환: (PublicDataRecord, fallback). `fallback=True`면 목업을 썼다 —
    `Health.public_data_fallback`가 이 값을 그대로 노출한다.

    API 스레드 소유 — 외부 HTTP 호출이 SIAP I/O 스레드를
    막으면 안 된다."""
    source = get_source(conn, source_id) if source_id else default_source(conn)
    if source is None:
        raise LookupError("public_data_source 가 비어 있다 — fixtures/seed.sql 을 확인하라")

    kma_key = os.environ.get(API_KEY_ENV)
    payload: dict | None = None
    fallback = True
    if kma_key:
        try:
            payload = _fetch_kma_live(kma_key)
            fallback = False
        except (urllib.error.URLError, TimeoutError, ValueError, OSError):
            payload = None      # 조용히 삼키지 않는다 — 아래에서 목업으로 대체할 뿐, 예외 자체는 버린다(폴백이 곧 처리다)
    if payload is None:
        payload = _load_mock()

    if region is None and item is None:
        region, item = _derive_region_item(payload)

    record_id = repository.insert_public_data_record(
        conn, source_id=source.id, payload=payload, region=region, item=item,
    )
    conn.commit()
    record = repository.get_by_id(conn, "public_data_record", record_id)
    return record, fallback
