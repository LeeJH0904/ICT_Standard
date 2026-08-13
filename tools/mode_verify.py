"""tools/mode_verify.py — 단계 4(`sim/`·전송 계층) 신설 검증기.

개발 착수 지시서 §3.6 이 요구하는 4항목:
  ① `socat` 등 외부 도구 호출 0 (CLAUDE.md §1-8)
  ② replay 입력이 `dir="rx"` 만 주입 (F-042)
  ③ 주입 벡터 `X01`~`X08` 이 골든과 바이트 동일 (시연 시나리오 §3.1)
  ④ 네트워크 없이 동작 (loopback `127.0.0.1` 만 사용, 외부 호스트 문자열 없음)
  ⑤ simulate 모드가 신선한 DB에서 실제로 장치·텔레메트리·장치상태를 채운다
     (F-198 회귀 가드 — "하드웨어 없이 검증 가능"은 재현 경로가 빈 화면이면
     성립하지 않는다)

"실행 가능한 것은 직접 실행 결과로 판정한다"(CLAUDE.md §6.2, F-136/F-142
가 남긴 교훈) — ①·④는 정적 스캔이지만, ②·③·⑤는 `sim/replayer.py`·
`sim/inject.py`·`sim/virtual_node.py`를 실제로 불러 동작 결과를 본다.

실행: python tools/mode_verify.py   (저장소 루트에서)
종료 코드: 전부 통과 0 / 하나라도 실패 1
"""
from __future__ import annotations

import json
import re
import socket
import sys
import threading
import time
from pathlib import Path

if sys.stdout.encoding and sys.stdout.encoding.lower().replace("-", "") != "utf8":
    try:
        sys.stdout.reconfigure(errors="replace")
    except Exception:
        pass

REPO_ROOT = Path(__file__).resolve().parent.parent
PROJECT_CODE = REPO_ROOT / "project_code"
SIM_DIR = PROJECT_CODE / "sim"
RUN_PY = PROJECT_CODE / "run.py"

sys.path.insert(0, str(PROJECT_CODE))

R: list[tuple[bool, str, str]] = []


def t(name: str, ok: bool, note: str = "") -> None:
    R.append((bool(ok), name, note))


# ═══════════════════════════════════════════════════════════════
#  ① socat 등 외부 도구 호출 0 (CLAUDE.md §1-8)
# ═══════════════════════════════════════════════════════════════
def check_no_external_tools() -> None:
    targets = list(SIM_DIR.glob("*.py")) + [RUN_PY]
    hits: list[str] = []
    for p in targets:
        text = p.read_text(encoding="utf-8")
        for m in re.finditer(r"socat|subprocess\.(run|Popen|call)", text):
            # subprocess 호출 자체는 금지가 아니다(예: xcodec_verify.py 는
            # 빌드에 쓴다) — 이 파일들(sim/·run.py)에는 subprocess 호출이
            # 전혀 없어야 한다는 것이 확인 대상이다.
            hits.append(f"{p.relative_to(REPO_ROOT)}:{text.count(chr(10), 0, m.start()) + 1}: {m.group(0)}")
    t("sim/*.py · run.py 에 socat/subprocess 호출 0건 (CLAUDE.md §1-8)", not hits, "; ".join(hits[:5]))


# ═══════════════════════════════════════════════════════════════
#  ④ 네트워크 없이 동작 — loopback 이외 호스트 문자열이 없는가 (정적 스캔)
# ═══════════════════════════════════════════════════════════════
def check_loopback_only() -> None:
    targets = list(SIM_DIR.glob("*.py")) + [RUN_PY]
    # IPv4 자리표시(문서/주석의 예시)는 제외 — 실제 bind/connect 인자로
    # 쓰인 호스트 리터럴만 본다. 이 프로젝트의 관례는 기본값을
    # "127.0.0.1" 로 두는 것이므로, 그 외의 non-loopback IPv4/도메인
    # 리터럴이 host= 기본값·상수로 등장하면 위반이다.
    bad: list[str] = []
    host_pattern = re.compile(r'host\s*[:=]\s*"([^"]+)"')
    for p in targets:
        text = p.read_text(encoding="utf-8")
        for m in host_pattern.finditer(text):
            host = m.group(1)
            if host not in ("127.0.0.1", "localhost"):
                bad.append(f"{p.relative_to(REPO_ROOT)}: host={host!r}")
    t("sim/*.py · run.py 의 host 기본값이 loopback(127.0.0.1) 뿐이다", not bad, "; ".join(bad[:5]))


