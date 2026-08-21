# 생성형 AI 활용 및 검증 방식
## 1. 두 가지 AI 활용 층위

이 제출물은 생성형 AI 활용을 다음 두 층위로 구분한다.

| 층위 | 활용 | 결과를 신뢰하는 방법 |
|---|---|---|
| 개발 과정 | 기획·코드·테스트·UI·문서 초안 작성 보조 | 표준 문서 대조, 회귀 테스트, 골든 벡터, 역할이 분리된 `fix_log` 처리로 검토 |
| 앱 기능 | OpenAI Responses API를 이용한 규칙 설명 초안 생성 | Structured Outputs와 서버 2차 검증 후에도 미승인 `draft_text`로만 저장 |

AI가 만든 결과를 그대로 제어 명령으로 사용하지 않는 것이 공통 원칙이다.

## 2. 개발 과정에서의 활용

생성형 AI는 다음 작업의 초안을 만들고 반복 수정하는 보조 도구로 사용됐다.

- 요구사항과 TTA 표준 조항을 코드·DB·API·화면에 매핑
- Python·C 구현과 테스트 초안 작성
- API/UI 동작 흐름과 문서 정리
- 코드·명세·테스트 간 불일치 후보 탐색과 수정안 제시

최종 결정은 저장소 규약과 사용자 확인을 거쳤다. 특히 계약 변경, 표준 미규정 정책, 승인 게이트, 실제 하드웨어·외부 API처럼 
결과를 과장할 수 있는 지점은 자동 판정하지 않았다. 발견과 수정은 검증자/작업자 역할을 분리한 `fix_log` 절차로 추적했다.

산출물은 다음 방식으로 검토한다.

- Python 단위·API 통합 테스트
- C와 Python이 공유하는 손작성 골든 벡터 대조
- DB CHECK·트리거와 승인/실행 게이트 회귀 테스트
- 키가 없는 오프라인 기본 경로의 전체 테스트
- 개발 코드가 아니라 최종 제출본 자체에서 재실행하는 검증

## 3. 앱 기능으로서의 OpenAI 규칙 초안

`project_code/backend/services/mms.py`는 `control_model.exec_method='llm_draft'`인 모델에 한해 OpenAI Responses API를 한 번 호출한다.

| 항목 | 구현 |
|---|---|
| Base URL | `OPENAI_BASE_URL`, 기본값 `https://api.openai.com/v1` |
| 경로 | `POST {OPENAI_BASE_URL}/responses` |
| 인증 | `OPENAI_API_KEY`를 Bearer 헤더로 전송 |
| 모델 | `OPENAI_MODEL`, 예시 `gpt-5.4-mini` |
| 출력 | `text.format.type='json_schema'` Structured Outputs |
| 저장 | `store=false` |
| 의존성 | Python 표준 라이브러리 `urllib`만 사용 |
| 환경 설정 | `run.py`가 `project_code/.env`를 자동 로드하며 프로세스 환경변수 우선 |

## 4. 프롬프트와 데이터 최소화

서버는 기상청 원본 payload 전체, 사용자 정보, 장치 식별자와 API 키를 모델에 보내지
않는다. 다음 값만 검증해 JSON 입력으로 보낸다.

- 예보 최고기온 `forecast_tmax_c`
- 작물 고온 임계값 `crop_tmax_c`
- 모델 메타정보의 `recommend_action`
- 데이터 출처 설명

고정 instructions는 입력 JSON을 지시가 아닌 불신 데이터로 취급하고, 제공된 값만 비교하며, 
실행 가능한 JSON·코드·제어 필드·승인 결과를 만들지 말라고 요구한다.
응답 스키마는 추가 필드가 없는 `{"draft_text": "string"}` 한 개뿐이다.

## 5. 응답 검증

프롬프트와 Structured Outputs를 통과해도 서버가 다시 검증한다.

1. HTTPS URL과 2xx 응답인지 확인한다.
2. 응답을 최대 256 KiB로 제한한다.
3. UTF-8 JSON object와 `status='completed'`, `error=null`을 확인한다.
4. 완료된 message 안에 `output_text`가 정확히 하나인지 확인한다.
5. 출력 문자열을 다시 JSON으로 파싱한다.
6. 키가 `draft_text` 하나뿐인지 확인한다.
7. 공백이 아닌 1~1,000자이며 제어문자가 없는지 확인한다.
8. 거부·불완전·오류·모호한 출력은 전부 폐기한다.

API 키, Authorization 헤더, 프롬프트와 응답 원문은 로그에 남기지 않는다.

## 6. 오프라인 폴백

다음 경우 외부 호출을 하지 않거나 결과를 폐기하고 기존 임계값 초안으로 전환한다.

- `OPENAI_API_KEY` 또는 `OPENAI_MODEL` 미설정
- 유효하지 않은 Base URL이나 입력값
- DNS·TLS·연결·타임아웃 오류
- HTTP 4xx/5xx와 rate limit
- 크기·JSON·상태·스키마·문자열 검증 실패

실제 AI 성공은 `generation='AI'`, 폴백은 `generation='THRESHOLD_FALLBACK'`으로 저장한다. 
API 키와 네트워크가 없어도 전체 애플리케이션과 테스트가 정상 동작하므로 온라인 AI는 필수 의존성이 아니다.

## 7. 사람 검토와 승인 게이트

AI 결과는 `control_rule.draft_text`에만 저장된다. 생성 직후에는 다음 값이 모두 비어 있다.

- `condition_expr`
- `action_json`
- `target_install_id`
- `approved_at`
- `approved_by`

사용자가 승인 API에서 조건·명령·대상을 직접 입력하고 승인해야만 실행 경로가 열린다.
AI 문자열을 제어 필드로 파싱하거나 복사하는 경로는 없다. 이 불변조건은 서비스·API 테스트와 DB CHECK·트리거가 함께 강제한다.

## 8. 검증 범위

네트워크 없는 자동 테스트는 요청 URL·헤더·모델·JSON Schema, 정상 AI 응답,
키/모델 부재, HTTP 오류, 전송 오류, 과대·비정상·거부 응답, 비밀값 비노출과 승인 게이트를 검증한다.

실제 OpenAI 호출은 유효한 프로젝트 키와 해당 계정에서 사용할 수 있는 모델이필요하므로 제출물 제작 과정에서 자동 실행하지 않는다. 
운영자가 `project_code/.env`나 프로세스 환경변수를 설정한 뒤 `docs/AI_규칙_초안_시연.md` 절차로 확인한다. 
대화 이력, 스트리밍, 도구 호출, 다중 제공자, 재시도 큐와 프롬프트 버전 관리는 추후 발전 가능 요소로 남긴다.
