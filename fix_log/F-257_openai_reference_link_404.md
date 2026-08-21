# F-257 · AI 활용 문서의 Responses API 공식 근거 링크가 404

| 항목 | 값 |
|---|---|
| 심각도 | 위험 |
| 분류 | 문서불일치 |
| 대상 | `docs/ai-usage.md:59` · 제출본 동기 사본 · `project_docs/dev/F-189_AI_규칙_초안_개선_방안.md:62` |
| 발견일 | 2026-08-21 |
| 상태 | 수정완료 |

## 근거

F-189 개선안 §3은 OpenAI 공식 문서를 Responses API 요청·응답 규격의 근거로 지정한다. 제출본 `docs/ai-usage.md`도 같은 링크를 구현 검증 근거로 제공한다.

현재 공식 OpenAI 문서 인덱스가 제시하는 Create a response 참조 주소는 다음과 같다.

`https://developers.openai.com/api/reference/resources/responses/methods/create`

## 현상

세 문서는 폐기된 다음 주소를 사용한다.

`https://developers.openai.com/api/reference/responses/create`

2026-08-21 직접 요청 결과 이 주소는 404이고, 현재 주소의 Markdown 문서는 HTTP 200으로 `json_schema`, `store`, `max_output_tokens`, `output_text` 필드를 제공한다.

## 영향

코드의 API 계약 자체는 현재 공식 참조와 일치하지만, 심사자와 유지보수자가 제출 문서의 근거 링크를 따라가면 페이지를 열 수 없다. F-189의 외부 규격 추적성과 검증 재현성이 약해진다.

## 재현

```powershell
Invoke-WebRequest -UseBasicParsing -Uri 'https://developers.openai.com/api/reference/responses/create'
# HTTP 404

Invoke-WebRequest -UseBasicParsing -Uri 'https://developers.openai.com/api/reference/resources/responses/methods/create.md'
# HTTP 200
```

## 제안

개발본·제출본·F-189 개선안의 링크를 현재 공식 주소로 함께 갱신한다.

---

## 작업자 처리 기록

| 일시 | 상태 | 내용 |
|---|---|---|
| 2026-08-21 | 수정완료 | 제출본·수정본 `docs/ai-usage.md`와 F-189 개선 문서의 링크를 현재 공식 `resources/responses/methods/create` 주소로 교체했다. 기존 주소의 404와 새 공식 주소의 유효성을 재확인했다. |

