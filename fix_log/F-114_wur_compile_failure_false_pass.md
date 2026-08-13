# F-114 · WUR 검사가 모든 컴파일 실패를 정상 속성 경고로 오판함

| 항목 | 값 |
|---|---|
| 심각도 | 오류 |
| 분류 | 코드버그 |
| 대상 | `project_code/firmware/tests/check_wur.py:37-73` |
| 발견일 | 2026-08-08 |
| 상태 | 수정완료 |

## 근거

`CLAUDE.md` §4.2는 `bp_write`와 `bp_write_f32`의 반환값을 버릴 때 `-Werror=unused-result` 때문에 빌드가 실패해야 한다고 규정한다. 펌웨어 설계서 §4.1도 실패 원인을 `warn_unused_result` 속성과 `-Werror=unused-result`의 조합으로 한정한다. 따라서 회귀 검사는 단순히 비정상 종료만 볼 것이 아니라 그 계약 때문에 실패했는지 확인해야 한다.

## 현상

`check_wur.py`는 각 스니펫의 컴파일 종료 코드가 0이면 회귀로 기록하고, 0이 아니면 원인을 보지 않고 정상으로 처리한다. stderr의 `unused-result` 진단은 전혀 검사하지 않는다.

실제 모듈을 로드한 뒤 `SNIPPETS` 두 항목을 존재하지 않는 파일명으로 메모리 주입하고 `main()`을 실행했다. GCC는 `No such file`로 실패했지만 스크립트는 다음을 출력하고 exit 0을 반환했다.

```text
OK(F-113): bp_write()/bp_write_f32() return-value discard correctly fails to compile
MISSING_SNIPPETS_CHECK_WUR_EXIT 0
```

또한 `-U__GNUC__`로 실제 헤더의 `SIAP_WUR` fallback을 빈 매크로로 만든 실행에서도 MinGW 표준 헤더가 `VARARGS not implemented` 등 무관한 오류로 실패하자 같은 OK·exit 0이 나왔다. 즉 속성이 없는데 다른 오류 하나만 있으면 검사가 녹색이다.

## 영향

WUR 스니펫 파일이 삭제·오타·문법 오류 상태이거나 컴파일러/헤더 설정이 깨져도 `make test_bitpack`의 `check_wur` 선행조건이 통과한다. 그 상태에서 `SIAP_WUR`나 `-Werror=unused-result`가 함께 회귀해도 자동 출구는 원인을 구분하지 못해 F-113의 수정 증거가 무효가 된다.

## 재현

1. `check_wur.py`를 모듈로 로드한다.
2. `SNIPPETS`를 존재하지 않는 C 파일 두 개로 바꾼다.
3. 실제 `main([gcc, -std=c99, -Werror=unused-result, -I../core])`을 호출한다.
4. 실제 결과: GCC 컴파일 실패를 정상으로 간주하여 `OK(F-113)`과 exit 0.

## 제안

각 실패의 stderr가 해당 함수의 `warn_unused_result`/`unused-result` 진단인지 확인하고, 소스 누락·구문 오류·헤더 오류·도구 실패는 검사 실패로 분리한다. 스니펫 존재와 컴파일러 실행 가능 여부를 선검사하고, “누락 스니펫”과 “무관한 `#error`” 반례를 회귀로 고정한다.

---

## Claude 처리 기록

| 일시 | 상태 | 내용 |
|---|---|---|
| 2026-08-08 | 신규 | GPT 단계 2a 2차 검증에서 스니펫 파일 누락·무관한 컴파일 오류가 모두 `OK(F-113)`·exit 0으로 거짓 통과하는 것을 재현 |
| 2026-08-08 | 확인 | `check_wur.py`를 모듈로 로드해 `SNIPPETS`를 존재하지 않는 파일명으로 바꾸고 `main()` 실행 — `No such file` 컴파일 실패에도 `OK(F-113)`·exit 0이 나옴을 확인 |
| 2026-08-08 | 수정완료 | `check_wur.py`를 재작성: ① 컴파일러(`cc --version`) 실행 가능 여부를 가장 먼저 확인 ② 각 스니펫 파일이 실재하는지 컴파일 시도 전에 확인(없으면 즉시 `unusable`로 분류) ③ 컴파일이 실패했을 때 그 stdout+stderr 진단문에 `unused-result`/`warn_unused_result`/`unused_result` 중 하나가 실제로 있는지 확인 — 없으면 "실패는 했지만 원인이 다르다"로 별도 분류해 FAIL 처리. 세 경로(컴파일러 없음·스니펫 없음·무관한 컴파일 오류) 모두 `FAIL(F-114)`로 명확히 보고하도록 함. 결함 주입 재현: ① `SNIPPETS`를 존재하지 않는 파일 2개로 교체 → `FAIL(F-114): ... snippet source missing` 2건, exit 1 ② 반환값 폐기와 무관한 구문 오류 스니펫 주입 → `FAIL(F-114): ... compile failed but NOT due to unused-result`, exit 1 ③ 존재하지 않는 컴파일러 이름 전달 → `FAIL(F-114): compiler ... is not runnable`, exit 1. 정상 케이스(원본 스니펫 + 실제 gcc)는 여전히 `OK(F-113/F-114)`·exit 0. 회귀: `make test_bitpack && ./test_bitpack` 정상 동작 유지 |
| 2026-08-08 | 재발(단계 2b) | **check_wur.py 자체는 옳았지만 검사 대상 목록이 낡았다.** 단계 2b 에서 `siap_frame.h` 로 `SIAP_WUR` 가 9개(encode_hdr/np/mcp, tx_put_hdr/rsc/nec/np/mcp/device_id) 새로 생겼는데 `SNIPPETS` 튜플은 `bitpack.h` 의 2개뿐이었고, 신설 테스트 타깃(`test_siap_frame` 등)도 `check_wur` 를 선행조건으로 물지 않아 새 헤더 쪽 회귀는 어떤 자동 출구도 검증하지 못했다 — F-113/F-114 가 막았던 것과 같은 종류의 구멍이 새 코드에서 재발한 것이다. `test_bitpack_wur_bp_write.c` 와 동일한 패턴(반환값을 그냥 버리는 최소 `main()`)으로 9개 스니펫을 신설하고 `SNIPPETS` 에 추가, `Makefile` 의 `test_siap_frame` 타깃에도 `check_wur` 를 선행조건으로 걸었다. 결함 주입 재현: `siap_tx_put_hdr` 의 `SIAP_WUR` 를 실제로 제거 → `make check_wur` 가 정확히 `FAIL(F-113): siap_tx_put_hdr() return-value discard did not fail to compile` 로 검출(다른 8개는 여전히 OK), 원상복구 후 재확인. 회귀: `make check_wur` 11개 스니펫 전량 `OK(F-113/F-114)` · `make && ./test_siap_frame` 등 4종 전량 통과 |
