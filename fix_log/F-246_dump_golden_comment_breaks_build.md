# F-246 · dump_golden.c의 조기 주석 종료로 교차검증 빌드가 깨진다

| 항목 | 값 |
|---|---|
| 심각도 | 오류 |
| 분류 | 코드버그 |
| 대상 | 제출본 `project_code/firmware/tests/dump_golden.c:1-22` · `Makefile:84-88` |
| 발견일 | 2026-08-18 |
| 상태 | 신규 |

## 근거

최종 README §3은 C 구현과 Python 구현이 동일한 `golden.jsonl`로 검증되며 그 일치가
상호운용성의 증거라고 설명한다. Makefile은 `dump_golden`을 C/Python 교차검증 전용
덤프 유틸리티로 정의한다.

## 현상

파일 1행에서 시작한 블록 주석이 9행의 `*/judgement=normal/alert`에서 조기 종료된다.
따라서 9~21행의 한국어 설명과 `*` 접두사가 C 토큰으로 노출되고, 22행에는 짝이 없는
`*/`가 남는다. `make dump_golden`은 이 파일을 직접 컴파일한다.

## 영향

기본 `TARGETS`의 `test_golden`과는 별개지만, README가 상호운용성 증거로 제시한
C/Python 전량 교차비교를 최종 제출물만으로 빌드·재현할 수 없다.

## 재현

```sh
cd project_code/firmware/tests
make dump_golden
# dump_golden.c:9 이후 설명문에서 C 구문 오류
```

현재 검수 환경에는 C 컴파일러가 없어 명령 자체는 실행하지 못했으나, 블록 주석
구조는 소스 정적 판독으로 확정된다.

## 제안

9행의 선행 `*/`를 제거해 22행에서 주석을 한 번만 닫고, `dump_golden`을 실제 빌드하는
검사를 제출 전 출구에 포함한다.

---

## 작업자 처리 기록

| 일시 | 상태 | 내용 |
|---|---|---|
|  |  |  |
