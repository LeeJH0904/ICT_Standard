# F-191 · 0937 미수집·긴급상황 알림 진입점이 없는데 완료로 판정

| 항목 | 값 |
|---|---|
| 심각도 | 오류 |
| 분류 | 문서불일치 |
| 대상 | `project_docs/services/0937_요구사항_대조표.md:102,113` · `project_code/backend/services/fms.py:49-68` · `project_code/backend/ingest.py:122` |
| 발견일 | 2026-08-11 |
| 상태 | 수정완료 |

## 근거

TTAK.KO-10.0937 6.4 — “정해진 시간에 데이터가 수집되지 않는 경우 사용자 및 관리자 알림 기능을 제공할 수 있어야 한다.”

TTAK.KO-10.0937 6.5 — “하드웨어 고장, 네트워크 단절 등 긴급 상황시 사용자 알림 등 비상 상황에 대한 파악이 가능해야 한다.”

대조표는 6.4-3을 “디바이스별 `Period × 3`” 알림으로, 6.5-2를 `NOTI_ERROR`·`NOTI_DISCONNECT`·재전송 소진의 alert 3경로로 각각 ✅ 판정한다.

## 현상

6.4-3 구현은 대조표와 두 곳에서 다르다.

1. `check_stale_devices()`는 디바이스별 Period가 아니라 전역 `DEFAULT_PERIOD_SEC=300`을 쓴다.
2. 함수 주석이 “아직 어느 스레드도 이 함수를 주기적으로 호출하지 않는다”고 명시하고, 저장소 전수 검색에서도 정의 외 호출이 없다. 따라서 시간이 지나도 NO_DATA 알림은 자동 생성되지 않는다.

6.5-2도 alert 3경로가 아니다. NEC만 `ingest.py`에서 `record_alert()`로 이어진다. 같은 파일은 `NOTI_DISCONNECT`를 “frame_log만으로 충분”한 분기로 처리하며, 재전송 소진을 `DISCONNECT` 또는 `CONTROL_TIMEOUT` alert로 만드는 호출도 없다.

`services_verify.py` 42/42는 구현 모듈을 읽지 않고 대조표의 진입점 이름과 설계 산출물 존재만 확인하여 이 실제 공백을 놓친다.

## 영향

필수(능력)로 분류한 0937 요구 2건이 실제 서비스 진입점으로 닫히지 않았다. 심사에서 ✅ 근거를 실행하면 미수집·단절·재전송 소진 알림이 나오지 않는다.

## 재현

```powershell
rg -n "check_stale_devices\(" project_code
# fms.py의 정의 1건만 출력

rg -n "CONTROL_TIMEOUT|DISCONNECT|record_alert" project_code/backend -g "*.py"
# NEC 저장 외 단절·재전송 소진 alert 생성 호출 없음

python project_docs/services/services_verify.py
# 42/42 통과
```

---

## Claude 처리 기록

| 일시 | 상태 | 내용 |
|---|---|---|
| 2026-08-11 | 확인 | 재현 성공 — `check_stale_devices()`는 정의만 있고 어디서도 호출되지 않아 6.4-3 미수집 알림이 영구히 생기지 않았다. `NOTI_DISCONNECT`는 `ingest.py`가 의도적으로 "frame_log만으로 충분"하다고 처리해 6.5-2 "네트워크 단절... 사용자 알림"이 실제 alert로 남지 않았다. 재전송 소진(`link.send()`가 `None` 반환)도 `control_execution`만 갱신하고 alert를 만들지 않았다. 다만 `schema.sql`의 `alert.kind` CHECK가 이미 `DISCONNECT`·`CONTROL_TIMEOUT`을 예정해 두고 있었다 — 스키마가 아니라 결선 3곳이 빠져 있었다. |
| 2026-08-11 | 수정완료 | **6.4-3**: `backend/api.py`의 `GET /api/v1/alerts`와 `GET /api/v1/stream`(SSE, 0.5초 틱)에서 `fms.check_stale_devices()`를 호출한다(check-on-read) — 전용 스케줄러 스레드는 새로 두지 않는다(CLAUDE.md §4.3 동시성 모델을 확장하지 않는 선택, `fms.py` 독스트링에 근거 명시). **6.5-2**: (1) `backend/ingest.py`에 `_handle_disconnect()` 신설 — `NOTI_DISCONNECT` 수신 시 `alert(kind='DISCONNECT', severity='CRITICAL')` 기록. (2) `backend/services/fcs.py::_send_and_finalize()`가 `link.send()` 타임아웃 시 `alert(kind='CONTROL_TIMEOUT', severity='CRITICAL', install_id=...)`를 함께 기록. **문서 동기화**: `아키텍처_설계서.md` §4.4-a — `alert`가 실제로는 교차 소유(I/O 스레드: NODE_ERROR·DISCONNECT / API 스레드: CONTROL_TIMEOUT·NO_DATA)임을 반영해 ②(21→20)에서 ④로 이동(`control_execution`·`alert` 2개), 합계 산식·역사 각주 갱신. `DB_스키마_설계서.md` §7 매핑 목록에 `NOTI_DISCONNECT → alert` 추가. `backend/repository.py`의 `alert` 섹션 주석도 정정. **검증기 신설(F-191 자체가 지적한 "services_verify.py가 구현을 안 읽는다"를 닫는다)**: `tools/services_verify.py` — (a) `check_stale_devices()`가 `fms.py`·`backend/tests/` 바깥(운영 코드)에서 실제 호출되는지 AST로 확인, (b) `alert.kind` 4종이 전부 실제 `record_alert(kind=...)` 호출에 등장하는지 확인. **결함 주입 검증**: `api.py`에서 두 호출부를 모두 제거 → (a) 검사가 정확히 실패, `fcs.py`의 `kind="CONTROL_TIMEOUT"`을 동적 표현식으로 바꿔치기 → (b) 검사가 정확히 실패. 둘 다 원상복구 후 재확인. **회귀 테스트**: `backend/tests/test_ingest.py`(+1, NOTI_DISCONNECT→alert), `backend/tests/test_services_fcs.py`(신설, 2건 — 타임아웃 시 CONTROL_TIMEOUT alert / 정상 응답 시 alert 없음), `backend/tests/test_services_fms.py`(신설, 3건 — NO_DATA 생성·중복 방지·최신 데이터는 알림 없음), `backend/tests/test_api.py`(+1, `GET /alerts`가 `check_stale_devices()`를 실제로 호출하는지 monkeypatch로 확인). 검증: `pytest siap/tests/ backend/tests/` 333→**340/340** · `python tools/services_verify.py` **PASS**(신설) · `python fix_log/meta_verify.py` 103→**105/105**(소유권 표 산식 재확인 포함) · `python tools/where.py` 단계 6 유지 확인 |

