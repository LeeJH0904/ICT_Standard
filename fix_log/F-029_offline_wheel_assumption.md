# F-029 · 오프라인 의존성의 순수 Python 전제 오류

| 항목 | 값 |
|---|---|
| 심각도 | 위험 |
| 분류 | 문서불일치 |
| 대상 | `project_docs/arch/아키텍처_설계서.md:348-369` |
| 발견일 | 2026-08-03 |
| 상태 | 수정완료 |

## 근거

공고문 소스코드 제출 안내 — 외부 의존으로 실행 불가하면 재현 제외 가능

FastAPI 공식 PyPI — FastAPI는 Pydantic과 Starlette에 의존한다.

Pydantic Core 공식 PyPI — OS·Python ABI별 바이너리 wheel이 별도로 배포된다.

## 현상

문서는 "의존성은 3개"이고 세 패키지가 모두 순수 Python이므로 심사자 OS를 몰라도 된다고 서술한다. 이는 직접 의존성만 센 것이며 FastAPI의 전이 의존성에 플랫폼별 `pydantic-core`가 포함된다. 한 OS에서 `pip download`한 wheels 폴더가 다른 OS/Python ABI에서 그대로 설치된다는 보장이 없다.

## 영향

오프라인 설치가 핵심 재현 경로인데 심사 환경과 맞는 wheel이 없으면 설치 단계에서 실패한다. 아직 `requirements.txt`와 `wheels/`가 없어 실제 호환 범위도 검증되지 않았다.

## 제안

직접/전이 의존성을 구분하고 버전을 고정한 뒤, 지원할 Python·OS 조합별 오프라인 설치 검증 결과와 wheel 구성을 명시한다.

---

## Claude 처리 기록

| 일시 | 상태 | 내용 |
|---|---|---|
| 2026-08-03 | 확인 | `fastapi → pydantic → pydantic-core`(Rust)가 플랫폼별 바이너리 휠임을 확인. **"셋 다 순수 Python"은 직접 의존성만 센 것으로 사실이 아니다** |
| 2026-08-03 | 수정완료 | §8.1에 전이 의존성 경고 추가. §8.3을 3단 대응으로 재작성 — ① 버전 고정 + `--platform` 지정 다중 플랫폼 휠 동봉 ② **무의존 폴백 경로** ③ 조기 검증 |
| 2026-08-03 | — | ②가 핵심이다. `firmware/tests`, `contracts/test_contract.py`, `db/verify.py` **셋은 표준 라이브러리만으로 동작**하므로, `pip install`이 실패해도 표준 준수의 근거는 남는다. README에 이 순서로 적는다 || | | |
