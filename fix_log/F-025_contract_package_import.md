# F-025 · 계약 인터페이스 패키지 import 실패

| 항목 | 값 |
|---|---|
| 심각도 | 오류 |
| 분류 | 코드버그 |
| 대상 | `project_docs/contracts/siap_iface.py:8` |
| 발견일 | 2026-08-03 |
| 상태 | 수정완료 |

## 근거

`Frame_구조_명세서.md` §5 — 서비스 계층은 `contracts/siap_iface.py`의 Protocol을 참조한다.

아키텍처 설계서 §2 — `backend/`는 `contracts/`를 통해 `SiapLink`를 사용한다.

## 현상

`siap_iface.py`가 `from frame import ...` 절대 import를 사용한다. 스크립트 폴더를 직접 `sys.path`에 넣은 경우만 동작하고, 프로젝트 루트에서 정상적인 패키지 경로로 가져오면 `frame` 최상위 모듈이 없어 실패한다.

## 영향

아키텍처대로 `backend`가 `contracts.siap_iface`를 가져오는 순간 시작 단계에서 중단된다. 현재 계약 테스트는 `siap_iface.py`를 import하지 않아 이 오류를 검출하지 못한다.

## 재현

```powershell
cd <저장소 루트>
python -B -c "import project_docs.contracts.siap_iface"
# ModuleNotFoundError: No module named 'frame'
```

## 제안

패키지 상대 import를 사용하고, 실제 소비 방식과 같은 경로의 import smoke test를 계약 테스트에 포함한다.

---

## Claude 처리 기록

| 일시 | 상태 | 내용 |
|---|---|---|
| 2026-08-03 | 확인 | `ModuleNotFoundError: No module named 'frame'` 재현 |
| 2026-08-03 | 수정완료 | `try: from .frame import ... / except ImportError: from frame import ...` 로 패키지·스크립트 양쪽 지원. 계약 테스트에 import smoke test 추가 || | | |
