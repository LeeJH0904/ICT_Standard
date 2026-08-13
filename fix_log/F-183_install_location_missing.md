# F-183 · 정상 장치 등록이 필수 설치위치와 단위를 NULL로 저장

| 항목 | 값 |
|---|---|
| 심각도 | 오류 |
| 분류 | 문서불일치 |
| 대상 | `project_code/backend/repository.py:85` · `project_code/backend/repository.py:128` · `project_code/backend/schema.sql:70` |
| 발견일 | 2026-08-11 |
| 상태 | 수정완료 |

## 근거

1369-P1 6.2.5 — 장치설치정보에는 설치위치 등이 포함되어야 한다. 7.2.2.5 — 설치 위치 속성은 속성값과 단위가 함께 포함되어야 한다.

## 현상

`upsert_device_install_info()`의 `install_location`과 `install_loc_unit` 기본값은 `None`이고 `_handle_connection()`은 두 값을 넘기지 않는다. DDL도 nullable이다. 정상 등록 직후 실제 행은 둘 다 NULL이었다. F-170은 기존 위치를 재연결 때 보존하고 측정 행으로 복사할 뿐 위치를 입력하는 경로를 만들지 않았다. F-158 때 같은 6.2.5 문장의 설치일자는 NOT NULL로 보강했으므로 현재 판정은 일관되지 않다. 표준이 옳고 설계·구현이 틀렸다.

## 영향

모든 동적 장치가 위치 없는 설정 데이터가 되고 환경 측정 위치에도 NULL이 전파된다.

## 재현

```python
con = db.init_db('case.db', seed=True)
_connect_sensor(con)
row = con.execute('SELECT install_location,install_loc_unit FROM device_install_info').fetchone()
assert tuple(row) == (None, None)
```

---

## Claude 처리 기록

| 일시 | 상태 | 내용 |
|---|---|---|
| 2026-08-11 | 확인 | **판정(§11.3): 표준이 옳고 설계·구현이 틀렸다.** 재현 그대로 확인 — 정상 REQ_SET_CONNECTION 처리 뒤 `device_install_info.install_location`/`install_loc_unit`는 항상 NULL이었다. 0943 REQ_SET_CONNECTION은 위치를 나르는 필드가 없고(SIAP은 1369-P1의 "설치위치" 개념 자체를 모른다), API 명세서 §3 쓰기 7건에도 장치별 위치를 입력하는 경로가 없다 — F-176(장치 관리자)이 마주쳤던 것과 같은 "이 참조 구현에는 별도 입력 수단이 없다" 상황임을 확인 |
| 2026-08-11 | 수정완료 | F-176과 같은 근거로 해결 — 장치별 세부 위치를 지어내지 않고(CLAUDE.md §1-1), 그 장치가 설치된 **온실 자신의 위치**(`greenhouse_info.location`/`location_unit`, 이미 실존하는 값)를 기본값으로 쓴다. ① `repository.py`에 `get_greenhouse_location()` 신설. ② `ingest.py::_handle_connection()`이 **최초 등록(신규 install 행)일 때만** 이 기본값을 `upsert_device_install_info()`에 넘긴다 — F-170의 COALESCE 보존 의미론과 충돌하지 않기 위해서다: 재연결마다 계속 넘기면 COALESCE가 매번 "새 값이 왔다"고 보고 덮어써, 장차 더 구체적인 위치가 다른 경로로 설정돼도 재연결 한 번에 다시 온실 기본값으로 되돌아간다(F-170이 막으려던 것과 같은 문제가 다른 값으로 재발). 이를 위해 `upsert_device_install_info()` 호출 전에 `find_device_install_by_siap()`로 기존 행 존재를 먼저 확인한다(약간의 중복 조회를 감수) |
| 2026-08-11 | 회귀테스트 | `backend/tests/test_ingest.py`에 2건 신설(최초 등록이 온실 위치를 기본값으로 채움 / 재연결이 이미 설정된 더 구체적인 위치를 온실 기본값으로 되돌리지 않음). `backend/tests/test_repository.py`에 2건 신설(`get_greenhouse_location` 시드 값 조회 / 없는 온실이면 (None,None)). `cd project_code && python -m pytest backend/tests/` **182/182** 재확인 |