def check_simulate_runs_without_network() -> None:
    """`socket.AF_INET`로 `127.0.0.1`에 실제 bind·accept·connect 왕복이
    되는지 직접 실행해 확인한다 — 외부 네트워크 인터페이스가 없어도
    (예: 심사 환경이 오프라인이어도) 동작해야 한다는 것의 실증."""
    from sim.virtual_node import VirtualNodeServer
    from siap.link import SiapNodeLink

    srv = VirtualNodeServer(port=0, control_port=None,
                             device_value_period=0.3, keep_alive_period=10.0,
                             late_node_delay=100.0)
    # port=0 이면 OS 가 임의 포트를 배정한다 — 실제 배정 포트를 알아야
    # 클라이언트가 접속할 수 있다.
    srv._srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv._srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv._srv.bind(("127.0.0.1", 0))
    port = srv._srv.getsockname()[1]
    srv._srv.listen(1)
    srv._srv.settimeout(0.2)
    th = threading.Thread(target=srv._accept_loop, name="modeverify-vnode", daemon=True)
    th.start()
    srv._threads.append(th)

    link = SiapNodeLink(gcg_id=1)
    ok = False
    note = ""
    try:
        link.start("simulate", proto_mode="strict", host="127.0.0.1", socket_port=port)
        deadline = time.monotonic() + 3.0
        while time.monotonic() < deadline:
            if len(link.registry()) >= 3:
                ok = True
                break
            time.sleep(0.05)
        if not ok:
            note = f"3초 안에 노드 3대 등록 실패 (실제 {len(link.registry())}개)"
    finally:
        link.stop()
        srv.stop()
    t("simulate 모드 — loopback TCP 왕복으로 노드 3대 등록 (외부 네트워크 불필요)", ok, note)


# ═══════════════════════════════════════════════════════════════
#  ② replay 입력이 dir="rx" 만 주입 (F-042)
# ═══════════════════════════════════════════════════════════════
def check_replay_injects_rx_only(tmp_dir: Path) -> None:
    from sim import _wire as wire
    from sim.replayer import Replayer

    rx_frame = wire.build_req_set_connection(msg_id=1, gcg_id=1, node_id=3)
    tx_frame = wire.build_noti_keep_alive(msg_id=2, gcg_id=1, node_id=3)   # 주입되면 안 됨

    log = tmp_dir / "mode_verify_session.jsonl"
    with open(log, "w", encoding="utf-8") as f:
        f.write(json.dumps({"t": 0.0, "dir": "rx", "hex": rx_frame.hex()}) + "\n")
        f.write(json.dumps({"t": 0.01, "dir": "tx", "hex": tx_frame.hex()}) + "\n")

    r = Replayer(log, port=0, speed=50.0)
    r._srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    r._srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    r._srv.bind(("127.0.0.1", 0))
    port = r._srv.getsockname()[1]
    r._srv.listen(1)
    r._srv.settimeout(0.2)
    th = threading.Thread(target=r._accept_and_play, name="modeverify-replayer", daemon=True)
    th.start()
    r._thread = th

    client = socket.create_connection(("127.0.0.1", port), timeout=2.0)
    client.settimeout(1.5)
    received = b""
    deadline = time.monotonic() + 1.5
    while time.monotonic() < deadline:
        try:
            chunk = client.recv(4096)
        except socket.timeout:
            break
        if not chunk:
            break
        received += chunk
    client.close()
    r.stop()

    t("replay — dir=\"tx\" 레코드는 절대 소켓에 주입되지 않는다 (F-042)",
      tx_frame not in received, f"실제 수신: {received.hex()}")
    t("replay — dir=\"rx\" 레코드만 정확히 주입된다 (F-042)",
      received == rx_frame, f"실제 수신: {received.hex()}, 기대: {rx_frame.hex()}")
    t("replay — skipped_tx 통계가 tx 제외 사실을 기록한다", r.stats["skipped_tx"] == 1,
      f"실제 {r.stats}")


