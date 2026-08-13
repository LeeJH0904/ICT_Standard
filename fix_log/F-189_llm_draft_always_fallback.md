# F-189 · llm_draft가 항상 임계값 폴백이라 AI 초안 시연이 성립하지 않음

| 항목 | 값 |
|---|---|
| 심각도 | 치명 |
| 분류 | 문서불일치 |
| 대상 | `project_code/backend/services/mms.py:87-96` · `project_docs/demo/시연_시나리오.md:51,69` · `docs/ai-usage.md` |
| 발견일 | 2026-08-11 |
| 상태 | 보류 |

## 근거

공고문 개요 — “지정된 TTA 표준 134개 중 3개 이상을 조합 사용하고 생성형 AI 활용한 애플리케이션 데모개발”.

공고문 1차 평가 「생성형 AI 활용성」 — “바이브코딩이 수행한 단계 및 역할과 산출물(소스코드 검증 등) 검토 방식”.

시연 시나리오 S5는 “AI가 만든 규칙 초안”과 “기상청 예보 → AI 규칙 초안”을 실제 화면 증거로 제시한다. `CLAUDE.md` §9는 `docs/ai-usage.md`를 생성형 AI 활용 단계와 검증 방식의 근거 문서로 지정한다.

## 현상

`mms._try_llm_draft()`는 입력이나 설정과 무관하게 항상 `None`을 반환한다. 따라서 `control_model.exec_method='llm_draft'`인 시드 모델도 실제 생성형 AI를 호출하지 않고 `_threshold_draft()`로만 내려가며, `generation`은 항상 `THRESHOLD_FALLBACK`이다.

HTTP로 `demo-model-llm-irrigation`을 직접 호출한 결과는 201이지만 다음과 같았다.

```text
origin=AI_DRAFT
generation=THRESHOLD_FALLBACK
draft_text=예보 최고기온 34°C가 임계값 33°C를 초과합니다 ... 관수 장치 가동을 권장합니다.
```

`createRuleDraft`가 `mms.run_model()`을 호출하고 생성 경로를 기록한다는 구조 자체는 확인됐다. 그러나 실제 AI 경로는 한 번도 실행될 수 없다. 더구나 정본 참조표가 지정한 `docs/ai-usage.md`도 존재하지 않는다.

## 영향

현재 S5를 “AI가 만든 규칙 초안”으로 시연하면 실행 결과와 설명이 어긋난다. 생성형 AI 활용성 15점의 기능 증거와 검토 방식 문서가 동시에 비어 있어, 단계 6 기능 3의 핵심 주장이 성립하지 않는다.

## 재현

```python
# seed=True인 임시 DB와 create_app()으로 실제 HTTP 요청
POST /api/v1/rules
{"origin": "AI_DRAFT", "model_id": "demo-model-llm-irrigation"}

# 실측
HTTP 201
response.generation == "THRESHOLD_FALLBACK"
```

```powershell
rg -n "def _try_llm_draft|return None" project_code/backend/services/mms.py
rg --files docs
# standard-findings.md만 출력되고 ai-usage.md는 없음
```

---

## Claude 처리 기록

| 일시 | 상태 | 내용 |
|---|---|---|
| 2026-08-11 | 확인 | 재현 성공(`_try_llm_draft()`가 입력·설정 무관하게 항상 `None`, `docs/ai-usage.md` 부재 자체도 확인). 다만 **재현 직후 근거를 직접 확인해 판정 범위를 정정**(§11.3 "판정 근거를 처리 기록에 남긴다") — 공고문 1차 평가 배점표 원문("생성형 AI 활용성 15점 — 기획·코드작성·UI설계·데이터정리·기능 등 **바이브코딩이 수행한 단계 및 역할**과 산출물 검토 방식")과 `project_docs/demo/시연_시나리오.md:51`("AI가 만든 규칙 초안이 **승인 없이는 구동기에 닿지 않는다**")을 대조한 결과, 이 15점 항목의 채점 근거는 "배포된 앱이 런타임에 LLM을 호출하는가"가 아니라 "**이 제출물을 만드는 개발 과정**에서 생성형 AI(바이브코딩)를 어떻게 썼고 검증했는가"이며, S5의 채점 근거도 승인 게이트 안전성(F-017 등, 이미 구현·검증됨)이지 실제 추론 여부가 아니다. 따라서 이 발견의 실제 결함은 `docs/ai-usage.md` 부재 하나이고, `_try_llm_draft()`가 `None`인 것 자체는 `origin`(의도)/`generation`(실행 결과) 분리 설계(F-083)가 이미 `THRESHOLD_FALLBACK`으로 정직하게 표시하고 있어 "명백한 허위"에 해당하지 않는다고 판단(§1). 이 재해석을 사용자에게 보고하고 처리 범위를 확인받았다. |
| 2026-08-11 | 보류 | **사용자 결정(2026-08-11)**: `docs/ai-usage.md`는 지금 신설하되, 단계 7(`web/`)·단계 8(보드 3종 실물 통합)이 아직 남아 있어 전체 개발 과정을 아우르는 서술을 지금 확정하면 마지막 두 단계의 실적이 빠진 채 "작성 완료"로 보일 위험이 있다(§1 "명백한 허위" 원칙과 같은 이유) — **본문 없이 "이 문서가 채워야 할 항목"만 명시한 뼈대로 신설**하고, 실제 내용 작성은 모든 개발 단계가 끝난 뒤 진행하기로 확정. `docs/ai-usage.md` 신설 — §1 이 문서가 답해야 하는 질문(공고문 원문 인용, "개발 과정 AI 활용"과 "앱 기능으로서의 AI"를 분리), §2 채워야 할 절 5개(2.1 단계별 AI 역할표, 2.2 산출물 검증 방식, 2.3 사람 검토 지점, 2.4 `mms.py llm_draft`의 실제 상태를 있는 그대로 적을 자리, 2.5 한계) 각각의 내용 명세. **재검토 시점: 단계 8 완료 직후** — 그때 이 뼈대를 채우고 상태를 `수정완료`로 전환한다. `mms.py` 코드 변경은 이번 처리에 포함하지 않는다(F-190이 이미 `_threshold_draft`의 하드코딩만 정리했고, `_try_llm_draft()`의 실제 제공자 연동 여부는 §2.4에서 단계 8 이후 결정하기로 사용자가 유보). |

