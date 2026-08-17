# F-238 · 단계 8 빌드 출구가 세 보드 모두 실패

| 항목 | 값 |
|---|---|
| 심각도 | 오류 |
| 분류 | 코드버그 |
| 대상 | `Branch_2:tools/where.py` · 보드 3종 |
| 발견일 | 2026-08-16 |
| 상태 | 수정완료 |

## 근거

개발 착수 지시서 §1.2 — “출구 조건은 명령이다.” §3.10 출구 ①은 보드 3종 빌드 성공이다.

## 현상

`where.py::_build_and_size()`는 Makefile을 요구하지만 세 보드에 Makefile이 없다. BUILD.md는 IDE·arduino-cli만 안내한다. 그래서 단계 8 직접 판정은 3종 모두 실패하지만 `run_all.py`는 21/21을 보고한다.

## 영향

완료 신고와 저장소의 단계 판정이 반대이며, 제출물만으로 같은 빌드 출구를 재실행할 수 없다.

## 재현

```text
tools.where.check_stage_8()
=> sensor/actuator/esp32 모두 (False, 'Makefile 없음')
```

## 제안

실제 지원하는 빌드 방식을 단계 출구와 하나로 맞춘다.

---

## 작업자 처리 기록

| 일시 | 상태 | 내용 |
|---|---|---|
| 2026-08-17 | 확인 | `where.py::_build_and_size` 가 `board_dir/Makefile` 을 요구하나 세 보드에는 Makefile 이 없다(설계상 Arduino IDE/arduino-cli 빌드, BUILD.md §2). 반면 `run_all.py` 는 `*_verify.py` 를 glob 으로 찾아 `board_verify.py`(실제 §3.10 게이트, size_report.txt↔55% 실측·SKIP 의미론)를 돌리므로 통과 — `where.py` 직접 판정만 3종 FAIL 이라 완료 신고와 저장소 판정이 어긋났다. `where.py` 는 run_all·§6.1 게이트에 포함되지 않는 독립 단계 진단기임을 확인. |
| 2026-08-17 | 수정완료 | `where.py::check_stage_8` 에서 죽은 `_build_and_size`(Makefile 요구·40% 지표) 와 관련 상수(`SRAM_BUDGET_BYTES`·`SRAM_BUDGET_RATIO`·`_parse_avr_size`·`_AVR_SIZE_RE`·`BOARD_DIRS`)를 제거. avr-size↔예산 실측은 `board_verify.py`(55% 정본)에 위임하고, 물리 3종 빌드는 툴체인 의존이라 MANUAL 항목으로 남김. 결과 `check_stage_8` = MANUAL(실물 빌드) · board_verify OK · MANUAL(로그 replay). `test_where.py` 4/4 유지(해당 테스트는 stage_2c·stage_0 만 참조, 제거 심볼 미사용). |

