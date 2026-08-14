# Frame 구조 명세서 (모듈 경계 계약)

> **역할**: 계층 간에 오가는 **유일한 타입**을 정의한다. 프로토콜 계층(0943 해석)과 서비스 계층(데이터·화면)은 이 파일 외의 서로의 심볼을 참조하지 않는다.
> **근거**: TTAK.KO-10.0943 7장 / `SIAP_메시지_명세서.md`
> **산출물**: `contracts/frame.py`, `contracts/siap_iface.py`, `contracts/test_contract.py` — 단계 1(개발_착수_지시서 §3.1)에서 `project_code/contracts/`로 이관 완료
> **검증**: 계약 제약 **64/64 통과** (§6, F-106·F-107·F-110·F-215 반영 실측치)

---

## 1. 경계 설계

```
   프로토콜 계층 (0943)              ┃ 계약 ┃        서비스 계층 (1369-P1 / 0937)
                                     ┃      ┃
 [펌웨어] → [바이트] → [디코더] ─────╂Frame ╂──→ [DB] → [API] → [화면]
 [펌웨어] ← [바이트] ← [인코더] ←────╂Frame ╂←── [제어 명령]
                                     ┃      ┃
   siap/  firmware/  sim/            ┃      ┃   backend/  web/
```

| 원칙 | 내용 |
|---|---|
| **`contracts/` 타입만 통과** | 경계를 넘는 값은 `contracts/frame.py`에 정의된 타입뿐이다. `bytes`, `dict`, `siap/` 내부 헬퍼는 넘지 않는다 |
| **표준 해석은 한 곳에서만** | 0943 조항 해석은 전부 프로토콜 계층이 담당한다. 서비스 계층은 판정 결과(`violations`)를 렌더링만 한다 |
| **예외를 던지지 않는다** | 파싱 실패해도 `violations`가 채워진 `Frame`을 반환한다. 깨진 프레임이 기능 2의 표시 대상이기 때문 |
| **불변** | 모든 dataclass는 `frozen=True`. 하위 계층이 만든 값을 상위 계층이 수정할 수 없다 |
| **계약 변경 절차** | 표준 조항 번호를 근거로 제안 → `contracts/` 수정 → 골든 벡터 재생성 → 양쪽 테스트 재통과 |

---

## 2. 핵심 설계 결정 — `MsgKind` / `WIRE_CODE` 분리

표 7-4에서 `NOTI_ERROR`와 `NOTI_DEVICE_VALUE`가 **동일 코드 0x0800**을 갖는다. 이를 그대로 `IntEnum`으로 두면 뒤에 정의한 멤버가 앞 멤버의 **별칭(alias)** 이 되어 두 메시지의 구분이 언어 차원에서 소실된다.

따라서 **논리적 종류**와 **전송 코드**를 분리했다.

| 구분 | 타입 | 내용 |
|---|---|---|
| `MsgKind` | `Enum` (auto) | 34종 논리 메시지. 항상 고유 |
| `WIRE_CODE` | `dict[MsgKind, int]` | `strict` 모드 — 표준 원문 그대로. 고유 코드 **33개** (0x0800 중복) |
| `WIRE_CODE_EXT` | `dict[MsgKind, int]` | `extended` 모드 — 개정 제안안. 고유 코드 **34개** |

`extended` 모드의 재배치:

| 메시지 | strict | extended |
|---|---|---|
| `NOTI_ERROR` | 0x0800 | 0x0800 |
| `NOTI_DEVICE_VALUE` | **0x0800** | **0x0801** |
| `NOTI_DISCONNECT` | 0x0801 | 0x0802 |
| `NOTI_REBOOT` | 0x0802 | 0x0803 |
| `NOTI_KEEP_ALIVE` | 0x0803 | 0x0804 |
| RESERVED 시작 | 0x0805 (0x0804 공백) | 0x0805 (연속) |

`Frame`은 `header.msg_type`(전송된 원본 코드)과 `kind`(해석된 논리 종류)를 **둘 다** 보관한다. 검증 뷰가 원본 코드를 그대로 보여줄 수 있어야 하기 때문이다.

