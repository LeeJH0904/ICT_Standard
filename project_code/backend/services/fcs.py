"""
backend/services/fcs.py — TTAK.KO-10.0937 6.5 FCS(스마트팜제어서비스).

"장치관리서비스와 연동하여 사용자가 지정한 명령을 구동기가 실행하도록
제어 명령을 전달하는 서비스"(0937 6.5).

담당 조항: 6.5 전부 · A.2-5·6·7 · A.3-1 (0937_요구사항_대조표.md §4.1)
진입점: execute · manual_control · query_history

순서가 중요하다(아키텍처 §3.2) — `control_execution` 레코드를 먼저 기록하고,
성공한 경우에만 프레임을 송신한다. DB 제약(승인 게이트)이 송신의 선행
조건이 되어야 "AI 출력이 직접 구동기를 제어하지 않는다"가 코드 경로로
보장된다(CLAUDE.md §1-7).

F-186 — `SiapLink.send()`가 응답을 동기 반환하므로, 이 모듈(API 스레드에서
호출된다)이 `result_rsc`·`responded_at` UPDATE까지 같은 커넥션으로 직접
수행한다(아키텍처 §4.4-a④ 정정).
"""
from __future__ import annotations

import json
import sqlite3

try:                    # F-025 와 같은 원칙
    from backend import repository
except ImportError:
    import pathlib
    import sys
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent.parent))
    from backend import repository

try:
    from contracts.frame import ValueType
    from contracts.siap_iface import FrameBuilder, SiapLink
except ImportError:
    import pathlib
    import sys
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent.parent))
    from contracts.frame import ValueType
    from contracts.siap_iface import FrameBuilder, SiapLink


class ExecutionGateError(Exception):
    """승인 게이트가 막았다(`trg_exec_requires_approval` 등). `api.py`가
    409/400 Problem 으로 옮긴다."""

    def __init__(self, message: str, *, constraint: str | None = None) -> None:
        super().__init__(message)
        self.constraint = constraint


class ExecutionTimeoutError(Exception):
    """`Timeout × (Retry Count + 1)` 안에 응답이 없었다(표 7-18). 실행
    이력은 이미 기록됐고 `result_rsc`만 비어 있다 — `api.py`가 504 Problem
    으로 옮기되 본문에 실행 id를 함께 준다."""

    def __init__(self, message: str, *, exec_id: str) -> None:
        super().__init__(message)
        self.exec_id = exec_id


def execute(conn: sqlite3.Connection, link: SiapLink, builder: FrameBuilder, rule_id: str, *,
            timeout: float | None = None):
    """`POST /api/v1/rules/{id}/execute` — 0937 6.5. **요청 본문이 없다.**
    명령과 대상은 승인 스냅샷(`control_rule.action_json`·`target_install_id`)
    에서만 읽는다 — 클라이언트가 무엇도 지정할 수 없다(API 명세서 §4.2)."""
    rule = repository.get_control_rule(conn, rule_id)
    if rule is None:
        raise LookupError(f"control_rule {rule_id} 없음")
    if not rule.is_approved:
        raise ExecutionGateError(
            "미승인 규칙으로는 제어를 실행할 수 없다", constraint="trg_exec_requires_approval",
        )
    install = repository.get_device_install(conn, rule.target_install_id)
    if install is None or install.siap_node_id is None or install.siap_device_id is None:
        raise LookupError(
            f"target_install_id={rule.target_install_id} 의 SIAP 연동 정보가 없다",
        )
    # F-030/F-049 — 승인된 것과 정확히 같은 명령·대상을 그대로 옮긴다.
    # trg_exec_command_matches_approved 는 TEXT 동치를 보므로, action_json
    # 문자열을 다시 파싱→직렬화해 바이트가 어긋나면(키 순서 등) DB가 막는다
    # — round-trip이 안전한 이유는 양쪽 다 json.dumps(x, ensure_ascii=False)
    # 로 동일하게 직렬화하고 dict 삽입 순서를 json.loads 가 보존하기 때문이다.
    command = json.loads(rule.action_json)
    try:
        exec_id = repository.insert_control_execution(
            conn, origin="RULE", rule_id=rule_id, install_id=rule.target_install_id, command=command,
        )
        conn.commit()
    except sqlite3.IntegrityError as e:
        conn.rollback()
        raise ExecutionGateError(str(e), constraint=repository.constraint_name_from_error(e)) from e
    return _send_and_finalize(conn, link, builder, exec_id, install, command, timeout)


