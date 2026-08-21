# F-259 · F-258의 온실·예보 메타데이터가 rules 표·초안 카드에 표출되지 않음

| 항목 | 값 |
|---|---|
| 심각도 | 오류 |
| 분류 | 코드버그 |
| 대상 | `project_code/web/rules.html:31,178-211,308-322` · `project_code/backend/api.py:397-403,860-862` · `project_code/backend/services/dms.py:210-214` · 제출본 동기 사본 |
| 발견일 | 2026-08-21 |
| 상태 | 수정완료 |

## 근거

TTAK.KO-10.0937 6.2-1 — “데이터관리서비스는 공개된 공공데이터서비스로부터 필요한 외부 데이터를 수집하여 데이터베이스에 기록하는 기능을 제공해야 한다.”

`F-258_kma_location_request_missing.md` §6 — 초안 카드와 공공데이터 표에 “온실명 / WGS84 위경도 / 기상청 격자 / 예보 발표회차 / 예보 대상일 / TMX / LIVE 또는 DEMO_FIXTURE·FALLBACK”을 표시하도록 완료 기준을 정했다. F-258 작업자 처리 기록에서 후속으로 명시한 것은 승인 대상 온실 정합 검사(§8-8)와 실키 스모크(§8-10)뿐이며, 이 표시 기준은 보류하지 않았다.

## 현상

온실 선택과 API 요청 자체는 연결됐다. `rules.html:396`이 선택한 `greenhouse_id`를 `POST /api/v1/rules`에 싣고, `api.py:860`이 그 온실로 DMS 수집을 호출한다. 그러나 결과 표출은 F-258 완료 기준의 일부만 구현됐다.

1. 공공데이터 표는 출처·온실명·레코드의 `nx/ny`·`base_date/base_time`·수집시각·일반 `item`·출처 배지만 표시한다. 온실 API가 반환하는 WGS84 위도·경도는 `greenhousesById`에 적재한 뒤 렌더링하지 않는다.
2. 예보 대상일과 TMX는 `payload.response.body.items.item` 안에만 있고 `PublicDataRecord`의 명시 필드나 화면 렌더 경로가 없다. 일반 항목 문자열 `TMX·TMN·POP·REH·SKY`는 실제 예보 대상일과 TMX 값이 아니다.
3. `pendingCardHtml()`·`approvedCardHtml()`·`rejectedCardHtml()`은 규칙 문구와 생성 경로만 표시한다. 어느 온실·위경도·격자·발표회차·예보 대상일·TMX를 근거로 초안이 만들어졌는지 카드에서 확인할 수 없다. `Rule` 응답에도 이 결속 정보가 없다.
4. 키가 없는 정상 오프라인 경로에서 `dms.py:210-214`는 `DEMO_FIXTURE`를 적재하면서 `nx/ny/base_date/base_time`을 모두 `NULL`로 지운다. 실제 HTTP 재현 결과 선택 온실 `demo-gh-1`은 서울 좌표와 격자 `(60,127)`을 갖지만 새 공공데이터 행은 `greenhouse_id='demo-gh-1'`, `data_origin='DEMO_FIXTURE'` 외 네 필드가 `null`이었다. `rules.html:316-317`은 이를 전부 `—`로 표시한다.
5. F-258 관련 pytest 55건, `web_verify.py` 75/75, `api_verify.py` 71/71, `route_verify.py`가 모두 통과하지만 위 표시 항목의 존재와 API→DOM 값 전달을 검사하지 않는다.

개발본과 최종 제출본의 `rules.html`, `web/static/api.js`, `backend/api.py` SHA-256은 각각 일치하므로 제출본에도 같은 현상이 있다.

## 영향

화면에서 초안이 선택한 온실의 예보를 사용했다고 안내하지만, 심사자는 실제로 어느 좌표·격자·발표회차·대상일·TMX가 사용됐는지 확인할 수 없다. 특히 기본 오프라인 데모에서는 위치 격자와 발표회차가 `—`로 보여 F-258의 위치 결속 구현을 화면으로 증명하지 못한다. 규칙 카드와 공공데이터 행의 연결도 보이지 않아, 다른 온실 또는 다른 회차의 예보가 사용돼도 UI만으로 구별할 수 없다.

## 재현

```powershell
python project_code/run.py --mode simulate --serve --http-port 8765 --db <새_DB_경로>

# 온실은 WGS84와 격자 (60,127)를 반환한다.
Invoke-RestMethod http://127.0.0.1:8765/api/v1/greenhouses

# rules 화면과 같은 요청이다.
$body = @{origin='AI_DRAFT'; condition_expr=$null;
  model_id='demo-model-llm-irrigation'; greenhouse_id='demo-gh-1';
  inputs=@{crop_tmax_c=33}} | ConvertTo-Json -Depth 5
Invoke-RestMethod http://127.0.0.1:8765/api/v1/rules `
  -Method Post -ContentType application/json -Body $body

# 최신 행은 greenhouse_id와 DEMO_FIXTURE만 결속되고 nx/ny/base_date/base_time은 null이다.
Invoke-RestMethod 'http://127.0.0.1:8765/api/v1/publicdata/records?limit=10'

