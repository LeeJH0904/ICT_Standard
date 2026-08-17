#!/usr/bin/env python3
"""단계 0 신설 검증기 — 오프라인 설치 · 제출 요건.

개발_착수_지시서 §3.0 출구③ / 신설 항목:
  1) 휠 3종(fastapi·uvicorn·pyserial) + 전이 의존성이 플랫폼별로 존재
  2) zip 예상 크기 200MB 이하
  3) .hex/.bin/.elf/.exe/.apk 0개
  4) CLAUDE.md §2.1 제외 대상(표준 문서 md 파일/ · .omc/ · __pycache__/ · _to_delete/)이
     .gitignore 와 패키징에서 빠지는가
  5) 런타임/디버그 SQLite DB(*.db 등)가 git 에 추적되지 않는가 (F-240·F-160)

크기·실행파일 스캔은 git 이 무시하는 파일(런타임 DB 등)을 제외하고 계산해 실제
제출물(git 추적 파일)과 일치시킨다 (F-240).

실행: python tools/offline_verify.py   (저장소 루트에서)
종료 코드: 전부 통과 0 / 하나라도 실패 1
"""

from __future__ import annotations

import functools
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

# F-102 — 한국어 Windows 기본 콘솔은 CP949 다. 출력 문자는 그 안에서 고르는 것이
# 원칙이고(아래 CHECKS 의 문구가 이를 지킨다), 이 가드는 새 문자가 섞여도 검증기
# 자체가 UnicodeEncodeError 로 중단되는 것만은 막는 2중 방어다 (F-045 와 동일 원칙).
if sys.stdout.encoding and sys.stdout.encoding.lower().replace("-", "") != "utf8":
    try: sys.stdout.reconfigure(errors="replace")
    except Exception: pass

REPO_ROOT = Path(__file__).resolve().parent.parent
PYTHON = sys.executable

# CLAUDE.md §2.1 — .gitignore 로 매칭을 검사할 수 있는 제외 대상 4개.
# `.git/` 은 git 저장소 구조상 .gitignore 대상이 될 수 없으므로(자기 자신을
# 무시하는 패턴은 무의미) 여기 넣지 않는다 — 패키징(zip) 스캔에서만 별도로
# 뺀다 (F-097 3번째 반례).
GITIGNORE_TARGET_DIRS = ["표준 문서 md 파일", ".omc", "__pycache__", "_to_delete"]
EXCLUDE_GLOB_PATTERNS = ["_stage*"]  # _stage*/ — 접두어 매칭

# 실제 패키징(zip 크기 · 실행파일 스캔)에서 제외할 대상 — .gitignore 대조 대상
# 4개 + `.git/`(F-097 3번째 반례: 이전에는 여기 빠져 있어 zip 크기·실행파일
# 스캔에 .git 오브젝트가 그대로 잡혔다).
EXCLUDE_DIRS = GITIGNORE_TARGET_DIRS + [".git"]

FORBIDDEN_EXT = {".hex", ".bin", ".elf", ".exe", ".apk"}

# CLAUDE.md §4.3: "Python 3.11+". 심사자 환경(OS·파이썬 버전)을 모르므로
# 3.11~3.13 × win/linux 6조합을 전부 오프라인 설치로 확인한다 (아키텍처 설계서
# §8.3 "다른 파이썬 버전은 필요 시 추가" 대응). pydantic-core 만 버전별 바이너리가
# 갈리고 나머지는 순수 파이썬(py3-none-any)이라 추가 비용은 휠 4개뿐이다.
TARGET_PLATFORMS = [
    (platform_tag, py_ver, "cp", f"cp{py_ver}")
    for platform_tag in ("win_amd64", "manylinux2014_x86_64")
    for py_ver in ("311", "312", "313")
]

REQUIRED_PACKAGES = ["fastapi", "uvicorn", "pyserial"]

MAX_ZIP_BYTES = 200 * 1024 * 1024


