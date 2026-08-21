# F-260 · 단기예보 100건 제한으로 정상 응답의 TMX를 누락해 FALLBACK 처리

| 항목 | 값 |
|---|---|
| 심각도 | 오류 |
| 분류 | 코드버그 |
| 대상 | `project_code/backend/services/dms.py:73-89,158-192,217-240` · 최종 제출본 동기 사본 |
| 발견일 | 2026-08-21 |
| 상태 | 수정완료 |

## 근거

TTAK.KO-10.0937 6.2-1 — “데이터관리서비스는 공개된 공공데이터서비스로부터 필요한 외부 데이터를 수집하여 데이터베이스에 기록하는 기능을 제공해야 한다.”

[기상청 API허브 「동네예보(초단기실황·초단기예보·단기예보) 조회」 4.3 단기예보조회](https://apihub.kma.go.kr/apiList.do?apiMov=4.+%EB%8F%99%EB%84%A4%EC%98%88%EB%B3%B4%28%EC%B4%88%EB%8B%A8%EA%B8%B0%EC%8B%A4%ED%99%A9%C2%B7%EC%B4%88%EB%8B%A8%EA%B8%B0%EC%98%88%EB%B3%B4%C2%B7%EB%8B%A8%EA%B8%B0%EC%98%88%EB%B3%B4%29+%EC%A1%B0%ED%9A%8C&seqApi=10&seqApiSub=286) — `numOfRows`는 한 페이지 결과 수이고 응답은 `totalCount`, `items.item`, `category`, `fcstDate`, `fcstValue`를 제공한다. 공식 요청 예시는 `numOfRows=1000`이다.

F-258의 완료 기준과 현재 `dms._validate_kma_response()` 계약은 성공 응답에 요청 격자와 숫자형 `TMX`가 있어야 `LIVE`로 기록하도록 정했다. 따라서 `TMX`가 뒤쪽 항목에 있을 수 있는 페이지를 일부만 받은 상태에서 “TMX 없음”을 데이터 부재로 판정하면 안 된다.

## 현상

`_kma_request_url()`의 `num_of_rows` 기본값이 100이다. 2026-08-21 14:00 발표회차, 격자 `(60,127)`에 대해 최종 제출본 `.env`의 인증키로 비밀값을 출력하지 않고 실 API를 호출한 결과는 다음과 같았다.

| 요청 | HTTP / 결과코드 | 전체 건수 | 반환 건수 | TMX |
|---|---|---:|---:|---:|
| `numOfRows=100` (현재 코드) | `200 / 00 NORMAL_SERVICE` | 798 | 100 | 0건 |
| `numOfRows=1000` | `200 / 00 NORMAL_SERVICE` | 798 | 798 | 3건 |

첫 100건은 2026-08-21 15:00~23:00 범위이며 `PCP, POP, PTY, REH, SKY, SNO, TMP, UUU, VEC, VVV, WAV, WSD`만 포함했다. `TMX`는 뒤쪽에 있어 첫 페이지 100건에는 없었다.

기상청 서버는 정상 응답했지만 `_validate_kma_response()`는 `TMX`를 찾지 못해 `False`를 반환한다. 호출자는 정상 payload를 버리고 고정 목업을 적재하며 `data_origin='FALLBACK'`으로 기록한다. 실행 중 로컬 API의 최근 레코드에서도 인증키 설정 이후 생성된 3건이 모두 `FALLBACK`이고, 발표회차와 요청 격자는 `NULL`로 지워진 것을 확인했다.

개발본과 최종 제출본의 `dms.py`, `api.py`, `rules.html` SHA-256은 각각 동일하므로 두 사본 모두 같은 결함을 갖는다.

## 영향

인증키·온실 격자·기상청 통신이 모두 정상이어도, `TMX`가 첫 100건 뒤에 배치된 일반적인 응답은 항상 폴백된다. rules 페이지에는 모든 실호출 결과가 `FALLBACK`으로 보이고, AI 초안은 실예보 최고기온이 아니라 목업의 고정 `TMX` 값을 사용한다. HTTP 오류·인증 실패와 정상 응답의 페이지 절단이 동일한 폴백으로 합쳐져 운영자가 원인을 화면이나 로그에서 구분할 수도 없다.

## 재현

1. 최종 제출본 `project_code/.env`에 이 API 사용 승인을 받은 `KMA_API_KEY`를 설정한다.
2. 격자 `(60,127)`이 저장된 온실로 rules 페이지에서 `AI_DRAFT` 초안을 생성한다.
3. 공공데이터 표 또는 `GET /api/v1/publicdata/records`에서 새 레코드가 `FALLBACK`인지 확인한다.
4. 같은 `base_date`, `base_time`, `nx`, `ny`로 인증키를 노출하지 않고 직접 호출한다.
5. `numOfRows=100`에서는 `resultCode=00`, `totalCount=798`, 반환 100건, `TMX=0`이고 `numOfRows=1000`에서는 반환 798건, `TMX=3`임을 확인한다.

## 제안

1. `totalCount`를 확인해 모든 페이지를 수집하거나, 최소한 `TMX`가 발견될 때까지 페이지를 순회한다. 현재 자료량에서는 공식 예시처럼 `numOfRows=1000`으로 요청해도 전부 수신되지만, 장기적으로는 페이지 순회가 안전하다.
2. 회귀 테스트에 `TMX`가 100번째 항목 이후에 있는 정상 응답을 추가하고, 수집 결과가 `LIVE`이며 실제 TMX를 저장하는지 검증한다.
3. HTTP·JSON 오류, 기상청 `resultCode` 오류, 빈 응답, 격자 불일치, TMX 미수신을 비밀정보 없이 구분 기록한다.

## 작업자 처리 기록

| 일시 | 상태 | 내용 |
|---|---|---|
| 2026-08-21 | 신규→확인 | 코드 대조로 재현. `_kma_request_url(num_of_rows=100)` 기본값을 `_fetch_kma_live`가 그대로 써 첫 페이지 100건만 수신 → `_validate_kma_response`가 TMX(뒤쪽 배치) 부재로 `False` → 호출자가 정상 payload를 버리고 목업 적재·`data_origin='FALLBACK'`. 인증키·격자·통신이 정상이어도 항상 폴백되는 코드버그로 확정. 실측 표(numOfRows=100→TMX 0건 / 1000→TMX 3건, totalCount=798)는 근거로 인용하되 본 처리는 비밀값 없이 코드 경로로 재현. |
| 2026-08-21 | 확인→수정완료 | 재현→수정→회귀(§11.3 코드버그). 사용자 지시로 **최종 제출본을 먼저 편집한 뒤 개발본에 동기**. **수정**(`dms.py`, 순수 수집 로직 — 컬럼·계약·화면·API 표면 변경 없음): `_fetch_kma_live`를 `totalCount` 기반 페이지 순회로 재작성. 한 페이지 조회를 `_fetch_kma_page`로 분리(`numOfRows=_VILAGE_PAGE_ROWS=1000` — 기상청 공식 요청 예시값, `pageNo` 순회), `_payload_items`·`_payload_total_count` 헬퍼로 안전 파싱, 순회 상한 `_VILAGE_MAX_PAGES=20`(무한 루프 방지). `len(items) < totalCount`인 동안 다음 페이지를 받아 첫 페이지 구조에 합쳐 반환하므로, TMX가 첫 100건 뒤에 있어도 `_validate_kma_response`·`_extract_forecast`가 정상 수집·판정한다. 현재 자료량(798건)은 첫 페이지(1000건)로 전부 수신되고, 이보다 많아지면 순회가 나머지를 마저 모은다(제안 §1). 기존 monkeypatch 테스트는 `_fetch_kma_live`를 통째로 대체하므로 영향 없음. **회귀**(`test_services_dms.py` 3건): ①`test_fetch_kma_live_merges_pages_until_total_f260` — TMX가 2페이지에 있는 응답을 `_fetch_kma_page` 스텁으로 주입, `seen==[1,2]`·102건 병합·LIVE 판정·`_extract_forecast==("20260822",34.0)` 확인. ②`test_fetch_kma_live_single_page_no_extra_request_f260` — `totalCount`가 한 페이지에 다 담기면 `seen==[1]`(추가 요청 없음). ③`test_paginated_normal_response_is_live_not_fallback_f260` — end-to-end `fetch_public_data`가 2페이지 정상응답을 FALLBACK 아닌 LIVE로 기록하고 목업 고정값이 아니라 실예보 TMX(34.0) 저장. **검증**: 개발 pytest 462/462(+3) · `run_all.py` 21/21 · `meta_verify.py` 119/119 · `offline_verify.py` 전체 통과(실행 중 생긴 `__pycache__`·`runtime.db` 임시 산출물 정리 후 재확인). 개발본·제출본 `dms.py`·`test_services_dms.py` SHA-256 동일. |

## 남긴 것 (F-260 범위 밖)

- **제안 §3 — 폴백 원인 구분 로깅**: HTTP·JSON 오류, `resultCode` 오류, 빈 응답, 격자 불일치, TMX 미수신을 비밀값 없이 구분 기록하는 것은 별개의 관측성 개선이다. 본 건의 확정 버그(페이지 절단으로 인한 오폴백)는 위 수정으로 해소했고, 이 로깅 강화는 코드버그가 아니라 개선 제안이라 착수하지 않았다. 필요 시 별도 F-로 다룬다.
- **§8-10 실키 스모크**: 실제 `KMA_API_KEY` 없이는 LIVE 페이지 순회를 실 서버로 판정할 수 없어 미실행(F-258·F-259와 동일 보류). 회귀는 `_fetch_kma_page`를 monkeypatch로 대체해 순회·병합 경로를 검증한다.
