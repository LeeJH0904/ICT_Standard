# AI 규칙 초안 시연 절차

## 1. 준비

실제 API 키를 화면·영상·로그·저장소에 노출하지 않는다. 예제 파일을 복사하고 `project_code/.env`에 값을 입력한다.

```powershell
Copy-Item project_code/.env.example project_code/.env
notepad project_code/.env
python project_code/run.py --mode simulate --serve
```

`OPENAI_API_KEY`에 실제 키를, 
`OPENAI_MODEL`에 사용하는 OpenAI 프로젝트에서 접근 가능한 모델 ID를 넣는다. 
같은 파일의 `KMA_API_KEY`는 기상청 실데이터 수집용이며 AI 시연만 할 때는 비워 둘 수 있다. 
`run.py`는 `project_code/.env`를 자동으로 읽고, 같은 이름의 프로세스 환경변수가 있으면 그 값을 우선한다. 


## 2. 실제 AI 성공 경로

1. 브라우저에서 `http://127.0.0.1:8000/rules.html`을 연다.
2. 생성 방식은 `AI_DRAFT`를 선택한다. 모델 ID 입력란은 없으며 화면이 `demo-model-llm-irrigation`을 내부 고정값으로 전송한다.
3. 입력값에 `{"crop_tmax_c":33}`을 넣고 초안을 생성한다.
4. 저장된 규칙 카드에서 `생성 경로: AI`와 AI가 작성한 한국어 초안을 확인한다.
5. 카드가 여전히 `미승인`이고 실행 버튼이 없으며 사람 승인 양식만 보이는지 확인한다.
6. 승인 전 API 응답의 `action`, `target_install_id`, `approved_at`, `approved_by`가 모두 `null`인지 확인한다.
7. 사람이 조건·명령·대상을 입력해 승인한 뒤에만 실행 버튼이 생기는지 확인한다.

## 3. 오프라인 폴백 경로

현재 프로세스를 종료하고 `project_code/.env`의 `OPENAI_API_KEY`를 비운다.
프로세스 환경변수로 키를 설정했다면 새 PowerShell을 연 뒤 다시 실행한다.

```powershell
python project_code/run.py --mode simulate --serve
```

같은 방식으로 초안을 만들면 규칙 카드에 `생성 경로: THRESHOLD_FALLBACK`과
폴백 안내가 표시돼야
한다. 초안 생성·사람 승인·실행 게이트는 계속 동작해야 한다.

## 4. 실패 진단

| 결과 | 확인할 항목 |
|---|---|
| `THRESHOLD_FALLBACK` | 키·모델 환경변수, HTTPS Base URL, 네트워크 연결 |
| HTTP 401 폴백 | API 키와 OpenAI 프로젝트 권한 |
| 모델 오류/404 폴백 | `OPENAI_MODEL`이 계정에서 사용 가능한 정확한 모델 ID인지 확인 |
| 타임아웃 폴백 | 네트워크 상태와 `OPENAI_TIMEOUT_SEC` 1~30초 범위 |

실패 상세나 응답 원문 대신 서버는 상태 종류만 기록한다. API 키는 어떤 로그에도
출력하지 않는다.