@functools.lru_cache(maxsize=1)
def _gitignored_files() -> frozenset[Path]:
    """git 이 무시하는(추적하지 않고 .gitignore 에 걸리는) 파일의 절대경로 집합.
    실제 제출물은 git 추적 파일(또는 git archive)이므로, 저장소 폴더를 그대로 walk
    하는 이 검증기도 같은 기준으로 무시 파일을 빼야 크기·실행파일 스캔이 실제
    제출물과 일치한다 (F-240 — 런타임 SQLite DB 6개가 .gitignore 됐는데도 폴더
    walk 에는 잡혀 138.9MB 로 부풀던 문제). git 이 없으면 빈 집합(사전 검사 생략)."""
    git_exe = shutil.which("git")
    if not git_exe:
        return frozenset()
    proc = subprocess.run(
        [git_exe, "ls-files", "--others", "--ignored", "--exclude-standard", "-z"],
        cwd=str(REPO_ROOT), capture_output=True, text=True,
        encoding="utf-8", errors="replace", timeout=60,
    )
    if proc.returncode != 0:
        return frozenset()
    out: set[Path] = set()
    for rel in proc.stdout.split("\0"):
        rel = rel.strip()
        if rel:
            out.add((REPO_ROOT / rel).resolve())
    return frozenset(out)


def _is_excluded(path: Path) -> bool:
    parts = path.relative_to(REPO_ROOT).parts
    for part in parts:
        if part in EXCLUDE_DIRS:
            return True
        for pattern in EXCLUDE_GLOB_PATTERNS:
            prefix = pattern.rstrip("*")
            if part.startswith(prefix):
                return True
    # F-240 — git 이 무시하는 파일(런타임 DB 등)은 실제 제출물에 들어가지 않는다.
    if path.resolve() in _gitignored_files():
        return True
    return False


def _norm_pkg(name: str) -> str:
    return name.strip().lower().replace("-", "_")


# name (연산자 앞) / 연산자 / 버전 을 각각 분리해서 뽑는다. 확장자([extra])나
# 환경 마커(;)가 붙으면 연산자가 안 잡혀 op="" 가 되고, 아래에서 "느슨한 지정자"로
# 취급되어 실패한다 — 이 프로젝트는 extras 를 쓰지 않으므로 보수적으로 막는다.
_REQ_LINE = re.compile(r"^([A-Za-z0-9][A-Za-z0-9_.-]*)\s*(==|>=|<=|~=|!=|===|>|<)?\s*([^\s;]*)")
# 휠 파일명: {배포명}-{버전}-{python tag}-{abi tag}-{platform tag}.whl.
# 배포명 세그먼트는 '-' 가 전부 '_' 로 치환되어 있으므로(PEP 427) 첫 '-' 앞이 이름,
# 그다음 '-' 앞이 버전이다.
_WHEEL_RE = re.compile(r"^([A-Za-z0-9_.]+)-([^-]+)-.+\.whl$", re.I)


def _parse_requirements(req: Path) -> list[tuple[str, str, str]]:
    """requirements.txt 의 유효 행에서 (이름, 연산자, 버전) 을 뽑는다.
    F-097 1번째 반례: 예전에는 이름만 보아 4번째 직접 의존성을 놓쳤다.
    F-103 1번째 반례: 이름만 다시 보게 고친 뒤에도 `>=`·`~=` 처럼 재현성을
    깨는 느슨한 지정자를 그대로 통과시켰다 — 이제 연산자·버전까지 반환해
    호출자가 `==` 인지 검사하게 한다."""
    results: list[tuple[str, str, str]] = []
    for raw in req.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        line = line.split(";", 1)[0].strip()  # 환경 마커 제거
        m = _REQ_LINE.match(line)
        if not m:
            results.append((line, "", ""))
            continue
        results.append((m.group(1), m.group(2) or "", m.group(3) or ""))
    return results


def _wheel_name_version(fname: str) -> tuple[str, str] | None:
    m = _WHEEL_RE.match(fname)
    if not m:
        return None
    return _norm_pkg(m.group(1)), m.group(2)


