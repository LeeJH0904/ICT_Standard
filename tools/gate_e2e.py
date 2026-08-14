#!/usr/bin/env python3
"""tools/gate_e2e.py — 승인 게이트를 HTTP 레벨에서 다시 뚫어본다.

개발_착수_지시서 §3.8(단계 6) 신설 검증기. `schema.sql`의 CHECK·트리거
8종(F-017·F-030·F-039·F-048·F-049·F-091)이 이미 승인·거부를 봉인했다 —
이 스크립트는 그것을 **믿지 않고** `backend/api.py`가 만든 실제 FastAPI
앱을 HTTP 요청으로 다시 두드려, DB 트리거가 아니라 API 표면 자체가
우회 경로를 만들지 않았는지 확인한다(API 명세서 §4.2).

`httpx`(TestClient 의존성)가 `wheels/`에 없어(CLAUDE.md §4.1 의존성
최소화) `backend/tests/_asgi_client.py`(의존성 0)를 그대로 재사용한다 —
검증기와 테스트가 서로 다른 HTTP 클라이언트로 같은 결론에 도달하면
그 자체가 F-080류 자기 검증 순환이 아니라는 근거이지만, 새 의존성을
추가할 이유가 되지는 않는다.

실행: python tools/gate_e2e.py   (저장소 루트에서)
종료 코드: 통과 0 / 실패 1
"""
from __future__ import annotations

import sys
from pathlib import Path

if sys.stdout.encoding and sys.stdout.encoding.lower().replace("-", "") != "utf8":
    try:
        sys.stdout.reconfigure(errors="replace")
    except Exception:
        pass

REPO_ROOT = Path(__file__).resolve().parent.parent
PROJECT_CODE = REPO_ROOT / "project_code"
sys.path.insert(0, str(PROJECT_CODE))
sys.path.insert(0, str(PROJECT_CODE / "backend" / "tests"))

from _asgi_client import call                                     # noqa: E402
from backend import db, repository                                # noqa: E402
from backend.api import create_app                                # noqa: E402
from contracts.fake_link import FakeFrameBuilder, FakeSiapLink    # noqa: E402
from contracts.frame import DevType                                # noqa: E402

RESULTS: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    RESULTS.append((name, ok, detail))
    mark = "OK" if ok else "FAIL"
    print(f"  [{mark}] {name}" + (f"  {detail}" if detail and not ok else ""))


def _check_no_tx(name: str, link: FakeSiapLink, before: int) -> None:
    """F-225 — HTTP/DB 거부만으로는 구동기 무동작을 증명하지 못한다.
    거부 요청 직전의 실제 link TX 계수와 직후 값을 독립 대조한다."""
    after = int(link.stats().get("tx", -1))
    check(f"{name}: 거부 전후 제어 TX 증가 0건(F-225)", after == before,
          f"tx before={before}, after={after}")


def _fresh_app(tmp_dir: Path):
    tmp_dir.mkdir(parents=True, exist_ok=True)
    db_path = tmp_dir / "gate_e2e.db"
    con = db.init_db(db_path, seed=True)
    con.close()
    link = FakeSiapLink()
    link.start("simulate")
    builder = FakeFrameBuilder(gcg_id=1)
    app = create_app(db_path=db_path, link=link, builder=builder,
                      run_mode="simulate", proto_mode="strict")
    return app, db_path, link, builder


def _register_install(db_path: Path, node_id: int, device_id: int, subtype: int, builder) -> str:
    con = db.connect(db_path)
    gh = repository.get_default_greenhouse_id(con)
    info_id = repository.get_or_create_device_info(con, device_kind="ACTUATOR",
                                                     model_name=f"SIAP-0x{subtype:02X}",
                                                     device_name="dev")
    install_id = repository.upsert_device_install_info(
        con, device_info_id=info_id, device_name="v", siap_node_id=node_id,
        siap_device_id=device_id, siap_subtype=subtype)
    repository.link_device_install(con, gh, install_id)
    con.commit()
    con.close()
    builder.device_kinds[(node_id, device_id)] = (DevType.ACTUATOR, subtype)
    return install_id


def scenario_unapproved_rule_blocked(tmp_dir: Path) -> None:
    """시나리오 1 — 승인 없이 execute → 거부."""
    app, db_path, link, builder = _fresh_app(tmp_dir / "s1")
    r = call(app, "POST", "/api/v1/rules", json={"origin": "WIZARD", "draft_text": "미승인"})
    check("규칙 초안 생성 201", r.status_code == 201, str(r.status_code))
    rule_id = r.json()["id"]

    tx_before = int(link.stats()["tx"])
    re_ = call(app, "POST", f"/api/v1/rules/{rule_id}/execute")
    _check_no_tx("미승인 규칙 execute", link, tx_before)
    check("미승인 규칙 execute -> 409", re_.status_code == 409, str((re_.status_code, re_.text)))
    body = re_.json()
    check("409 본문에 constraint=trg_exec_requires_approval",
          body.get("constraint") == "trg_exec_requires_approval", str(body))

    execs = call(app, "GET", "/api/v1/executions").json()
    check("control_execution 행이 생기지 않았다", execs["total"] == 0, str(execs))


