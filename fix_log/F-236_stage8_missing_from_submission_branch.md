# F-236 · 현재 제출 브랜치에 단계 8 산출물이 없음

| 항목 | 값 |
|---|---|
| 심각도 | 치명 |
| 분류 | 요건위반 |
| 대상 | 현재 `Branch_1` · 단계 8 산출물 |
| 발견일 | 2026-08-16 |
| 상태 | 수정완료 |

## 근거

공고문 「소스코드 제출 안내」 재현성 — “제출물만으로 실제 실행(재현)이 가능한 전체 소스코드를 제출해야 함.” 진위·창작성 조항은 제출 소스가 영상·시연 구현과 일치해야 한다고 정한다.

## 현상

현재 Branch_1에는 두 AVR 소스와 board_verify.py와 DHT22 로그가 없고 Branch_2에만 있다.

## 영향

현재 브랜치 제출 시 완료한 AVR 실연동을 재현할 수 없다.

## 재현

HEAD 트리에는 없고 Branch_2 트리에는 있다.

---

## 작업자 처리 기록

| 일시 | 상태 | 내용 |
|---|---|---|
| 2026-08-17 | 확인 | 신고 전제("Branch_1에 단계 8 산출물 없음")가 직전 세션의 브랜치 복구·push로 이미 해소됨을 확인. `git ls-tree -r HEAD` 로 `arduino_sensor_node`·`arduino_actuator_node`·`esp32_node`·`tools/board_verify.py`·`project_code/logs/session_01_uno_dht22.jsonl` 전부 존재, `node_state.c` F-198 선언 11건·sensor `.ino` DHT22 5건 확인. `origin/Branch_1`과 `1e69a1e`로 0 ahead/0 behind. |
| 2026-08-17 | 수정완료 | 제출 브랜치 `Branch_1` HEAD가 단계 8 산출물 전량을 포함하고 원격과 동기화됨. 별도 코드 변경 없이 복구로 해소. (참고: `Branch_2`는 병행 브랜치로, 제출 대상은 `Branch_1`.) |