# ═══════════════════════════════════════════════════════════════
#  ③ 주입 벡터 X01~X08 이 골든과 바이트 동일 + 실제 송신 경로 + 판정 결과
# ═══════════════════════════════════════════════════════════════
def check_injection_vectors_match_golden() -> None:
    """F-147 이전에는 `inject.vector_bytes()`를 같은 `inject.GOLDEN_PATH`에서
    다시 읽은 문자열과만 비교했다 — 자기 자신과의 비교라 `inject.inject()`
    실제 송신 함수도, 제어 채널도, 디코더도 전혀 거치지 않았다. 바이트
    변조·Node ID 불일치(F-145)·순차 주입 재동기 유실(F-146) 이 셋 다
    있어도 이 검사가 8/8 로 거짓 통과했다."""
    from sim import inject

    with open(inject.GOLDEN_PATH, encoding="utf-8") as f:
        golden = {v["id"]: v for v in (json.loads(line) for line in f if line.strip())}

    mismatches: list[str] = []
    for vid in sorted(inject.ALLOWED_VECTORS):
        expect = golden[vid]["hex"].upper()
        actual = inject.vector_bytes(vid).hex().upper()
        if actual != expect:
            mismatches.append(f"{vid}: 실제={actual} 기대={expect}")
    t(f"주입 벡터 {len(inject.ALLOWED_VECTORS)}종(X01~X08)이 golden.jsonl 과 바이트 동일",
      not mismatches, "; ".join(mismatches))

    # CLAUDE.md §6.3 표 — X01~X07 은 위반(judgement=violation)이지만
    # X08(NEC=배터리 저전력)은 위반이 아니라 judgement=alert 다(F-060,
    # "정상 NEC 알림을 위반으로 표시하면 alert·ACK 경로가 막힌다"). 목록
    # 자체를 정본으로 삼지 않고 골든과 다시 대조한다(F-080 독립 입력).
    expect_judgement = {f"X0{i}": "violation" for i in range(1, 8)}
    expect_judgement["X08"] = "alert"
    judgement_mismatches = [
        f"{vid}: judgement={golden[vid]['judgement']} 기대={expect}"
        for vid, expect in expect_judgement.items() if golden[vid]["judgement"] != expect
    ]
    t("X01~X07 은 judgement=violation, X08 은 judgement=alert (F-060)",
      not judgement_mismatches, "; ".join(judgement_mismatches))


def check_injection_actual_wire_bytes() -> None:
    """F-150 — F-147 이 추가한 live 판정 검사는 S4-b 5종의 `Frame.violations`
    코드만 본다. 판정을 결정하지 않는 자리(예: X06 마지막 바이트는 Value
    의 LSB 이지 Value Type 이 아니다)가 변조돼도 판정이 안 바뀌어 그 검사를
    통과한다 — 결함 주입으로 실측(마지막 바이트 XOR 는 통과, Version 바이트
    XOR 는 실패). 그리고 X02·X04·X08 은 live 판정 검사 대상에도 없다.

    시연 시나리오 §3.1 이 요구하는 것은 "판정이 맞다"가 아니라 "**영상 속
    hex 와 제출 golden.jsonl 의 hex 가 같다**"이다 — 이건 판정 결과가 아니라
    실제로 소켓에 나간 바이트 그 자체를 캡처해서 대조해야만 검증된다.
    `VirtualNodeServer`/`SiapNodeLink`/디코더를 전혀 거치지 않고,
    `inject.inject()`가 맨 소켓에 쓰는 바이트를 서버 쪽에서 직접 받아
    golden.jsonl 원본과 정확히 일치하는지 8종 전부 확인한다."""
    from sim import inject

    with open(inject.GOLDEN_PATH, encoding="utf-8") as f:
        golden = {v["id"]: v for v in (json.loads(line) for line in f if line.strip())}

    mismatches: list[str] = []
    for vid in sorted(inject.ALLOWED_VECTORS):
        expect = bytes.fromhex(golden[vid]["hex"])

        srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        srv.bind(("127.0.0.1", 0))
        port = srv.getsockname()[1]
        srv.listen(1)
        srv.settimeout(2.0)

        received = bytearray()

        def server(expected_len: int = len(expect)) -> None:
            conn, _ = srv.accept()
            conn.settimeout(2.0)
            try:
                while len(received) < expected_len:
                    chunk = conn.recv(4096)
                    if not chunk:
                        break
                    received.extend(chunk)
            except socket.timeout:
                pass
            finally:
                conn.close()

        th = threading.Thread(target=server, name=f"modeverify-wirecap-{vid}", daemon=True)
        th.start()

        client = socket.create_connection(("127.0.0.1", port), timeout=2.0)
        sent = inject.inject(vid, client)
        client.close()
        th.join(timeout=3.0)
        srv.close()

        actual = bytes(received)
        if sent != expect or actual != expect:
            mismatches.append(
                f"{vid}: inject() 반환={sent.hex().upper()} 실제 수신={actual.hex().upper()} "
                f"기대={expect.hex().upper()}"
            )
    t(f"주입 벡터 {len(inject.ALLOWED_VECTORS)}종 — inject() 가 실제 소켓에 쓰는 바이트가 "
      "golden.jsonl 과 정확히 같다 (F-150)", not mismatches, "; ".join(mismatches))


