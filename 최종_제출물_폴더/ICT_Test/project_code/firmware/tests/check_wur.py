#!/usr/bin/env python3
"""SIAP_WUR / -Werror=unused-result 회귀 검사.

test_bitpack.c 는 반환값을 절대 버리지 않으므로, SIAP_WUR 가 헤더에서
빠지거나 Makefile 의 -Werror=unused-result 가 빠져도 스스로 드러내지
못한다 — "반환값을 버리면 컴파일이 실패한다"는 계약 자체가 검사
대상이다. test_bitpack_wur_bp_write.c / test_bitpack_wur_bp_write_f32.c
두 파일은 일부러 반환값을 버리며, 이 스크립트는 그 둘이 "컴파일에
실패하는 것"을 성공으로 판정한다.

셸 스크립트(if/then/fi, 리다이렉션)로 짜지 않고 Python 으로 짠 이유
( 처리 중 발견) — mingw32-make 는 POSIX sh 를 못 찾으면 cmd.exe 로
조용히 떨어지는데, cmd.exe 는 sh 문법을 모른다. `tools/where.py` 가
PowerShell 에서 `make` 를 부르는 경로가 정확히 이 상황이다. Make
레시피를 `python check_wur.py <CC> <CFLAGS...>` 한 줄로 두면 셸이
무엇이든 동일하게 동작한다 — 단어 분리 말고는 셸 고유 문법이 없다.

"컴파일이 실패했다"만으로는 부족하다. 스니펫 파일이 삭제되거나
(`No such file`), 컴파일러 자체가 없거나, 헤더가 깨져 무관한 오류가
나도 종료 코드는 똑같이 0이 아니다 — 그러면 이 검사는 "SIAP_WUR 가
정상 작동한다"를 증명하지 못한 채로 통과해 버린다. 그래서 ① 스니펫이
실재하는지 ② 컴파일러가 실행 가능한지 를 먼저 확인하고, ③ 컴파일이
실패했을 때 그 진단문에 실제로 `unused-result`/`warn_unused_result`
가 있는지까지 확인한다 — 실패의 "원인"이 계약 위반인지 봐야 한다.

실행: python check_wur.py <CC> [CFLAGS...]   (firmware/tests/ 에서)
종료 코드: 0 = 두 스니펫 모두 "unused-result 진단으로" 컴파일 실패,
           1 = 회귀(컴파일 성공) 또는 검사 자체가 불가능한 상태 발견
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

# 원칙과 같은 2중 방어 — 이 스크립트 자신의 print() 는 ASCII 뿐이라
# 실질적으로 걸릴 일이 없지만, 표현 못 하는 문자가 섞여도 중단만은 막는다.
if sys.stdout.encoding and sys.stdout.encoding.lower().replace("-", "") != "utf8":
    try: sys.stdout.reconfigure(errors="replace")
    except Exception: pass

HERE = Path(__file__).resolve().parent

# (표시 이름, 소스 파일) — 각 함수를 독립적으로 검사한다. 하나로 합치면
# 한쪽의 SIAP_WUR 만 빠지는 부분 회귀를 가려낼 수 없다.
#
# 재발(단계 2b) — siap_frame.h 로 SIAP_WUR 가 새로 9개 옮겨갔는데
# (siap_encode_hdr/np/mcp, siap_tx_put_hdr/rsc/nec/np/mcp/device_id) 이
# 목록은 bitpack.h 의 2개뿐이었다. Makefile 의 새 테스트 타깃(test_siap_frame
# 등)도 check_wur 를 선행조건으로 물지 않아, "반환값을 버리면 컴파일이
# 실패한다"는 계약이 siap_frame.h 쪽에서는 자동 출구로 전혀 검증되지
# 않았다 — bitpack.c/.h 에서 가 고쳤던 것과 같은 종류의 구멍이
# 새 헤더에서 그대로 재발한 것이다.
SNIPPETS = (
    ("bp_write", "test_bitpack_wur_bp_write.c"),
    ("bp_write_f32", "test_bitpack_wur_bp_write_f32.c"),
    ("siap_encode_hdr", "test_siap_frame_wur_encode_hdr.c"),
    ("siap_encode_np", "test_siap_frame_wur_encode_np.c"),
    ("siap_encode_mcp", "test_siap_frame_wur_encode_mcp.c"),
    ("siap_tx_put_hdr", "test_siap_frame_wur_tx_put_hdr.c"),
    ("siap_tx_put_rsc", "test_siap_frame_wur_tx_put_rsc.c"),
    ("siap_tx_put_nec", "test_siap_frame_wur_tx_put_nec.c"),
    ("siap_tx_put_np", "test_siap_frame_wur_tx_put_np.c"),
    ("siap_tx_put_mcp", "test_siap_frame_wur_tx_put_mcp.c"),
    ("siap_tx_put_device_id", "test_siap_frame_wur_tx_put_device_id.c"),
)

# gcc/clang 진단이 실제로 warn_unused_result 계약 때문에 실패했다고
# 말하는 표지. 대소문자·컴파일러별 문구 차이를 흡수하려 두 형태를 본다.
WUR_MARKERS = ("unused-result", "warn_unused_result", "unused_result")


def _run(cmd: list[str]) -> tuple[int, str]:
    """ 와 같은 부류 — text=True 는 로케일 기본 인코딩
    (한국어 Windows에서는 cp949)으로 디코딩한다. gcc 진단이 소스 주석의
    UT 문자(em dash 등)를 그대로 인용하면 cp949로 못 읽어
    UnicodeDecodeError 가 난다. 명시적으로 utf-8 을 쓴다."""
    try:
        proc = subprocess.run(cmd, capture_output=True, encoding="utf-8", errors="replace")
        return proc.returncode, (proc.stdout or "") + (proc.stderr or "")
    except OSError as exc:
        return -1, f"실행 실패: {exc}"


def main(argv: list[str]) -> int:
    if not argv:
        print("usage: check_wur.py <CC> [CFLAGS...]", file=sys.stderr)
        return 2
    cc, cflags = argv[0], argv[1:]

    # 선검사 ① — 컴파일러 자체가 실행 가능한가. 이게 안 되면 아래
    # 모든 판정이 무의미하다(모든 컴파일이 "실패"로 보여 거짓 OK 를 낼 수 있다).
    cc_rc, cc_out = _run([cc, "--version"])
    if cc_rc != 0:
        print(f"FAIL: compiler '{cc}' is not runnable (rc={cc_rc}): {cc_out[-300:]}")
        return 1

    regressed: list[str] = []
    unusable: list[str] = []
    for label, src_name in SNIPPETS:
        src = HERE / src_name
        # 선검사 ② — 스니펫 자체가 없으면 gcc 는 'No such file' 로
        # 실패한다. 그 실패는 unused-result 계약과 무관하므로, 컴파일을
        # 시도하기 전에 먼저 걸러 별도 사유로 보고한다.
        if not src.exists():
            unusable.append(f"{label}: snippet source missing ({src_name})")
            continue

        obj = HERE / f"_wur_check_{label}.o"
        rc, diag = _run([cc, *cflags, "-c", str(src), "-o", str(obj)])
        if obj.exists():
            obj.unlink()

        if rc == 0:
            regressed.append(label)
            continue

        # 핵심 — 컴파일이 실패했다는 사실만으로 "정상"이라 판정하지
        # 않는다. 실패 원인이 warn_unused_result 진단인지 진단문 자체를 본다.
        if not any(marker in diag for marker in WUR_MARKERS):
            unusable.append(
                f"{label}: compile failed but NOT due to unused-result "
                f"(diagnostic tail: {diag[-300:]!r})"
            )

    if regressed or unusable:
        for label in regressed:
            print(f"FAIL: {label}() return-value discard did not fail to "
                  f"compile - SIAP_WUR / -Werror=unused-result regression")
        for msg in unusable:
            print(f"FAIL: {msg} - check_wur cannot confirm the "
                  f"unused-result contract is enforced")
        return 1

    print("OK: bp_write()/bp_write_f32() return-value discard "
          "correctly fails to compile due to the unused-result contract")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
