# F-040 · 즉시 회신 디스패치와 계약이 불완전함

| 항목 | 값 |
|---|---|
| 심각도 | 오류 |
| 분류 | 문서불일치 |
| 대상 | `project_docs/arch/아키텍처_설계서.md:83-131`, `project_docs/contracts/siap_iface.py:39-58` |
| 발견일 | 2026-08-03 |
| 상태 | 수정완료 |

## 근거

0943 6.2.2 — 노드의 Request에 제어기가 Response하고 노드의 Notify에 제어기가 ACK하는 양방향 모델

0943 표 7-1·7.3.1 — 요청 처리 실패 시 Response에 해당 RSC 오류 코드를 담아 보낸다.

0943 8.1.3.1~8.1.3.4 — 네 Request는 노드→GCG 역방향도 가능하다.

## 현상

수정된 `handle()`은 `REQ_SET_CONNECTION`과 Notify 4종만 처리한다. `NOTI_REBOOT`은 표에서 "NOTI_* 5종"이라 적었지만 실제 match에 없고, 역방향 가능한 설정 Request 4종도 Response를 만들지 않는다. 위반 Request는 종류와 오류 RSC를 알 수 있어도 일괄 `None`으로 버린다. 또한 의사코드가 호출하는 `build.res_set_connection(...)`은 `FrameBuilder` Protocol에 없고, `build.ack(frame)`은 계약의 `ack(node_id, msg_id)` 시그니처와 다르다.

## 영향

F-027에서 추가한 회신 경로를 그대로 구현할 수 없으며, 표준 메시지 일부는 여전히 응답·ACK 없이 타임아웃된다. 34종 전량 구현 주장과 실제 모듈 계약이 어긋난다.

## 제안

노드발 가능 Request 전량과 Notify 5종의 디스패치 표를 계약 메서드와 1:1로 맞추고, 파싱 가능한 오류 Request에는 대응 Response+RSC를 반환하는 규칙을 명시한다.

---

## Claude 처리 기록

| 일시 | 상태 | 내용 |
|---|---|---|
| 2026-08-03 | 확인 | 타당. `handle()` 은 노드발 Request 5종 중 1종(REQ_SET_CONNECTION)만 처리했고 `NOTI_REBOOT` 이 match 에서 누락되어 있었다. `build.res_set_connection` 은 `FrameBuilder` 에 없었고 `ack` 시그니처도 어긋났다 |
| 2026-08-03 | 수정완료 | 방향표를 `contracts/frame.py` 로 올렸다 — `NODE_ORIGINATED_REQUESTS`(5종) · `NODE_ORIGINATED_NOTIFIES`(5종) · `RESPONSE_OF`(14쌍) · `reply_kind()`. 서비스 계층이 표준 방향을 다시 해석하지 않는다(CLAUDE.md §3.4) |
| 2026-08-03 | 수정완료 | `FrameBuilder` 에 회신 빌더 7종 추가(`res_set_*` 5종 · `error_response` · `ack`). **계약 변경** — `ack(node_id, msg_id)` → `ack(req: Frame)`. 근거는 7.2.2: 복사 대상이 `Message Identifier` 하나가 아니라 `GCG ID`·`Node ID` 를 포함한다. CLAUDE.md §5 절차에 따라 사용자 확인 대상으로 보고했다 |
| 2026-08-03 | 수정완료 | 위반 프레임 회신 규칙을 7.3.1 근거로 명문화 — Request 로 해석되면 대응 Response 에 오류 RSC 를 실어 회신, Notify·해석 불가·헤더 미달은 회신 없음. Notify 무회신은 ACK 가 헤더뿐이라 오류를 실을 수단이 없어 내린 자체 결정이며 `docs/standard-findings.md` 등재 대상 |
| 2026-08-03 | 수정완료 | 계약 테스트 9종 추가(`test_contract.py` 37 → 46종). NOTI_REBOOT 누락·게이트웨이발 Request 오회신·Response 재회신을 각각 검출한다 |
