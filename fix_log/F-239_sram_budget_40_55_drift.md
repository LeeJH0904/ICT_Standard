# F-239 · 단계 8 SRAM 예산이 40%와 55%로 분기됨

| 항목 | 값 |
|---|---|
| 심각도 | 오류 |
| 분류 | 문서불일치 |
| 대상 | `Branch_2` 개발 지시서·펌웨어 설계서·BUILD.md·where.py·board_verify.py |
| 발견일 | 2026-08-16 |
| 상태 | 수정완료 |

## 근거

개발 착수 지시서 §1.5 — “SRAM 예산은 전체 globals ... 기준 55% 이하”이며 `board_verify.py`가 대조한다.

## 현상

지시서와 `board_verify.py`는 55%로 Uno 1,038B·Pro Mini 1,057B를 통과시킨다. 반면 BUILD.md §4, 펌웨어 설계서 검증표, `where.py`는 40%를 요구한다.

## 영향

같은 실측값이 board_verify에서는 통과하고 where에서는 실패하여 현재 합격선을 재현할 수 없다.

## 제안

55% 전체-globals와 과거 40% 슬라이스의 의미를 분리하고 모든 현재 출구를 동기화한다.

---

## 작업자 처리 기록

| 일시 | 상태 | 내용 |
|---|---|---|
| 2026-08-17 | 확인 | **판정: 55% 전체-globals 가 정본.** 개발_착수_지시서 §1.5·펌웨어 설계서 §3.4(2026-08-16 결정)가 이미 "avr-size / Arduino 'Global variables use' 기준 전체 globals 55%"로 명문화했고 `board_verify.py`(§6.1 게이트)가 이 55%를 `size_report.txt` 와 실측 대조한다. 40%는 분모가 다른 *펌웨어 데이터 슬라이스* 추정치(§3.5, `firmware_verify.py` 전용). 스테일 40%가 `where.py`·`BUILD.md:74`·`펌웨어_설계서:1129` 세 곳에 남아 board_verify(55%)와 어긋났음을 확인. |
| 2026-08-17 | 수정완료 | (1) `where.py` 의 40% 상수·판정 로직은 F-238 처리로 제거(예산 대조를 board_verify 55%에 위임). (2) `BUILD.md:74` 를 "전체 globals 2048B의 55% = 1126B(§3.4, board_verify.py), 40%는 슬라이스 추정(firmware_verify.py)"으로 정정. (3) `펌웨어_설계서:1129` 를 "§3.4 표 실측 교체·전체-globals 55% 이하(board_verify 정본), 슬라이스 40%는 firmware_verify 분리"로 정정. 이제 모든 현재 출구가 55% 전체-globals 로 단일. |
