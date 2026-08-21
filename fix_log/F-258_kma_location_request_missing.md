# F-258 · 기상청 실예보 호출에 위경도 기반 위치·발표시각 입력 경로가 없음

| 항목 | 값 |
|---|---|
| 심각도 | 오류 |
| 분류 | 코드버그 |
| 대상 | `project_code/backend/services/dms.py:76-106` · `project_code/web/rules.html:37-58,360-369` · `project_code/backend/schema.sql:51-72,398-412` · 제출본 동기 사본 |
| 발견일 | 2026-08-21 |
| 상태 | 수정완료 |

## 근거

[기상청 API허브 「동네예보(초단기실황·초단기예보·단기예보) 조회」 4.3 단기예보조회](https://apihub.kma.go.kr/apiList.do?apiMov=4.+%EB%8F%99%EB%84%A4%EC%98%88%EB%B3%B4%28%EC%B4%88%EB%8B%A8%EA%B8%B0%EC%8B%A4%ED%99%A9%C2%B7%EC%B4%88%EB%8B%A8%EA%B8%B0%EC%98%88%EB%B3%B4%C2%B7%EB%8B%A8%EA%B8%B0%EC%98%88%EB%B3%B4%29+%EC%A1%B0%ED%9A%8C&seqApi=10&seqApiSub=286) — `getVilageFcst` 요청에는 `base_date`, `base_time`, `nx`, `ny`, `authKey`가 필요하다. `nx`·`ny`는 일반 위도·경도가 아니라 기상청 동네예보 격자 좌표다.

TTAK.KO-10.0937 6.2-1 — “데이터관리서비스는 공개된 공공데이터서비스로부터 필요한 외부 데이터를 수집하여 데이터베이스에 기록하는 기능을 제공해야 한다.”

`project_docs/services/0937_요구사항_대조표.md` 6.3-4 — “사전 획득 방식 채택. `public_data_record`에 저장된 값을 읽는다.” 사전 획득한 값은 사용 대상 온실의 위치에 대응하는 공공데이터여야 한다.

## 현상

`dms._fetch_kma_live()`가 만드는 URL에는 `authKey`, `dataType`, `numOfRows`, `pageNo`만 있고 공식 필수 요청값인 `base_date`, `base_time`, `nx`, `ny`가 없다.

또한 다음 사용자·데이터 경로가 존재하지 않는다.

1. 사용자가 농장 또는 온실의 WGS84 위도·경도를 입력하는 화면과 API
2. WGS84 위도·경도를 기상청 동네예보 격자 `nx`·`ny`로 변환하는 단계
3. 위경도·격자와 대상 온실을 결속하여 저장하는 구조
4. 현재 한국 표준시와 기상청 자료 제공 지연을 고려하여 유효한 `base_date`·`base_time`을 선택하는 단계
5. 규칙 초안이 어느 온실·격자·발표회차의 예보를 사용했는지 보여 주고 보존하는 경로

현재 목업은 고정 격자 `60,127`을 담고 있고, Rules 화면은 온실 위치를 선택하지 않은 채 서버의 전역 최신 공공데이터 레코드를 사용한다. 따라서 서로 다른 위치의 온실도 같은 예보를 사용하게 된다.

## 영향

유효한 `KMA_API_KEY`를 넣어도 실 API 요청이 성립하지 않으며, 실패는 목업 폴백으로 전환된다. 사용자는 실제 기상청 예보가 적용된 것으로 오인할 수 있다.

필수 파라미터만 임의 상수로 추가해도 문제는 닫히지 않는다. 고정 격자는 등록된 온실 위치와 무관하고, 발표회차를 잘못 선택하면 `NO_DATA` 또는 과거 예보를 받는다. 이 상태에서 생성한 AI/임계 규칙은 대상 구동기의 실제 지역과 다른 최고기온을 근거로 삼을 수 있다.

## 재현

```powershell
rg -n "url =|base_date|base_time|nx|ny" 최종_제출물_폴더/ICT_Test/project_code/backend/services/dms.py
# URL에는 authKey/dataType/numOfRows/pageNo만 존재한다.

rg -n "greenhouse|latitude|longitude|kma_nx|kma_ny" 최종_제출물_폴더/ICT_Test/project_code/web/rules.html
# 규칙 초안 생성에 위치 선택·표시·전달 경로가 없다.
```

공식 예시와 같은 형식으로 `base_date`, `base_time`, `nx`, `ny`를 모두 넣지 않은 현재 `_KMA_URL` 요청은 정상 단기예보 조회 계약을 충족하지 않는다.

## 제안

### 1. 사용자 흐름

위경도는 규칙 생성 때마다 반복 입력하지 않는다.

```text
설정 화면에서 온실 선택
→ 사용자가 WGS84 위도·경도 입력
→ 서버가 값·범위 검증
→ 서버가 기상청 격자 nx·ny 계산
→ 위경도·격자를 온실에 저장
→ Rules에서 온실 선택
→ 저장된 격자와 최신 발표회차로 단기예보 수집
→ 선택한 온실의 TMX로 초안 생성
```

`settings.html`에 “기상 위치” 영역을 추가한다. 온실, WGS84 위도, WGS84 경도, 저장 버튼, 계산된 기상청 격자, 마지막 변경시각을 표시한다. 위도·경도는 숫자 입력으로 명확히 구분하고 단위와 예시를 함께 제공한다.

사용자는 GPS 또는 지도에서 확인한 WGS84 위도·경도를 입력한다. `nx`·`ny`는 내부 파생값이므로 사용자가 직접 입력하거나 수정하게 하지 않는다.

F-258의 위치 입력 범위는 사용자가 제공한 WGS84 위도·경도로 한정하며, 별도의 외부 위치 변환 서비스나 추가 API 키를 요구하지 않는다.

### 2. 위경도 입력과 검증

브라우저 입력값을 그대로 저장하거나 기상청 요청에 쓰지 않는다. 백엔드가 숫자·유한값·범위를 검증한 뒤 격자를 계산한다.

- 위도: WGS84, `-90 <= latitude <= 90`
- 경도: WGS84, `-180 <= longitude <= 180`
- `NaN`, 무한대, 빈 문자열, 숫자로 보이는 임의 문자열은 거부
- 위도와 경도를 뒤바꾼 입력을 줄이기 위해 필드 라벨·예시·서버 오류 문구를 분리
- 저장 전에 계산된 `nx`·`ny`가 기상청 격자의 유효한 정수인지 확인

저장된 유효 위치가 없으면 임의 좌표를 만들지 않고 위치 미설정 상태를 표시한다. 오프라인 데모는 시드 온실에 위경도·격자를 고정 fixture로 제공하되 `DEMO_FIXTURE`임을 표시한다.

### 3. 위치 저장 계약

기존 `greenhouse_info.location_type`은 `GPS`, `location_unit`은 `WGS84`로 기록한다. 자유 텍스트 `location`에 구조화 좌표를 유일하게 저장하지 말고 다음 숫자·파생 필드를 `greenhouse_info`에 추가하거나 1:1 확장 테이블로 분리한다. 한 트랜잭션에서 함께 갱신한다.

| 필드 | 의미·제약 |
|---|---|
| `latitude` | WGS84 위도, `-90 <= value <= 90` |
| `longitude` | WGS84 경도, `-180 <= value <= 180` |
| `kma_nx` | 위경도에서 계산한 정수 격자 X |
| `kma_ny` | 위경도에서 계산한 정수 격자 Y |
| `coordinate_source` | `MANUAL`·`DEMO_FIXTURE` 등 좌표 출처 |
| `coordinates_updated_at` | 좌표 확정·변경 시각 |

위경도를 변경하면 이전 격자를 그대로 재사용하지 말고 같은 요청 안에서 재계산에 성공한 경우에만 전량 커밋한다. 실패하면 기존 저장값을 보존한다. 런타임 설정 변경이므로 `config_change_log`에도 변경 주체·이전값·새 값을 기록한다.

`public_data_record`에는 최소한 `greenhouse_id`, 실제 요청 `base_date`, `base_time`, `nx`, `ny`, 실데이터/폴백 구분을 추적할 수 있어야 한다. 원본 payload만으로 추적할 경우에도 이 값들을 응답 검증 후 payload와 함께 보존하고, 조회 API가 노출해야 한다.

### 4. 기상청 격자 변환

`backend/services/kma_grid.py`처럼 네트워크와 무관한 순수 함수로 분리한다.

```python
latlon_to_kma_grid(latitude: float, longitude: float) -> tuple[int, int]
```

기상청 활용가이드의 Lambert Conformal Conic 동네예보 격자 변환식과 반올림 규칙을 그대로 옮긴다. 서울·제주·부산 등 공식/독립 기준 좌표를 골든 벡터로 고정하고, 경계·잘못된 범위·결정론을 단위 테스트한다. 외부 API나 네트워크 없이 순수 함수만으로 검증할 수 있어야 한다.

### 5. 발표회차 선택과 KMA 요청

`Asia/Seoul` 기준으로 현재 시각을 계산하고, 단기예보 발표시각 목록과 API 제공 지연을 반영해 이미 이용 가능한 가장 최신 회차를 선택한다. 시각 계산도 순수 함수로 분리한다.

```python
select_vilage_base_datetime(now_kst: datetime) -> tuple[str, str]
```

요청은 `urllib.parse.urlencode()`로 구성하여 키와 요청값을 문자열 연결하지 않는다.

```text
authKey, dataType=JSON, pageNo, numOfRows,
base_date=YYYYMMDD, base_time=HHMM, nx, ny
```

HTTP 성공만으로 실데이터 성공으로 판정하지 않는다. JSON의 `response.header.resultCode == '00'`, `items.item` 존재, 요청 격자 일치, 최신 예보일자의 `TMX` 존재까지 확인한 후 `fallback=False`로 기록한다. `NO_DATA`이면 직전 유효 발표회차를 제한 횟수 내에서 한 번 재시도할 수 있지만, 인증 오류·잘못된 파라미터는 재시도하지 않는다.

### 6. Rules 결속과 화면 표시

AI 초안 폼에서 온실을 먼저 선택하게 하고 `greenhouse_id`를 요청에 포함한다. 서버는 해당 온실에 저장된 격자로 DMS 레코드를 수집하거나 같은 온실·격자의 최신 유효 레코드를 재사용한다. 전역 “가장 최근 레코드”를 위치 확인 없이 가져오지 않는다.

초안 카드와 공공데이터 표에는 다음 정보를 표시한다.

```text
온실명 / WGS84 위경도 / 기상청 격자 / 예보 발표회차 /
예보 대상일 / TMX / LIVE 또는 DEMO_FIXTURE·FALLBACK
```

초안 승인 시 선택한 `target_install_id`가 초안의 `greenhouse_id`에 속하는지 서버에서 검사한다. 다른 온실 장치를 선택하면 422로 거부하여 예보 위치와 제어 위치가 어긋나지 않게 한다.

### 7. 실패 정책

- 실제 키가 있는데 인증·파라미터·응답 검증이 실패한 경우 원인을 로그와 상태 API에 구분해 남긴다.
- 목업 사용 여부를 `public_data_fallback` 하나의 “키 부재 여부”로 추정하지 말고 마지막 수집 결과에 근거해 표시한다.
- 폴백 데이터를 사용한 초안에는 `DEMO/FALLBACK` 배지를 표시한다. 실데이터로 오인시킬 수 있는 무표시 자동 폴백은 금지한다.
- KMA 키는 로그·응답·DB·제출물에 기록하지 않는다.
- 외부 API가 없어도 테스트와 데모는 가능해야 하지만, fixture 데이터와 LIVE 데이터의 출처는 절대 같은 상태로 표시하지 않는다.

### 8. 완료 기준과 회귀 시험

1. 위경도 빈값·비숫자·`NaN`·무한대·범위 초과를 각각 거부하는지 검증한다.
2. 위경도 저장 성공 시 위경도·격자가 원자적으로 갱신되고 실패 시 이전 값이 유지되는지 검증한다.
3. `latlon_to_kma_grid()` 골든 벡터와 범위 오류를 검증한다.
4. 발표시각 직전·직후·자정·월/연도 경계에서 `base_date`·`base_time`을 검증한다.
5. KMA 요청 URL에 8개 요청인자가 모두 들어가며 비밀키가 로그에 남지 않는지 검증한다.
6. HTTP 200 안의 오류 `resultCode`, 빈 items, TMX 부재, 격자 불일치를 실데이터 성공으로 오판하지 않는지 검증한다.
7. 두 온실의 서로 다른 위경도를 서로 다른 `nx`·`ny`로 호출하고 레코드·초안이 뒤섞이지 않는지 검증한다.
8. 다른 온실의 구동기로 승인하려는 반례가 거부되는지 검증한다.
9. LIVE·FALLBACK·DEMO_FIXTURE가 화면과 API에서 구분되는지 검증한다.
10. 실제 키를 넣은 수동 스모크 테스트에서 KMA 응답의 TMX와 저장 레코드·초안 문장이 같은지 확인한다. 실제 키 스모크 결과가 없으면 “실 API 검증 완료”로 판정하지 않는다.
11. 제출본을 먼저 수정·검증한 뒤 개발본에 그대로 동기화하고, 관련 파일 해시와 전체 회귀 출구를 다시 대조한다.

---

## 작업자 처리 기록

| 일시 | 상태 | 내용 |
|---|---|---|
| 2026-08-21 | 신규→확인 | 개발본·제출본 양쪽에서 재현 확인. ① `dms.py::_fetch_kma_live` URL에 `authKey`·`dataType`·`numOfRows`·`pageNo`만 있고 필수값 `base_date`·`base_time`·`nx`·`ny` 없음(공식 `getVilageFcst` 계약 위반). ② `greenhouse_info`(schema.sql:50-70)에 위경도·격자 컬럼 없음 — `location`/`location_type`/`location_unit`뿐. ③ `rules.html` 초안 폼에 온실 선택 경로 없음(작물 임계값만). ④ 목업 격자 `60,127` 고정. 온실별 위치와 무관하게 전역 최신 레코드 사용. |
| 2026-08-21 | 확인→수정완료 | **DB 스키마 방식 = `greenhouse_info` 컬럼 추가로 확정(사용자 결정).** 구현: (1) `backend/services/kma_grid.py` 신설 — WGS84→기상청 격자 Lambert Conformal Conic 순수 함수 `latlon_to_kma_grid()` + `validate_latlon()`(NaN·무한대·범위·비숫자 거부). 서울(60,127)·부산(98,76)이 기상청 공표값과 독립 일치. (2) `dms.py` — `select_vilage_base_datetime()`(KST·제공지연 10분·월/연 경계, 순수) + `_kma_request_url()` 8인자 `urlencode` + `_validate_kma_response()`(resultCode 00·items·격자일치·TMX) + `fetch_public_data(greenhouse_id=)`가 온실 격자로 수집, 출처 `LIVE`/`FALLBACK`/`DEMO_FIXTURE` 판정(키부재=DEMO_FIXTURE, 키有 실패=FALLBACK). (3) `schema.sql`(개발+정본 바이트동일) — `greenhouse_info`에 `latitude`·`longitude`·`kma_nx`·`kma_ny`·`coordinate_source`·`coordinates_updated_at` + CHECK(범위·격자정수·부분저장금지), `public_data_record`에 `greenhouse_id`·`base_date`·`base_time`·`nx`·`ny`·`data_origin` 추적. 테이블31·트리거37·인덱스8 불변. (4) `models.py`·`repository.py`(`get_greenhouse_grid`·`set_greenhouse_location` 원자적 UPDATE+`config_change_log` 이력·`list_greenhouses`·`get_greenhouse`). (5) `api.py`+`openapi.json` — `GET /api/v1/greenhouses`·`PUT /api/v1/greenhouses/{id}/location`(위경도만 받아 서버가 격자 재계산, 범위검증 400, 미존재 404, X-User-Id 필수) 2종 추가(경로22→24·오퍼레이션23→25·쓰기7→8), `create_rule_draft`에 `greenhouse_id` 결속, `health.public_data_fallback`을 키부재추정→마지막 레코드 `data_origin` 근거로. (6) `web/settings.html` 기상 위치 UI(온실·위경도·저장·격자·변경시각), `web/rules.html` 초안 온실 선택 + LIVE/DEMO_FIXTURE/FALLBACK 배지(색+텍스트), `web/static/api.js` 메서드 2종. (7) `seed.sql` 데모 온실 서울 좌표(DEMO_FIXTURE, 목업 격자 60,127 정합). **아키텍처 §4.4-a**: `greenhouse_info`가 시드전용→④교차로 이동(시드 CREATE + API 스레드 런타임 위치 UPDATE, `device_install_info` 선례와 동일). 문서 카운트 전량 동기(API명세서·화면설계서·0937대조표·아키텍처·검증자프롬프트·CLAUDE §3.5 인접). **회귀 테스트 신설 3파일 55건**(`test_kma_grid` 격자골든·범위, `test_services_dms` 발표회차·URL·응답검증·출처판정·격자결속, `test_greenhouse_location` API 입력검증·404·원자성) + F-256 테스트를 배지 방식으로 갱신(F-256 보장 유지). **검증**: 개발 backend 450 · siap 포함 450 · 계약 64/64 · meta_verify 119/119 · offline_verify 전체통과 · run_all 21/21 · web_verify 75/75 · web_live 27/27. **제출본 미러 동기**(project_code 13+1파일 바이트동일, 제출본 F-258 테스트 52 통과, 빌드 아티팩트 정리). **오탐 처리**: meta_verify에 SYNTH(`math.sin`) 허용 기전 신설(좌표 투영은 §1-1 합성센서데이터 아님) + 환경변수명 오탐 ALLOW 갱신. |
| 2026-08-21 | 후속 보류 | **완료기준 §6/§8-8(승인 시 `target_install_id`가 초안 온실에 속하는지 422 정합 검사)은 사용자 결정으로 후속 과제로 남김.** 사유: `control_rule`에 `greenhouse_id` 컬럼 추가가 필요해 스키마·repository·api·테스트를 3개 트리에 또 확장하는 별도 작업이며, 이번 범위(핵심 요청 성립·온실별 위치 배선·출처 배지)와 분리 가능. 핵심 버그(격자·발표시각 필수 입력 경로 부재)와 위치 배선은 닫혔다. §8-10(실키 스모크 테스트)은 실제 `KMA_API_KEY` 없이는 판정 불가라 미실행 — "실 API 검증 완료"로 판정하지 않는다(§8-10 규정 준수). |
