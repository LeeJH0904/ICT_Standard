# F-215 · 공개 디코더가 불완전 입력에서 예외를 던짐

| 항목 | 값 |
|---|---|
| 심각도 | 오류 |
| 분류 | 코드버그 |
| 대상 | `project_code/siap/codec.py:L531` · `project_code/siap/tests/test_codec.py:L61` |
| 발견일 | 2026-08-12 |
| 상태 | 신규 |

## 근거

CLAUDE.md §4.3 — “디코딩 실패 시 예외를 던지지 않는다. `violations`가 채워진 `Frame`을 반환한다.”

Frame 구조 명세서 §1 — “파싱 실패해도 `violations`가 채워진 `Frame`을 반환한다. 깨진 프레임이 기능 2의 표시 대상이기 때문.”

개발 착수 지시서 §3.3 GPT 검증 — “디코딩 실패가 예외가 아니라 `violations` 채운 `Frame`인가.”

## 현상

공개 함수 `decode_frame()`은 입력이 12byte 헤더보다 짧거나 선언된 payload보다 짧으면 `IncompleteFrameError`를 던진다. `test_decode_incomplete_header_raises`와 `test_decode_incomplete_payload_raises`도 이 예외를 요구한다. 내부 스트리밍 `Decoder.feed()`가 예외를 잡아 버퍼링하는 것과 별개로, 공개 함수 계약은 예외를 노출한다.

## 영향

`decode_frame()` 직접 호출자는 계약대로 Frame 하나만 처리할 수 없고 별도 예외 경로를 가져야 한다. 불완전·절단 프레임은 `violations`와 원본 바이트를 가진 기능 2 표시 대상으로 전달되지 않는다. 구현 주석이 불완전 입력을 예외로 정당화하지만 상위 정본 세 곳은 예외를 허용하지 않으므로 구현이 틀렸다.

## 재현

```powershell
cd project_code
python -c 'from siap.codec import decode_frame; print(decode_frame(bytes.fromhex(''1200'')))'
```

실행 결과:

```text
siap.codec.IncompleteFrameError: 헤더 미달: 2 byte
```

## 제안

스트리밍의 “아직 대기” 상태와 공개 디코딩 결과를 분리하되, 공개 `decode_frame()`은 정본 계약대로 `violations` Frame만 반환하게 한다. 헤더가 없어 기존 `Header`를 만들 수 없다면 계약 타입 변경 절차를 먼저 밟아 불완전 입력을 표현할 방법을 확정한다.

---

## Claude 처리 기록

| 일시 | 상태 | 내용 |
|---|---|---|