def check_wheels_present() -> tuple[bool, str]:
    wheels_dir = REPO_ROOT / "project_code" / "wheels"
    req = REPO_ROOT / "project_code" / "requirements.txt"
    if not wheels_dir.exists():
        return False, "project_code/wheels/ 없음"
    if not req.exists():
        return False, "project_code/requirements.txt 없음"

    parsed = _parse_requirements(req)
    declared = {_norm_pkg(n) for n, _, _ in parsed}
    required = {_norm_pkg(n) for n in REQUIRED_PACKAGES}
    problems = []
    if declared != required:
        extra = sorted(declared - required)
        missing_decl = sorted(required - declared)
        if extra:
            problems.append(f"CLAUDE.md §4.3 미승인 직접 의존성: {extra}")
        if missing_decl:
            problems.append(f"requirements.txt 에서 누락된 직접 의존성: {missing_decl}")

    # F-103 1번째 반례 — 아키텍처 §8.3(F-099 정정)은 직접 의존성 3개를 == 로
    # 정확히 고정한다고 정한다. >=·~=·!= 등은 재현성(같은 버전 재현)을 깨뜨린다.
    loose = [f"{n}{op}{ver}" for n, op, ver in parsed if op != "==" or not ver]
    if loose:
        problems.append(f"아키텍처 §8.3 위반 - == 로 정확히 고정되지 않은 요구사항: {loose}")

    if problems:
        return False, "; ".join(problems)

    names = [p.name for p in wheels_dir.glob("*.whl")]
    if not names:
        return False, "wheels/ 안에 .whl 파일 0개"
    missing = [pkg for pkg in REQUIRED_PACKAGES
               if not any(n.lower().startswith(_norm_pkg(pkg) + "-") for n in names)]
    if missing:
        return False, f"직접 의존성 휠 누락: {missing}"

    # F-103 2번째 반례 — 같은 배포명에 서로 다른 버전이 섞이면 "wheels/ 가 곧
    # 잠금"(F-099 정정)이라는 전제가 깨진다. 같은 버전의 플랫폼·ABI 별 파일은
    # 여러 개 있어도 된다(예: pydantic_core 의 win/manylinux × py311~313).
    by_name: dict[str, set[str]] = {}
    unparsed = []
    for n in names:
        parsed_wheel = _wheel_name_version(n)
        if parsed_wheel is None:
            unparsed.append(n)
            continue
        pkg, ver = parsed_wheel
        by_name.setdefault(pkg, set()).add(ver)
    if unparsed:
        return False, f"휠 파일명 해석 불가: {unparsed}"
    multi_version = {k: sorted(v) for k, v in by_name.items() if len(v) > 1}
    if multi_version:
        return False, f"배포명별 버전이 둘 이상(잠금 깨짐): {multi_version}"

    return True, (f"requirements.txt 직접 의존성 3종 == 고정 확인, "
                  f"휠 {len(names)}개 - 배포 {len(by_name)}종 각 단일 버전")


def check_offline_install() -> tuple[bool, str]:
    """실제로 --no-index --find-links 만으로, 플랫폼 2종에 오프라인 설치가 되는가.
    통과하면 전이 의존성(pydantic·starlette·anyio 등)도 로컬 wheels/ 안에 전부
    있다는 뜻이다 — pip 리졸버가 부족하면 여기서 즉시 실패한다."""
    req = REPO_ROOT / "project_code" / "requirements.txt"
    wheels = REPO_ROOT / "project_code" / "wheels"
    if not req.exists():
        return False, "project_code/requirements.txt 없음"

    details = []
    for platform_tag, py_ver, impl, abi in TARGET_PLATFORMS:
        with tempfile.TemporaryDirectory() as tmp:
            proc = subprocess.run(
                [
                    PYTHON, "-m", "pip", "install",
                    "-r", str(req),
                    "--no-index", "--find-links", str(wheels),
                    "--target", tmp,
                    "--platform", platform_tag,
                    "--python-version", py_ver,
                    "--implementation", impl,
                    "--abi", abi,
                    "--only-binary=:all:",
                ],
                capture_output=True, text=True, encoding="utf-8", errors="replace",
                timeout=120,
            )
            if proc.returncode != 0:
                tail = (proc.stdout + proc.stderr).strip().splitlines()[-10:]
                return False, f"{platform_tag}/py{py_ver} 오프라인 설치 실패:\n" + "\n".join(tail)
            details.append(f"{platform_tag}/py{py_ver} OK")
    return True, "; ".join(details)