def check_injection_wire_path_and_classification() -> None:
    """F-147 — `sim.inject.inject()` → 제어 채널 → 실제 게이트웨이 소켓 →
    `SiapNodeLink`/`Decoder` 전체 경로를 살아있는 simulate 링크로 왕복시켜,
    시연 시나리오 §3.1 S4-b 순서(X01→X03→X05→X06→X07)가 각각 올바른 판정
    코드를 낳는지 직접 확인한다. `inject.vector_bytes()`와의 자기 비교가
    아니라 `link.recv()`로 실제로 나온 `Frame.violations`를 본다 — F-145
    (Node ID 불일치)·F-146(연속 주입 재동기 유실) 두 결함 모두 이 경로가
    실제로 동작해야만 잡힌다."""
    from sim.virtual_node import VirtualNodeServer
    from siap.link import SiapNodeLink

    srv = VirtualNodeServer(port=0, control_port=0,
                             device_value_period=5.0, keep_alive_period=10.0,
                             late_node_delay=100.0)
    srv.start()
    port = srv._srv.getsockname()[1]
    ctrl_port = srv._ctrl_srv.getsockname()[1]

    link = SiapNodeLink(gcg_id=1)
    frames: list = []
    ok = False
    note = ""
    try:
        link.start("simulate", proto_mode="strict", host="127.0.0.1", socket_port=port)

        def collect() -> None:
            for f in link.recv():
                frames.append(f)
        th = threading.Thread(target=collect, name="modeverify-collect", daemon=True)
        th.start()

        deadline = time.monotonic() + 3.0
        while time.monotonic() < deadline and len(link.registry()) < 3:
            time.sleep(0.05)

        ctrl = socket.create_connection(("127.0.0.1", ctrl_port), timeout=2.0)
        ctrl.settimeout(2.0)
        expect = [
            ("X01", "INVALID_VERSION"),
            ("X03", "INVALID_FORMAT"),
            ("X05", "INVALID_TRANSMISSION_TYPE"),
            ("X06", "INVALID_DATA_TYPE"),
            ("X07", "INVALID_DATA_SUBTYPE"),
        ]
        for vid, _ in expect:
            ctrl.sendall(f"INJECT {vid}\n".encode("ascii"))
            reply = ctrl.recv(200)
            if not reply.startswith(b"OK"):
                note = f"{vid} 주입 응답 실패: {reply!r}"
                raise RuntimeError(note)
            time.sleep(0.3)
        ctrl.close()

        time.sleep(0.5)
        by_id = {f.header.msg_id: f for f in frames}
        mismatches = []
        for vid, code in expect:
            msg_id = golden_msg_id(vid)
            f = by_id.get(msg_id)
            if f is None:
                mismatches.append(f"{vid}(msg_id={msg_id}) 프레임 자체가 도달하지 않음")
                continue
            actual = [v.code_name for v in f.violations]
            if actual != [code]:
                mismatches.append(f"{vid}: 실제={actual} 기대=['{code}']")
        ok = not mismatches
        note = "; ".join(mismatches)
    finally:
        link.stop()
        srv.stop()
    t("실제 inject() 송신 → simulate 링크 왕복 → S4-b 5종 판정 일치 (F-147)", ok, note)


