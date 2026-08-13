# F-216 · mode 검증기가 골든 밖의 새 센서값을 통과

| 항목 | 값 |
|---|---|
| 심각도 | 오류 |
| 분류 | 코드버그 |
| 대상 | `tools/mode_verify.py:361` · `project_code/sim/virtual_node.py:92` |
| 발견일 | 2026-08-12 |
| 상태 | 신규 |

## 근거

공고문 「소스코드 제출 안내」 진위·창작성 — “제출한 소스코드는 증빙영상·발표 시연의 구현 내용과 일치해야” 한다. `CLAUDE.md` §1-1은 단계 4~7 예외를 **골든 벡터 원본 그대로의 재사용**으로 한정한다. 개발 착수 지시서 §1.4는 신설 검증기가 함수 존재가 아니라 호출 결과를 검사해야 한다고 정한다.

## 현상

`check_simulate_populates_devices_and_telemetry()`는 장치 4개와 텔레메트리·장치상태 행이 생겼는지만 본다. `VirtualNodeServer`가 사용한 `(Subtype, Value Type, Value)`가 `contracts/vectors/golden.jsonl`에 실제로 존재하는지는 대조하지 않는다.

현재 저장소의 값은 골든 원본과 일치하므로 합성 데이터 위반은 아니다. 그러나 런타임에서 값 풀을 골든에 없는 온도 26.7, 습도 62.5, 관수밸브 77로 치환해도 `mode_verify.py`는 11/11, 종료 코드 0을 냈다. 세 쌍 모두 골든 53건의 값 집합에 없음을 먼저 확인했다.

## 영향

골든 원본 재사용이라는 F-148·F-152 기각 조건이 회귀 가드에 들어 있지 않다. 개발자가 새 고정 센서값을 넣어도 단계 4 출구와 `run_all.py`가 녹색이므로, CLAUDE.md §1-1 위반을 검증기가 막지 못한다.

## 재현

```python
from sim import virtual_node as vn
from tools import mode_verify

vn._load_value_pool = lambda: {
    vn.SUBTYPE_TEMPERATURE: (2, 1104517530),       # FLOAT 26.7, 골든에 없음
    vn.SUBTYPE_HUMIDITY: (2, 1115291648),          # FLOAT 62.5, 골든에 없음
    vn.SUBTYPE_IRRIGATION_VALVE: (1, 77),          # UINT 77, 골든에 없음
}
assert mode_verify.main() == 0
# 실측: 11/11 통과
```

---

## Claude 처리 기록

| 일시 | 상태 | 내용 |
|---|---|---|
| | | |
