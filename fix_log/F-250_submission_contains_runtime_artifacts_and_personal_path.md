# F-250 · 최종 제출 폴더에 런타임 산출물과 개인 경로가 포함됨

| 항목 | 값 |
|---|---|
| 심각도 | 오류 |
| 분류 | 요건위반 |
| 대상 | `최종_제출물_폴더/ICT_Test/.omc/` · `project_code/.pytest_cache/` · `project_code/**/__pycache__/` · `project_code/backend/runtime.db` |
| 발견일 | 2026-08-20 |
| 상태 | 수정완료 |

## 근거

공고문 「소스코드 제출 안내」 — “빌드 산출물(node_modules·build·.git 등)·실행파일(.exe·.apk 등) 제외”.

공고문 「공정 평가(블라인드)」 — “평가 대상 제출물(기획서·증빙영상·발표자료·소스코드)에는 응모자를 특정할 수 있는 정보(성명·소속·학교·로고·얼굴 등)를 표기·노출할 수 없음”.

제출본 `README.md:193-194`도 캐시(`__pycache__/`)와 런타임 DB(`*.db`)를 ZIP에서 제외한다고 선언한다.

## 현상

`최종_제출물_폴더/ICT_Test`를 숨김 파일까지 전수 조사한 결과 제출 제외 대상 60개, 12,481,037 byte가 들어 있다.

- `.omc` 상태 파일 8개(5,247 byte)
- `.pytest_cache` 파일 5개(35,675 byte)
- `__pycache__`/`.pyc` 46개(1,208,883 byte)
- `project_code/backend/runtime.db` 1개(11,231,232 byte)

특히 `.omc/state/sessions/01ec5bbf-0d25-4867-a258-f0e06188465a/last-tool-error-state.json`의 `tool_input_preview`에는 Windows 사용자 홈과 사용자명을 포함한 절대 개인 경로가 남아 있다. 파일 생성·수정 시각은 2026-08-18로, 이번 검증 실행 전에 이미 존재한 산출물이다.

## 영향

현재 폴더를 그대로 ZIP으로 만들면 전체 소스코드 제출물에 개발 도구 상태·테스트 캐시·컴파일 캐시·실행 DB가 함께 들어간다. 이는 공고문의 산출물 제외 규정과 제출 README의 자체 선언에 어긋나며, 개인 경로는 블라인드 평가에서 응모자를 추정할 단서가 된다.

압축 크기 자체는 실측 17.35 MiB로 200MB 제한을 통과하지만, 크기 통과가 파일 종류 및 블라인드 위반을 해소하지는 않는다.

## 재현

```powershell
$root = Resolve-Path '.\최종_제출물_폴더\ICT_Test'
Get-ChildItem -LiteralPath $root -Recurse -Force -File |
  Where-Object {
    $_.FullName -match '\\.omc\\|\\.pytest_cache\\|\\__pycache__\\|\.pyc$|\.db(?:-shm|-wal)?$'
  }

rg -n '[A-Za-z]:[/\\]Users[/\\][^/\\]+[/\\]' '.\최종_제출물_폴더\ICT_Test\.omc'
```

실측: 제외 대상 60개, `last-tool-error-state.json`에서 개인 절대 경로 1건.

## 제안

원본 개발 폴더를 직접 압축하지 말고 허용 목록 기반의 새 staging 폴더를 만든 뒤, `.omc`·pytest/Python 캐시·런타임 DB·실행파일·개인 경로가 0건인지 재검사하고 그 staging 폴더만 ZIP으로 생성한다.

---

## 작업자 처리 기록

| 일시 | 상태 | 내용 |
|---|---|---|
| 2026-08-20 | 확인 | 최종 제출 폴더를 숨김 파일까지 재검사해 `.omc`·pytest/Python 캐시·`runtime.db` 합계 60개, 12,481,037 byte를 재현했다. `.omc` 내부 개인 절대 경로 노출도 상세 기록과 일치한다. |
| 2026-08-20 | 수정완료 | 최종 제출 폴더에서 `.omc`·`.pytest_cache`·`__pycache__`·`.pyc`·`runtime.db`를 제거해 금지 대상 0건으로 정리했다. `.gitignore`에 표준 원문 제외 규칙을 복원하고 `tools/offline_verify.py::check_final_submission_clean()`을 추가해 실제 staging의 산출물·개인 절대 경로를 gitignore와 독립 검사한다. 결함·정상 반례 테스트 4/4, offline_verify 전체 통과. 삭제 대상은 캐시·도구 상태·실행 DB로 재생성 가능하다. |