def manual_control(conn: sqlite3.Connection, link: SiapLink, builder: FrameBuilder, *,
                    install_id: str, action: dict, user_id: str, timeout: float | None = None):
    """`POST /api/v1/control` — 0937 부속서 A 1·2 수동제어/원격제어. 권한
    출처가 규칙이 아니라 지시한 사용자다(`X-User-Id` 필수) — 승인 규칙의
    대상 제약을 받지 않는다(API 명세서 §4)."""
    if not repository.user_exists(conn, user_id):
        raise LookupError(f"user_id={user_id} 없음 — 1369-P1 7.2.2.6 사용자정보에 실재하지 않는다")
    install = repository.get_device_install(conn, install_id)
    if install is None:
        raise LookupError(f"install_id={install_id} 없음")
    if install.siap_node_id is None or install.siap_device_id is None:
        raise LookupError(f"install_id={install_id} 는 SIAP 연동 정보가 없다")
    exec_id = repository.insert_control_execution(
        conn, origin="MANUAL", issued_by=user_id, install_id=install_id, command=action,
    )
    conn.commit()
    return _send_and_finalize(conn, link, builder, exec_id, install, action, timeout)


def _send_and_finalize(conn: sqlite3.Connection, link: SiapLink, builder: FrameBuilder,
                        exec_id: str, install, command: dict, timeout: float | None):
    value_type = ValueType[command["value_type"]]
    frame = builder.device_control(
        install.siap_node_id, [(install.siap_device_id, command["value"], value_type)],
    )
    resp = link.send(frame, timeout=timeout)
    if resp is None:
        # F-186 — 타임아웃도 msg_id 는 남긴다(무엇을 기다렸는지 증거로).
        repository.update_execution_result(
            conn, exec_id, siap_msg_id=frame.header.msg_id, result_rsc=None, responded_at=None,
        )
        # F-191 — 0937 6.5-2 "긴급 상황시 사용자 알림"의 재전송 소진 경로.
        # `Timeout × (Retry Count + 1)`(표 7-18) 안에 응답이 없다는 것은
        # 구동기가 명령을 받지 못했을 수도 있다는 뜻이라 사용자가 알아야
        # 한다 — `alert.kind` CHECK가 이미 `CONTROL_TIMEOUT`을 예정해
        # 두고 있었다(F-186과 같은 원칙 — API 스레드가 동기 응답 지점에서
        # 직접 쓴다, `update_execution_result` 바로 옆).
        repository.record_alert(
            conn, kind="CONTROL_TIMEOUT", severity="CRITICAL",
            message=f"exec_id={exec_id} install_id={install.id} 제어 명령 응답 시간 초과",
            install_id=install.id,
        )
        conn.commit()
        raise ExecutionTimeoutError(f"exec_id={exec_id} 노드가 응답 시간 안에 회신하지 않았다",
                                     exec_id=exec_id)
    repository.update_execution_result(
        conn, exec_id, siap_msg_id=frame.header.msg_id,
        result_rsc=int(resp.rsc) if resp.rsc is not None else None,
        responded_at=repository.now_iso(),
    )
    conn.commit()
    return repository.get_control_execution(conn, exec_id)


def query_history(conn: sqlite3.Connection, **kwargs):
    """`GET /api/v1/executions` — 0937 6.5 "제어 명령, 구동 시간 등 제어
    이력 정보를 조회"."""
    return repository.list_control_executions(conn, **kwargs)