### 2.1 `resolve_kind()` — 0x0800 판별

```python
resolve_kind(msg_type: int, payload_len: int, mode="strict") -> MsgKind | None
```

`NEC`는 1 byte, `DEVICE_MAIN_INFO`는 7 byte이므로 두 메시지의 유효 페이로드 길이 집합은 배타적이다.

| `payload_len` | 판정 |
|---|---|
| 1 | `NOTI_ERROR` |
| 7, 14, 21, … | `NOTI_DEVICE_VALUE` |
| 그 외 (0 포함) | `None` → `INVALID_FORMAT` (0x09) |

**표준의 코드 충돌을 표준 내부 정보만으로 해소할 수 있음이 코드로 증명된다.**

---

## 3. 타입 구성

### 3.1 표준 정의 열거형

| 타입 | 개수 | 출처 |
|---|---|---|
| `MsgKind` | 34 | 표 7-2 / 7-3 / 7-4 |
| `TransType` | 3 | 표 7-6 |
| `RSC` | 10 | 표 7-10 (원문 표기 `SUCESS` 오타 → 코드는 `SUCCESS`) |
| `NEC` | 10 | 표 7-12 |
| `DevType` | 2 | 표 7-14 |
| `ValueType` | 3 (+RESERVED) | 표 7-14 |
| `TransferMode` | 3 | 표 7-15 |
| `Status` | 3 | 표 7-13 / 7-15 |
| `Subtype` | 16 | 항목 = 1369-P1 6.3.3 / 6.3.4, 코드값 = 자체 할당 |

`Subtype`은 최상위 비트로 센서(0x01~0x0A) / 액추에이터(0x81~0x86)를 구분하며 `.dev_type` 프로퍼티를 제공한다.

### 3.2 구조체

`Header`는 **전송된 원본 비트값을 그대로 보존한다.** `msg_type`과 `trans_type` 모두 raw `int`이며, 해석은 `resolve_kind()` / `resolve_trans_type()` 이 담당한다.

> 표 7-6 미정의값 0x03을 `TransType`으로 변환하면 `ValueError`가 발생해 "예외를 던지지 않는다"는 계약과 충돌한다. 기능 2의 위반 주입 케이스 #5가 바로 이 값이므로, 헤더는 원본을 담고 판정은 분리한다.

| dataclass | 크기 상수 | 출처 |
|---|---|---|
| `Header` | `HEADER_BYTES = 12` | 그림 7-1 |
| `NodeProperty` | `NP_BYTES = 8` | 표 7-13 |
| `DeviceMainInfo` | `DMI_BYTES = 7` | 표 7-14 |
| `DeviceProperty` | `DP_BYTES = 30` | 표 7-15 |
| `MsgControlProfile` | `MCP_BYTES = 7` | 표 7-18 |

### 3.3 `Frame`

```python
@dataclass(frozen=True)
class Frame:
    header: Header | None             # 12byte 헤더 미달일 때만 None
    kind: MsgKind | None            # 해석된 논리 종류
    rsc / nec                       # 단일 코드 필드
    node_property                   # 구조체 (있을 때만)
    device_main_infos: tuple[...]   # 가변 배열
    device_properties: tuple[...]
    device_ids: tuple[int, ...]
    profile
    raw: bytes                      # 원본 바이트 (검증 뷰 hex 덤프용)
    violations: tuple[Violation,...] # 비어 있으면 정상
    t: float                        # 수신 시각 (로그 재생용)
```

헤더가 12byte보다 짧으면 알 수 없는 필드 값을 0으로 만들어내지 않고
`header=None`으로 둔다. 이 경우에도 `raw`에는 수신 조각 전체를, `violations`에는
`INVALID_FORMAT (0x09, 7.3.1)`을 보존하여 서비스 계층이 저장·표시할 수 있다.
완전한 헤더가 있고 payload만 부족하면 실제 `Header`와 원본 조각을 그대로
보존한다. 두 경우 모두 회신·송신·대기 매칭 대상이 아니며, 스트리밍 디코더는
프레임 경계가 확정될 때까지 조각을 방출하지 않고 다음 바이트를 기다린다.

