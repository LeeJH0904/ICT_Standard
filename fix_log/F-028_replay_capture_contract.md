# F-028 · 실측 캡처와 replay 입력 계약 불일치

| 항목 | 값 |
|---|---|
| 심각도 | 오류 |
| 분류 | 문서불일치 |
| 대상 | `project_docs/arch/아키텍처_설계서.md:191-204`, `schema.sql:433-445` |
| 발견일 | 2026-08-03 |
| 상태 | 수정완료 |

## 근거

공고문 소스코드 제출 안내 — "제출물만으로 실제 실행(재현)이 가능한 전체 소스코드"

pySerial 공식 URL Handler 문서 — `spy://` 출력은 기본 hex dump 또는 raw/log이며 JSONL 레코드를 생성하지 않는다.

## 현상

아키텍처는 `spy://` 래핑만으로 별도 캡처 코드 없이 로그를 만든다고 하지만 replay는 `rec["t"]`, `rec["hex"]`가 있는 JSONL을 요구한다. 두 형식을 변환하는 단계가 없다. 또한 `frame_log.t`는 epoch인데 예시 재생식 `sleep(rec["t"] - elapsed)`은 첫 레코드에서 epoch 전체를 대기한다. 첫 타임스탬프를 빼는 정규화가 누락됐다.

## 영향

실측 로그가 replay 입력으로 바로 사용되지 않으며, 예시 식을 따르면 심사자 기본 경로가 사실상 멈춘다. 하드웨어 없이 재현한다는 핵심 경로가 단절된다.

## 제안

캡처 JSONL 스키마와 변환 책임을 명시하고, 상대 시간은 `(rec.t - first_t) / speed - monotonic_elapsed`로 계산한다. 캡처→replay 종단 테스트를 둔다.

---

## Claude 처리 기록

| 일시 | 상태 | 내용 |
|---|---|---|
| 2026-08-03 | 확인 | `spy://`는 hex dump 텍스트를 뱉고 JSONL이 아니다. epoch `t`로 `sleep(t - elapsed)` 하면 첫 레코드에서 **약 57년** 대기함을 계산으로 확인 |
| 2026-08-03 | 수정완료 | §5.3 **캡처 형식과 변환 책임** 신설 — `logs/raw_*.txt`(spy 원본, 진위 근거) → `sim/capture.py` → `logs/session_*.jsonl`(replay 입력). §5.4 재생식을 `(rec.t - first_t)/speed` 상대 시간 + `time.monotonic()` 기준으로 정정. 캡처→변환→replay 종단 테스트 요구 추가 || | | |
