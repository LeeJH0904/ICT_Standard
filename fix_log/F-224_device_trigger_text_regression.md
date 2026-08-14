# F-224 · 디바이스 등록 트리거 정정이 본문과 주석에 남지 않음

| 항목 | 값 |
|---|---|
| 심각도 | 오류 |
| 분류 | 문서불일치 |
| 대상 | `project_docs/arch/아키텍처_설계서.md:367-368` · `project_docs/arch/아키텍처_설계서.md:392-394` · `project_code/backend/repository.py:49,79,132-138` · F-198 |
| 발견일 | 2026-08-13 |
| 상태 | 수정완료 |

## 근거

TTAK.KO-10.0943 §8.1.3.2 — `REQ_SET_DEVICE_PROPERTY`는 현재 디바이스 속성값을 사용 목적에 따라 변경하는 메시지이며 Request/Response가 역방향으로도 전송될 수 있다. 현재 계약은 이 메시지와 §8.1.3.3 `REQ_SET_NODE_DEVICE_PROPERTY_ALL`에 `DEVICE_PROPERTY × N`을 배정한다.

아키텍처 §4.4-a의 최신 표도 디바이스 등록 트리거를 위 두 메시지로 정정하고, 페이로드 없는 `REQ_SET_CONNECTION`이 아니라고 명시한다.

## 현상

같은 절의 F-176·F-182 설명은 장치 등록·관리자 결속·변경 이력 트리거를 여전히 `REQ_SET_CONNECTION`과 삭제된 `_handle_connection`으로 적는다. `repository.py`의 `record_config_change()`, 소유권 머리말, `upsert_device_install_info()` 주석에도 같은 이름이 남아 있다.

현재 실제 dispatch는 `ingest._handle_device_property()`가 `REQ_SET_DEVICE_PROPERTY`와 `REQ_SET_NODE_DEVICE_PROPERTY_ALL`을 처리한다. 따라서 표·구현이 옳고 본문·주석이 틀리다.

## 영향

F-198 수정완료 기록이 “repository 주석 잔재도 함께 갱신”했다고 주장하지만 실제 잔재가 남아 있다. 변경 이력·설치 시점·재연결 의미를 잘못된 메시지에 결속해 이후 유지보수와 테스트 픽스처가 다시 불가능한 Frame 조합으로 회귀할 수 있다.

## 제안

F-176·F-182 설명과 repository 주석을 현재 dispatch 및 §4.4-a 표에 맞추고, 삭제된 함수명과 옛 트리거 문자열을 회귀 검색한다.

---

## Claude 처리 기록

| 일시 | 상태 | 내용 |
|---|---|---|
| 2026-08-14 | 확인 | 실제 dispatch는 `ingest.handle()`이 `REQ_SET_DEVICE_PROPERTY`·`REQ_SET_NODE_DEVICE_PROPERTY_ALL`을 `_handle_device_property()`로 보내며 `REQ_SET_CONNECTION`의 `LAYOUT`은 `(0, 0)`이다. 아키텍처 F-176·F-182 설명과 repository 소유권·등록 주석에 폐기된 메시지와 함수명이 남은 것을 확인했다. |
| 2026-08-14 | 수정완료 | 아키텍처 F-176·F-182와 repository의 변경 이력·소유권·upsert 주석을 두 디바이스 속성 메시지 및 `_handle_device_property()` 기준으로 통일했다. 관련 절과 주석에서 폐기된 트리거·함수명을 금지하는 meta 검사를 추가했고, 옛 `REQ_SET_CONNECTION` 주석 재주입 시 FAIL을 확인했다. |
