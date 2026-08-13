# F-130 · 공통 최소 Period가 디바이스별 전송·Event·오류 감지 의미론을 무효화

| 항목 | 값 |
|---|---|
| 심각도 | 치명 |
| 분류 | 코드버그 |
| 대상 | `project_code/firmware/core/node_state.c:129-188,261-317` · 펌웨어 설계서 §6.3·§6.6 |
| 발견일 | 2026-08-09 |
| 상태 | 수정완료 |

## 근거

0943 표 7-15 — `Period`는 각 `DEVICE_PROPERTY` 안의 14 bit 필드이며 원문은 데이터 전달주기(sec 단위)라고 정한다. 같은 표는 `Transfer Mode`가 Event 또는 Both이면 `Value`가 `Lower Value`보다 작거나 `Upper Value`보다 클 때 값을 전송한다고 정한다.

0943 8.2.1.1 — 오류 현상이 수정될 때까지 Notify Error Interval 간격으로 주기적인 오류 알림메시지를 전달한다고 정한다.

0943 8.2.1.2 — `NOTI_DEVICE_VALUE`는 노드에 연결된 디바이스 값을 주기적으로 알리기 위한 메시지다.

펌웨어 설계서 §6.3도 `Period`를 명시적으로 디바이스별 주기라고 판정하고, §6.6은 Event/Both가 임계 이탈 시 알림을 보낸다고 적는다.

## 현상

`_device_value_period_ms()`는 Periodic/Both 디바이스의 최소 `Period` 하나만 반환한다. `_pending_encode()`는 그 공통 만료마다 Periodic/Both 디바이스 전량을 한 프레임에 넣는다. Period=10초와 60초인 디바이스를 함께 두면 60초 디바이스도 10초마다 전송된다.

`_due_tick()`에는 Event 임계 이탈을 검사하는 경로가 없고, `_scan_devices_for_fault()`도 `SIAP_DUE_DEVICE_VALUE`가 선 뒤에만 호출된다. Event-only 노드는 device-value due가 영원히 생기지 않으므로 임계 이탈 알림도, 디바이스 오류에 따른 `FAULT` 진입도 일어나지 않는다.

구현의 최소 Period 공통 주기 결정은 설계서에 없고 표준의 디바이스별 필드를 노드 공통값으로 축소한다. 소프트웨어 마감시각을 디바이스별로 관리하는 것은 하드웨어 타이머를 디바이스 수만큼 요구한다는 뜻이 아니다.

## 영향

표 7-15의 Period·Transfer Mode 의미론과 8.2.1.1/8.2.1.2 알림 흐름을 구현하지 못한다. 느린 디바이스는 과다 전송되고 Event/Both의 이벤트 부분은 동작하지 않으며, Event-only 노드의 오류는 영구히 보고되지 않는다. 표준 참조 구현이라는 핵심 주장이 무너진다.

## 재현

저장소 파일은 바꾸지 않고 `test_node_state.c`를 stdin으로 GCC에 전달하면서 반례를 추가했다.

```text
Period=10/60초 두 디바이스, t=10초: payload_len 7 기대 -> FAIL(실제 14)
Event, lower=0/upper=10/value=100: NOTI_DEVICE_VALUE 기대 -> FAIL
Event-only read 실패, 60초 경과: FAULT 기대 -> FAIL
기존 61개는 전부 PASS, 주입 4개 중 위 세 개 FAIL (61/65)
```

## 제안

최소 Period 공통 주기는 CLAUDE.md §3.5나 설계서 §9에 정식 결정으로 추가하지 않는다. 디바이스별 Period와 Event/Both를 보존하는 스케줄을 먼저 결정해야 한다. 오류 감지 주기는 표준 미규정 결정으로 기록할 수 있지만 Event-only를 포함한 모든 유효 구성에서 감지가 일어나는 정책을 확정한 뒤 기록한다.

---

## Claude 처리 기록