**표준 외 확장 3개 필드의 근거**

| 필드 | 목적 |
|---|---|
| `raw` | 검증 뷰가 hex를 다시 만들 필요 없게 원본 보존 |
| `violations` | 표준 위반 판정 결과. **`clause` 문자열에 조항 번호를 담아** 화면이 `INVALID_FORMAT (0x09) — 7.3.1절`을 그대로 출력 |
| `t` | 리플레이 로그 재생 시 타임라인 복원 |

```python
@dataclass(frozen=True)
class Violation:
    code: int          # RSC 또는 NEC 값
    code_name: str     # 'INVALID_FORMAT'
    clause: str        # '7.3.1'   ← 화면 표시
    detail: str        # 'Payload Length=24, 실제 수신 18byte'
```

---

## 4. `LAYOUT` / `element_count()` — N 산출의 정본

표준은 가변 요소 개수 N을 전달하는 필드를 정의하지 않는다. `Payload Length` 역산이 유일한 방법이며, 그 규칙을 `LAYOUT` 한 곳에 모았다.

```python
LAYOUT: dict[MsgKind, tuple[int, int]]   # (고정부 byte, 요소 byte)
element_count(kind, payload_len) -> int | None
```

메시지 34종 전량이 등록되어 있고, `None` 반환은 곧 `INVALID_FORMAT` (0x09, 7.3.1)이다.

### 4.1 N=0 처리 — 구현 결정 (표준 미규정)

| 형태 | N=0 | 근거 |
|---|---|---|
| 고정부 **있음** + 가변부 (`RES_SET_CONNECTION` 등) | **허용** | 디바이스가 0개인 노드가 실제로 존재할 수 있다 |
| 고정부 **없음** + 가변부만 (`REQ_SET_DEVICE_CONTROL`, `NOTI_DEVICE_VALUE` 등) | **거부** | 페이로드가 비어 '페이로드 없음' 메시지와 구별되지 않고, 의미도 없다 |

> 이 규칙은 계약 검증 테스트가 발견한 구멍을 메운 것이다. 규칙이 없으면 `0x0800 + payload_len=0`이 `NOTI_DEVICE_VALUE(N=0)`로 잘못 해석된다.

### 4.2 N 상한 — 구현 결정 (표준 미규정, F-120)

0943 표 7-13은 `Num. of Devices`를 8bit로 두어 표준 자체는 N=255까지 연다. CLAUDE.md §3.5는 AVR SRAM 2KB·`Timeout ≥ 2 × wire_time` 산식에서 **노드당 디바이스 상한 N=16**을 자체 결정으로 닫았다(F-064). `element_count()`는 나머지 검사를 통과한 뒤에도 `n > 16`이면 `None`(`INVALID_FORMAT`, 7.3.1)을 반환한다 — N=17 이상은 표준 위반은 아니지만 이 프로젝트의 메모리·타임아웃 전제가 깨지므로 거부한다. 골든 벡터 B11(N=17)이 이 분기의 경계 사례다.

---

## 5. `SiapLink` 인터페이스

`contracts/siap_iface.py`. 서비스 계층은 이 `Protocol` 외의 프로토콜 계층 심볼을 참조하지 않는다.

```python
class SiapLink(Protocol):
    def start(run_mode, *, proto_mode="strict", **opts) -> None
    def stop() -> None
    def recv() -> Iterator[Frame]          # 위반 프레임도 그대로 흘려보냄
    def send(frame, timeout=None) -> Frame | None
    def registry() -> dict[int, NodeProperty]
    def devices(node_id) -> tuple[DeviceMainInfo, ...]
    def stats() -> dict
```

| 파라미터 | 값 |
|---|---|
| `run_mode` | `hardware` / `replay` / `simulate` |
| `proto_mode` | `strict` / `extended` (§2) |

