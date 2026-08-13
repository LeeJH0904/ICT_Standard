# F-015 · 1:N 관계의 단일 부모 카디널리티 미강제

| 항목 | 값 |
|---|---|
| 심각도 | 오류 |
| 분류 | 코드버그 |
| 대상 | `project_docs/db/schema.sql:108-143` |
| 발견일 | 2026-08-03 |
| 상태 | 수정완료 |

## 근거

1369-P1 7.1(1) — "특정한 1개의 온실은 1개의 농장에만 포함된다."

1369-P1 7.1(3) — "온실 정보는 사용자 정보와 N:1 '온실 관리' 관계를 가진다."

1369-P1 7.1(4) — "1개의 장치는 1개의 온실에 설치될 수 있다."

1369-P1 7.1(7) — "설치된 장치들은 1명의 사용자에 의해 관리된다."

그림 7-1·7-2도 동일한 1:N/N:1 카디널리티를 표시한다.

## 현상

`greenhouse_own`, `greenhouse_manage`, `device_install`, `device_manage`은 두 FK의 복합 기본키만 가진다. 따라서 동일한 자식 식별자에 서로 다른 부모 식별자를 조합하면 모두 삽입된다. 복합 PK는 동일한 쌍의 중복만 막을 뿐 1:N의 단일 부모 조건을 강제하지 않는다.

## 영향

하나의 온실이 여러 농장에 동시에 속하거나, 하나의 설치 장치가 여러 온실·여러 관리자에 동시에 귀속될 수 있다. ER 모델을 직역하고 관계 무결성을 DDL로 강제한다는 설계 원칙이 성립하지 않는다.

## 재현

```python
import sqlite3
from pathlib import Path
c = sqlite3.connect(":memory:")
c.executescript(Path("schema.sql").read_text(encoding="utf-8"))
c.execute("PRAGMA foreign_keys=ON")
c.execute("INSERT INTO user_info(id,created_at,updated_at,name) VALUES('u1','t','t','U1'),('u2','t','t','U2')")
c.execute("INSERT INTO farm_info(id,created_at,updated_at,name,owner_id) VALUES('f1','t','t','F1','u1'),('f2','t','t','F2','u2')")
c.execute("INSERT INTO greenhouse_info(id,created_at,updated_at,name) VALUES('g1','t','t','G1')")
c.execute("INSERT INTO greenhouse_own VALUES('f1','g1')")
c.execute("INSERT INTO greenhouse_own VALUES('f2','g1')")  # 성공 — 표준상 허용되면 안 됨
```

## 제안

각 1:N 관계의 자식 FK에 적절한 `UNIQUE` 제약을 추가하고 네 관계 모두에 회귀 테스트를 추가한다.

---

## Claude 처리 기록

| 일시 | 상태 | 내용 |
|---|---|---|
| 2026-08-03 | 확인 | 지적된 4건뿐 아니라 **8건 전부** 미강제임을 재현. 1369-P1 **7.1 개념적 모델** 원문 대조 결과 (1)(3)(4)(5)(7)(8)(9)(10)이 모두 1:N 또는 N:1을 명시하고 있음 |
| 2026-08-03 | 수정완료 | 관계 테이블 8종에 `UNIQUE` 제약 추가 — `greenhouse_own(greenhouse_id)`, `greenhouse_manage(greenhouse_id)`, `device_install(install_id)`, `device_manage(install_id)`, `device_state(device_state_id)`, `env_measure(env_state_id)`, `greenhouse_env(env_state_id)`, `operating_env(env_state_id)`. 각 제약에 조항 번호 주석 부착. 회귀 테스트 8종 추가 |
| 2026-08-03 | — | **근본 원인**: 7.2 논리적 모델은 "쌍 유일성"만 규정하고 실제 카디널리티는 7.1 개념적 모델에 있다. 설계 시 7.1을 읽지 않은 것이 원인. DB 설계서에 §4.1-a로 명문화 |