def check_zip_size() -> tuple[bool, str]:
    total = 0
    file_count = 0
    for p in REPO_ROOT.rglob("*"):
        if p.is_dir():
            continue
        if _is_excluded(p):
            continue
        try:
            total += p.stat().st_size
        except OSError:
            continue
        file_count += 1
    mb = total / (1024 * 1024)
    ok = total <= MAX_ZIP_BYTES
    return ok, f"제출 대상 추정 {mb:.1f} MB ({file_count}개 파일, 압축 전 크기) - 한도 200 MB"


def _clean_known_build_dirs() -> None:
    """실행파일 스캔 전에 알려진 C 빌드 디렉터리(Makefile 보유)를 정리한다.

    F-111 — 단계 2a 출구(`make test_bitpack && ./test_bitpack`)를 문서
    그대로 실행하면 `test_bitpack.exe` 가 남는다. 그 직후 이 스캔이
    도는데, 출구 명령도 `where.py` 도 정리를 호출하지 않으므로 "문서에
    적힌 명령만 그대로 따라했는데 다음 검증이 깨진다"는 워크플로 결함이
    남는다. 사람이 별도 clean 단계를 기억해야 하는 구조 대신, 검증기
    자신이 알려진(Makefile 이 소유를 선언한) 빌드 산출물을 먼저 치우고
    "그 나머지에 낯선 실행파일이 있는가"를 본다 — 이건 결과를 봐주는
    게 아니라, 이 스캔이 애초에 잡으려는 것(제출물에 섞여 들어갈 뻔한
    실행파일)과 정상적인 개발 중간 산물을 구분하는 것이다. `make` 가
    없거나 clean 이 실패해도(아직 빌드한 적이 없는 상태 등) 조용히
    넘어간다 — 여기서 실패시키는 건 이 함수의 책임이 아니고, 진짜
    지워지지 않는 실행파일이 있다면 아래 스캔이 그대로 잡아낸다."""
    firmware = REPO_ROOT / "project_code" / "firmware"
    if not firmware.exists():
        return
    for makefile in firmware.rglob("Makefile"):
        try:
            subprocess.run(["make", "clean"], cwd=str(makefile.parent),
                            capture_output=True, timeout=60)
        except Exception:
            pass


def check_no_binaries() -> tuple[bool, str]:
    _clean_known_build_dirs()
    hits = []
    for p in REPO_ROOT.rglob("*"):
        if p.is_dir():
            continue
        if _is_excluded(p):
            continue
        if p.suffix.lower() in FORBIDDEN_EXT:
            hits.append(str(p.relative_to(REPO_ROOT)))
    if hits:
        return False, f"실행파일 {len(hits)}개 발견: {hits[:10]}"
    return True, "실행파일 0개"


def _active_gitignore_patterns(gi: Path) -> list[str]:
    """주석(#)·빈 줄을 뺀 실제 규칙 행만 남긴다 (F-097 2번째 반례: 이전에는
    파일 전체 텍스트에 이름이 '어딘가' 있으면 통과해, 주석 한 줄에만 적어도
    규칙 없이 통과했다). 실제 매칭 판정은 git 에 맡기고(아래), 이 함수는
    "규칙이 하나라도 있는가"를 먼저 걸러내는 빠른 사전 검사로만 쓴다."""
    patterns = []
    for raw in gi.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        patterns.append(line)
    return patterns