> **허용 타입 목록** — 데이터 흐름의 주 통로는 `Frame`이지만, 조회 API는 구조체를 직접 돌려준다. 모두 `contracts/frame.py`에 정의된 타입이므로 경계 원칙을 만족한다.
>
> | 메서드 | 반환 | 비고 |
> |---|---|---|
> | `recv()` / `send()` | `Frame` | 주 통로 |
> | `registry()` | `dict[int, NodeProperty]` | 등록 노드 조회 |
> | `devices()` | `tuple[DeviceMainInfo, ...]` | 디바이스 목록 조회 |
> | `stats()` | `dict[str, int \| float]` | 원시 타입만 |
>
> `NodeProperty`·`DeviceMainInfo`는 0943 구조체이지만 **`contracts/`에 정의**되어 있다. 서비스 계층이 `siap/` 내부를 모르는 상태는 유지된다. "`Frame` 하나뿐"이라는 초기 서술이 부정확했으므로 위와 같이 정정한다.

### 5.1 `FrameBuilder`

서비스 계층이 비트 배치를 몰라도 되게 하는 빌더.

**(1) 게이트웨이발 Request** — 화면·서비스가 능동적으로 보낸다. `link.send()` 경유.

```python
device_control(node_id, [(device_id, value, value_type)]) -> Frame   # 8.1.5
get_device_value(node_id, [device_id])                    -> Frame   # 8.1.4.4
get_node_property(node_id)                                -> Frame   # 8.1.4.1
set_device_property(node_id, props: list[DeviceProperty]) -> Frame   # 8.1.3.2 (F-086)
reboot(node_id)                                           -> Frame   # 8.1.6
```

> **F-086 계약 변경 (2026-08-07 사용자 승인)** — 0943 8.1.3.2 는 `REQ_SET_DEVICE_PROPERTY`(표
> 7-2, 0x0004)를 **양방향**으로 규정한다: 기본 방향은 GCG→노드이며, 온실통합제어기가 N개
> 디바이스 속성값을 내려보내는 메시지다. 게이트웨이발 빌더가 없으면 설정 API
> (`PATCH /api/v1/device-property`)가 이 프레임을 만들 수단이 없다. `res_set_device_property()`
> (아래 (2))는 노드발 역방향에 대한 회신이라 이 자리를 대신하지 못한다. `props` 의 각
> 요소는 대상 디바이스를 `device_main_info.device_id` 로 가리킨다.

