# F-013 · Windows JSON 인코딩으로 계약 테스트 실패

| 항목 | 값 |
|---|---|
| 심각도 | 오류 |
| 분류 | 코드버그 |
| 대상 | `project_docs/contracts/test_contract.py:96-98`, `project_docs/siap/spec_verify.py:163` |
| 발견일 | 2026-08-03 |
| 상태 | 수정완료 |

## 근거

`CLAUDE.md` §4.1 — "파일 인코딩 UTF-8, 개행 LF"

`test_contract.py:98` — `json.load(open(p))`

`spec_verify.py:163` — `json.dump(vectors, open("spec_examples.json","w"), ensure_ascii=False, indent=1)`

## 현상

두 파일 모두 텍스트 파일을 열 때 `encoding="utf-8"`과 개행을 지정하지 않는다. 현재 저장된 `spec_examples.json`은 UTF-8이므로 한국어 Windows의 기본 CP949 환경에서 `python test_contract.py`를 실행하면 `UnicodeDecodeError`로 중단된다. 반대로 같은 환경에서 `spec_verify.py`를 실행하면 결과 JSON이 CP949·CRLF로 다시 작성되어 프로젝트 인코딩 규약을 위반한다.

## 영향

문서에 기재된 계약 검증 29/29를 기본 Windows 환경에서 재현할 수 없다. 검증 스크립트를 실행하는 것만으로 정본 JSON의 인코딩과 개행이 바뀔 수도 있다.

## 재현

```powershell
cd project_docs/contracts
python test_contract.py
# UnicodeDecodeError: 'cp949' codec can't decode byte ...
```

별도 임시 폴더에서 기본 환경으로 `spec_verify.py`를 실행한 결과 생성된 JSON은 엄격한 UTF-8 디코딩에 실패하고 CRLF를 포함했다. `PYTHONUTF8=1`을 설정한 경우에만 계약 테스트가 29/29 통과했다.

## 제안

입출력 파일 경로를 `Path(__file__)` 기준으로 고정하고 `encoding="utf-8"`, 필요한 경우 `newline="\n"`을 명시한다.

---

## Claude 처리 기록

| 일시 | 상태 | 내용 |
|---|---|---|
| 2026-08-03 | 확인 | `spec_examples.json`에 비ASCII 126바이트 존재 확인. CP949 기본 환경에서 `test_contract.py` 디코딩 실패, `spec_verify.py` 출력이 CP949+CRLF로 재작성됨을 재현 |
| 2026-08-03 | 수정완료 | `spec_verify.py` — `HERE = Path(__file__).resolve().parent` 도입, 출력에 `encoding="utf-8", newline="
"` 명시. `test_contract.py` — 입력 경로를 `Path(__file__)` 기준으로 고정하고 `encoding="utf-8"` 명시. 두 파일의 인코딩 미지정 `open()` 0건 확인. 다른 디렉터리 및 `PYTHONIOENCODING=cp949` 환경에서 36/36 통과, 생성 JSON에 CRLF 없음 |
