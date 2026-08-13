#!/usr/bin/env python3
"""tools/run_live_verify.py — `run.py --serve`가 실제로 REST API 서버를
띄우는가(F-188).

단계 6의 기존 출구 명령(`pytest`·`route_verify`·`gate_e2e`·`nodetype_verify`)
은 전부 `backend.api.create_app()`이 만든 앱 객체를 직접(ASGI로) 두드린다
— `run.py` 자신이 그 앱을 실제 프로세스로 기동하는지는 아무도 보지
않았다(F-188 재현: `python run.py --mode simulate`를 실행한 뒤 다른
터미널에서 health 를 두드리면 연결이 거부됐다). 이 검증기는 `run.py`를
**실제 서브프로세스**로 띄우고 HTTP 로 두드린다 — 단위테스트가 못 보는
프로세스 기동 자체를 본다(db_live_verify.py·mode_verify.py와 같은 부류).

실행: python tools/run_live_verify.py   (저장소 루트에서)
종료 코드: 통과 0 / 실패 1
"""
from __future__ import annotations

import json
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

if sys.stdout.encoding and sys.stdout.encoding.lower().replace("-", "") != "utf8":
    try:
        sys.stdout.reconfigure(errors="replace")
    except Exception:
        pass

REPO_ROOT = Path(__file__).resolve().parent.parent
PROJECT_CODE = REPO_ROOT / "project_code"
RUN_PY = PROJECT_CODE / "run.py"

RESULTS: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    RESULTS.append((name, ok, detail))
    mark = "OK" if ok else "FAIL"
    print(f"  [{mark}] {name}" + (f"  {detail}" if detail and not ok else ""))


def _free_port() -> int:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def _wait_health(http_port: int, timeout: float = 10.0) -> dict | None:
    deadline = time.monotonic() + timeout
    url = f"http://127.0.0.1:{http_port}/api/v1/health"
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=1.0) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except (urllib.error.URLError, ConnectionError, TimeoutError, OSError):
            time.sleep(0.2)
    return None


def _post(url: str, body: dict, headers: dict) -> tuple[int, dict]:
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST",
                                  headers={"Content-Type": "application/json", **headers})
    try:
        with urllib.request.urlopen(req, timeout=3.0) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode("utf-8"))


def _run_mode(mode: str, tmp_dir: Path) -> None:
    http_port, socket_port, control_port = _free_port(), _free_port(), _free_port()
    db_path = tmp_dir / f"{mode}.db"
    args = [sys.executable, str(RUN_PY), "--mode", mode, "--serve",
            "--http-port", str(http_port), "--db", str(db_path), "--socket-port", str(socket_port)]
    if mode == "simulate":
        args += ["--control-port", str(control_port)]

    proc = subprocess.Popen(args, cwd=str(PROJECT_CODE), stdout=subprocess.PIPE,
                             stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace")
    try:
        health = _wait_health(http_port)
        check(f"[{mode}] --serve 가 REST API 를 실제로 띄운다 (F-188)", health is not None,
              "health 응답 없음(타임아웃) — 프로세스 출력: " + (proc.stdout.read(2000) if proc.poll() is not None else "(아직 실행 중)"))
        if health is not None:
            check(f"[{mode}] health.run_mode 일치", health.get("run_mode") == mode, str(health))

        if health is None:
            # 서버가 뜨지 않았으니 뒤이은 HTTP 호출도 전부 실패할 게 뻔하다 —
            # 트레이스백을 쏟는 대신 실패로 명시하고 다음 모드로 넘어간다.
            check(f"[{mode}] POST /sim/inject (건너뜀 — 서버가 뜨지 않음)", False,
                  "health 실패로 이 검사는 건너뛴다")
        elif mode == "simulate":
            status, body = _post(f"http://127.0.0.1:{http_port}/api/v1/sim/inject",
                                  {"vector_id": "X01"}, headers={"X-User-Id": "demo-user-1"})
            ok = (status == 202 and body.get("judgement") == "violation"
                  and any(v.get("code_name") == "INVALID_VERSION" for v in body.get("violations", [])))
            check("[simulate] POST /sim/inject 가 골든 벡터 X01 을 실제로 주입해 INVALID_VERSION 판정",
                  ok, str((status, body)))
        elif mode == "replay":
            status, body = _post(f"http://127.0.0.1:{http_port}/api/v1/sim/inject",
                                  {"vector_id": "X01"}, headers={"X-User-Id": "demo-user-1"})
            check("[replay] POST /sim/inject 는 라이브 주입 채널이 없어 409(정직한 거부)",
                  status == 409, str((status, body)))
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5.0)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=5.0)


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)
        print("[simulate --serve]")
        _run_mode("simulate", tmp_dir)
        print("[replay --serve]")
        _run_mode("replay", tmp_dir)

    failed = [n for n, ok, _ in RESULTS if not ok]
    print()
    print(f"  {len(RESULTS) - len(failed)}/{len(RESULTS)} 통과")
    if failed:
        print("[FAIL] tools/run_live_verify.py")
        for n in failed:
            print(f"  - {n}")
        return 1
    print("[PASS] tools/run_live_verify.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
