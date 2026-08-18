"""
backend/services/ — TTAK.KO-10.0937 서비스 계층. ems·dms·mms·fms·fcs 5종.

조항 ↔ 모듈 배정은 0937 요구사항을 따른다. 6.6 FOS는
이 프로젝트의 증명 대상 4가지와 접점이 없어 구현하지
않는다.

계층 규칙 — 이 패키지는 `siap/` 내부 심볼을 import하지
않는다. `contracts/`(Frame·SiapLink·FrameBuilder Protocol)만 참조한다.
"""
