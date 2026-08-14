# F-226 · 노드종류 검증기가 api.py의 디바이스 종류 하드코딩을 놓침

| 항목 | 값 |
|---|---|
| 심각도 | 오류 |
| 분류 | 코드버그 |
| 대상 | `tools/nodetype_verify.py:142-205,254-276` |
| 발견일 | 2026-08-13 |
| 상태 | 수정완료 |

## 근거

`CLAUDE.md` §0 핵심 주장 3 — “노드 추가 시 서버 코드 수정이 0줄”이어야 한다.

`CLAUDE.md` §1-6 — “`project_code/backend/`에 노드 종류·디바이스 종류 하드코딩”은 금지다.

개발 착수 지시서 §3 단계 6 — 검증 범위는 `project_code/backend/**` 전체다.

## 현상

정적 장치명 검사는 `backend/services/**`만 순회한다. F-194 보완의 동적 검사는 `mms._threshold_draft()` 한 함수만 호출한다. 따라서 서비스 밖인 `backend/api.py`에 디바이스 종류별 특례 문자열을 추가해도 두 검사 모두 영향을 받지 않는다.

실제 파일을 바꾸지 않고 `Path.read_text()` 반환값에 `SPECIAL_DEVICE_KIND = 환기팬`을 추가한 결과 `tools/nodetype_verify.py`는 검사 6종과 최종 PASS를 그대로 출력하고 종료 코드 0을 반환했다. 현재 `backend/api.py`에 해당 하드코딩이 있다는 뜻은 아니며, 검증 범위가 규약보다 좁다는 결함이다.

## 영향

API나 repository 등 서비스 밖 backend 코드에 새 장치 종류 분기를 넣어도 단계 6 출구가 통과한다. 핵심 주장 3을 자동 검증했다는 결론을 낼 수 없다.

## 재현

```python
from pathlib import Path
from tools import nodetype_verify as verify

original = Path.read_text
api_path = (verify.BACKEND_DIR / api.py).resolve()

def mutant(self, *args, **kwargs):
    text = original(self, *args, **kwargs)
    if self.resolve() == api_path:
        return text + '\nSPECIAL_DEVICE_KIND = 환기팬\n'
    return text

Path.read_text = mutant
print(verify.main())
# [PASS] tools/nodetype_verify.py, 종료 코드 0
```

## 제안

장치 종류 정적 검사의 범위를 `backend/**/*.py` 전체로 맞추고, 허용되는 레지스트리 변환과 금지된 종류별 업무 분기를 구조적으로 구분하는 독립 반례를 둔다.

---

## Claude 처리 기록

| 일시 | 상태 | 내용 |
|---|---|---|
| 2026-08-13 | 확인 | `Path.read_text()`를 통해 `backend/api.py`에 `SPECIAL_DEVICE_KIND = "환기팬"`을 주입했다. backend 파일 21개를 열거하면서도 장치명 검사는 services만 보아 최종 exit 0이었다. |
| 2026-08-14 | 수정완료 | 장치 종류 문자열 검사를 테스트 픽스처를 제외한 `backend/**/*.py` 제품 코드 전체로 넓히고, 목록 밖 이름도 `device_kind`/`device_type` 상수 대입 구조로 탐지한다. `api.py`에 같은 `환기팬` 상수를 주입하는 회귀가 위반을 검출하고 현재 backend는 오탐 없이 통과한다. |