def scenario_rejected_rule_blocked(tmp_dir: Path) -> None:
    """시나리오 2 — 거부된 규칙 → 거부(승인 시도도, 실행 시도도)."""
    app, db_path, link, builder = _fresh_app(tmp_dir / "s2")
    r = call(app, "POST", "/api/v1/rules", json={"origin": "WIZARD", "draft_text": "거부 예정"})
    rule_id = r.json()["id"]

    rr = call(app, "POST", f"/api/v1/rules/{rule_id}/reject", json={"reason": "부적절한 조건"},
              headers={"X-User-Id": "demo-user-1"})
    check("거부 200", rr.status_code == 200, str(rr.status_code))

    install_id = _register_install(db_path, 3, 1, 0x85, builder)
    tx_before = int(link.stats()["tx"])
    ra = call(app, "POST", f"/api/v1/rules/{rule_id}/approve",
              json={"condition_expr": "x", "action": {"value": 1, "value_type": "UINT"},
                    "target_install_id": install_id}, headers={"X-User-Id": "demo-user-1"})
    _check_no_tx("거부된 규칙 승인 시도", link, tx_before)
    check("거부된 규칙 승인 시도 -> 409", ra.status_code == 409, str((ra.status_code, ra.text)))

    tx_before = int(link.stats()["tx"])
    re_ = call(app, "POST", f"/api/v1/rules/{rule_id}/execute")
    _check_no_tx("거부된 규칙 execute", link, tx_before)
    check("거부된 규칙 execute -> 409(여전히 미승인)", re_.status_code == 409, str(re_.status_code))


def scenario_approved_target_immutable(tmp_dir: Path) -> None:
    """시나리오 3 — 승인 후 대상(target_install_id) 변조 시도 → 거부.
    API 표면에는 애초에 '다른 대상으로 execute' 를 요청할 필드가 없다
    (execute 요청 본문 자체가 없다, API 명세서 §4.2) — 유일한 변조 경로는
    같은 규칙을 다른 대상으로 재승인하는 것뿐이고, 그것도 봉인돼 있다."""
    app, db_path, link, builder = _fresh_app(tmp_dir / "s3")
    install_a = _register_install(db_path, 3, 1, 0x85, builder)
    install_b = _register_install(db_path, 3, 2, 0x85, builder)

    r = call(app, "POST", "/api/v1/rules", json={"origin": "WIZARD", "draft_text": "대상 A"})
    rule_id = r.json()["id"]
    ra = call(app, "POST", f"/api/v1/rules/{rule_id}/approve",
              json={"condition_expr": "x", "action": {"value": 1, "value_type": "UINT"},
                    "target_install_id": install_a}, headers={"X-User-Id": "demo-user-1"})
    check("규칙을 대상 A 로 승인 200", ra.status_code == 200, str(ra.status_code))

    tx_before = int(link.stats()["tx"])
    ra2 = call(app, "POST", f"/api/v1/rules/{rule_id}/approve",
               json={"condition_expr": "x", "action": {"value": 1, "value_type": "UINT"},
                     "target_install_id": install_b}, headers={"X-User-Id": "demo-user-1"})
    _check_no_tx("승인 대상 변조 시도", link, tx_before)
    check("같은 규칙을 대상 B 로 재승인 -> 409(변조 거부)", ra2.status_code == 409, str(ra2.status_code))

    re_ = call(app, "POST", f"/api/v1/rules/{rule_id}/execute")
    check("execute 202", re_.status_code == 202, str((re_.status_code, re_.text)))
    check("실제 송신 대상이 A(원 승인 그대로)", re_.json()["install_id"] == install_a,
          str(re_.json().get("install_id")))


def scenario_control_action_extra_field_rejected(tmp_dir: Path) -> None:
    """시나리오 4 — action 에 install_id 를 몰래 실어도 거부(F-051)."""
    app, db_path, link, builder = _fresh_app(tmp_dir / "s4")
    install_id = _register_install(db_path, 3, 1, 0x85, builder)
    r = call(app, "POST", "/api/v1/rules", json={"origin": "WIZARD", "draft_text": "x"})
    rule_id = r.json()["id"]
    tx_before = int(link.stats()["tx"])
    ra = call(app, "POST", f"/api/v1/rules/{rule_id}/approve",
              json={"condition_expr": "x",
                    "action": {"value": 1, "value_type": "UINT", "install_id": "다른-장치"},
                    "target_install_id": install_id}, headers={"X-User-Id": "demo-user-1"})
    _check_no_tx("action 대상 은닉 승인", link, tx_before)
    check("action 에 install_id 를 넣으면 400(F-051)", ra.status_code == 400, str(ra.status_code))


