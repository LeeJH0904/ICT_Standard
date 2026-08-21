# F-256 · Rules 화면의 예보 최고기온 입력이 서버에서 무시됨

| 항목 | 값 |
|---|---|
| 심각도 | 오류 |
| 분류 | 코드버그 |
| 대상 | `project_code/web/rules.html:49-50,366` · `project_code/backend/api.py:769-777` · 제출본 동기 사본 |
| 발견일 | 2026-08-21 |
| 상태 | 수정완료 |

## 근거

TTAK.KO-10.0937 6.3-3·6.3-4의 구현 결정은 `backend/api.py:770`에 “DMS가 사전 획득한 공공데이터를 입력으로 쓴다”고 기록돼 있다.

F-189 개선안 §6도 외부 모델에 보낼 `forecast_tmax_c`를 “기존 코드가 검증하여 추출한 최소 데이터”로 정의하고, 전체 기상청 payload 대신 DMS가 획득한 TMX만 전송하도록 정한다.

## 현상

Rules 화면은 입력 예시로 `{forecast_tmax_c:35,crop_tmax_c:30}`을 제시하고 “공공데이터 표의 행을 참고해 예보값을 채워 넣습니다”라고 안내한 뒤 해당 JSON을 그대로 `body.inputs`로 보낸다.

그러나 API는 `inputs.forecast_tmax_c`를 읽지 않는다. `public_data_record_id`가 없으면 새 DMS 레코드를 수집하고, 그 payload를 `inputs[forecast_payload]`에 넣는다. `mms.py`는 이 `forecast_payload`의 TMX만 사용한다.

실행 반례에서 화면과 같은 요청으로 `forecast_tmax_c=999`를 전송해도 초안은 목업 TMX 34°C를 사용했다.

```text
요청 inputs = {forecast_tmax_c: 999, crop_tmax_c: 33}
응답 generation = THRESHOLD_FALLBACK
응답 draft_text = 예보 최고기온 34°C가 임계값 33°C를 초과합니다 ...
```

## 영향

사용자는 입력한 예보값이 AI/임계값 판단에 반영됐다고 오인한다. UI에 노출된 핵심 입력 하나가 무효이며, 화면 설명과 실제 DMS 기반 실행 경로가 불일치한다.

## 재현

```powershell
python project_code/run.py --mode simulate --serve

$body = @{
  origin='AI_DRAFT'
  model_id='demo-model-llm-irrigation'
  inputs=@{forecast_tmax_c=999; crop_tmax_c=33}
} | ConvertTo-Json -Depth 4
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/api/v1/rules -ContentType application/json -Body $body
# draft_text에는 999가 아니라 DMS 목업의 34가 기록됨
```

## 제안

UI에는 실제 사용자 입력인 `crop_tmax_c`만 명확한 숫자 필드로 받는다. 기존 공공데이터 행을 선택하려는 기능이라면 `public_data_record_id`를 행 선택 UI와 결선하고, 임의 `forecast_tmax_c` 입력은 제거한다.

---

## 작업자 처리 기록

| 일시 | 상태 | 내용 |
|---|---|---|
| 2026-08-21 | 수정완료 | Rules 화면의 임의 JSON·`forecast_tmax_c` 입력을 제거하고 `crop_tmax_c` 숫자 필드만 전송하도록 변경했다. 예보는 DMS 최신 레코드에서만 가져오며 API는 직접 전달된 `forecast_tmax_c`를 HTTP 400으로 거부한다. UI/API 회귀 테스트를 추가했고 전체 440건이 통과했다. |

