# F-253 · verify 화면의 listNodes 호출이 화면–API 대응표에서 다시 누락

| 항목 | 값 |
|---|---|
| 심각도 | 오류 |
| 분류 | 문서불일치 |
| 대상 | `project_docs/web/화면_설계서.md:77` · `project_code/web/verify.html:346` · 제출본 동일 파일 |
| 발견일 | 2026-08-20 |
| 상태 | 수정완료 |

## 근거

화면 설계서 §2.1은 “각 화면이 어느 API를 읽고 쓰는지”를 고정하는 대응표다. 선행 결함 F-201은 이 표와 실제 화면의 GET 호출 집합을 양방향으로 대조하도록 수정되어 `수정완료`되었다.

## 현상

현재 `verify.html:346`은 주입 대상 노드를 고르기 위해 `api.listNodes({ limit: 500 })`를 호출한다. 그러나 화면 설계서 §2.1의 `verify.html` 행 읽기 칸에는 `listFrames`·`listViolations`·`listAlerts`·`injectVector`·`streamEvents`만 있고 `listNodes`가 없다.

도구를 정상 루트 구조로 복원해 제출 소스와 문서를 대조하면 `web_live_verify.py`가 다음과 같이 실패한다.

```text
FAIL 화면_설계서.md §2.1 읽기 칸이 실제 GET 호출과 화면별로 정확히 일치 (F-201)
     verify.html: 문서 누락 ['listNodes']
```

## 영향

화면–API 추적표가 실제 네트워크 표면의 정본 역할을 다시 잃었다. F-201의 수정완료 판정과 회귀 가드 기대가 깨졌으며, 설계서만 읽는 검토자는 검증 화면이 노드 목록 API에 의존한다는 사실을 알 수 없다.

## 재현

```powershell
rg -n "api\.listNodes" .\project_code\web\verify.html
rg -n "verify.html" .\project_docs\web\화면_설계서.md

# tools/가 저장소 루트에 있는 정상 구조에서
python .\tools\web_live_verify.py
# 문서 누락 ['listNodes'], exit 1
```

## 제안

§2.1 `verify.html` 읽기 칸에 `listNodes`를 추가하고, 복원된 전체 검증 진입점에서 F-201 검사가 실제로 실행되도록 한다.

---

## 작업자 처리 기록

| 일시 | 상태 | 내용 |
|---|---|---|
| 2026-08-20 | 확인 | `verify.html::populateNodeFilter()`의 `api.listNodes({ limit: 500 })` 호출과 화면 설계서 §2.1 대응표를 직접 대조해 문서에 `listNodes`만 누락된 것을 확인했다. |
| 2026-08-20 | 수정완료 | 화면 설계서 §2.1의 `verify.html` 읽기 칸에 실제 노드 필터 호출 `listNodes`를 추가했다. 구현 변경은 없다. `web_live_verify.py` F-201 양방향 대조 27/27, `web_verify.py` 75/75 통과. |