# ═══════════════════════════════════════════════════════════════
#  F-198 — 기본 재현 경로(simulate)가 신선한 DB에서 실제로 장치·텔레메트리·
#  장치상태를 채우는가. "하드웨어 없이 표준 준수를 검증할 수 있다"
#  (CLAUDE.md §7)는 재현 경로가 실제로 데이터를 만들어야 성립한다 — F-198
#  은 REQ_SET_CONNECTION 이 페이로드가 없어(LAYOUT (0,0)) 이 데모가 등록된
#  노드는 있는데 장치는 하나도 없는 빈 화면만 보여줬던 결함이다(원 재현:
#  /api/v1/nodes/{id}/devices · /telemetry · /device-states 전부 빈 배열).
#  settings.html·rules.html 의 장치 선택 드롭다운은 모두 이 DB 행에서
#  나오므로("설정 대상"·"수동 제어 대상"), device_install_info 가 채워짐을
#  확인하는 것이 곧 그 UI 대상이 비지 않음을 보장한다 — 별도로 uvicorn 을
#  띄워 HTTP 로 다시 확인하지 않는다(느리고 중복).
# ═══════════════════════════════════════════════════════════════
def check_simulate_populates_devices_and_telemetry(tmp_dir: Path) -> None:
    from backend import db as backend_db
    from backend import ingest as backend_ingest
    from sim.virtual_node import VirtualNodeServer
    from siap.link import SiapNodeLink

    db_path = tmp_dir / "mode_verify_devices.db"
    backend_db.init_db(db_path).close()

    # run.py::_make_on_frame() 과 같은 지연 연결 패턴(F-160 — SQLite 연결은
    # 연 스레드 안에서만 쓸 수 있다)이지만, 연결을 이 스코프의 변수에 담아
    # 검사가 끝나면 명시적으로 닫는다 — run.py 는 프로세스 종료로 회수하면
    # 되지만, 이 검증기는 같은 프로세스가 계속 돌며 tempdir 를 정리해야
    # 해서 열린 채로 두면 Windows 에서 파일 잠금으로 정리가 실패한다.
    state: dict = {}

    def on_frame(frame) -> None:
        conn = state.get("conn")
        if conn is None:
            conn = backend_db.connect(db_path)
            state["conn"] = conn
        backend_ingest.handle(frame, conn)

    srv = VirtualNodeServer(port=0, control_port=0,
                             device_value_period=0.5, keep_alive_period=10.0,
                             late_node_delay=100.0)
    srv.start()
    port = srv._srv.getsockname()[1]

    link = SiapNodeLink(gcg_id=1)
    ok = False
    devices = telemetry = states = 0
    try:
        link.start("simulate", proto_mode="strict", host="127.0.0.1", socket_port=port,
                   on_frame=on_frame)
        deadline = time.monotonic() + 8.0
        while time.monotonic() < deadline:
            probe = backend_db.connect(db_path)
            try:
                devices = probe.execute("SELECT COUNT(*) FROM device_install_info").fetchone()[0]
                telemetry = probe.execute("SELECT COUNT(*) FROM env_measurement").fetchone()[0]
                states = probe.execute("SELECT COUNT(*) FROM device_state_data").fetchone()[0]
            finally:
                probe.close()
            # 기본 노드 3대(온도 센서 2·습도 센서 1·관수밸브 1 = 장치 4개)가
            # 전부 등록되고, 센서·액추에이터 각각 값이 최소 1건 이상 와야
            # "빈 화면"이 아니다.
            if devices >= 4 and telemetry >= 1 and states >= 1:
                ok = True
                break
            time.sleep(0.2)
    finally:
        link.stop()      # join()으로 SIAP I/O 스레드가 완전히 멎을 때까지 기다린다
        srv.stop()
        conn = state.get("conn")
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass      # 이미 멎은 스레드가 연 연결 — 닫기 실패는 무시(정리는 tempdir 쪽이 흡수)
    note = "" if ok else f"8초 안에 채워지지 않음 (devices={devices} telemetry={telemetry} states={states})"
    t("simulate 모드 — 신선한 DB에서 장치·텔레메트리·장치상태가 실제로 채워진다 (F-198)", ok, note)


def golden_msg_id(vector_id: str) -> int:
    from sim import inject
    with open(inject.GOLDEN_PATH, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            v = json.loads(line)
            if v["id"] == vector_id:
                return v["header"]["Message Identifier"]
    raise KeyError(vector_id)


def main() -> int:
    import tempfile

    check_no_external_tools()
    check_loopback_only()
    check_simulate_runs_without_network()
    with tempfile.TemporaryDirectory() as td:
        check_replay_injects_rx_only(Path(td))
    # ignore_cleanup_errors — Windows 에서 SQLite 파일 핸들이 다른 스레드에
    # 속해 정리 시점에 아직 완전히 풀리지 않을 수 있다(F-160 과 같은 종류의
    # 스레드 경계 문제, 검사 자체의 정확성과는 무관).
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as td:
        check_simulate_populates_devices_and_telemetry(Path(td))
    check_injection_vectors_match_golden()
    check_injection_actual_wire_bytes()
    check_injection_wire_path_and_classification()

    w = max(len(n) for _, n, _ in R)
    print("단계 4 sim/ · 전송 계층 검증 (개발 착수 지시서 §3.6)\n")
    for ok, n, note in R:
        print(f"  {'PASS' if ok else 'FAIL'}  {n:<{w}}  {note}")
    p = sum(1 for o, *_ in R if o)
    print(f"\n  {p}/{len(R)} 통과")
    return 0 if p == len(R) else 1


if __name__ == "__main__":
    sys.exit(main())