| 일시 | 상태 | 내용 |
|---|---|---|
| 2026-08-09 | 확인 | 재현 스크립트와 동일하게 `_device_value_period_ms()`가 Periodic/Both 중 최소 Period 하나만 돌려주고 `_pending_encode()`가 그 공통 만료마다 Periodic/Both 전량을 묶어 보냄을 소스에서 확인. `_due_tick()`에 Event 임계 검사 경로가 없고 `_scan_devices_for_fault()`도 DUE_DEVICE_VALUE bit가 선 뒤에만 불려 Event-only 노드는 오류 감지 자체가 발생하지 않음을 확인 |
| 2026-08-09 | 수정완료 | **결정(표준 미규정, CLAUDE.md §3.5 대상 — 사용자 보고 예정): Period(표 7-15)는 Transfer Mode 와 무관하게 "이 디바이스를 얼마나 자주 스캔하는가"다.** Periodic/Both/Event 세 모드 전부 자기 Period 로 스캔되고, 스캔 *결과의 처리* 만 Transfer Mode 가 가른다 — Periodic·Both 는 스캔마다 무조건 전송, Event 는 [Lower Value, Upper Value] 밖일 때만 전송(값 해석은 `siap_value_as_int/uint/float()`로 `Value Type` 을 따름, F-022). 오류 감지(8.2.1.1)도 이 스캔에 얹혀 Event-only 노드도 자기 Period 로 감지한다 — Periodic 존재 여부에 기대지 않는다. 구현: `node_state.h`에 `dev_next_due[16]`(디바이스별 다음 스캔 절대시각)·`dev_due`(스캔 대기 비트마스크) 추가, `t_device_value` 단일 타이머 제거. `node_state.c`에 `_dev_due_tick()`(디바이스별 스케줄 진행)·`_dp_out_of_range()`(타입별 임계 비교) 신설, `_due_send_next()`의 DEVICE_VALUE 분기를 이번 스캔에서 due 로 표시된 디바이스만 순회하도록 재작성(읽기 실패 첫 건에서 FAULT 로 중단, 그 전까지 성공한 디바이스는 값만 갱신하고 이번 회차엔 미전송 — 다음 스캔에서 재시도되므로 유실이 아니라 한 주기 지연). `_pending_encode()`의 NOTI_DEVICE_VALUE 는 `pending.arg` 비트마스크(보낼 devices[] 인덱스)로 요소를 정한다(재전송에도 유지, F-041과 합치). 회귀 테스트 3종을 `test_node_state.c`에 추가: `test_device_specific_period_scheduling_F130`(Period=10s/60s 두 디바이스가 독립 스케줄로 동작, 60s 시점엔 함께 due), `test_event_mode_sends_only_out_of_range_F130`(범위 안일 땐 미전송, Upper Value 이탈 시 전송), `test_event_only_fault_detection_F130`(Event 단독 디바이스도 자기 Period 로 오류 감지). 결함 주입: `_dp_out_of_range()`를 항상 `false` 를 돌려주도록 되돌린 사전수정본으로 실행 — Event 테스트 2건이 정확히 실패(87/89)함을 확인, 원복 후 재통과. `test_bitpack`(41/41)·`test_siap_frame`(143/143)·`test_status_codes`(53/53)·`test_golden`(253/253)·`tools/core_purity_verify.py`(7/7)·`project_docs/firmware/firmware_verify.py`(51/51)·`tools/run_all.py`(12/12) 회귀 확인. `docs/standard-findings.md`(표준결함 전용, §3.6)이 아니라 CLAUDE.md §3.5 표에 이 결정을 추가할지는 세션 보고에서 사용자에게 확인 요청 |
| 2026-08-09 | 수정완료(정본화) | 사용자 검토로 최초 정본화 문구("Period는 Transfer Mode와 무관한 스캔 주기다")가 표 7-15의 표준 의미("데이터 전달주기")를 재정의하는 것으로 읽힌다는 지적을 받아들여 **문구를 표준 의미/구현 재사용으로 분리**했다 — "Period의 표준상 의미는 데이터 전달주기다. 본 구현은 별도 샘플링 주기 필드가 없어 이를 내부 스캔 간격으로도 재사용할 뿐이며, 표준 필드 의미의 재정의가 아니다." `node_state.c`(§`_dev_due_tick`)·`node_state.h`(`dev_next_due`/`dev_due` 필드 주석) 두 곳의 동일 과잉주장도 같은 문구로 고쳤다. 사용자가 추가로 지적한 미결정 공백 2건을 별도 행으로 분리해 결정하고 기록했다: **(1) Both 모드** — 이 구현은 디바이스당 스캔이 자기 Period 한 번뿐이라 Both가 사실상 Periodic과 동일하게 동작한다(이벤트 조기 감지 없음). 대안(디바이스별 두 번째 스케줄·전역 이벤트 틱)을 검토했으나 AVR 2KB SRAM·타이머 3종 예산과 충돌하는 구현 확대가 필요해 채택하지 않았다 — 사용자가 이 이유를 결정 근거에 명시하도록 요청함. **(2) Period=0** — 사실상 매 poll 스캔(현행 `_advance_deadline`의 `interval==0 → now+1` 동작)으로 허용, §4.1-a 하한 미설정 유지. 코드 변경 없음(두 결정 모두 기존 동작을 정본으로 채택). 문서 3곳에 동일 내용으로 반영: `CLAUDE.md` §3.5(3행 추가) · `펌웨어_설계서.md` §6.3(표준 의미/재사용 분리 서술 + Transfer Mode별 조건표 + Both 제약 서술 + Period=0 서술 추가) · §9(3행 추가, §0 요약 "여섯"→"아홉" 동기화). `project_docs/firmware/firmware_verify.py`의 F-074 교차검증(0절 한글 수사=9절 표 행수) 51/51 재통과로 수치 일치 확인. `tools/run_all.py` 12/12·`fix_log/meta_verify.py` 91/91·`tools/where.py`(단계 2c 유지) 회귀 확인 |
