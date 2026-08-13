# F-097 · 오프라인 검증기가 잘못된 의존성·제외 정책을 거짓 통과

| 항목 | 값 |
|---|---|
| 심각도 | 오류 |
| 분류 | 코드버그 |
| 대상 | `tools/offline_verify.py:25-28,59-69,138-145` |
| 발견일 | 2026-08-08 |
| 상태 | 수정완료 |

## 근거

개발 착수 지시서 §3.0은 이 검증기가 직접 의존성 3종과 전이 의존성의 플랫폼별 존재, 그리고 `CLAUDE.md` §2.1 제외 대상이 `.gitignore`와 패키징에서 빠지는지를 검사하도록 정한다.

`CLAUDE.md` §4.3 — 의존성은 `fastapi` · `uvicorn` · `pyserial` 3개다.

공고문 3장 소스코드 제출 안내 — 빌드 산출물 `node_modules` · `build` · `.git` 등과 실행파일을 제외한다.

## 현상

세 가지 잘못된 상태가 통과한다.

1. `check_wheels_present()`는 휠 이름만 보고 `requirements.txt`를 파싱하지 않는다. 임시 복제본에 네 번째 직접 의존성 `click==8.4.2`를 추가해도 이미 전이 휠로 동봉되어 있어 6개 플랫폼 설치와 검증기 전체가 종료 코드 0이었다.
2. `check_gitignore_excludes()`는 주석과 규칙을 구분하지 않는다. 실제 규칙 없이 제외 대상 이름을 주석 한 줄에만 적어도 `True`였고 전체 검증기가 통과했다.
3. `EXCLUDE_DIRS`가 정본의 `.git/`을 누락한다. `_is_excluded(REPO_ROOT / .git / config)`의 실제 결과는 `False`였다.

현재 실제 요구사항은 직접 의존성 3개이고, 현재 `.gitignore` 규칙도 임시 Git 저장소에서 모두 매치됐다. 현재 제출물 위반이 아니라 신설 출구 검증기의 거짓 통과 결함이다.

## 영향

단계 0 출구가 성공해도 의존성이 늘었거나 제외 규칙이 무효이거나 `.git/`이 패키징 대상에 남을 수 있다. 공고문의 재현성과 빌드 산출물 제외를 완료 판정이 보장하지 못한다.

## 재현

1. `Path.read_text`가 제외 대상 이름만 든 주석을 반환하도록 메모리 주입한다.
2. `check_gitignore_excludes()`를 호출한다.
3. 실제 결과: `True, 제외 대상 4종 전부 .gitignore 에 있음`.
4. 별도 임시 복제본의 요구사항에 `click==8.4.2`를 추가하고 전체 검증기를 실행한다.
5. 실제 결과: 5개 항목 전부 `OK`, 종료 코드 0.

## 제안

요구사항의 유효 행을 파싱해 정확한 집합을 대조하고, `.gitignore`는 실제 패턴 매칭으로 검사한다. `.git/`을 포함해 실제 생성한 ZIP 엔트리와 제외 집합을 대조한다.

---

## Claude 처리 기록

| 일시 | 상태 | 내용 |
|---|---|---|
| 2026-08-08 | 신규 | GPT 단계 0 독립 검증에서 반례 3종 재현 |
| 2026-08-08 | 수정완료 | ① `check_wheels_present()`가 `requirements.txt`를 실제 파싱(`_parse_requirements`)해 `REQUIRED_PACKAGES`(3종)와 집합 비교 — 4번째 의존성이 섞이면 즉시 실패한다. ② `check_gitignore_excludes()`를 주석·빈 줄을 제거한 활성 규칙만으로 검사하도록 재작성하고, 부분 문자열 포함 대신 `fnmatch` 기반 패턴 매칭(`_pattern_covers`)으로 바꿨다. ③ `EXCLUDE_DIRS`(패키징 스캔용)에 `.git`을 추가했다 — `.gitignore` 대조 대상(`GITIGNORE_TARGET_DIRS`)과는 분리했다(`.git/`은 git 구조상 `.gitignore`에 적을 대상이 아니다). 재현 3종 전부 반전 확인: 4번째 의존성 주입 → FAIL, 주석뿐인 `.gitignore` → FAIL, `.git/config` → `_is_excluded=True`. `python tools/offline_verify.py` 전체 통과(6조합 오프라인 설치 포함) 유지. 회귀 테스트는 `fix_log/meta_verify.py` §5-a 에 추가(pure 함수를 임시 디렉터리로 직접 검증, 3종 전량) |
