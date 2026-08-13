# F-116 · B02 N=0 형식 오류가 정상 골든으로 생성됨

| 항목 | 값 |
|---|---|
| 심각도 | 오류 |
| 분류 | 코드버그 |
| 대상 | `project_docs/contracts/vectors/golden_layout.py:282-285` · `golden_verify.py:134-149, 211-227, 362-366` |
| 발견일 | 2026-08-08 |
| 상태 | 수정완료 |

## 근거

TTAK.KO-10.0943 §8.1.5는 `REQ_SET_DEVICE_CONTROL`이 “페이로드에 제어하고자 하는 디바이스 주 속성값을 포함하여 전송된다”고 명시한다. 표 7-10은 `INVALID_FORMAT`(0x09)을 “메시지 포맷 방식 오류”로 정의한다. Frame 구조 명세서 §4.1과 `contracts/frame.py:306-326`은 이를 구체화하여 고정부 없이 가변부만 있는 메시지의 N=0을 거부한다.

## 현상

B02의 note는 “N=0 거부”, `n=None`, `element_count()가 None을 돌려 INVALID_FORMAT”이라고 정확히 적었다. 하지만 `V()` 호출에 `violations`가 없어 생성 함수의 기본 규칙에 따라 `judgement=normal`, `violations=[]`가 된다. 양쪽 `golden.jsonl`이 같은 잘못된 판정을 담고 있다.

`golden_verify.py`도 B02의 `n is None`과 계약의 `element_count() is None`은 검사하면서, 그 결과가 `judgement=violation`이어야 한다는 연결은 검사하지 않는다. 오히려 판정 수를 `violation 7 / alert 1 / normal 44`로 고정하여 모순을 정상 상태로 봉인한다.

## 영향

C 디코더는 계약대로 B02를 `INVALID_FORMAT/7.3.1`로 거부하지만 골든이 성공을 요구해 `test_golden`이 148/150으로 실패한다. 단계 2b 출구를 통과할 수 없고, 잘못된 골든을 C 코드에 맞추려 하면 올바른 디코더를 망가뜨리게 된다.

## 재현

1. `make` 후 `project_code/firmware/tests/test_golden`을 실행한다.
2. B02의 “디코드 SUCCESS”와 “재인코딩 바이트열 일치” 두 항목이 실패한다.
3. 실제 결과는 **148/150, exit 1**이다.
4. `python project_docs/contracts/vectors/golden_verify.py`는 같은 모순을 **29/29, exit 0**으로 놓친다.

## 제안

B02에 `INVALID_FORMAT`(0x09), clause `7.3.1` 위반을 명시하고 정본에서 두 JSONL을 재생성한다. 동시에 판정 수를 `normal 43 / violation 8 / alert 1`로 갱신하고, `n is None`인 벡터가 normal/alert일 수 없다는 의미 검사를 추가한다.

---

## Claude 처리 기록

| 일시 | 상태 | 내용 |
|---|---|---|
| 2026-08-08 | 확인 | `make && ./test_golden` 148/150 재현 확인. `golden_layout.py:282-285` 의 B02 `V()` 호출에 `violations=` 인자가 없어 생성 규칙(`"violation" if violations else "normal"`)에 따라 `judgement=normal`이 되는 것을 소스에서 직접 확인. C 디코더(`siap_element_count`)는 계약(고정부 없이 가변부만 있는 메시지는 N>=1)대로 정확히 거부하고 있어 코드가 아니라 골든 데이터의 자기 모순임을 판정 |
| 2026-08-08 | 수정완료 | `golden_layout.py`: `VIO()` 정의를 `V()` 바로 뒤로 이동(B02 가 참조해야 하므로)하고, B02 항목에 `violations=VIO(0x09,"INVALID_FORMAT","7.3.1","Payload Length=0, 가변부만 있는 메시지는 N>=1 필요")` 를 추가. `golden_layout.py` 직접 실행으로 `golden.jsonl`·`golden_ext.jsonl` 재생성(직접 편집 없음, CLAUDE.md §6.2) 후 `project_code/contracts/vectors/golden.jsonl` 사본에 복사. `golden_verify.py` 갱신: ① 판정 분류 카운트 `violation 7→8, normal 44→43`(이후 F-120 의 B11 로 8→9, 43 유지) ② "n is None 인 벡터는 normal/alert 일 수 없다"는 신설 의미 검사 ③ B02 전용 검사에 `judgement==violation` + `INVALID_FORMAT/7.3.1` 확인 추가 ④ `derive()`(바이트 독립 재판정 함수)에 "고정부 없이 가변부만 있는데 rest==0"인 후보만 있으면 `INVALID_FORMAT/7.3.1`을 재도출하는 분기 신설(`resolve_kind()`/`element_count()` 를 부르지 않고 `LAYOUT` 표만으로 같은 결론에 도달해야 진짜 교차검증이므로). 검증: B02 원상(violations 제거)으로 되돌리면 `golden_verify.py`의 "n is None..." 검사와 B02 전용 검사가 각각 FAIL 함을 확인 후 재적용. 회귀: `python project_docs/contracts/vectors/golden_verify.py` **31/31**(당시 29/29) · `python project_code/contracts/test_contract.py` **62/62** · `make && ./test_golden` **253/253**(F-120 의 B11 포함, 당시 148/150) |

