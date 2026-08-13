"""
backend/db.py — DB 연결 팩토리. ★ PRAGMA는 이 파일에서만 건다 (CLAUDE.md §4.3).

아키텍처 설계서 §4.4 "SQLite 사용 규칙"의 표를 그대로 구현한다.
`foreign_keys=ON`은 SQLite 기본값이 OFF이므로 연결마다 켜야 하고, 한 곳에서만
켜야 빠뜨리지 않는다 — 이 파일이 그 한 곳이다. `backend/` 어디에서도
`sqlite3.connect()`를 직접 부르지 않는다.

스레드별 연결 — 아키텍처 설계서 §4.1 "연결: 스레드별 연결. check_same_thread=False
금지"를 그대로 지킨다. 이 모듈은 커넥션을 캐싱하지 않는다 — 호출할 때마다
새 연결을 연다(짧은 트랜잭션 전제, §4.4 "트랜잭션은 짧게. 프레임 1건 = 트랜잭션 1건").
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent
SCHEMA_PATH = BACKEND_DIR / "schema.sql"
SEED_PATH = BACKEND_DIR.parent / "fixtures" / "seed.sql"


def connect(db_path: str | Path) -> sqlite3.Connection:
    """일반 런타임 연결. 스키마가 이미 적용된 기존 DB 파일(또는 `:memory:`가
    아닌 새 파일)에 붙는다. PRAGMA 4종은 매 연결마다 새로 건다 — 아키텍처
    설계서 §4.4 표:
      - journal_mode=WAL   읽기가 쓰기를 막지 않음
      - foreign_keys=ON    SQLite 기본값이 OFF (F-016류 재발 방지의 핵심)
      - busy_timeout=5000  쓰기 겹침 시 즉시 실패 대신 대기
    row_factory=sqlite3.Row — models.py가 컬럼명으로 접근한다(위치 인덱스 금지,
    컬럼 추가 시 조용히 깨지는 F-024/F-049류 실수를 구조로 막는다)."""
    con = sqlite3.connect(str(db_path))
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    con.execute("PRAGMA journal_mode = WAL")
    con.execute("PRAGMA busy_timeout = 5000")
    return con


def init_db(db_path: str | Path, *, seed: bool = True,
            schema_path: Path = SCHEMA_PATH, seed_path: Path = SEED_PATH) -> sqlite3.Connection:
    """새 DB를 만든다 — `schema.sql` 실행 + (기본) `fixtures/seed.sql` 실행.

    `:memory:`를 포함해 이미 존재하는 파일에도 안전하게 쓸 수 있도록,
    DDL 실행 전에는 PRAGMA만 걸고(스키마가 아직 없으므로 journal_mode는
    파일 생성 후에도 유효), executescript로 스키마 전체를 한 번에 적용한다.
    executescript는 자체 트랜잭션을 커밋하므로 이후 seed도 별도 커밋한다."""
    con = sqlite3.connect(str(db_path))
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    con.execute("PRAGMA journal_mode = WAL")
    con.execute("PRAGMA busy_timeout = 5000")
    con.executescript(schema_path.read_text(encoding="utf-8"))
    # executescript 안에 이미 PRAGMA foreign_keys=ON 이 있지만(schema.sql 1행),
    # 새 연결마다 다시 켜는 것이 이 함수의 계약이다(§4.4 — 연결마다 켠다).
    con.execute("PRAGMA foreign_keys = ON")
    if seed and seed_path.exists():
        con.executescript(seed_path.read_text(encoding="utf-8"))
        con.commit()
    return con


def table_names(con: sqlite3.Connection) -> list[str]:
    """`sqlite_master`에서 사용자 테이블 이름만 뽑는다(내부 sqlite_* 테이블 제외).
    `tools/db_live_verify.py`와 테스트가 공유하는 조회 — 스키마 카운트를
    두 곳에서 따로 세면 F-080류(자기 자신과만 대조)가 재발한다."""
    rows = con.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' "
        "ORDER BY name"
    ).fetchall()
    return [r["name"] for r in rows]


def trigger_names(con: sqlite3.Connection) -> list[str]:
    rows = con.execute(
        "SELECT name FROM sqlite_master WHERE type='trigger' ORDER BY name"
    ).fetchall()
    return [r["name"] for r in rows]


def index_names(con: sqlite3.Connection) -> list[str]:
    """자동 생성 UNIQUE/PK 인덱스(`sqlite_autoindex_*`)는 `schema.sql`의
    명시적 `CREATE INDEX` 8개와 다른 근원이라 제외한다 — DB 스키마
    설계서 §6.1 "인덱스 8개"가 세는 대상이 그것이다."""
    rows = con.execute(
        "SELECT name FROM sqlite_master WHERE type='index' "
        "AND name NOT LIKE 'sqlite_autoindex_%' ORDER BY name"
    ).fetchall()
    return [r["name"] for r in rows]
