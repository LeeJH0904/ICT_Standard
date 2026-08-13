# F-190 · 노드종류 검증기가 서비스 계층의 장치별 하드코딩을 놓침

| 항목 | 값 |
|---|---|
| 심각도 | 치명 |
| 분류 | 코드버그 |
| 대상 | `project_code/backend/services/mms.py:46,80-83` · `tools/nodetype_verify.py:45-99` |
| 발견일 | 2026-08-11 |
| 상태 | 수정완료 |

## 근거

`CLAUDE.md` §0 핵심 주장 3 — “노드 추가 시 서버 코드 수정이 0줄이다.”

`CLAUDE.md` §1-6 절대 금지 — “`project_code/backend/`에 노드 종류·디바이스 종류 하드코딩”.

개발 착수 지시서 §3.8은 `tools/nodetype_verify.py`가 `project_code/backend/**`의 노드·디바이스 종류 문자열 하드코딩 0건을 판정해야 한다고 정한다.

## 현상

`mms.py`는 `HIGH_TEMP_THRESHOLD_C = 33.0`을 고정하고, 모든 threshold 및 llm 폴백 모델 출력에 “관수 장치 가동”을 직접 넣는다. 모델 메타정보의 `output_spec`, 대상 장치 데이터, Subtype 레지스트리를 보지 않는다. 다른 작물 기준이나 송풍기·냉난방기 모델을 추가하려면 서비스 코드를 수정해야 한다.

그런데 `nodetype_verify.py`는 보드 이름 토큰 11종과 정확히 `node_id == <정수>` 형태만 검사한다. 장치 종류 문자열과 서비스 분기는 검사하지 않는다. 현재의 잘못된 코드가 그대로 있는데도 검증기는 통과했다.

```text
[OK] 보드/MCU 이름 리터럴 0건
[OK] node_id 정수 리터럴 분기 0건
[PASS] tools/nodetype_verify.py
```

## 영향

핵심 주장 3의 기계 증거가 실제 금지 대상을 보지 않는다. 현재 코드도 관수 장치에 종속되어 있으므로 새 장치·모델 확장에서 “서버 코드 수정 0줄”이 깨진다.

## 재현

```powershell
python tools/nodetype_verify.py
rg -n "HIGH_TEMP_THRESHOLD_C|관수 장치" project_code/backend/services/mms.py
```

첫 명령은 통과하고 두 번째 명령은 실제 장치별 하드코딩을 출력한다.

---

## Claude 처리 기록

| 일시 | 상태 | 내용 |
|---|---|---|
| 2026-08-11 | 확인 | 재현 성공 — `_threshold_draft()`가 `HIGH_TEMP_THRESHOLD_C=33.0` 상수와 `"관수 장치 가동을 권장합니다"` 문자열을 f-string에 직접 박아 두었고, `tools/nodetype_verify.py`는 보드/MCU 토큰 11종·`node_id==정수` 분기만 보아 이 종류의 하드코딩을 검사 대상에 두지 않았다는 지적 그대로였다. |
| 2026-08-11 | 수정완료 | **원인**: 임계값·권장 문구 모두 Python 소스 상수 — 새 작물 기준이나 다른 장치(송풍기·냉난방기) 모델을 추가하려면 `mms.py`를 고쳐야 했다(§1-6 위반). **수정**: (1) `HIGH_TEMP_THRESHOLD_C` 상수 제거 — 임계값은 `control_model.input_spec`이 이미 선언해 둔 대로 호출자가 `inputs['crop_tmax_c']`로 공급한다(6.3-3 "입력값"), 없으면 값을 추측하지 않고 그렇게 말한다(§1-1 원칙과 대칭). (2) 권장 조치 문구는 `control_model.output_spec.recommend_action`(6.3-2 "출력값" 메타정보)에서 읽는다 — `_output_spec()` 신설. `fixtures/seed.sql`의 기존 2개 모델 `output_spec`에 `recommend_action:"관수 장치 가동"` 추가, `demo-model-llm-irrigation.input_spec`에도 `crop_tmax_c`를 맞춰 추가(폴백 경로가 두 모델 공통이므로). 이제 새 장치 종류 모델은 `control_model` 행 등록만으로 추가되고 `backend/`는 한 줄도 바뀌지 않는다. **검증기 보강**: `tools/nodetype_verify.py`에 검사 ④ 신설 — `backend/services/**/*.py`의 문자열 리터럴(독스트링 제외, f-string 리터럴 조각 포함)에서 1369-P1 6.3.4 액추에이터 명칭 토큰(`창 개폐`·`보온덮개`·`송풍기`·`관수`·`냉난방`·`차광`)을 AST로 스캔. `backend/tests/`·`repository.py` 등은 범위 밖(자유 사용자 문장·독스트링 서술이라 오탐이므로 F-190 자체 근거로 배제). **결함 주입 검증**: 수정된 `_threshold_draft`에 `recommend = "관수 장치"`를 임시로 재주입 → `nodetype_verify.py`가 정확히 그 줄을 `mms.py:100: 장치 종류 문자열 하드코딩 의심 - '관수' in '관수 장치'`로 잡아 exit 1 — 원상복구 후 exit 0 재확인. **회귀 테스트**: `backend/tests/test_services_mms.py` 신설 4건 — 런타임에 `control_model` 새 행(`"송풍기 가동"`·`"냉난방기 냉방 가동"`)을 INSERT해 `mms.py` 소스를 전혀 모르는 새 장치 모델의 초안 문구가 그 데이터 그대로 나오는지 확인(하드코딩이면 항상 같은 문구가 나왔을 것), `crop_tmax_c` 누락 시 명시적 메시지, 임계값 이하일 때 "관수" 문자열이 전혀 없는지. `test_api.py`에 1건 추가(`inputs` 생략 시 HTTP 경로에서도 동일 동작). `CLAUDE.md` §3.5 결정표에 이 미규정 결정(임계값=inputs, 문구=output_spec) 추가. 검증: `pytest siap/tests/ backend/tests/` **333/333**(328→333, +5) · `python tools/nodetype_verify.py` **PASS**(검사 5종, 신설 검사 결함 주입으로 확인) · `python tools/route_verify.py` **PASS** · `python tools/gate_e2e.py` **16/16** · `python project_docs/api/api_verify.py` **71/71** · `python fix_log/meta_verify.py` **102/102** |

