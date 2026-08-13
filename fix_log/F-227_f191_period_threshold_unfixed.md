# F-227 · F-191 수정완료 뒤에도 미수집 기준이 고정 900초

| 항목 | 값 |
|---|---|
| 심각도 | 오류 |
| 분류 | 코드버그 |
| 대상 | `project_code/backend/services/fms.py:45-71` · `project_code/backend/tests/test_services_fms.py:41,65-70` · F-191 |
| 발견일 | 2026-08-13 |
| 상태 | 신규 |

## 근거

TTAK.KO-10.0937 §6.4 — “데이터 수집 주기 및 구역을 지정하여 정해진 시간에 환경 데이터를 수집 할 수 있어야 한다.”

같은 절 — “정해진 시간에 데이터가 수집되지 않는 경우 사용자 및 관리자 알림 기능을 제공할 수 있어야 한다.”

`0937_요구사항_대조표.md` §1.4는 이를 디바이스별 `Period × 3`으로 판정한다.

## 현상

F-191은 이 함수가 디바이스별 Period가 아니라 전역 300초를 쓴다는 점을 첫 번째 결함으로 기록했다. 그러나 수정완료 처리에는 호출 결선과 알림 경로만 반영됐고 이 부분은 남았다.

현재 `check_stale_devices()`는 `DEFAULT_PERIOD_SEC=300`에 배수 3을 적용해 모든 디바이스를 900초로 판정한다. 회귀 테스트도 프레임에서 `period=60`을 선언한 뒤 기대 임계값을 디바이스 Period가 아니라 같은 전역 상수로 계산하여 결함을 정상값으로 고정한다.

Period 60초인 센서의 마지막 측정 후 181초 시점에 직접 판정했을 때 `created=[]`, alert 0건이었다. 요구·대조표 기준 임계점은 180초다.

## 영향

짧은 주기로 수집해야 하는 센서의 데이터가 끊겨도 최대 12분 더 늦게 알림이 발생한다. F-191의 상태만 `수정완료`이고 그 원 지적 일부는 실제로 고쳐지지 않았다.

## 재현

```python
from pathlib import Path
from tempfile import TemporaryDirectory
import sys
sys.path.insert(0, str(Path(backend/tests).resolve()))

from backend import db, repository
from backend.services import fms
from test_services_fms import _connect_and_report_temperature, _future_iso

with TemporaryDirectory() as td:
    conn = db.init_db(Path(td) / fms.db, seed=True)
    _connect_and_report_temperature(conn)  # DeviceProperty.period == 60
    created = fms.check_stale_devices(conn, _future_iso(181))
    print(created, len(repository.list_alerts(conn)))
    conn.close()
# [] 0
```

## 제안

마지막 측정값과 함께 해당 디바이스의 실제 Period를 영속·조회해 각각 `Period × 3`으로 판정하고, 테스트는 60초 선언에 대해 180초 경계를 독립 상수로 대조한다.

---

## Claude 처리 기록

| 일시 | 상태 | 내용 |
|---|---|---|

