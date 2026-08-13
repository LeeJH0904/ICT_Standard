# F-176 · 동적 설치 장치의 관리자 관계가 항상 누락됨

| 항목 | 값 |
|---|---|
| 심각도 | 오류 |
| 분류 | 문서불일치 |
| 대상 | `project_docs/arch/아키텍처_설계서.md:336` · `project_code/backend/ingest.py:151` |
| 발견일 | 2026-08-11 |
| 상태 | 수정완료 |

## 근거

TTAK.KO-10.1369-Part1 7.1(7) — “설치된 장치들은 1명의 사용자에 의해 관리된다.”

TTAK.KO-10.1369-Part1 7.2.2.10은 사용자 정보와 장치설치 정보 사이의 `장치 관리` 관계를 정의한다.

## 현상

아키텍처 §4.4-a는 `device_manage`를 시드 로더 전용으로 분류하고 “이후 어느 스레드도 쓰지 않는다”고 정한다. 그러나 시드에는 설치 장치가 없고, `REQ_SET_CONNECTION`을 처리하는 `_handle_connection()`은 `device_info`, `device_install_info`, `device_install`만 만든다. 따라서 런타임에 등록된 모든 장치의 `device_manage` 행은 0개다. 구현이 설계를 따랐지만 표준 원문과 충돌하므로 표준이 옳고 설계·구현이 틀렸다.

## 영향

표준의 N:1 장치관리 관계가 참조 구현의 정상 Plug & Play 경로에서 성립하지 않는다. DDL의 `UNIQUE(install_id)`는 관리자가 둘 이상인 경우만 막고, 관리자 0명은 막지 못한다.

## 재현

```text
seed=True DB에 정상 REQ_SET_CONNECTION 1건을 ingest.handle()로 처리
SELECT COUNT(*) FROM device_install_info;  -- 1
SELECT COUNT(*) FROM device_manage;        -- 0
```

## 제안

동적 설치 시 기본 온실의 관리자와 `device_manage`를 같은 트랜잭션에서 결속하도록 설계의 쓰기 소유권부터 정정한다.

---

## Claude 처리 기록

| 일시 | 상태 | 내용 |
|---|---|---|
| 2026-08-11 | 확인 | **판정(§11.3): 표준이 옳고 설계·구현이 틀렸다.** `schema.sql` 자신의 주석(`device_manage` 테이블 정의 바로 위, F-176 조사 중 재확인)도 이미 "7.1(7) 설치된 장치들은 1명의 사용자에 의해 관리된다"를 근거로 `UNIQUE(install_id)`를 걸어 뒀다 — 즉 스키마 설계 의도 자체는 표준을 정확히 읽었는데, 아키텍처 설계서 §4.4-a가 `device_manage`를 "시드 로더 전용·런타임 쓰기 금지"로 잘못 분류했고 `_handle_connection()`이 그 분류를 그대로 따라 이 관계를 채우지 않았다. 재현 그대로 확인 — seed 뒤 정상 REQ_SET_CONNECTION 1건 처리 시 `device_install_info`=1, `device_manage`=0 |
| 2026-08-11 | 수정완료 | ① `backend/repository.py`에 `get_greenhouse_manager_user_id()`(1369-P1 §7.1(3) `greenhouse_manage`에서 조회) · `link_device_manage()`(`link_device_install()`과 같은 멱등 패턴, `UNIQUE(install_id)` 존재 확인 후 INSERT) 신설. ② `backend/ingest.py::_handle_connection()`이 `link_device_install()` 직후 `link_device_manage()`를 부르도록 결선 — 관리자는 그 장치가 설치된 온실의 관리자를 그대로 쓴다(이 데모는 온실 1개 고정이라 유일하게 결정됨, 별도 "장치 관리자 지정" API가 없다는 §3.5 신규 결정과 함께 CLAUDE.md §3.5·아키텍처 설계서 §4.4-a에 기록). ③ 아키텍처 설계서 §4.4-a — `device_manage`를 ①(시드 전용, 9개→**8개**)에서 ②(SIAP I/O 스레드, 19개→**20개**)로 이동, `9+19+2+1=31` → `8+20+2+1=31`로 갱신, F-176 설명 각주 추가. ④ `fixtures/seed.sql` 머리말 주석 — "이후 어느 스레드도 쓰지 않는다" 목록에서 `device_manage` 제거, 새 경로 설명 추가 |
| 2026-08-11 | 회귀테스트 | `backend/tests/test_repository.py`에 3건(`get_greenhouse_manager_user_id` 정상/None, `link_device_manage` 멱등) 신설. `backend/tests/test_ingest.py`에 2건(`_handle_connection` 뒤 `device_manage` 채워짐, 재연결 시 중복 없음) 신설. `cd project_code && python -m pytest backend/tests/` **168/168**. `python fix_log/meta_verify.py`의 "쓰기 소유권 분류 파싱" 검사가 문서를 다시 파싱해 `값=8 값=20 값=2 값=1`·"테이블 31개를 전부 덮음"을 자동으로 재확인(하드코딩된 숫자가 없어 문서 수정만으로 검증기가 새 분류를 인식) — **97/97** 재확인. `python tools/run_all.py` **15/15** 재확인 |
