"""C 인코더 ↔ Python 인코더 교차 검증 — 개발_착수_지시서 §3.5(단계 3) 신설 검증기.

**주장 1** — "서로 다른 MCU 3종이 동일 표준 프로토콜로 혼용 동작한다"의 절반은
C 와 Python 두 코덱이 같은 골든 벡터에서 같은 판정을 내리는 것이다
(CLAUDE.md §4.4). 이 검증기가 그 절반을 기계로 확인한다.

절차:
  1. `firmware/tests/dump_golden.c` 를 빌드해 실행한다 — 골든 벡터 53건 **전량**을
     C 디코더에 먹인다.
       · judgement=normal/alert → 디코드 후 재인코딩한 hex 를 낸다
       · judgement=violation    → 거부 판정(RSC+clause)을 낸다(F-136)
     judgement(normal/alert/violation)는 category(정상/경계값/위반)와 축이
     다르다 — 경계값 11건 중 2건(N 상한 초과 등)은 judgement=violation 이고,
     위반 8건 중 1건(NEC=0x07)은 judgement=alert 다(F-060). 그래서 "34+11"
     같은 고정 개수를 쓰지 않고 golden.jsonl 에서 매번 다시 센다.
  2. 같은 53건을 Python `siap/codec.py::decode_frame()` 으로 판정한다 —
     normal/alert 는 `encode_frame()` 까지, violation 은 `violations[0]` 을 본다.
  3. **재인코딩 대상**은 C 출력 · Python 출력 · golden.jsonl 원본 hex 세 값이,
     **위반 대상**은 C 판정 · Python 판정 · golden.jsonl 이 적어 둔 기대값
     세 값이 전부 일치하는지 대조한다 — 파일 하나만 보고 판정하지 않는다
     (F-080, 독립 입력 최소 2개: C 실행 결과와 golden.jsonl 원본).

F-136 — 이전 버전은 violation 9건(judgement 기준)을 아예 건너뛰고 "44+9=53"
이라는 항등식에만 포함시켜, "53건 전량 대조"라는 출구 문구를 실제로는
충족하지 못했다. 위반 판정까지 양쪽 언어에서 독립적으로 재구성해 대조한다.

실행: python tools/xcodec_verify.py   (저장소 루트에서)
종료 코드: 전부 통과 0 / 하나라도 실패 1
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

if sys.stdout.encoding and sys.stdout.encoding.lower().replace("-", "") != "utf8":
    try:
        sys.stdout.reconfigure(errors="replace")
    except Exception:
        pass

REPO_ROOT = Path(__file__).resolve().parent.parent
PROJECT_CODE = REPO_ROOT / "project_code"
FW_TESTS = PROJECT_CODE / "firmware" / "tests"
GOLDEN_PATH = PROJECT_CODE / "contracts" / "vectors" / "golden.jsonl"

sys.path.insert(0, str(PROJECT_CODE))


def _load_golden() -> list[dict]:
    with open(GOLDEN_PATH, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def _build_and_run_c_dump() -> tuple[dict[str, str], dict[str, tuple[int, str]], str, int]:
    """dump_golden 을 빌드·실행한다.
    돌려주는 값: (재인코딩 hex, {id: (rsc, clause)} 위반 판정, stderr 로그, 종료코드).

    CLAUDE.md §1-3 — 실행파일을 커밋하지 않는다. `make clean` 이 걸릴 때까지
    기다리지 않고, 이 함수가 끝나기 전에 스스로 빌드 산출물을 지운다 — 그래야
    이 검증기를 돌리는 것 자체가 `fix_log/meta_verify.py` 의 실행파일 스캔을
    건드리지 않는다(빌드형 검증기는 자기 산출물을 자기 책임으로 치운다).

    F-142 — `run.returncode` 를 호출자가 반드시 보게 한다. 예전에는 stdout
    만 파싱해 건수가 맞으면 "빌드·실행 성공"으로 판정했다 — assertion·
    sanitizer·비정상 종료로 죽어도 죽기 전까지 53건을 이미 다 찍었다면
    출력 내용은 완전한데 프로세스는 실패한 상태로 끝난다. 그 구분은
    `run.returncode` 로만 가능하므로 값을 버리지 않고 그대로 돌려준다."""
    build = subprocess.run(["make", "dump_golden"], cwd=FW_TESTS,
                            capture_output=True, text=True)
    if build.returncode != 0:
        return {}, {}, f"빌드 실패: {build.stdout}\n{build.stderr}", build.returncode

    exe = FW_TESTS / "dump_golden.exe"
    if not exe.exists():
        exe = FW_TESTS / "dump_golden"
    try:
        run = subprocess.run([str(exe)], cwd=FW_TESTS, capture_output=True, text=True,
                              encoding="utf-8", errors="replace")
    finally:
        # `make clean` 전체가 아니라 이 파일이 만든 산출물만 지운다 — 같은
        # 프로세스 안에서 다른 검증기(where.py 등)가 방금 빌드해 둔
        # test_*.exe 를 건드리지 않는다.
        for name in ("dump_golden.exe", "dump_golden"):
            p = FW_TESTS / name
            if p.exists():
                p.unlink()

    hex_out: dict[str, str] = {}
    violation_out: dict[str, tuple[int, str]] = {}
    for line in run.stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split(" ")
        if len(parts) >= 3 and parts[1] == "VIOLATION":
            vid = parts[0]
            try:
                rsc = int(parts[2])
            except ValueError:
                continue
            clause = " ".join(parts[3:])
            violation_out[vid] = (rsc, clause)
        elif len(parts) == 2:
            vid, hexstr = parts
            hex_out[vid] = hexstr.upper()
    return hex_out, violation_out, run.stderr, run.returncode


def main() -> int:
    from contracts.frame import Header  # noqa: F401  (import 경로 확인용)
    from siap import codec

    R: list[tuple[bool, str, str]] = []

    def t(name: str, ok: bool, note: str = "") -> None:
        R.append((bool(ok), name, note))

    vectors = _load_golden()
    t(f"골든 벡터 {len(vectors)}건 로드", len(vectors) == 53,
      "" if len(vectors) == 53 else f"기대 53건, 실제 {len(vectors)}건")

    reencodable = [v for v in vectors if v["judgement"] in ("normal", "alert")]
    violation_vecs = [v for v in vectors if v["judgement"] == "violation"]
    t(f"재인코딩 대상(judgement=normal/alert) {len(reencodable)}건 + "
      f"위반 판정 대상(judgement=violation) {len(violation_vecs)}건 = 53건",
      len(reencodable) + len(violation_vecs) == 53, "")

    c_hex, c_violations, c_stderr, c_returncode = _build_and_run_c_dump()
    # F-142 — 종료코드를 출력 건수와 독립적으로 먼저 본다. 예전에는 이
    # 검사가 없어, stdout 이 완전해도(53건 다 찍은 뒤 죽어도) 8/8 로
    # 통과했다 — 종료코드만 강제로 바꿔 재현해도 검출되지 않았다.
    t("dump_golden 정상 종료 (exit code 0) (F-142)", c_returncode == 0,
      f"실제 종료코드: {c_returncode}" if c_returncode != 0 else "")
    t("dump_golden 빌드·실행 성공", bool(c_hex) or bool(c_violations),
      c_stderr[:300] if not (c_hex or c_violations) else "")
    t(f"C 출력이 재인코딩 대상 {len(reencodable)}건 전량을 냈다 (실제 {len(c_hex)}건)",
      len(c_hex) == len(reencodable),
      "" if len(c_hex) == len(reencodable) else f"C stderr: {c_stderr[:300]}")
    t(f"C 출력이 위반 판정 대상 {len(violation_vecs)}건 전량을 냈다 (실제 {len(c_violations)}건) (F-136)",
      len(c_violations) == len(violation_vecs),
      "" if len(c_violations) == len(violation_vecs) else f"C stderr: {c_stderr[:300]}")

    # ── 재인코딩 대상 — C hex ↔ Python hex ↔ golden hex ──────────
    mismatches: list[str] = []
    py_fail: list[str] = []
    for v in reencodable:
        vid = v["id"]
        golden_hex = v["hex"].upper()
        try:
            frame = codec.decode_frame(bytes.fromhex(v["hex"]), "strict",
                                        node_known=lambda n: True)
            if frame.violations:
                py_fail.append(f"{vid}: 예상치 못한 위반 {frame.violations}")
                continue
            py_hex = codec.encode_frame(frame, "strict").hex().upper()
        except Exception as e:                              # noqa: BLE001 — 검증기는 원인을 그대로 보고한다
            py_fail.append(f"{vid}: 예외 {e!r}")
            continue

        c_h = c_hex.get(vid)
        if c_h is None:
            mismatches.append(f"{vid}: C 출력 없음(dump_golden 이 SKIP 했다)")
            continue
        if not (c_h == py_hex == golden_hex):
            mismatches.append(f"{vid}: C={c_h} PYTHON={py_hex} GOLDEN={golden_hex}")

    t(f"Python 인코더가 {len(reencodable)}건 전량 예외 없이 재인코딩", not py_fail, "; ".join(py_fail[:5]))
    t(f"C 출력 ↔ Python 출력 ↔ golden.jsonl 원본 hex — {len(reencodable)}건 전량 바이트 일치",
      not mismatches, "; ".join(mismatches[:5]) + (f" 외 {len(mismatches) - 5}건" if len(mismatches) > 5 else ""))

    # ── 위반 판정 대상 — C 판정 ↔ Python 판정 ↔ golden 기대값 (F-136) ──
    violation_mismatches: list[str] = []
    for v in violation_vecs:
        vid = v["id"]
        expect = v["violations"][0]
        node_known = (lambda n: False) if v.get("inject") == "unregistered_node" else (lambda n: True)
        frame = codec.decode_frame(bytes.fromhex(v["hex"]), "strict", node_known=node_known)
        if not frame.violations:
            violation_mismatches.append(f"{vid}: Python 이 위반을 검출하지 못했다")
            continue
        py_code = frame.violations[0].code
        py_clause = frame.violations[0].clause

        c_result = c_violations.get(vid)
        if c_result is None:
            violation_mismatches.append(f"{vid}: C 출력 없음(dump_golden 이 SKIP 했다)")
            continue
        c_code, c_clause = c_result

        if not (c_code == py_code == expect["code"] and c_clause == py_clause == expect["clause"]):
            violation_mismatches.append(
                f"{vid}: C=({c_code},{c_clause!r}) PYTHON=({py_code},{py_clause!r}) "
                f"GOLDEN=({expect['code']},{expect['clause']!r})"
            )

    t(f"C 판정 ↔ Python 판정 ↔ golden.jsonl 기대값 — 위반 {len(violation_vecs)}건 전량 일치 (F-136)",
      not violation_mismatches,
      "; ".join(violation_mismatches[:5]) + (f" 외 {len(violation_mismatches) - 5}건"
                                              if len(violation_mismatches) > 5 else ""))

    w = max(len(n) for _, n, _ in R)
    print("C 인코더 ↔ Python 인코더 교차 검증 (개발_착수_지시서 §3.5, 단계 3)\n")
    for ok, n, note in R:
        print(f"  {'PASS' if ok else 'FAIL'}  {n:<{w}}  {note}")
    p = sum(1 for o, *_ in R if o)
    print(f"\n  {p}/{len(R)} 통과")
    return 0 if p == len(R) else 1


if __name__ == "__main__":
    sys.exit(main())
