"""진입점 — SiapLink 호출만 (CLAUDE.md §2).

아키텍처 설계서 §9.1 기동 인자 · §9.2 기동 순서를 따른다.

F-160 — §9.2 의 5단계 중 "2. DB 준비"는 원래 단계 5(`backend/`)가 채우기로
한 항목이었다(이 문서 당초 서술). `backend/`가 실제로 생긴 뒤에도 이
파일이 갱신되지 않아, 실행 경로가 여전히 DB를 열지도 `on_frame`을 연결하지도
않은 채 남아 있었다 — `ingest.py`가 완성돼도 실제로 호출되지 않으면
"정상 NEC → alert 저장 + ACK 회신"(F-060) 같은 주장이 실행 경로에서
성립하지 않는다. 이번 수정으로 "2. DB 준비"(파일 없으면 `init_db`, 있으면
`connect`, `_prepare_db_path()`)와 `on_frame` 주입(`_make_on_frame()`)을
세 모드 함수에 모두 채운다.

F-188 — "5. uvicorn 기동"이 단계 6(`services/`·`api.py`) 완성 뒤에도
결선되지 않아, `python run.py --mode simulate`를 실행해도 HTTP 서버가
뜨지 않았다(관찰 시간만 기다리다 정상 종료). `--serve` 플래그로 분리했다
— 기본(플래그 없음)은 이전과 동일하게 관찰 시간만큼 기다리다 요약을
찍고 종료한다(개발 착수 지시서 §3.6 출구①·②, 회귀 없음). `--serve`를
주면 `backend.api.create_app()`으로 앱을 만들고 `uvicorn.run()`을 불러
Ctrl-C 로 멈출 때까지 떠 있는다 — `web/`(단계 7)가 실제로 두드릴 서버가
이 경로에서 나온다. `simulate` 모드는 `sim/inject.py`를 감싼 `inject_fn`
도 함께 준다(`POST /api/v1/sim/inject`, F-084) — `virtual_node.py`의
로컬 제어 채널로 골든 벡터 원본 바이트를 흘려보낸다.
F-154 — `on_frame`은 부수효과(DB 반영) 전용이다. 회신은 `on_frame`
이 설정되어도 여전히 `_default_reply()`가 만든다(표준 해석은 프로토콜
계층에만, CLAUDE.md §3.4).
F-167 — `on_frame`에 `backend.ingest.bind(conn)`을 직접 꽂지 않는다.
`bind(conn)`은 **호출자가 넘긴 연결을 그대로 클로저에 가둘 뿐**이라, 그
연결을 만든 스레드가 아닌 곳(SIAP I/O 스레드)에서 호출되면 `sqlite3.
ProgrammingError`로 죽는다(아키텍처 설계서 §4.1 "스레드별 연결",
`check_same_thread=False` 금지 — F-160 재현 실측). 이 파일의
`_make_on_frame(db_path)`는 그 대신 **경로만** 받아 I/O 스레드 안에서
첫 호출 시점에 지연 연결한다. `bind(conn)`은 스레드 경계가 이미 보장된
호출자(테스트, 단일 스레드 스크립트)를 위해 `backend/ingest.py`에 남아 있다.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

# CLAUDE.md §3.5 F-045 — 검증기·진입점 콘솔 출력은 CP949 표현 가능 범위
# 밖의 문자(em dash 등)에도 죽지 않아야 한다. tools/*_verify.py 전반과
# 같은 가드.
if sys.stdout.encoding and sys.stdout.encoding.lower().replace("-", "") != "utf8":
    try:
        sys.stdout.reconfigure(errors="replace")
    except Exception:
        pass

REPO_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(REPO_ROOT))

from siap.link import SiapNodeLink                    # noqa: E402


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="run.py",
        description="TTAK.KO-10.0943 / 1369-Part1 / 0937 참조 구현 진입점",
    )
    parser.add_argument(
        "--mode",
        choices=["hardware", "replay", "simulate"],
        default="replay",
        help="전송 계층 모드 (아키텍처 설계서 §5.1). 기본값은 심사자 기본 경로인 replay",
    )
    parser.add_argument("--port", default=None, help="hardware 모드의 시리얼 포트")
    parser.add_argument("--log", default=None, help="replay 모드가 재생할 로그 (project_code/logs/*.jsonl)")
    parser.add_argument("--speed", type=float, default=1.0, help="replay 재생 배속")
    parser.add_argument(
        "--proto",
        choices=["strict", "extended"],
        default="strict",
        help="strict(기본) / extended — CLAUDE.md §6.2 골든 벡터 분리와 대응",
    )
    parser.add_argument(
        "--duration", type=float, default=None,
        help="simulate 모드에서 관찰할 시간(초). 기본 10초. replay 는 로그 재생 완료를 기다린다",
    )
    parser.add_argument("--socket-port", type=int, default=None,
                         help="replay/simulate 서버가 열 TCP 포트 (기본은 §5.1 표: replay=5555, simulate=5556)")
    parser.add_argument("--control-port", type=int, default=5557,
                         help="simulate 모드 가상 노드의 주입 제어 채널 포트 (sim/inject.py 용)")
    parser.add_argument("--capture", default=None,
                        help="실측 로그 캡처 경로 (rx/tx 프레임을 logs/*.jsonl 포맷으로 기록). "
                             "hardware·simulate 모드 전용. 단계 8 출구 ③")
    parser.add_argument("--db", default=None,
                         help="DB 파일 경로 (기본: project_code/backend/runtime.db). "
                              "F-160 — §9.2 '2. DB 준비': 없으면 schema.sql+seed 로 새로 만들고, 있으면 그대로 연다")
    parser.add_argument("--serve", action="store_true",
                         help="F-188 — §9.2 '5. uvicorn 기동'. 주면 REST API를 띄우고 Ctrl-C "
                              "까지 떠 있는다(web/ 가 실제로 두드릴 서버). 주지 않으면 기존과 "
                              "동일하게 --duration 만큼만 관찰하고 종료한다")
    parser.add_argument("--http-port", type=int, default=8000, help="--serve 의 REST API 포트")
    return parser


def _prepare_db_path(args: argparse.Namespace) -> Path:
    """F-160 — 아키텍처 설계서 §9.2 '2. DB 준비'. 매 실행마다 호출한다
    ("2번이 매번 실행된다" — 심사자가 DB 파일을 지우거나 처음 실행해도
    동작해야 한다). 파일이 이미 있으면 스키마를 다시 적용하지 않는다 —
    `init_db()`를 기존 파일에 또 돌리면 시드가 중복 INSERT 된다.

    이 초기화용 연결은 메인 스레드에서 열고 스키마·시드 적용 직후 바로
    닫는다. 프레임 처리에 실제로 쓸 연결은 SIAP I/O 스레드 안에서 따로
    연다(`_make_on_frame()`) — SQLite 연결은 만든 스레드에서만 쓸 수 있어
    (아키텍처 설계서 §4.1 "스레드별 연결", `check_same_thread=False` 금지),
    메인 스레드에서 연 연결을 I/O 스레드로 넘기면 첫 프레임 처리에서
    `ProgrammingError: SQLite objects created in a thread can only be
    used in that same thread`로 죽는다(F-160 재현 실측)."""
    from backend import db as backend_db

    db_path = Path(args.db) if args.db else REPO_ROOT / "backend" / "runtime.db"
    if not db_path.is_absolute():
        db_path = REPO_ROOT / db_path
    if not db_path.exists():
        backend_db.init_db(db_path).close()
        print(_cp949_safe(f"[run.py] DB 신규 생성 — {db_path}"))
    else:
        print(_cp949_safe(f"[run.py] DB 기존 파일 연결 — {db_path}"))
    return db_path


def _make_on_frame(db_path: Path):
    """F-160 — `on_frame`은 SIAP I/O 스레드 안에서 호출된다(`link._io_loop`).
    그 첫 호출 시점에 **그 스레드 안에서** 연결을 연다 — `bind()`(backend/
    ingest.py)를 메인 스레드에서 미리 연 연결과 함께 쓰면 위 스레드 위반이
    난다. 이 연결은 명시적으로 닫지 않는다: `run.py`는 프로세스 종료로
    끝나고, 닫으려면 또 다른 스레드 경계 문제(스레드 종료 후 메인 스레드가
    닫으려 하면 같은 `ProgrammingError`)를 만든다 — OS가 프로세스 종료 시
    파일 핸들을 회수한다."""
    from backend import db as backend_db
    from backend import ingest as backend_ingest

    state: dict = {}

    def _on_frame(frame):
        conn = state.get("conn")
        if conn is None:
            conn = backend_db.connect(db_path)
            state["conn"] = conn
        backend_ingest.handle(frame, conn)

    return _on_frame


def _make_inject_fn(control_port: int):
    """F-188 — `POST /api/v1/sim/inject`(F-084)가 부를 콜백. `simulate`
    모드에서만 의미가 있다 — `virtual_node.py`의 로컬 제어 채널에
    `INJECT <id>`를 보내 실제로 골든 벡터 원본 바이트를 게이트웨이로
    흘려보내고, 반환값은 `sim.inject.vector_bytes()`가 주는 같은 원본
    바이트다(`virtual_node.py` 자신도 이 함수로 바이트를 얻으므로 둘은
    항상 같다 — "영상 속 hex == golden.jsonl 의 hex"라는 판정 근거가
    이 경로에서도 그대로 성립한다)."""
    from sim import inject as sim_inject

    def _inject(vector_id: str) -> bytes:
        sim_inject._cli_inject(vector_id, "127.0.0.1", control_port)
        return sim_inject.vector_bytes(vector_id)

    return _inject


def _ensure_public_data_baseline(db_path: Path) -> None:
    """rules 화면 ① 공공데이터 표가 첫 화면부터 비어 있지 않도록, 레코드가
    하나도 없으면 시작 시 예보를 1건 수집해 둔다(KMA_API_KEY 없으면 목업 폴백).
    이미 있으면(재시작·기존 DB) 아무것도 하지 않아 재시작마다 쌓이지 않는다.
    스레드 기동 후 API 가 뜨기 직전 한 번만 실행되는 seed 성격의 쓰기다."""
    from backend import db as backend_db
    from backend.services import dms

    conn = backend_db.connect(db_path)
    try:
        _, total = dms.list_records(conn, limit=1)
        if total == 0:
            _, fallback = dms.fetch_public_data(conn)
            print(_cp949_safe(f"[run.py] 공공데이터 기본 1건 수집 ({'목업' if fallback else '기상청 실데이터'})"))
    except Exception as e:   # noqa: BLE001 — 기본 수집 실패가 서버 기동을 막지 않게 한다
        print(_cp949_safe(f"[run.py] 공공데이터 기본 수집 건너뜀: {e}"))
    finally:
        conn.close()


def _serve_app(*, db_path: Path, link, builder, run_mode: str, proto: str,
               http_port: int, inject_fn=None) -> None:
    """F-188 — §9.2 '5. uvicorn 기동'. `create_app()`으로 앱을 만들고
    Ctrl-C 로 멈출 때까지 떠 있는다. `link`·`builder`는 `contracts/
    siap_iface.py` Protocol만 만족하면 된다(`backend/api.py::create_app()`
    독스트링과 같은 계약) — 이 함수는 어느 모드에서 왔는지 모른다."""
    import uvicorn
    from backend.api import create_app

    app = create_app(db_path=db_path, link=link, builder=builder,
                      run_mode=run_mode, proto_mode=proto, inject_fn=inject_fn)
    _ensure_public_data_baseline(db_path)
    print(_cp949_safe(f"[run.py] REST API 기동 — http://127.0.0.1:{http_port} (Ctrl-C 로 종료)"))
    # timeout_graceful_shutdown — Ctrl-C 시 열려 있는 SSE 스트림(/api/v1/stream 은
    # 무한 제너레이터라 클라이언트가 안 닫으면 안 끝난다)을 최대 2초만 기다리고
    # 강제 종료한다. 이게 없으면 브라우저 대시보드 탭이 열려 있는 동안 graceful
    # shutdown 이 그 연결을 무한정 기다려 프로세스가 안 죽는다(Windows 에서 특히).
    uvicorn.run(app, host="127.0.0.1", port=http_port, log_level="warning",
                timeout_graceful_shutdown=2)


def _cp949_safe(s: str) -> str:
    """실제 안전장치는 모듈 로드 시점의 `sys.stdout.reconfigure(errors="replace")`
    다(F-045) — 이 함수는 호출부에 "이 출력은 콘솔 인코딩을 의식했다"는
    표식을 남기는 항등 함수다."""
    return s


class _JsonlCapture:
    """rx/tx 프레임을 logs/*.jsonl 포맷({"t","dir","hex"})으로 기록한다(단계 8
    출구 ③). SIAP I/O 스레드가 단독으로 부른다(link._io_loop) — 시리얼·소켓
    소유 스레드와 같아 별도 락이 필요 없다(아키텍처 §4.3). t 는 첫 프레임을
    0.0 으로 한 상대 시각(초) — session_00_golden.jsonl 과 같은 관례라 replay 가
    간격을 정규화해 그대로 재생한다. tx 는 게이트웨이 응답이므로 replay 가
    바이트열을 대조하고, rx 는 노드가 보낸 것이라 주입된다(F-042)."""

    def __init__(self, path: Path) -> None:
        self._fh = path.open("w", encoding="utf-8")
        self._t0: float | None = None
        self.count = 0

    def __call__(self, direction: str, raw: bytes) -> None:
        now = time.time()
        if self._t0 is None:
            self._t0 = now
        rec = {"t": round(now - self._t0, 3), "dir": direction, "hex": raw.hex().upper()}
        self._fh.write(json.dumps(rec) + "\n")
        self._fh.flush()   # 캡처 도중 Ctrl+C 로 끊겨도 이미 받은 프레임은 남는다
        self.count += 1

    def close(self) -> None:
        self._fh.close()


def _make_capture(args: argparse.Namespace) -> "_JsonlCapture | None":
    if not args.capture:
        return None
    path = Path(args.capture)
    path.parent.mkdir(parents=True, exist_ok=True)
    print(_cp949_safe(f"[run.py] 실측 캡처 → {path}"))
    return _JsonlCapture(path)


def _run_simulate(args: argparse.Namespace) -> int:
    from sim.virtual_node import VirtualNodeServer

    duration = args.duration if args.duration is not None else 10.0
    port = args.socket_port or 5556

    server = VirtualNodeServer(port=port, control_port=args.control_port)
    server.start()
    print(_cp949_safe(f"[run.py] 가상 노드 서버 기동 (port={port}, 제어포트={args.control_port})"))

    db_path = _prepare_db_path(args)
    capture = _make_capture(args)
    link = SiapNodeLink(gcg_id=1)
    link.start("simulate", proto_mode=args.proto, host="127.0.0.1", socket_port=port,
               on_frame=_make_on_frame(db_path), capture=capture)

    try:
        if args.serve:
            from siap.build import FrameBuilderImpl
            builder = FrameBuilderImpl(1, args.proto, registry=link)
            inject_fn = _make_inject_fn(args.control_port)
            try:
                _serve_app(db_path=db_path, link=link, builder=builder, run_mode="simulate",
                           proto=args.proto, http_port=args.http_port, inject_fn=inject_fn)
            except KeyboardInterrupt:
                pass
        else:
            print(_cp949_safe(f"[run.py] SIAP I/O 스레드 기동 — {duration:.0f}초간 관찰"))
            try:
                time.sleep(duration)
            except KeyboardInterrupt:
                pass
    finally:
        stats = link.stats()
        registry = link.registry()
        link.stop()
        server.stop()
        if capture is not None:
            capture.close()
            print(_cp949_safe(f"[run.py] 캡처 {capture.count}프레임 기록: {args.capture}"))

    print(_cp949_safe(
        f"[run.py] 종료 — 등록 노드 {len(registry)}개, "
        f"rx={stats['rx']} tx={stats['tx']} 위반={stats['violations']}"
    ))
    for node_id, node in sorted(registry.items()):
        print(_cp949_safe(f"  - node_id={node_id} status={node.status.name}"))
    if args.serve:
        return 0
    return 0 if len(registry) > 0 and stats["rx"] > 0 and stats["tx"] > 0 else 1


def _resolve_log_path(args: argparse.Namespace) -> Path | None:
    if args.log:
        p = Path(args.log)
        return p if p.is_absolute() else REPO_ROOT / p
    default = REPO_ROOT / "logs" / "session_00_golden.jsonl"
    return default if default.exists() else None


def _run_replay(args: argparse.Namespace) -> int:
    from sim.replayer import Replayer

    log_path = _resolve_log_path(args)
    if log_path is None:
        print(_cp949_safe(
            "[run.py] 재생할 로그가 없다 — --log 로 경로를 지정하거나 "
            "먼저 'python -m sim.golden_log' 로 기본 로그를 생성하라."
        ))
        return 1
    if not log_path.exists():
        print(_cp949_safe(f"[run.py] 로그 파일을 찾을 수 없음: {log_path}"))
        return 1

    port = args.socket_port or 5555
    replayer = Replayer(log_path, port=port, speed=args.speed)
    replayer.start()
    print(_cp949_safe(f"[run.py] replay 서버 기동 — {log_path.name} (speed={args.speed}, port={port})"))

    db_path = _prepare_db_path(args)
    link = SiapNodeLink(gcg_id=1)
    link.start("replay", proto_mode=args.proto, host="127.0.0.1", socket_port=port,
               on_frame=_make_on_frame(db_path))

    if args.serve:
        # F-188 — 재생은 백그라운드에서 계속 진행되고(Replayer 는 자체
        # 스레드), 이 스레드는 API 를 Ctrl-C 까지 띄운다. replay 는 라이브
        # 주입 채널이 없다(virtual_node.py 의 제어 채널과 달리 로그 재생
        # 서버는 명령을 받지 않는다) — inject_fn=None, API 는 409로 정직하게
        # 거부한다(api.py 자체 로직).
        from siap.build import FrameBuilderImpl
        builder = FrameBuilderImpl(1, args.proto, registry=link)
        try:
            _serve_app(db_path=db_path, link=link, builder=builder, run_mode="replay",
                       proto=args.proto, http_port=args.http_port, inject_fn=None)
        except KeyboardInterrupt:
            pass
        stats = link.stats()
        link.stop()
        replayer.stop()
        print(_cp949_safe(
            f"[run.py] 종료 — 재생 {replayer.stats['sent']}건, "
            f"rx={stats['rx']} tx={stats['tx']} 위반={stats['violations']}"
        ))
        if replayer.error is not None:
            print(_cp949_safe(f"[run.py] replay 실패: {replayer.error}"))
            return 1
        return 0

    # 안전망 — 로그가 비정상적으로 길거나 재생 서버가 멈춰도 run.py 자체는
    # 무한 대기하지 않는다(§9.3 "좀비 스레드를 남기지 않는다"와 같은 원칙).
    safety_upper = args.duration if args.duration is not None else 60.0
    finished = replayer.done.wait(timeout=safety_upper)
    # replayer.done 은 "송신 루프가 끝났다"는 뜻일 뿐, SIAP I/O 스레드가
    # 소켓 버퍼에 남은 마지막 바이트를 실제로 다 읽었다는 보장은 아니다.
    # "값이 바뀌지 않으면 안정됐다"는 판정은 실측에서 틀렸다 — I/O 스레드는
    # 재생 내내(수 초에 걸쳐) 프레임을 하나씩 처리하므로, 마지막 프레임
    # 하나만 아직 도착 전인 짧은 순간에도 두 번 연속 같은 값이 나와 조기
    # 종료했다(마지막 프레임을 5번 중 5번 다 놓침). 얼마나 와야 하는지
    # 이미 알고 있으므로(`replayer.stats['sent']`) 그 개수에 도달할 때까지
    # 기다리는 쪽이 정확하다 — 최대 2초.
    expected_rx = replayer.stats["sent"]
    for _ in range(40):
        if link.stats()["rx"] >= expected_rx:
            break
        time.sleep(0.05)

    stats = link.stats()
    link.stop()
    replayer.stop()

    if not finished:
        print(_cp949_safe(f"[run.py] 재생이 {safety_upper:.0f}초 안에 끝나지 않아 강제 종료"))
    if replayer.error is not None:
        print(_cp949_safe(f"[run.py] replay 실패: {replayer.error}"))
    print(_cp949_safe(
        f"[run.py] 종료 — 재생 {replayer.stats['sent']}건, tx 기대 "
        f"{replayer.stats['matched_tx']}/{replayer.stats['expected_tx']}건 일치, "
        f"rx={stats['rx']} tx={stats['tx']} 위반={stats['violations']}"
    ))
    return 0 if finished and replayer.error is None else 1


def _run_hardware(args: argparse.Namespace) -> int:
    if not args.port:
        print(_cp949_safe("[run.py] hardware 모드는 --port 가 필요하다 (예: --port COM3 또는 /dev/ttyUSB0)"))
        return 1
    db_path = _prepare_db_path(args)
    capture = _make_capture(args)
    link = SiapNodeLink(gcg_id=1)
    try:
        link.start("hardware", proto_mode=args.proto, port=args.port,
                   on_frame=_make_on_frame(db_path), capture=capture)
    except Exception as e:                      # noqa: BLE001 — 실물 연결 실패를 그대로 보고한다
        print(_cp949_safe(f"[run.py] 시리얼 포트 연결 실패: {e}"))
        if capture is not None:
            capture.close()
        return 1
    try:
        if args.serve:
            from siap.build import FrameBuilderImpl
            builder = FrameBuilderImpl(1, args.proto, registry=link)
            # F-188 — hardware 모드는 실물 링크에 조작된 프레임을 흘리지
            # 않는다(CLAUDE.md §1-1) — inject_fn 을 아예 주지 않는다.
            # api.py 자신도 run_mode="hardware"면 별도로 409 를 거부한다.
            try:
                _serve_app(db_path=db_path, link=link, builder=builder, run_mode="hardware",
                           proto=args.proto, http_port=args.http_port, inject_fn=None)
            except KeyboardInterrupt:
                pass
        else:
            duration = args.duration if args.duration is not None else 10.0
            print(_cp949_safe(f"[run.py] hardware 모드 기동 (port={args.port}) — {duration:.0f}초간 관찰"))
            try:
                time.sleep(duration)
            except KeyboardInterrupt:
                pass
    finally:
        stats = link.stats()
        link.stop()
        if capture is not None:
            capture.close()
            print(_cp949_safe(f"[run.py] 캡처 {capture.count}프레임 기록: {args.capture}"))
    print(_cp949_safe(f"[run.py] 종료 — rx={stats['rx']} tx={stats['tx']} 위반={stats['violations']}"))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.mode == "simulate":
        return _run_simulate(args)
    if args.mode == "replay":
        return _run_replay(args)
    return _run_hardware(args)


if __name__ == "__main__":
    sys.exit(main())