# 정적 확인: WGS84·예보 대상일·TMX 렌더와 카드 결속이 없다.
rg -n latitude|longitude|fcstDate|fcstValue|TMX|pendingCardHtml|renderPublicData project_code/web/rules.html
```

현재 환경의 브라우저 인스턴스 목록이 비어 실제 픽셀 렌더는 확인하지 못했다. 위 현상은 실제 HTTP 응답과 해당 응답을 소비하는 DOM 생성 코드로 재현했다.

## 제안

- 공공데이터 응답에서 예보 대상일과 TMX를 화면이 표준 해석 없이 사용할 수 있는 명시 필드로 제공하고, 온실 응답의 위경도·등록 격자와 함께 표에 표시한다.
- `DEMO_FIXTURE`·`FALLBACK`에서도 “등록 온실 격자”와 “실제 KMA 요청 격자”를 혼동하지 않도록 라벨을 분리해, 알려진 위치는 보이되 실행되지 않은 LIVE 요청을 꾸며내지 않는다.
- 초안이 사용한 `greenhouse_id`와 `public_data_record_id`를 규칙에 결속하여 카드가 동일 메타데이터를 표시하게 한다.
- 문자열 존재 검사 대신 실제 API 응답 fixture를 `renderPublicData()`와 카드 렌더러에 넣어 각 셀·배지가 생성되는지 회귀 시험한다.

---

## 작업자 처리 기록

| 일시 | 상태 | 내용 |
|---|---|---|
| 2026-08-21 | 신규→확인 | 재현. 코드 대조로 확인: (1) `renderPublicData()`가 `greenhousesById`에 적재한 온실 위경도를 렌더하지 않음, (2) 예보 대상일·TMX가 `payload.items` 안에만 있고 `PublicDataRecord` 명시 필드·렌더 경로 없음, (3) `pendingCardHtml`·`approvedCardHtml`·`rejectedCardHtml`에 온실·격자·발표회차·예보 근거 표시 없고 `Rule` 응답에 결속 정보 없음, (4) `dms.py`가 비-LIVE 경로에서 `nx/ny/base_*`를 NULL로 지워 기본 데모에서 위치 격자가 `—`로 보임. F-258 완료 기준 §6은 이 표시를 보류하지 않았음(보류는 §8-8 정합검사·§8-10 실키 스모크뿐). 코드버그로 확정. |
| 2026-08-21 | 확인→수정완료 | 재현→수정→회귀(§11.3). **DB**(schema.sql 3트리 바이트 동일): `public_data_record`에 `forecast_date`·`forecast_tmax_c` — 예보 대상일·TMX를 payload 파싱이 아니라 명시 컬럼으로. '실제 초안에 쓰인 예보값'이라 LIVE·FALLBACK·DEMO_FIXTURE 전부 채운다(nx/ny·base_*는 '실제 요청'이라 폴백 NULL 유지 — 제안 §2 라벨 분리). `control_rule`에 `public_data_record_id`(초안 근거 결속 FK, AI_DRAFT만 채워짐, 승인 게이트 CHECK와 무관). **서비스**: `dms._extract_forecast(payload)`가 TMX 항목의 fcstDate·fcstValue 추출(기상청 스키마 해석은 서비스 계층에만, §3.4). `mms.draft_rule(...public_data_record_id)`·`api.create_rule_draft`가 근거 레코드 결속. **API**: `_record_dict`에 예보 2필드, `_rule_forecast_dict`+`_rule_dict(r, conn)`에 `public_data_record_id`+`forecast` 스냅샷(결속 레코드에서 유도, 카드가 표와 동일 메타데이터 렌더). `get_rule`은 conn 개방 중 dict 생성하도록 재구성. **화면**(rules.html): 공공데이터 표 컬럼 = 출처·온실·위경도(WGS84)·온실 격자(등록)·발표회차·예보(대상일·최고기온)·수집시각·실데이터 여부. 등록 격자·위경도는 온실 객체에서, 예보값은 레코드 명시 필드에서 렌더 — 데모에서도 위치 결속이 보이되 실행 안 된 LIVE 요청은 꾸며내지 않음. 미승인·승인·거부 카드에 `forecastLineHtml(rule)` 근거 예보 블록 추가. **openapi.json**: PublicDataRecord 예보 2필드, Rule `public_data_record_id`+`forecast`(nullable 필수·유도 스냅샷). **회귀**: `test_services_dms.py` 4건(예보 추출·DEMO_FIXTURE 저장·LIVE 저장), `test_api.py` 2건(AI 초안 결속·WIZARD 무결속, 실행 end-to-end), `test_rules_ui.py` 2건(렌더 배선·카드 결속) + F-256 회귀를 '전송 금지 정밀검사'로 갱신(서버값 표시는 허용, blanket 금지 제거). `api_verify` 반례 매트릭스 3건 추가(52종). 검증: 개발 pytest 459/459 · api_verify 71/71 · web_verify 75/75 · web_live 27/27 · db_live · meta 통과 · run_all 21/21 · offline 전체 통과. 개발본·정본·제출본 동기(대상 파일 SHA-256 일치). |

## 남긴 것 (F-259 범위 밖)

- **§8-8 승인 대상 온실 정합검사**: F-258에서 사용자가 명시 보류. 본 건은 표시용 결속(`public_data_record_id`)만 추가했고 `control_rule.greenhouse_id` 1급 컬럼+승인 시 정합 CHECK는 그 보류 항목이므로 착수하지 않았다. 카드 표시 목적은 결속 레코드→greenhouse_id 경유로 충족된다.
- **§8-10 실키 스모크**: 실제 `KMA_API_KEY` 없이는 LIVE 경로를 판정할 수 없어 미실행. dms 테스트는 `_fetch_kma_live`를 monkeypatch로 대체해 LIVE 저장 경로만 검증한다.

