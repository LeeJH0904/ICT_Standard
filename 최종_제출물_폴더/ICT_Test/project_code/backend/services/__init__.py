"""
backend/services/ — TTAK.KO-10.0937 서비스 계층. ems·dms·mms·fms·fcs 5종.

조항 ↔ 모듈 배정은 0937_요구사항_대조표.md §4.1 이 정본이다. 6.6 FOS는
구현하지 않는다(같은 문서 §2.1 — 이 프로젝트의 증명 대상 4가지와 접점이
없다).

계층 규칙(CLAUDE.md §2.2) — 이 패키지는 `siap/` 내부 심볼을 import하지
않는다. `contracts/`(Frame·SiapLink·FrameBuilder Protocol)만 참조한다.
"""
