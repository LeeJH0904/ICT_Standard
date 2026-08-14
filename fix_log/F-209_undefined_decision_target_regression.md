# F-209 · 표준 미규정 결정의 폐기된 이관 규칙이 단계 1에 잔존

| 항목 | 값 |
|---|---|
| 심각도 | 오류 |
| 분류 | 문서불일치 |
| 대상 | `project_docs/contracts/Frame_구조_명세서.md:L291` · `project_code/contracts/frame.py:L389` · F-134 |
| 발견일 | 2026-08-12 |
| 상태 | 수정완료 |

## 근거

`CLAUDE.md` §3.5는 미규정 사항을 그 절과 관련 설계 문서에 기록하고, `docs/standard-findings.md`는 `표준결함` 전용이라 이관하지 않는다고 정한다. F-134도 이 방향으로 수정완료 처리됐다.

## 현상

Frame 구조 명세서의 위반 Notify 무회신 결정은 여전히 `docs/standard-findings.md`에 등재한다고 명령하고, 구현 계약 docstring도 그 파일을 참조한다. 실제 결정은 `CLAUDE.md` §3.5에 있으며 표준결함 정본에는 없다.

## 영향

단계 1 문서를 따르면 미규정 결정을 표준결함 정본에 섞어 19건 불변식과 메타 검증을 깨게 된다. F-134 수정완료가 동일 정책의 잔존 위치를 모두 닫지 못했다.

## 재현

```text
CLAUDE.md §3.5            -> 관련 결정 표 기록, standard-findings 이관 금지
Frame 명세서:L291        -> standard-findings.md에 등재
contracts/frame.py:L389 -> standard-findings.md 참조
standard-findings.md     -> 해당 결정 없음, 표준결함 19건만 존재
```

## 제안

두 잔존 참조를 §3.5 결정 표로 통일하고, 미규정 결정 문맥의 `standard-findings.md` 지시를 메타 검증으로 금지한다.

---

## Claude 처리 기록

| 일시 | 상태 | 내용 |
|---|---|---|
| 2026-08-14 | 확인 | `CLAUDE.md` §3.5는 표준 미규정 결정을 관련 설계 문서에 기록하고 `docs/standard-findings.md`로 이관하지 않도록 정하지만, Frame 명세서와 `contracts/frame.py::reply_kind()`는 여전히 그 파일을 참조한다. 표준결함 정본에는 해당 결정이 없고 meta 검증도 111/111 통과함을 확인했다. `project_code/contracts/` 편집은 계약 변경 승인 전까지 보류한다. |
| 2026-08-14 | 수정완료 | 사용자 승인 후 `contracts/frame.py::reply_kind()`와 Frame 구조 명세서 §5.2의 결정 위치를 `CLAUDE.md` §3.5 및 관련 명세로 통일했다. `standard-findings.md`는 표준 자체 결함 19건 전용임을 명시했고, 옛 “등재” 지시를 재주입하자 meta 검증이 FAIL로 반전했다. 동작·타입 변경은 없다. |
