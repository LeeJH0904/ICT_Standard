# F-196 · 웹 검증기가 실제 구현 디렉터리를 찾지 못함

| 항목 | 값 |
|---|---|
| 심각도 | 오류 |
| 분류 | 코드버그 |
| 대상 | `project_docs/web/web_verify.py:248-269` |
| 발견일 | 2026-08-12 |
| 상태 | 수정완료 |

## 근거

개발 착수 지시서 단계 7의 구현 범위는 `project_code/web/`이며, 출구 조건은 `project_docs/web/web_verify.py`가 그 구현을 설계와 대조하는 것이다.

## 현상

구현 디렉터리 후보가 저장소 루트의 `web/`과 `project_docs/web/`뿐이다. 실제 `project_code/web/`이 존재하지만 검증기는 `web/ 실물 없음 - 설계 단계이므로 실물 검사는 건너뛴다`를 출력하고 62/62로 종료한다. HTML·정적 모듈·접근성·금지 기능 구현 검사가 실행되지 않는다.

## 영향

단계 7 범위의 웹 구현이 틀리거나 없어도 설계 문서 검사만으로 출구 조건이 통과한다.

## 재현

현재 저장소에서 `python project_docs/web/web_verify.py`를 실행했다. `project_code/web/`이 존재하는데도 위 건너뛰기 문구와 `62/62 통과`를 확인했다.

---

## Claude 처리 기록

| 일시 | 상태 | 내용 |
|---|---|---|
| 2026-08-12 | 확인 | `project_docs/web/web_verify.py:248-249`의 후보 경로가 `HERE.parent.parent / "web"`(저장소 루트 `web/`)과 `HERE.parent / "web"`(`project_docs/web/web/`) 둘뿐이고 실제 구현 `project_code/web/`은 후보에 없음을 소스에서 확인. `python project_docs/web/web_verify.py` 실행 결과 "web/ 실물 없음 - 설계 단계이므로 실물 검사는 건너뛴다"로 62/62 통과함을 재현 |
| 2026-08-12 | 수정완료 | 후보 목록 맨 앞에 `HERE.parent.parent / "project_code" / "web"`을 추가(CLAUDE.md §2 디렉터리 구조가 정한 실제 경로). 기존 두 후보는 이전 스켈레톤 흔적으로 남겨 하위호환만 유지. 검증: `python project_docs/web/web_verify.py` 재실행 — "web/ 실물 4종 발견 - 실물 검사 수행"으로 전환되며 접근성 6항목(lang=ko·랜드마크·건너뛰기 링크·외부 리소스 0·localStorage 0·RSC/NEC 상수 0)이 실제로 실행됨을 확인, **62/62 → 68/68**로 통과 건수 증가(전부 PASS, FAIL 0). |

