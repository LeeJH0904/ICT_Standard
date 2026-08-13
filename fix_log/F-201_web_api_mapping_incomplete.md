# F-201 · 화면-API 대응표가 실제 읽기 호출 4종을 누락

| 항목 | 값 |
|---|---|
| 심각도 | 오류 |
| 분류 | 문서불일치 |
| 대상 | `project_docs/web/화면_설계서.md:77-78` · `project_code/web/verify.html:218` · `rules.html:135,265,268` |
| 발견일 | 2026-08-12 |
| 상태 | 수정완료 |

## 근거

TTAK.KO-10.0937 6.2 — "공공데이터 명칭, 제공기관, 등록일, 갱신일 등 공공데이터 메타 정보를 관리 할 수 있어야 한다."

TTAK.KO-10.0937 6.5 — "사용자가 지정한 명령을 장치관리서비스로 전송하고 제어 결과를 피드백 받을 수 있다."

화면 설계서 §5.2는 `Alert.frame_id`를 X08 원본 프레임 결속에 사용한다고 정하고, §6.1은 공공데이터 카드에 출처를 표시하며, §6.2는 승인 시 대상 장치를 선택하도록 정한다. 따라서 구현의 추가 조회가 맞고 §2.1 대응표가 틀렸다.

## 현상

§2.1은 `verify.html` 읽기에 `listAlerts`를 적지 않았고, `rules.html` 읽기에 `listPublicDataSources`·`listNodes`·`listNodeDevices`를 적지 않았다. 실제 구현은 네 오퍼레이션을 호출한다. `web_verify.py`는 대응표가 OpenAPI에 존재하는지만 보고 구현 호출 집합과 대조하지 않으며, `web_live_verify.py`는 구현 호출이 OpenAPI에 존재하는지만 보고 대응표와 대조하지 않아 각각 62/62와 16/16으로 통과한다.

## 영향

화면↔API 추적표가 실제 네트워크 표면의 정본 역할을 하지 못한다. 구현이 조회 경로를 추가하거나 제거해도 설계 대조 출구가 이를 검출하지 못한다.

## 재현

```powershell
rg -n "api\.(listAlerts|listPublicDataSources|listNodes|listNodeDevices)" project_code/web/verify.html project_code/web/rules.html
python project_docs/web/web_verify.py
python tools/web_live_verify.py
```

실제 호출 4종이 §2.1 표에 없지만 두 검증기는 62/62·16/16으로 통과한다.

---

## Claude 처리 기록

| 일시 | 상태 | 내용 |
|---|---|---|
| 2026-08-12 | 신규→확인 | 재현 명령 실행 결과와 신고 내용이 일치함을 확인. `rg`로 `verify.html`이 `api.listAlerts`(§5.2 X08 원본 프레임 결속용), `rules.html`이 `api.listPublicDataSources`(§6.1 공공데이터 카드 출처)·`api.listNodes`·`api.listNodeDevices`(§6.2 승인 시 대상 장치 선택)를 실제로 호출함을 확인 — 화면 설계서 §5.2·§6.1·§6.2 자체가 이미 이 호출들의 근거를 서술하고 있어 신고의 판정(설계서가 옳고 §2.1 표가 틀렸다)에 동의. `web_verify.py`(표↔openapi.json 대조)와 `web_live_verify.py`(구현↔api.js 대조)가 각각 반대쪽만 봐서 이 드리프트가 양쪽 다 통과로 빠져나간 구조적 원인도 코드로 확인 |
| 2026-08-12 | 확인→수정완료 | `project_docs/web/화면_설계서.md` §2.1 표에 `verify.html` 행 `listAlerts`, `rules.html` 행 `listPublicDataSources`·`listNodes`·`listNodeDevices` 4건 추가. 근본 원인(양쪽 검증기가 표를 실제 구현 호출과 교차 대조하지 않음)까지 닫기 위해 `tools/web_live_verify.py`에 새 검사 신설 — §2.1 표를 직접 파싱(`MAP_ROW_RE`)해 화면별 읽기 칸(`streamEvents`는 api.js 오퍼레이션이 아니므로 비교에서 제외)을 `api_js_defs`로 GET 메서드만 골라낸 실제 호출 집합과 **양방향**(문서 누락/구현 누락) 대조하는 `"화면_설계서.md §2.1 읽기 칸이 실제 GET 호출과 화면별로 정확히 일치 (F-201)"` 항목 추가(20→**22**항목) — 이후 표와 구현 중 어느 쪽이 조회 경로를 추가·제거해도 이 검사가 즉시 잡는다. **결함 주입 검증**: `verify.html` 행에서 `listAlerts`를 임시로 제거한 사본으로 실행 → 신설 검사가 `verify.html: 문서 누락 ['listAlerts']`로 즉시 FAIL, 원복 후 22/22 재통과 확인. 검증: `python tools/web_live_verify.py` **22/22**(신설 검사 포함) · `python project_docs/web/web_verify.py` **68/68**(표 대조 로직은 그대로이므로 통과, F-196 이후 실물 검사 활성 상태 유지) · `python fix_log/meta_verify.py` **109/109** |