**(2) 노드발 메시지에 대한 즉시 회신** — `siap/link.py::_default_reply()` 의 반환값이 된다
(F-040 채택, F-154 로 담당 이동 — 당시는 `ingest.handle()` 의 반환값이었다. `backend/ingest.handle()`
이 회신까지 만들려면 `siap/build.py`(`FrameBuilder`)를 알아야 해 CLAUDE.md §3.4"표준 해석은
프로토콜 계층에만"을 어긴다. `_default_reply()`는 `siap/` 안에서 `FrameBuilder`를 그대로
참조하므로 `backend/` 없이도 완결된다 — `backend.ingest.handle(frame, conn) -> None`은
DB 반영만 하는 부수효과이며, `siap/link.py`의 `on_frame` 훅에 `run.py::_make_on_frame(db_path)`
로 연결된다(F-167 — `backend.ingest.bind(conn)`을 직접 쓰지 않는다. `on_frame`은 SIAP I/O
스레드 안에서 호출되는데 `bind(conn)`은 호출자가 미리 연 연결을 그대로 가두므로, 다른
스레드에서 연 연결을 넘기면 `sqlite3.ProgrammingError`가 난다 — `_make_on_frame`은 DB
경로만 받아 그 스레드 안에서 지연 연결한다).

```python
res_set_connection(req, rsc, node=None, devices=())       -> Frame   # 8.1.1
res_set_node_property(req, rsc)                           -> Frame   # 8.1.3.1
res_set_device_property(req, rsc)                         -> Frame   # 8.1.3.2
res_set_node_device_property_all(req, rsc)                -> Frame   # 8.1.3.3
res_set_msg_flow_control_profile(req, rsc)                -> Frame   # 8.1.3.4
error_response(req, rsc)                            -> Frame | None  # 7.3.1
ack(req)                                                  -> Frame   # 8.2
```

> **계약 변경 (F-040)** — `ack(node_id, msg_id)` → `ack(req: Frame)`.
> 7.2.2에 따라 회신이 복사해야 하는 것은 `Message Identifier` 하나가 아니라
> `GCG ID`·`Node ID`를 포함한다. 회신 빌더 전부가 원본 `Frame`을 받는 이유가 같다.
> (2)가 없으면 `handle()`이 회신 Frame을 만들 수단이 없다 — 초안의 실제 결함이었다.
>
> **CLAUDE.md §5 절차 이행** — ① 근거: 0943 7.2.2 (복사 대상 3필드). ② **2026-08-05 사용자 승인.**
> ③ 골든 벡터 재생성 및 `test_contract.py` 53/53 재통과. ④ 이력을 이 절에 남김.
> 펌웨어 대응은 `siap_ack(const siap_hdr_t *req, siap_enc_t *enc)` 이며 같은 이유로
> 스칼라 3개를 나열하지 않는다 (펌웨어 설계서 §5.9).

서비스 계층의 제어 코드는 이렇게만 생긴다.

```python
frame = build.device_control(node_id=3, commands=[(5, 1.0, ValueType.UINT)])
res = link.send(frame, timeout=2.0)
if res and res.rsc == RSC.SUCCESS:
    ...
```

### 5.2 방향과 회신의 정본 (F-040)

"무엇에 무엇으로 답해야 하는가"는 `contracts/frame.py` 에만 존재한다. 서비스 계층이 이 표를 다시 만들면 표준 해석이 두 곳에 생긴다(CLAUDE.md §3.4).

```python
NODE_ORIGINATED_REQUESTS   # 5종 — 8.1.1 + 8.1.3.1~8.1.3.4 (양방향 설정 요청)
NODE_ORIGINATED_NOTIFIES   # 5종 — 8.2.1.1~8.2.1.5
RESPONSE_OF                # Request → Response, 14쌍 (표 7-2 / 7-3, +0x0400)
reply_kind(kind)           # 수신 종류 → 내가 보낼 회신 종류   (없으면 None)
expected_reply(kind)       # 송신 종류 → 되돌아와야 하는 종류   (없으면 None)
```

`reply_kind()`와 `expected_reply()`는 **쌍**이다. 전자는 받은 것에 무엇으로 답하는가, 후자는 보낸 것에 무엇이 돌아와야 하는가다. 후자가 없으면 응답 매칭이 `Message Identifier`만 보게 되어, 다른 요청의 지연 Response나 우연히 번호가 같은 ACK가 현재 호출의 결과로 반환된다(F-046).

| 송신 | `expected_reply()` | 근거 |
|---|---|---|
| Request 14종 | 대응 `RES_*` | 표 7-2 / 7-3 |
| Notify 5종 | `ACK` | 6.2.2 |
| `RES_*` · `ACK` | `None` — 회신을 기다리지 않는다 | 8.1 |

> 매칭 조건은 `Node ID` · `Message Identifier` · **`Message Type`** 셋 전부다. 기대와 다른 프레임은 대기 항목을 소비하지 않고 흘려보낸다 — 진짜 Response가 아직 올 수 있다.

| 수신 | `reply_kind()` | 근거 |
|---|---|---|
| 노드발 Request 5종 | 대응 `RES_*` | 8.1.1, 8.1.3.1~4 |
| Notify 5종 | `ACK` | 6.2.2 |
| `RES_*` · `ACK` | `None` — I/O 스레드가 `Message Identifier`로 매칭 | 8.1 |
| 게이트웨이발 Request | `None` — 노드가 보낼 수 없다 | 8장 시퀀스 |
| 해석 불가(`kind is None`) | `None` | — |

**위반 프레임에도 같은 표를 적용한다.** 7.3.1은 요청 처리 실패 시 Response에 오류 RSC를 담아 보내도록 규정하고, 표 7-10의 `INVALID_*` 코드가 그러기 위해 존재한다. 다만 `ACK`는 헤더뿐이라 오류를 실을 수단이 없으므로 **위반 Notify에는 회신하지 않는다** — 표준 미규정 사항에 대한 자체 결정이며 `CLAUDE.md` §3.5 결정 표와 이 절에 기록한다. `docs/standard-findings.md`는 표준 자체의 결함 19건 전용이므로 이 결정을 이관하지 않는다(F-209).

---

## 6. 검증 결과 — 62/62 통과

| 분류 | 항목 |
|---|---|
| **완전성** | `MsgKind` 34종 / `LAYOUT` 34종 전량 정의 / `WIRE_CODE` 34종 전량 정의 |
| **코드공간** | 모든 코드가 14bit 이내 및 블록 경계(REQ/RES/NOTI/ACK) 내 |
| **대응** | Request + 0x0400 = Response, 14쌍 전량 성립 |
| **errata** | `strict` 고유 코드 33개(중복 1건 확인) / `extended` 34개(해소 확인) / `extended` NOTI 최대 0x0804 |
| **판별** | 0x0800 × payload_len 5케이스, `extended` 0x0801, `strict` 0x0801, 미정의 코드 |
| **N 산출** | `element_count` 18케이스 (N=0 허용/거부 경계 포함) |
| **Subtype** | 16종 / 센서 10 · 액추에이터 6 / 코드 고유 |
| **상수** | 구조체 크기 5종 / RSC·NEC 각 10종 코드값 |
| **방향·회신 (F-040)** | Response 대응 14쌍 / 노드발 Request 5종 / Notify 5종 ACK / `NOTI_REBOOT` 누락 검출 / Response·ACK 무회신 / 게이트웨이발 Request 무회신 / `FrameBuilder` 회신 빌더 7종 노출 |
| **응답 매칭 (F-046)** | Request → 대응 Response 기대 / 다른 Response·ACK 로 완료 불가 / Notify → ACK 기대 / `reply_kind` ↔ `expected_reply` 쌍 관계 / 14종 고유 기대값 |
| **게이트웨이발 빌더 (F-086)** | `FrameBuilder` 게이트웨이발 Request 빌더 5종(`set_device_property` 포함) 노출 / `props` 시그니처 / 두지 않은 빌더 8종의 사유가 계약에 기재됨 |
| **Frame** | 기본 valid / violations 시 invalid / `clause` 보존 / `frozen` 불변 |
| **원본 보존** | `trans_type=0x03` 저장 및 해석 → `None` / `msg_type` raw int 유지 |
| **USER DEPENDENT** | `Value Type` 에 따라 경계값이 int·float로 각각 유지 |
| **교차 검증** | `SIAP_메시지_명세서.md` §8 예시 프레임 9건의 `kind` 해석 및 `payload_len` 일치 |
| **`FakeSiapLink` 계약 이행 (F-106)** | `fake_link.py` 실제 import + 인스턴스화 / `SiapLink` 메서드 7종의 존재·callable 여부 / 최소 정상 입력으로 7종 전부 호출해 반환형 확인(빈 클래스·문법 오류 반례로 검출 확인) |
| **`FakeSiapLink` 시그니처·Iterator 계약 (F-110)** | 7종 메서드의 파라미터 이름·kind·기본값이 `SiapLink` Protocol 과 `inspect.signature` 로 호환 확인(`start` 의 `**opts`, `send` 의 `timeout` 포함) / `start(..., 임의 키워드)`·`send(frame, timeout=2.0)` 실호출 / `recv()` 가 `Iterator` 계약(`iter(x) is x`) 을 만족(시그니처 결손 반례로 검출 확인) |

---

## 7. 다음 단계

**완료 (단계 1, 개발_착수_지시서 §3.1)**

- ~~`contracts/fake_link.py` — 개발용 대역 `SiapLink` 구현~~ → 구현 완료, `test_contract.py`가 Protocol 이행을 실제 호출로 검증(F-106)
- ~~`contracts/vectors/golden.jsonl` — 명세서 예시 9건 → 당시 52건 확장~~ → 완료, `project_code/contracts/vectors/`로 이관. 이후 단계 2b 중 F-120(B11, N 상한 초과) 추가로 **53건**(현재 주장, §4.2)

**남은 단계**

1. `firmware/core/siap_types.h` — 본 계약의 C 대응 (열거형·구조체·`LAYOUT`)
2. `siap/codec.py` — `bytes ↔ Frame`
