#!/usr/bin/env python3
"""firmware/tests/ 빌드 산출물 정리 — 셸 `rm` 에 기대지 않는다.

MinGW GCC 는 `-o test_bitpack` 로 지정해도 Windows 에서 `test_bitpack.exe`
를 만들고, `rm` 자체가 PATH에 없는 셸(POSIX sh 를 못 찾아 cmd.exe 로
떨어진 make)도 있다. 파일이 있으면 지우고 없으면 조용히 넘어가는
동작을 Python 표준 라이브러리만으로 한다 — 어떤 셸에서 `make clean` 을
불러도 같다.

실행: python clean.py <파일 이름...>   (firmware/tests/ 에서)
종료 코드: 항상 0.
"""
from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent


def main(argv: list[str]) -> int:
    for name in argv:
        p = HERE / name
        if p.exists():
            p.unlink()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
