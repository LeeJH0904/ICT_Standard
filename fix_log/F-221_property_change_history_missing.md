# F-221 · 사용자 속성 변경이 이력 없이 저장됨

| 항목 | 값 |
|---|---|
| 심각도 | 오류 |
| 분류 | 코드버그 |
| 대상 | `project_code/backend/services/ems.py:120-136` · `project_code/backend/repository.py:702-716` · `project_docs/arch/아키텍처_설계서.md` §4.4-a |
| 발견일 | 2026-08-13 |
| 상태 | 수정완료 |

## 근거

TTAK.KO-10.1369-Part1 §6.2.1 — “설정형 데이터는 데이터의 변경(생성, 수정, 삭제)에 대해 이력이 관리되어야 한다.” 같은 절은 설정형 데이터에 장치정보와 장치설치정보가 포함되어야 한다고 정한다.

아키텍처 §4.4-a는 `device_install_info`와 `config_change_log`를 SIAP I/O 스레드 소유로 분류하고, API 스레드 소유 테이블은 `control_rule`과 `public_data_record` 두 개뿐이라고 정한다.

## 현상

API 스레드의 `PATCH /device-property`가 `ems.set_device_property()`를 동기 호출하고, 성공 응답 뒤 같은 API 연결로 I/O 소유 `device_install_info`를 UPDATE한다. 이 경로는 `record_config_change()`를 호출하지 않는다.

F-182 회귀 테스트는 노드발 등록·재선언의 `get_or_create_device_info()`와 `upsert_device_install_info()`만 검사한다. 사람이 유발한 `update_device_property()` 경로는 빠져 있다.

## 영향

사용자가 수행한 설정 변경이 1369-Part1의 필수 이력에서 사라진다. 동시에 구현의 실제 쓰기 소유권이 설계 표와 달라져, “교차 지점은 `control_execution`·`alert` 2개”라는 동시성 전제가 성립하지 않는다.

## 재현

신선한 DB에서 실제 저장소 API로 장치를 만든 뒤 `update_device_property()`를 호출했다. 별도 전체 경로 재현에서는 `ems.set_device_property()`에 성공 RSC를 반환시켜 같은 결과를 확인했다.

```text
property_changed=True
config_history_before=2
config_history_after=2
new_history_rows=0
```

## 제안

사람이 유발한 설정 변경의 테이블·컬럼 소유자를 아키텍처에 명시하고, 성공 UPDATE와 같은 트랜잭션에서 변경 필드와 사용자 ID를 `config_change_log`에 기록한다.

---

## Claude 처리 기록

| 일시 | 상태 | 내용 |
|---|---|---|
| 2026-08-13 | 확인 | 실제 HTTP 설정 성공 전후 `config_change_log`를 실측했으며 증가량은 0이었다. `link.send()`의 동기 ACK 뒤 API 스레드가 저장하는 현재 구조를 확인해 `device_install_info`·`config_change_log`의 사용자발 설정 연산을 API 소유로 명시하는 판정안을 보고했다. |
| 2026-08-14 | 수정완료 | 사용자 설정의 실질 변경 필드와 전후값·`user_id`를 원본 UPDATE와 같은 트랜잭션의 `config_change_log`에 기록한다. 타임아웃은 설정과 이력을 모두 남기지 않는 회귀로 고정했다. 아키텍처 §4.4-a는 두 테이블을 교차 소유로 옮겨 7/18/2/4=31로 정정했고 메타 검증이 실제 표를 같은 값으로 파싱했다. 사용자 귀속을 임시 제거하자 F-221 회귀가 실패했고 원복 후 통과했다. |
| | | |
