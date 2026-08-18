"""backend/tests/test_db.py — 연결 팩토리 (아키텍처 설계서 §4.4)."""
from __future__ import annotations

import sqlite3

import pytest

from backend import db


@pytest.fixture()
def fresh_db(tmp_path):
    path = tmp_path / "test.db"
    con = db.init_db(path, seed=True)
    yield con
    con.close()


def test_foreign_keys_on_every_connection(tmp_path):
    """SQLite 기본값은 OFF다 — db.py 가 매 연결마다 켜야 한다(아키텍처 §4.4)."""
    path = tmp_path / "fk.db"
    db.init_db(path, seed=False).close()
    con = db.connect(path)
    try:
        assert con.execute("PRAGMA foreign_keys").fetchone()[0] == 1
    finally:
        con.close()


def test_journal_mode_is_wal(tmp_path):
    path = tmp_path / "wal.db"
    db.init_db(path, seed=False).close()
    con = db.connect(path)
    try:
        mode = con.execute("PRAGMA journal_mode").fetchone()[0]
        assert mode.lower() == "wal"
    finally:
        con.close()


def test_busy_timeout_set(tmp_path):
    path = tmp_path / "busy.db"
    db.init_db(path, seed=False).close()
    con = db.connect(path)
    try:
        assert con.execute("PRAGMA busy_timeout").fetchone()[0] == 5000
    finally:
        con.close()


def test_schema_creates_31_tables(fresh_db):
    """DB 스키마 설계서 §6.1 — 테이블 31개."""
    assert len(db.table_names(fresh_db)) == 31


def test_schema_creates_37_triggers(fresh_db):
    """DB 스키마 설계서 §6.1 — 트리거 37개."""
    assert len(db.trigger_names(fresh_db)) == 37


def test_schema_creates_8_indexes(fresh_db):
    """DB 스키마 설계서 §6.1 — 인덱스 8개."""
    assert len(db.index_names(fresh_db)) == 8


def test_seed_loads_single_farm_greenhouse_user(fresh_db):
    """DB 스키마 설계서 §7.4 — 농장 1 / 온실 1 / 사용자 1 (데모 고정값)."""
    assert fresh_db.execute("SELECT COUNT(*) FROM farm_info").fetchone()[0] == 1
    assert fresh_db.execute("SELECT COUNT(*) FROM greenhouse_info").fetchone()[0] == 1
    assert fresh_db.execute("SELECT COUNT(*) FROM user_info").fetchone()[0] == 1
    assert fresh_db.execute("SELECT COUNT(*) FROM greenhouse_own").fetchone()[0] == 1
    assert fresh_db.execute("SELECT COUNT(*) FROM greenhouse_manage").fetchone()[0] == 1


def test_seed_owned_tables_stay_empty_without_runtime_writer(fresh_db):
    """아키텍처 설계서 §4.4-a① — `device_manage`는 REQ_SET_CONNECTION 런타임
    등록 전까지 시드 이후 어느 스레드도 쓰지 않는다."""
    assert fresh_db.execute("SELECT COUNT(*) FROM device_manage").fetchone()[0] == 0


def test_seed_loads_control_model_and_public_data_source(fresh_db):
    """단계 6 — `control_model`·`public_data_source`는 등록 API가 없으므로
    (0937_요구사항_대조표.md §5-2, MMS·DMS §5-2) `fixtures/seed.sql`이
    유일한 등록 수단이다(아키텍처 §4.4-a① 원래 의도대로). 시드 이후로는
    두 테이블 모두 런타임 쓰기가 없다 — `control_model`은 조회 전용
    (`repository.get_control_model`), `public_data_source`도 조회 전용
    (`repository.list_public_data_sources`/`get_public_data_source`)이고
    수집 이력만 `public_data_record`에 API 스레드가 쓴다(§4.4-a③)."""
    assert fresh_db.execute("SELECT COUNT(*) FROM control_model").fetchone()[0] == 2
    assert fresh_db.execute("SELECT COUNT(*) FROM public_data_source").fetchone()[0] == 1


def test_init_db_without_seed_stays_empty(tmp_path):
    con = db.init_db(tmp_path / "noseed.db", seed=False)
    try:
        assert con.execute("SELECT COUNT(*) FROM farm_info").fetchone()[0] == 0
    finally:
        con.close()


def test_connect_row_factory_allows_column_access(fresh_db):
    row = fresh_db.execute("SELECT * FROM user_info LIMIT 1").fetchone()
    assert isinstance(row, sqlite3.Row)
    assert row["name"] == "관리자"