def check_gitignore_excludes() -> tuple[bool, str]:
    """F-103 3번째 반례 - 부분 문자열/자체 구현 fnmatch 는 gitignore 의 규칙
    순서와 '!' 재포함(negation) 의미를 모른다. '.omc/' 뒤에 '!.omc/' 한 줄만
    추가해도 실제로는 다시 포함되지만 이전 구현은 여전히 '매칭됨'으로 통과했다.
    표준 구현과 교차 검증한다(CLAUDE.md §6.2 F-095 원칙과 같은 이유) - 우리
    코드로 gitignore 의미론을 재구현하지 않고, 실제 git check-ignore 를
    임시 저장소에서 그대로 물어본다."""
    gi = REPO_ROOT / ".gitignore"
    if not gi.exists():
        return False, ".gitignore 없음"
    content = gi.read_text(encoding="utf-8")
    if not _active_gitignore_patterns(gi):
        return False, ".gitignore 에 주석 외 규칙이 없음"

    git_exe = shutil.which("git")
    if not git_exe:
        return False, "git 실행 파일을 찾을 수 없어 .gitignore 실제 의미를 검사할 수 없음"

    labels = list(GITIGNORE_TARGET_DIRS) + list(EXCLUDE_GLOB_PATTERNS)
    probe_names = list(GITIGNORE_TARGET_DIRS) + [p.rstrip("*") + "샘플" for p in EXCLUDE_GLOB_PATTERNS]

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        init = subprocess.run([git_exe, "init", "-q"], cwd=tmp_path,
                               capture_output=True, text=True, timeout=30)
        if init.returncode != 0:
            return False, f"임시 git 저장소 초기화 실패: {init.stderr.strip()}"
        (tmp_path / ".gitignore").write_text(content, encoding="utf-8")

        not_ignored = []
        for label, probe_name in zip(labels, probe_names):
            probe_dir = tmp_path / probe_name
            probe_dir.mkdir(parents=True, exist_ok=True)
            probe_file = probe_dir / "probe.txt"
            probe_file.write_text("", encoding="utf-8")
            result = subprocess.run(
                [git_exe, "check-ignore", "--no-index", str(probe_file.relative_to(tmp_path))],
                cwd=tmp_path, capture_output=True, text=True, timeout=30,
            )
            if result.returncode != 0:
                not_ignored.append(label)

    if not_ignored:
        return False, f"git 의미상 실제로 제외되지 않는 대상(순서·'!' 재포함 포함): {not_ignored}"
    n = len(labels)
    return True, f"제외 대상 {n}종이 git check-ignore 로 실제 확인됨 (.git/ 은 gitignore 대상 아님 - 패키징 스캔에서만 제외)"


def check_no_tracked_databases() -> tuple[bool, str]:
    """런타임/디버그 SQLite DB 가 git 에 추적되면 전체 소스 ZIP 에 실행 데이터가
    섞인다(F-240·F-160, 공고문 "빌드 산출물·실행파일 제외"). .gitignore 가 *.db 를
    무시해도 과거처럼 실수로 커밋되면(`git add -f` 등) 무시가 무력화되므로, 추적
    목록(git ls-files)을 직접 확인해 하나라도 있으면 실패시킨다 — DB 내용·크기는
    실행마다 달라 재현성·제출물 청결성을 흔든다."""
    git_exe = shutil.which("git")
    if not git_exe:
        return False, "git 실행 파일을 찾을 수 없어 추적 DB 를 확인할 수 없음"
    proc = subprocess.run(
        [git_exe, "ls-files", "-z"],
        cwd=str(REPO_ROOT), capture_output=True, text=True,
        encoding="utf-8", errors="replace", timeout=60,
    )
    if proc.returncode != 0:
        return False, f"git ls-files 실패: {proc.stderr.strip()}"
    db_suffixes = (".db", ".db-wal", ".db-shm", ".db-journal")
    tracked_db = [rel.strip() for rel in proc.stdout.split("\0")
                  if rel.strip() and rel.strip().endswith(db_suffixes)]
    if tracked_db:
        return False, (f"git 이 추적 중인 런타임 DB {len(tracked_db)}개 — "
                       f"`git rm --cached` 로 제외: {tracked_db[:10]}")
    return True, "추적 중인 *.db/-wal/-shm/-journal 0개 (.gitignore 로 제외 확인)"


CHECKS = [
    ("휠 3종 + 전이 의존성 존재(파일명)", check_wheels_present),
    ("오프라인 설치 실제 성공(win/linux, py311~313)", check_offline_install),
    ("제출 zip 예상 크기 <= 200MB", check_zip_size),
    ("실행파일(.hex/.bin/.elf/.exe/.apk) 0개", check_no_binaries),
    ("§2.1 제외 대상이 .gitignore 에 반영", check_gitignore_excludes),
    ("런타임 DB(*.db 등)가 git 에 추적되지 않음 (F-240)", check_no_tracked_databases),
]


def main() -> int:
    print("=== tools/offline_verify.py ===\n")
    all_ok = True
    for name, fn in CHECKS:
        ok, detail = fn()
        all_ok = all_ok and ok
        mark = "OK" if ok else "FAIL"
        print(f"[{mark}] {name}")
        if detail:
            for line in detail.splitlines():
                print(f"    {line}")
    print()
    print("전체 통과" if all_ok else "실패 항목 있음")
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
