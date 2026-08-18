"""
backend/services/fms.py — TTAK.KO-10.0937 6.4 FMS(스마트팜모니터서비스).

"장치관리서비스를 통해 수집된 센서 및 구동기의 환경 데이터와 구동 데이터를
모니터링하고 저장된 자료를 조회하는 서비스"(0937 6.4).

담당 조항: 6.4 전부 · A.1-2·3·4·5 · A.3-2 (0937_요구사항_대조표.md §4.1)
진입점: query_env · query_device_states · list_alerts · check_stale_devices

`on_device_value`의 실제 반영 로직은 `backend/ingest.py::_handle_device_value()`
에 있다(단계 5) — 이 모듈은 그것을 재구현하지 않는다. 여기서는 API가
필요로 하는 조회와 0937 6.4-3의 미수집 알림 판정만 새로 둔다.
"""
from __future__ import annotations

import sqlite3

try:                    # F-025 와 같은 원칙
    from backend import repository
except ImportError:
    import pathlib
    import sys
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent.parent))
    from backend import repository


def query_env(conn: sqlite3.Connection, **kwargs):
    """`GET /api/v1/telemetry` — 1369-P1 6.3.3 환경상태 데이터."""
    return repository.list_telemetry(conn, **kwargs)


def query_device_states(conn: sqlite3.Connection, **kwargs):
    """`GET /api/v1/device-states` — 1369-P1 6.3.4 장치상태 데이터."""
    return repository.list_device_states(conn, **kwargs)


def list_alerts(conn: sqlite3.Connection, **kwargs):
    """`GET /api/v1/alerts` — 0937 6.4-3 · 6.5-2 사용자 알림."""
    return repository.list_alerts_page(conn, **kwargs)


#: 0937_요구사항_대조표.md §4.4-b 배수 3의 근거 — 표 7-18 Num. of Retry 기본
#: 3회. 재전송이 전부 실패해야 미수집으로 본다.
STALE_RETRY_MULTIPLIER = 3

#: 과거 데이터나 SIAP 연동 전 설치 행은 Period가 NULL일 수 있다. 그런 행만
#: 호환 기본값을 쓰고, 표 7-15로 등록된 장치는 저장된 실제 Period를 쓴다.
DEFAULT_PERIOD_SEC = 300


def check_stale_devices(conn: sqlite3.Connection, now: str) -> list[str]:
    """0937 6.4-3 · A.1-4 — "정해진 시간에 데이터가 수집되지 않는 경우
    알림". 디바이스별 마지막 측정시각이 그 장치의 표 7-15
    `period_sec × 3`을 넘으면 `alert(kind='NO_DATA')`를 만든다.

    `Keep Alive`와의 차이 — Keep Alive는 노드 생존성(8.2.1.5)이다. 노드는
    살아 있고 특정 디바이스의 `NOTI_DEVICE_VALUE`만 멈춘 경우는 Keep Alive로
    잡히지 않는다 — 이 함수가 그 간극을 메운다.

    F-191 — 전용 스케줄러 스레드는 두지 않는다(새 스레드는 CLAUDE.md §4.3
    동시성 모델 확장이라 그 자체로 별도 결정이 필요하다). 대신 `api.py`가
    `GET /api/v1/alerts`(조회 시점, check-on-read)와 `GET /api/v1/stream`
    (SSE, 0.5초 틱마다)에서 이 함수를 호출한다 — 함수 자체는 DB만 보고
    판정하므로 언제 불러도 결과가 같다(멱등). 반환값은 새로 만든 alert id
    목록."""
    now_epoch = _iso_to_epoch(now)
    rows = conn.execute(
        "SELECT em.install_id AS install_id, MAX(s.measured_at) AS last_seen,"
        " COALESCE(di.period_sec, ?) AS period_sec"
        " FROM env_measure em JOIN env_state_data s ON s.id = em.env_state_id"
        " JOIN device_install_info di ON di.id = em.install_id"
        " GROUP BY em.install_id"
        , (DEFAULT_PERIOD_SEC,)
    ).fetchall()
    created: list[str] = []
    for row in rows:
        threshold_sec = row["period_sec"] * STALE_RETRY_MULTIPLIER
        last_epoch = _iso_to_epoch(row["last_seen"])
        if now_epoch - last_epoch <= threshold_sec:
            continue
        already = conn.execute(
            "SELECT 1 FROM alert WHERE install_id = ? AND kind = 'NO_DATA' AND ack_at IS NULL LIMIT 1",
            (row["install_id"],),
        ).fetchone()
        if already is not None:
            continue      # 이미 미확인 NO_DATA 알림이 떠 있다 — 중복 생성하지 않는다
        alert_id = repository.record_alert(
            conn, kind="NO_DATA", severity="WARN", install_id=row["install_id"],
            message=f"{threshold_sec}초 이상 데이터가 수집되지 않았습니다.",
        )
        created.append(alert_id)
    if created:
        conn.commit()
    return created


def _iso_to_epoch(s: str) -> float:
    from datetime import datetime
    return datetime.fromisoformat(s).timestamp()
