# F-240 · 런타임 DB 7개가 제출 대상에 남음

| 항목 | 값 |
|---|---|
| 심각도 | 위험 |
| 분류 | 요건위반 |
| 대상 | `.gitignore` · `tools/offline_verify.py` · 미추적 SQLite 7개 |
| 발견일 | 2026-08-16 |
| 상태 | 수정완료 |

## 근거

공고문 소스코드 제출 안내 — “빌드 산출물(node_modules·build·.git 등)·실행파일 ... 제외”. 제출물은 전체 소스코드 ZIP이다.

## 현상

현재 트리에 런타임 DB·WAL·SHM 7개 약 128MB가 있고 모두 `git check-ignore`에 잡히지 않는다. `offline_verify.py`는 이를 제출 크기에 포함해 138.9MB로 계산하지만 200MB 미만이라 전체 통과한다.

## 영향

작업 폴더를 그대로 압축하면 소스가 아닌 실행 데이터가 제출되며, DB 내용과 크기가 실행마다 달라 재현성과 제출물 청결성이 흔들린다. 아직 ZIP 생성 전이라 위험으로 판정한다.

## 재현

```text
git status --short => *.db, *.db-wal, *.db-shm 7개
git check-ignore ... => 출력 없음
python tools/offline_verify.py => 138.9MB, 전체 통과
```

## 제안

실제 소스 패키징 경로에서 생성 DB를 제외하고 이를 검증기가 실패로 탐지하게 한다.

---

## 작업자 처리 기록

| 일시 | 상태 | 내용 |
|---|---|---|
| 2026-08-17 | 확인 | 두 축으로 분리해 확인. (가) **패키징 제외**: `.gitignore` 에 `*.db`·`*.db-wal`·`*.db-shm`·`*.db-journal`(F-160)이 이미 있고 `git check-ignore` 가 런타임 DB 를 잡으며 `git ls-files` 상 추적 DB 0개 → git-archive 제출 경로는 이미 청결. (나) **검증기 탐지**: `offline_verify.py` 의 `check_zip_size`·`check_no_binaries` 가 `REPO_ROOT.rglob("*")` 로 폴더를 훑으며 `.gitignore` 를 모른다 → 온디스크 DB 6개(runtime.db×2·runtime_stage7.db·x_dbg.db·x_dbg2.db·x_test_api.db, 약 128MB)를 크기에 포함(138.9MB)하고 실패로도 탐지하지 못함. |
| 2026-08-17 | 수정완료 | `offline_verify.py`: (1) `_gitignored_files()`(`git ls-files --others --ignored --exclude-standard`) 신설, `_is_excluded()` 가 이를 참조해 무시 파일을 패키징 walk 에서 제외 → 크기 추정 **138.9MB→16.5MB**(실제 git-archive 와 일치, 307개 무시 파일 제외). (2) `check_no_tracked_databases()` 신설 — `git ls-files` 에 `*.db` 계열이 하나라도 있으면 FAIL(실수 커밋 방지), 현재 0개 PASS. **회귀**: `tools/tests/test_offline_verify.py` 신설(추적 DB 0 확인 + gitignore 된 DB 가 walk 에서 제외되는지 임시 파일로 검증) 2/2 PASS. 온디스크 DB 6개 자체는 gitignore 되어 제출물에 안 들어가나, 폴더 직접 압축 대비 삭제 여부는 사용자에게 확인 요청. |