def scenario_execute_no_body_field_accepted(tmp_dir: Path) -> None:
    """시나리오 5 — POST /rules/{id}/execute 는 요청 본문을 받지 않는다.
    본문을 보내도(악의적 시도) 무시되고 승인 스냅샷만 쓰인다는 것을,
    다른 대상 install_id 를 본문에 흘려보내 확인한다."""
    app, db_path, link, builder = _fresh_app(tmp_dir / "s5")
    install_a = _register_install(db_path, 3, 1, 0x85, builder)
    install_b = _register_install(db_path, 3, 2, 0x85, builder)
    r = call(app, "POST", "/api/v1/rules", json={"origin": "WIZARD", "draft_text": "x"})
    rule_id = r.json()["id"]
    call(app, "POST", f"/api/v1/rules/{rule_id}/approve",
         json={"condition_expr": "x", "action": {"value": 1, "value_type": "UINT"},
               "target_install_id": install_a}, headers={"X-User-Id": "demo-user-1"})

    # execute_rule() 핸들러는 body 파라미터를 아예 선언하지 않는다 — 보내도 무시된다.
    re_ = call(app, "POST", f"/api/v1/rules/{rule_id}/execute",
               json={"target_install_id": install_b, "action": {"value": 99, "value_type": "UINT"}})
    check("본문에 다른 대상을 실어도 202(무시됨)", re_.status_code == 202, str(re_.status_code))
    check("실제 대상은 여전히 승인된 A", re_.json()["install_id"] == install_a,
          str(re_.json().get("install_id")))
    check("실제 명령도 여전히 승인된 값(99 아님)", re_.json()["command"]["value"] == 1,
          str(re_.json().get("command")))


def scenario_manual_control_requires_known_user(tmp_dir: Path) -> None:
    """시나리오 6 — 수동 제어는 실재하는 사용자만 지시할 수 있다."""
    app, db_path, link, builder = _fresh_app(tmp_dir / "s6")
    install_id = _register_install(db_path, 5, 1, 0x83, builder)
    tx_before = int(link.stats()["tx"])
    r = call(app, "POST", "/api/v1/control",
             json={"install_id": install_id, "action": {"value": 1, "value_type": "UINT"}},
             headers={"X-User-Id": "ghost-user-unregistered"})
    _check_no_tx("미실재 사용자 수동제어", link, tx_before)
    check("미실재 사용자 수동제어 -> 400", r.status_code == 400, str(r.status_code))


def scenario_null_action_approval_rejected(tmp_dir: Path) -> None:
    """시나리오 7(F-192) — action=NULL(필드는 있지만 값이 null) 승인 시도는
    400 이어야 한다. F-039·F-091 계열 "필드가 있다"≠"값이 반드시 온다"
    회귀가 API 표면에 재발해도 이 시나리오가 직접 잡는다 — DB 트리거를
    거치지 않고 `_validate_control_action()` 을 HTTP 레벨에서 두드린다."""
    app, db_path, link, builder = _fresh_app(tmp_dir / "s7")
    install_id = _register_install(db_path, 3, 1, 0x85, builder)
    r = call(app, "POST", "/api/v1/rules", json={"origin": "WIZARD", "draft_text": "x"})
    rule_id = r.json()["id"]

    tx_before = int(link.stats()["tx"])
    ra = call(app, "POST", f"/api/v1/rules/{rule_id}/approve",
              json={"condition_expr": "x", "action": None, "target_install_id": install_id},
              headers={"X-User-Id": "demo-user-1"})
    _check_no_tx("action=NULL 승인", link, tx_before)
    check("action=NULL 승인 시도 -> 400", ra.status_code == 400, str((ra.status_code, ra.text)))

    rule = call(app, "GET", f"/api/v1/rules/{rule_id}").json()
    check("거부된 승인 시도가 규칙을 승인 상태로 만들지 않았다", rule.get("approved_at") is None, str(rule))

    tx_before = int(link.stats()["tx"])
    re_ = call(app, "POST", f"/api/v1/rules/{rule_id}/execute")
    _check_no_tx("action=NULL 뒤 미승인 execute", link, tx_before)
    check("승인되지 않았으므로 execute 도 여전히 409", re_.status_code == 409, str(re_.status_code))


def main() -> int:
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)
        print("[시나리오 1] 승인 없이 execute")
        scenario_unapproved_rule_blocked(tmp_dir)
        print("[시나리오 2] 거부된 규칙")
        scenario_rejected_rule_blocked(tmp_dir)
        print("[시나리오 3] 승인 후 대상 변조")
        scenario_approved_target_immutable(tmp_dir)
        print("[시나리오 4] action 에 대상 은닉(F-051)")
        scenario_control_action_extra_field_rejected(tmp_dir)
        print("[시나리오 5] execute 요청 본문 무시")
        scenario_execute_no_body_field_accepted(tmp_dir)
        print("[시나리오 6] 미실재 사용자 수동제어")
        scenario_manual_control_requires_known_user(tmp_dir)
        print("[시나리오 7] action=NULL 승인(F-192)")
        scenario_null_action_approval_rejected(tmp_dir)

    failed = [n for n, ok, _ in RESULTS if not ok]
    print()
    print(f"  {len(RESULTS) - len(failed)}/{len(RESULTS)} 통과")
    if failed:
        print("[FAIL] tools/gate_e2e.py")
        for n in failed:
            print(f"  - {n}")
        return 1
    print("[PASS] tools/gate_e2e.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
