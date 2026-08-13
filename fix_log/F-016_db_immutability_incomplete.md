# F-016 · 표준 유래 불변성 제약이 일부만 구현됨

| 항목 | 값 |
|---|---|
| 심각도 | 오류 |
| 분류 | 코드버그 |
| 대상 | `project_docs/db/schema.sql:447-516`, `project_docs/db/verify.py` |
| 발견일 | 2026-08-03 |
| 상태 | 수정완료 |

## 근거

1369-P1 7.2.2.4~7.2.2.6 — 장치정보·장치설치정보·사용자정보의 생성시간은 "생명주기 동안 수정될 수 없다."

1369-P1 7.2.2.7~7.2.2.10 — 관계를 구성하는 각 외래키는 "생명주기 동안 수정될 수 없다."

1369-P1 7.2.3.4 — 작동환경의 두 외래키는 "생명주기 동안 수정될 수 없다."

1369-P1 7.2.4.2~7.2.4.4 — 관계 식별자는 "데이터의 생명주기 동안 수정될 수 없다."

## 현상

DDL은 일부 트리거만 제공한다. 실제 실행 결과 다음 변경이 모두 허용된다.

- `device_info`, `device_install_info`, `user_info`의 `created_at` 변경
- `greenhouse_own`, `greenhouse_manage`, `device_install`, `device_manage`의 FK 변경
- `operating_env`의 FK 변경
- `device_state`, `env_measure`, `greenhouse_env`의 관계 `id` 변경

`verify.py`의 32개 테스트는 이 항목들을 검사하지 않으므로 전부 통과한다.

## 영향

문서의 "표준이 규정한 무결성 제약을 DDL로 강제" 및 "32/32 통과"가 표준 제약의 완전한 검증처럼 보이지만 실제로는 다수의 명시적 불변 조건이 빠져 있다.

## 재현

```python
import sqlite3
from pathlib import Path
c = sqlite3.connect(":memory:")
c.executescript(Path("schema.sql").read_text(encoding="utf-8"))
c.execute("INSERT INTO device_info(id,created_at,updated_at,device_name,device_kind,model_name) VALUES('d','t0','t0','D','SENSOR','M')")
c.execute("UPDATE device_info SET created_at='t1' WHERE id='d'")
print(c.execute("SELECT created_at FROM device_info WHERE id='d'").fetchone())
# ('t1',) — 변경 허용
```

## 제안

표준이 불변으로 명시한 속성 전체를 목록화해 트리거와 회귀 테스트를 1:1로 추가한다. 검증 결과는 단순 통과 개수뿐 아니라 표준 요구사항 대비 커버리지로 표현한다.

---

## Claude 처리 기록

| 일시 | 상태 | 내용 |
|---|---|---|
| 2026-08-03 | 확인 | 11건 전부 재현 — 생성시간 3종(`device_info`·`device_install_info`·`user_info`), 설정형 관계 FK 4종, 작동환경 FK 1종, 관계 식별자 3종 |
| 2026-08-03 | 수정완료 | 트리거 14개 추가 (총 15 → 29). 조항 번호를 `RAISE(ABORT)` 메시지에 포함. `verify.py`에 회귀 테스트 11종 추가 |
| 2026-08-03 | — | 지적대로 "32/32 통과"가 완전성을 오인하게 했다. 검증 규모를 **56종**으로 확대하고 설계서 §6.2에 항목을 분류별로 명시 |
