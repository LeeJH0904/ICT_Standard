# SIAP 메시지 명세서

> **표준**: TTAK.KO-10.0943 — 스마트팜 온실통합제어기와 센서-구동기통합 노드 간 통신 프로토콜
> **프로토콜명**: SIAP (Smartfarm-specialized Integrated Application Protocol)
> **판**: 제1판 2016.12.27 (2025 확인, 개정 없음)
> **출처**: 7장(메시지 구성) 표 7-1~7-18, 8장(메시지 흐름) 그림 8-1~8-61
> **검증**: 구조체 크기 8종 ↔ 표준 명시값 일치 / 메시지 34종 코드공간·대응 검증 / 예시 프레임 9건 왕복 검증 / `Value` 범위·왕복 15종 **전량 통과**

이 문서는 프레임 코덱 구현의 **직접 입력**이다. 표준 원문에는 hex 예시 프레임이 없으므로(그림 8-x는 필드 배치 블록 다이어그램), §8의 예시 프레임을 본 명세에서 유도해 생성했다.

---

## 1. 헤더 — 96 bit / 12 byte 고정

모든 메시지가 동일한 헤더를 갖는다. (그림 7-1, 표 7-5 ~ 7-8)

| 필드 | 비트 오프셋 | 길이(bit) | 바이트 위치 | 설명 |
|---|---|---|---|---|
| `Version` | 0 | 8 | 0 | 상위 니블.하위 니블 (0x12 = v1.2) |
| `Message Type` | 8 | 14 | 1~2 | 표 7-2 ~ 7-4 |
| `Transmission Type` | 22 | 2 | 2 | Unicast 0x00 / Multicast 0x01 / Broadcast 0x02 |
| `Message Identifier` | 24 | 16 | 3~4 | 0~65535 순환. Req↔Res, Noti↔ACK 매칭 |
| `Payload Length` | 40 | 16 | 5~6 | byte 단위 |
| `GCG ID` | 56 | 20 | 7~9 | hCode (TTAK.KO-06.0201/R1) |
| `Node ID` | 76 | 20 | 9~11 | hCode |

`Message Type`(14) + `Transmission Type`(2) + `Message Identifier`(16) = 32 bit가 **메시지 제어 필드**(7.2.2)를 이룬다.

> **바이트 정렬 없음.** `Message Type`(14bit)이 바이트 경계를 넘고, `GCG ID`/`Node ID`(각 20bit)는 9번째 바이트를 반씩 나눠 쓴다. C 구조체 직접 캐스팅 불가 — 비트 패킹 필수.

---

## 2. 페이로드 구조체 (7.3.3)

### 2.1 `NODE_PROPERTY` — 64 bit / 8 byte (표 7-13)

| 필드 | 오프셋 | 길이 | 설명 |
|---|---|---|---|
| `S/W Version` | 0 | 8 | 노드 소프트웨어 버전 |
| `GCG ID` | 8 | 20 | 온실통합제어기 식별자 |
| `Node ID` | 28 | 20 | 노드 식별자 |
| `Status` | 48 | 8 | NORMAL 0x00 / ABNORMAL 0x01 / UNKNOWN 0x02 |
| `Num. of Devices` | 56 | 8 | 노드에 연결된 디바이스 수 |

### 2.2 `DEVICE_MAIN_INFO` — 56 bit / 7 byte (표 7-14)

| 필드 | 오프셋 | 길이 | 설명 |
|---|---|---|---|
| `Device ID` | 0 | 8 | 디바이스 식별자 (노드 내 유일) |
| `Type` | 8 | 1 | 센서 0x00 / 액추에이터 0x01 |
| `Subtype` | 9 | 8 | 센서-구동기 타입 → §5 Subtype 레지스트리 |
| `Value Type` | 17 | 2 | INT 0x00 / UNSIGNED INT 0x01 / FLOAT 0x02 / RESERVED 0x03 |
| `Reserved` | 19 | 5 | 예약 (0으로 채움) |
| `Value` | 24 | 32 | Type 0x00 센서값 / Type 0x01 제어값 |

> `Subtype`(9~16bit)이 바이트 경계를 넘는다. `Type`+`Subtype`+`Value Type`+`Reserved` = 16bit를 한 워드로 읽고 시프트한다.

### 2.3 `DEVICE_PROPERTY` — 240 bit / 30 byte (표 7-15)

| 필드 | 오프셋 | 길이 | 설명 |
|---|---|---|---|
| `Device Main Info` | 0 | 56 | §2.2 |
| `Transfer Mode` | 56 | 2 | Periodic 0x00 / Event 0x01 / Both 0x02 |
| `Period` | 58 | 14 | 데이터 전달주기 (sec) |
| `Lower Value` | 72 | 32 | 하한값 (Event/Both일 때 이하면 전송) |
| `Upper Value` | 104 | 32 | 상한값 (Event/Both일 때 초과면 전송) |
| `Lower Limit` | 136 | 32 | Value 최소값 |
| `Upper Limit` | 168 | 32 | Value 최대값 |
| `Precision` | 200 | 32 | 정밀도 |
| `Status` | 232 | 8 | NORMAL 0x00 / ABNORMAL 0x01 / UNKNOWN 0x02 |

### 2.4 `COMBINED_PROPERTY` — 64 + N×240 bit (표 7-16)

`NODE_PROPERTY` + `DEVICE_PROPERTY` × N. 독립 구조체가 아니라 두 구조체의 연접이므로, 코덱에서 별도 타입으로 두지 않는다.

### 2.5 `DEVICE_ID` 그룹 — N×8 bit (표 7-17)

디바이스 식별자 1바이트씩 N개 나열.

### 2.6 `MSG_CONTROL_PROFILE` — 56 bit / 7 byte (표 7-18)

| 필드 | 오프셋 | 길이 | 설명 |
|---|---|---|---|
| `Message Receive Timeout` | 0 | 16 | 응답 만료 시간 (**sec** — §7 구현 결정) |
| `Num. of Retry` | 16 | 8 | 메시지 재전송 횟수 |
| `Notify Error Interval` | 24 | 16 | `NOTI_ERROR` 전송 주기 (**sec**) |
| `Keep Alive Interval` | 40 | 16 | `NOTI_KEEP_ALIVE` 전송 주기 (**sec**) |

### 2.7 단일 코드 필드

| 필드 | 길이 | 값 | 출처 |
|---|---|---|---|
| `RSC` | 8 bit / 1 byte | SUCCESS 0x00 ~ INVALID_FORMAT 0x09 (10종) | 표 7-9, 7-10 |
| `NEC` | 8 bit / 1 byte | ERROR_DEVICE_STATUS 0x00 ~ ERROR_UNKNOWN 0x09 (10종) | 표 7-11, 7-12 |

---

## 3. 메시지 명세 — 34종

`H` = 헤더 12 byte. `N` = 가변 개수.
방향: **N→G** 노드→GCG / **G→N** GCG→노드

### 3.1 Request (14종) — 0x0000 ~ 0x000D

| 메시지 | 코드 | 방향 | 페이로드 | 총 크기(byte) | 그림 |
|---|---|---|---|---|---|
| `REQ_SET_CONNECTION` | 0x0000 | N→G | (없음) | 12 | 8-4 |
| `REQ_SET_DEVICE_INIT` | 0x0001 | G→N | `DEVICE_ID`×N | 12 + 1N | 8-7 |
| `REQ_SET_DEVICE_INIT_ALL` | 0x0002 | G→N | (없음) | 12 | 8-10 |
| `REQ_SET_NODE_PROPERTY` | 0x0003 | 양방향 | `NODE_PROPERTY` | 20 | 8-13 |
| `REQ_SET_DEVICE_PROPERTY` | 0x0004 | 양방향 | `DEVICE_PROPERTY`×N | 12 + 30N | 8-16 |
| `REQ_SET_NODE_DEVICE_PROPERTY_ALL` | 0x0005 | 양방향 | `NODE_PROPERTY` + `DEVICE_PROPERTY`×N | 20 + 30N | 8-19 |
| `REQ_SET_MSG_FLOW_CONTROL_PROFILE` | 0x0006 | 양방향 | `MSG_CONTROL_PROFILE` | 19 | 8-22 |
| `REQ_GET_NODE_PROPERTY` | 0x0007 | G→N | (없음) | 12 | 8-25 |
| `REQ_GET_DEVICE_PROPERTY` | 0x0008 | G→N | `DEVICE_ID`×N | 12 + 1N | 8-28 |
| `REQ_GET_NODE_DEVICE_PROPERTY_ALL` | 0x0009 | G→N | (없음) | 12 | 8-31 |
| `REQ_GET_DEVICE_VALUE` | 0x000A | G→N | `DEVICE_ID`×N | 12 + 1N | 8-34 |
| `REQ_GET_MSG_FLOW_CONTROL_PROFILE` | 0x000B | G→N | (없음) | 12 | 8-37 |
| `REQ_SET_DEVICE_CONTROL` | 0x000C | G→N | `DEVICE_MAIN_INFO`×N | 12 + 7N | 8-40 |
| `REQ_SET_REBOOT` | 0x000D | G→N | (없음) | 12 | 8-43 |

### 3.2 Response (14종) — 0x0400 ~ 0x040D

**Request 코드 + 0x0400 = Response 코드** (14쌍 전량 확인). 모든 Response는 페이로드 선두에 `RSC` 1 byte를 갖는다.

| 메시지 | 코드 | 방향 | 페이로드 | 총 크기(byte) | 그림 |
|---|---|---|---|---|---|
| `RES_SET_CONNECTION` | 0x0400 | G→N | `RSC` + `NODE_PROPERTY` + `DEVICE_PROPERTY`×N | 21 + 30N | 8-5 |
| `RES_SET_DEVICE_INIT` | 0x0401 | N→G | `RSC` | 13 | 8-8 |
| `RES_SET_DEVICE_INIT_ALL` | 0x0402 | N→G | `RSC` | 13 | 8-11 |
| `RES_SET_NODE_PROPERTY` | 0x0403 | 양방향 | `RSC` | 13 | 8-14 |
| `RES_SET_DEVICE_PROPERTY` | 0x0404 | 양방향 | `RSC` | 13 | 8-17 |
| `RES_SET_NODE_DEVICE_PROPERTY_ALL` | 0x0405 | 양방향 | `RSC` | 13 | 8-20 |
| `RES_SET_MSG_FLOW_CONTROL_PROFILE` | 0x0406 | 양방향 | `RSC` | 13 | 8-23 |
| `RES_GET_NODE_PROPERTY` | 0x0407 | N→G | `RSC` + `NODE_PROPERTY` | 21 | 8-26 |
| `RES_GET_DEVICE_PROPERTY` | 0x0408 | N→G | `RSC` + `DEVICE_PROPERTY`×N | 13 + 30N | 8-29 |
| `RES_GET_NODE_DEVICE_PROPERTY_ALL` | 0x0409 | N→G | `RSC` + `NODE_PROPERTY` + `DEVICE_PROPERTY`×N | 21 + 30N | 8-32 |
| `RES_GET_DEVICE_VALUE` | 0x040A | N→G | `RSC` + `DEVICE_MAIN_INFO`×N | 13 + 7N | 8-35 |
| `RES_GET_MSG_FLOW_CONTROL_PROFILE` | 0x040B | N→G | `RSC` + `MSG_CONTROL_PROFILE` | 20 | 8-38 |
| `RES_SET_DEVICE_CONTROL` | 0x040C | N→G | `RSC` | 13 | 8-41 |
| `RES_SET_REBOOT` | 0x040D | N→G | `RSC` | 13 | 8-44 |

### 3.3 Notify / ACK (6종) — 0x0800 ~ 0x0803, 0x0C00

| 메시지 | 코드 | 방향 | 페이로드 | 총 크기(byte) | 그림 |
|---|---|---|---|---|---|
| `NOTI_ERROR` | 0x0800 | N→G | `NEC` | 13 | 8-48 |
| `NOTI_DEVICE_VALUE` | **0x0800** ※ | N→G | `DEVICE_MAIN_INFO`×N | 12 + 7N | 8-51 |
| `NOTI_DISCONNECT` | 0x0801 | 양방향 | (없음) | 12 | 8-54 |
| `NOTI_REBOOT` | 0x0802 | 양방향 | (없음) | 12 | 8-57 |
| `NOTI_KEEP_ALIVE` | 0x0803 | N→G | (없음) | 12 | 8-60 |
| `ACK` | 0x0C00 | 양방향 | (없음) | 12 | 8-49/52/55/58/61 |

※ 표준 원문의 코드 중복. §6 참조.

---

## 4. N 산출 규칙 ★

**표준은 가변 요소의 개수 N을 전달하는 필드를 정의하지 않는다.** 수신측은 `Payload Length`에서 역산해야 한다. 이것이 코덱 구현의 핵심 결정 사항이다.

| 메시지 | N 산출식 | 나머지 검사 |
|---|---|---|
| `REQ_SET_DEVICE_INIT`, `REQ_GET_DEVICE_PROPERTY`, `REQ_GET_DEVICE_VALUE` | `N = payload_len` | — (요소 1 byte) |
| `REQ_SET_DEVICE_PROPERTY` | `N = payload_len / 30` | `payload_len % 30 == 0` |
| `REQ_SET_NODE_DEVICE_PROPERTY_ALL` | `N = (payload_len - 8) / 30` | `(payload_len - 8) % 30 == 0` |
| `REQ_SET_DEVICE_CONTROL`, `NOTI_DEVICE_VALUE` | `N = payload_len / 7` | `payload_len % 7 == 0` |
| `RES_GET_DEVICE_PROPERTY` | `N = (payload_len - 1) / 30` | `(payload_len - 1) % 30 == 0` |
| `RES_SET_CONNECTION`, `RES_GET_NODE_DEVICE_PROPERTY_ALL` | `N = (payload_len - 9) / 30` | `(payload_len - 9) % 30 == 0` |
| `RES_GET_DEVICE_VALUE` | `N = (payload_len - 1) / 7` | `(payload_len - 1) % 7 == 0` |

> **나머지가 0이 아니거나 N이 음수이면 `INVALID_FORMAT` (0x09, 7.3.1).**
> 이 규칙이 기능 2(표준 준수 검증 뷰)의 위반 판정 근거 중 하나가 된다.
>
> **N > 16 도 같은 코드로 거부한다 (F-120).** 표 7-13의 `Num. of Devices`(8bit)는
> 표준상 N=255까지 열려 있지만, 노드당 디바이스 상한 N=16(CLAUDE.md §3.5, AVR
> SRAM 2KB·`Timeout ≥ 2 × wire_time` 전제에서 유도)을 넘으면 표준 위반은 아니어도
> 이 프로젝트의 자체 결정으로 거부한다.

### 4.1 `NOTI_ERROR` / `NOTI_DEVICE_VALUE` 판별 (코드 중복 해소)

두 메시지가 같은 코드 0x0800을 쓰지만 **페이로드 길이로 완전히 구분된다.**

| `payload_len` | 판정 |
|---|---|
| `1` | `NOTI_ERROR` (`NEC` 1 byte) |
| `7, 14, 21, …` (7의 배수, ≥7) | `NOTI_DEVICE_VALUE` (`DEVICE_MAIN_INFO`×N) |
| 그 외 | `INVALID_FORMAT` (0x09) |

`NEC`는 1 byte, `DEVICE_MAIN_INFO`는 7 byte이므로 두 집합은 교집합이 없다. **표준의 코드 충돌을 표준 내부 정보만으로 해소할 수 있음이 확인되었다.**

---

## 5. Subtype 레지스트리

0943 표 7-14의 `Subtype`(8bit)은 각주에서 `[RUCFS-0009] 온실 관제 데이터 규격`을 참조하도록 되어 있으나 해당 규격을 확보하지 않았다. **항목 집합은 TTAK.KO-10.1369-Part1에서 도출하고 코드값만 자체 할당**한다.

| Subtype | 항목 | `Type` | 단위 | 근거 |
|---|---|---|---|---|
| 0x01 | 온도 | 센서 | ℃ | 1369-P1 6.3.3.2 |
| 0x02 | 습도 | 센서 | % | 6.3.3.3 |
| 0x03 | 이산화탄소 | 센서 | ppm | 6.3.3.4 |
| 0x04 | 일사 | 센서 | W/㎡ | 6.3.3.5 |
| 0x05 | 풍향 | 센서 | degree | 6.3.3.6 |
| 0x06 | 풍속 | 센서 | m/s | 6.3.3.7 |
| 0x07 | 감우 | 센서 | ON/OFF | 6.3.3.8 |
| 0x08 | 토양수분장력 | 센서 | kPa | 6.3.3.9 |
| 0x09 | 전기전도도 | 센서 | dS/m | 6.3.3.10 |
| 0x0A | 수소이온농도 | 센서 | — | 6.3.3.11 |
| 0x81 | 창 개폐기 | 액추에이터 | % | 6.3.4.2 |
| 0x82 | 보온덮개 | 액추에이터 | % | 6.3.4.3 |
| 0x83 | 송풍기 | 액추에이터 | ON/OFF | 6.3.4.4 |
| 0x84 | 관수펌프 | 액추에이터 | ON/OFF + sec | 6.3.4.5 |
| 0x85 | 관수밸브 | 액추에이터 | ON/OFF or % | 6.3.4.6 |
| 0x86 | 냉난방기 | 액추에이터 | ON/OFF + ℃ | 6.3.4.7 |

- 최상위 비트로 센서(0x00~0x7F) / 액추에이터(0x80~0xFF)를 구분한다. `DEVICE_MAIN_INFO.Type`과 중복되지만 검증에 쓸 수 있다.
- **코드값은 `firmware/core/subtype_registry.h`와 `contracts/subtype.py` 두 곳에만 존재**한다. RUCFS-0009 확보 시 치환 지점이 2개소로 제한된다.
- 미정의 Subtype 수신 시 `INVALID_DATA_SUBTYPE` (0x07, 7.3.1).

---

## 6. 표준 원문의 실구현 장애 지점

0943은 제1판(2016.12.27) 그대로이며 개정 이력이 없다(2025 확인). 명세화·펌웨어 설계 과정에서 확인한 지점 **13건**은 다음과 같다.

| # | 내용 | 위치 | 등급 | 본 구현의 처리 |
|---|---|---|---|---|
| 1 | `NOTI_ERROR` = 0x0800, `NOTI_DEVICE_VALUE` = 0x0800 — **동일 코드 중복 할당** | 표 7-4 | 치명적 | `strict` 모드: §4.1 페이로드 길이 판별 / `extended` 모드: `NOTI_DEVICE_VALUE`를 0x0801로 재배치 후 이하 순차 이동 |
| 2 | Notify 코드가 0x0803까지인데 RESERVED 시작이 0x0805 — **0x0804 공백** (#1의 흔적) | 표 7-4 | 구조적 | `extended` 모드에서 RESERVED를 0x0804~로 정정 |
| 3 | **엔디안 규정 부재** | 전체 | 상호운용성 저해 | big-endian (network byte order) 고정 |
| 4 | **`Value Type = FLOAT`의 표현 방식 미명시** | 표 7-14 | 상호운용성 저해 | IEEE-754 single precision, big-endian |
| 5 | **가변 요소 개수 N의 전달 방법 미규정** | 7장 전체 | 구현 모호 | `Payload Length` 역산 (§4) |
| 5-a | **`DEVICE_PROPERTY`의 USER DEPENDENT 5필드 타입 선택 규칙 미규정** | 표 7-15 | 상호운용성 저해 | `Value Type` 을 따른다 (§7) |
| 5-b | **`MSG_CONTROL_PROFILE`의 시간 단위 미규정** — `Message Receive Timeout` · `Notify Error Interval` · `Keep Alive Interval`. 같은 표준의 `Period`(표 7-15)만 sec로 명시됨 | 표 7-18 | 상호운용성 저해 | 전부 sec로 통일 (§7) |
| 5-c | **`Message Receive Timeout` 과 가변 요소 개수 N 의 관계 미규정** — `Num. of Devices`(표 7-13, 8bit)는 N=255까지 허용해 `RES_SET_CONNECTION`이 7,671 byte까지 커지지만, 9600 baud에서 7.99초가 걸린다. 표준은 링크 속도·최대 프레임과 타임아웃을 잇는 규정을 두지 않는다 | 표 7-18 / 표 7-13 | 상호운용성 저해 | 노드당 디바이스 상한 N=16(501 byte)을 선언하고 `Timeout ≥ 2 × wire_time` 산식으로 기본값 2초를 유도 (아키텍처 §6.2-a) |
| 6 | `SUCESS` 오타 (SUCCESS) | 표 7-10 | 경미 | 코드에서는 `SUCCESS`로 표기하고 매핑표에 원문 표기 병기 |
| 7 | 8.2.1.3과 8.2.1.4 제목이 모두 "연결 해제 알림" (후자는 리부팅 알림) | 8.2.1.4 | 경미 | — |
| 8 | 그림 8-51 설명이 `NOTI_DEVICE_VALUE`를 `(RES_SET_REBOOT) 포맷`으로 오기 | 8.2.1.2 | 경미 | — |
| 9 | 그림 캡션 13개가 원문 레이아웃상 본문과 분리 (8-16, 8-22, 8-23, 8-26, 8-28, 8-38, 8-43, 8-44, 8-47, 8-48, 8-54, 8-57, 8-60) | 8장 | 문서 품질 | 그림 이미지 직접 판독으로 복원 완료 |
| 10 | **프레임 경계 구분자·무결성 검사 미규정** — 표 1-1은 통신 환경으로 유선(Ethernet, RS232, 485 등)을 명시한다. Ethernet은 자체 계층에서 프레이밍과 FCS를 제공하지만 **RS232/485는 순수 바이트 스트림**이다. 7장은 시작 구분자·길이 프리앰블·체크섬을 하나도 정의하지 않아, 바이트 1개가 유실되면 수신기가 프레임 경계를 영구히 잃는다. 손상된 바이트는 탐지되지 않고 유효 필드로 해석된다 | 표 1-1 / 7장 | 치명적 | 표준 프레임 형식은 **바꾸지 않는다**(구분자·CRC를 덧붙이면 준수가 아니게 된다). 수신측에서 `Version` + `resolve_kind` + `Transmission Type` + `element_count` **4조건 동시 만족** 시에만 프레임 시작으로 인정하는 재동기 규칙을 둔다. 프레임 간 무입력 판정 `T_gap` = 20 ms (펌웨어 설계서 §5.7) |

`docs/standard-findings.md`에 이 표를 옮기고, 1369-Part1에서 발견한 6건과 합쳐 **총 19건**을 기획서 4장(표준 실구현 검증 결과)의 근거로 사용한다.

> **#10은 문서 작성만으로는 나오지 않는 발견이다.** 명세 단계에서는 프레임이 이미 한 덩어리로 주어진다고 가정하게 되고, 바이트 스트림 위에 올려놓는 펌웨어 설계에 들어가서야 드러난다.

---

## 7. 구현 결정 사항

| 항목 | 결정 | 근거 |
|---|---|---|
| 바이트 정렬 | **비트 패킹 필수.** `bp_write` / `bp_read` / `bp_write_f32` / `bp_read_f32` 4개 함수 경유. C 구조체 직접 캐스팅 금지 | `Message Type`(14), `GCG/Node ID`(20), `Subtype`(9~16bit) 등이 바이트 경계를 넘음 |
| 엔디안 | **big-endian (network byte order)** | 표준 미규정 → 자체 결정 |
| FLOAT | **IEEE-754 single precision (4 byte), big-endian** | 표준 미규정 → 자체 결정 |
| `Reserved` 필드 | 송신 시 0으로 채움, 수신 시 무시 | 표 7-14 |
| 디코딩 실패 | **예외를 던지지 않고 `violations`가 채워진 Frame을 반환** | 깨진 프레임이 기능 2의 표시 대상 |
| `Message Identifier` | 송신마다 +1, 65535 다음 0 | 7.2.2 |
| `DEVICE_PROPERTY`의 USER DEPENDENT 5필드 | **`DEVICE_MAIN_INFO.Value Type` 을 따른다.** 표 7-15는 `Lower/Upper Value`·`Lower/Upper Limit`·`Precision`의 타입을 "USER DEPENDENT"로만 규정하고 선택 규칙을 정하지 않는다. 이들은 `Value` 와 같은 물리량의 경계·정밀도이므로 같은 타입으로 해석한다 | 표 7-15 (미규정) |
| `Transmission Type` 미정의값 | 0x03 수신 시 **원본값을 보존**하고 `INVALID_TRANSMISSION_TYPE`(0x08) 판정. 열거형으로 강제 변환하지 않는다 | 표 7-6 / 표 7-10 |
| `MSG_CONTROL_PROFILE`의 시간 3필드 | **전부 초(sec).** 표 7-18은 단위를 규정하지 않는다. 같은 표준에서 단위가 명시된 유일한 시간 필드가 표 7-15의 `Period`(sec)이므로 이에 맞춘다 | 표 7-18 (미규정) |
| 노드당 디바이스 상한 · `Timeout` 하한 | **N = 16** (최대 프레임 501 byte, 9600 baud 522 ms). `Timeout ≥ 2 × wire_time` 에서 기본 **2초**. 산식과 근거는 아키텍처 §6.2-a | 표 7-13 · 표 7-18 (관계 미규정 → §6-5c) |
| 재전송 | `MSG_CONTROL_PROFILE.Num. of Retry` 회, `Message Receive Timeout` 간격 | 5.2.2, 표 7-18, 그림 8-1/8-2 |

---

## 8. 예시 프레임

**표준 원문에는 hex 예시가 없다.** 아래는 본 명세에서 유도해 생성하고 왕복 검증한 것이며, 골든 벡터의 시드가 된다.

공통 헤더 값: `Version=0x12`(v1.2), `Transmission Type=0x00`(Unicast), `GCG ID=0x00001`, `Node ID=0x00003`

| # | ID | 메시지 | 방향 | 크기 | 조항 | 비고 |
|---|---|---|---|---|---|---|
| 1 | `REQ_SET_CONNECTION_min` | `REQ_SET_CONNECTION` | 노드→GCG | 12B | 8.1.1 | 페이로드 없음 |
| 2 | `RES_SET_CONNECTION_1dev` | `RES_SET_CONNECTION` | GCG→노드 | 51B | 8.1.1 | RSC+NODE_PROPERTY+DEVICE_PROPERTY×1 |
| 3 | `NOTI_DEVICE_VALUE_2sensor` | `NOTI_DEVICE_VALUE` | 노드→GCG | 26B | 8.2.1.2 | DEVICE_MAIN_INFO×2 |
| 4 | `REQ_SET_DEVICE_CONTROL_valve` | `REQ_SET_DEVICE_CONTROL` | GCG→노드 | 19B | 8.1.5 | 관수밸브 ON |
| 5 | `RES_SET_DEVICE_CONTROL_ok` | `RES_SET_DEVICE_CONTROL` | 노드→GCG | 13B | 8.1.5 | RSC=SUCCESS |
| 6 | `NOTI_ERROR_batlow` | `NOTI_ERROR` | 노드→GCG | 13B | 8.2.1.1 | NEC=ERROR_BATTERY_LOW |
| 7 | `REQ_GET_DEVICE_VALUE_3` | `REQ_GET_DEVICE_VALUE` | GCG→노드 | 15B | 8.1.4.4 | DEVICE_ID×3 |
| 8 | `REQ_SET_MSG_PROFILE` | `REQ_SET_MSG_FLOW_CONTROL_PROFILE` | GCG→노드 | 19B | 8.1.3.4 | MSG_CONTROL_PROFILE |
| 9 | `ACK_min` | `ACK` | 양방향 | 12B | 8.2 | 헤더만 |

```
REQ_SET_CONNECTION_min
  120000000100000000100003
RES_SET_CONNECTION_1dev
  1210000002002700001000030010000010000300030100C041CA6666003CC220000042A00000C220000042A000003DCCCCCD00
NOTI_DEVICE_VALUE_2sensor
  1220000003000E00001000030100C041CA666602014042740000
REQ_SET_DEVICE_CONTROL_valve
  12003000040007000010000305C2A000000001
RES_SET_DEVICE_CONTROL_ok
  12103000050001000010000300
NOTI_ERROR_batlow
  12200000060001000010000307
REQ_GET_DEVICE_VALUE_3
  120028000700030000100003010205
REQ_SET_MSG_PROFILE
  12001800080007000010000307D003001E003C
ACK_min
  123000000900000000100003
```

### 8.1 프레임 해부 예시 — `NOTI_DEVICE_VALUE_2sensor`

```
1220000003000E00001000030100C041CA6666020140...
└┬┘└───┬───┘└─┬┘└───┬────┘└──────┬──────────┘
 │     │      │     │            └ Payload: DEVICE_MAIN_INFO × 2
 │     │      │     └ GCG ID 0x00001 / Node ID 0x00003   (40bit)
 │     │      └ Payload Length = 0x000E = 14 byte        → N = 14/7 = 2
 │     └ MsgType 0x0800 | TransType 0x0 | MsgID 0x0003   (32bit)
 └ Version 0x12 (v1.2)

  DEVICE_MAIN_INFO[0] = 01 00 C0 41CA6666
    Device ID 0x01 | Type 0(센서) | Subtype 0x01(온도) | ValueType 2(FLOAT) | Value 25.3℃
  DEVICE_MAIN_INFO[1] = 02 01 40 42740000
    Device ID 0x02 | Type 0(센서) | Subtype 0x02(습도) | ValueType 2(FLOAT) | Value 61.0%
```

---

## 9. 골든 벡터 확장 계획

본 명세의 예시 9건을 시드로 `contracts/vectors/golden.jsonl`을 당시 52건까지 확장했다.
이후 단계 2b 중 F-120(N 상한 초과 경계 B11) 추가로 **53건**(현재 주장)이 됐다.

| 분류 | 개수 | 내용 |
|---|---|---|
| 정상 메시지 | 34 | §3의 34종 각 1건 (가변 요소는 N=1 또는 N=2) |
| 경계값 | 11 | N=0 / N=최대(16) / **N 상한 초과(17, F-120)** / 필드 최대·최소 / `Message Identifier` 랩어라운드(65535→0) / `Payload Length` 최대 |
| 위반 케이스 | 8 | 아래 표 |

### 9.1 위반 케이스 8종 — 기능 2 주입 시나리오

| # | 주입 | 기대 코드 | `clause` |
|---|---|---|---|
| 1 | `Version` 조작 (0x99) | `INVALID_VERSION` (0x01) | 7.3.1 |
| 2 | 미등록 `Node ID` | `INVALID_NODE_ID` (0x03) | 7.3.1 |
| 3 | `Payload Length` ≠ 실제 수신 길이 | `INVALID_FORMAT` (0x09) | 7.3.1 |
| 4 | `Message Type` = 0x000E (Reserved) | `INVALID_FORMAT` (0x09) | 표 7-2 |
| 5 | `Transmission Type` = 0x03 | `INVALID_TRANSMISSION_TYPE` (0x08) | 표 7-6 |
| 6 | `Value Type` = 0x03 (Reserved) | `INVALID_DATA_TYPE` (0x06) | 표 7-14 |
| 7 | 미등록 `Subtype` (0x40) | `INVALID_DATA_SUBTYPE` (0x07) | 표 7-14 |
| 8 | `NEC` = 0x07 수신 | `ERROR_BATTERY_LOW` (0x07) | 7.3.2 |

각 케이스가 정확한 코드와 **조항 번호**를 반환하는지가 기능 2의 판정 기준이다. 화면에는 `INVALID_FORMAT (0x09) — 7.3.1절` 형태로 그대로 출력한다.

---

## 10. 검증 결과

### 10.1 구조체 크기 ↔ 표준 명시값 (8종, 전량 일치)

| 구조체 | 계산값 | 표준 명시 | 출처 |
|---|---|---|---|
| Header | 12 B | 96 bit | 그림 7-1 |
| `NODE_PROPERTY` | 8 B | 64 bit | 표 7-13 / 표 7-16 |
| `DEVICE_MAIN_INFO` | 7 B | 56 bit | 표 7-14 / 표 7-15 |
| `DEVICE_PROPERTY` | 30 B | 240 bit | 표 7-15 / 표 7-16 |
| `MSG_CONTROL_PROFILE` | 7 B | 56 bit | 표 7-18 |
| `RSC` / `NEC` / `DEVICE_ID` | 각 1 B | 각 8 bit | 표 7-9 / 7-11 / 7-17 |

### 10.2 메시지 명세 (34종)

- 모든 `Message Type` 코드가 14 bit 범위 및 블록 경계(REQ 0x0000~0x03FF / RES 0x0400~0x07FF / NOTI 0x0800~0x0BFF / ACK 0x0C00~0x0FFF) 내
- **Request 코드 + 0x0400 = Response 코드** — 14쌍 전량 성립
- 중복 코드 1건 검출: 0x0800 (§6 #1)

### 10.3 예시 프레임 (9건)

- 헤더 왕복 검증 (encode → decode) 전량 통과
- `Payload Length` = 실제 페이로드 길이 일치 전량 확인
- `DEVICE_MAIN_INFO` FLOAT 값 복원: 25.3 → 25.3 (IEEE-754 single, big-endian)

### 10.4 `Value`(32 bit) 범위 강제와 왕복 — 29종 (F-044 · F-047 · F-055 · F-058)

표 7-14의 `Value Type`은 INT / UNSIGNED INT / FLOAT를 구분하는데, 세 타입이 같은 32 bit 자리를 쓴다. **범위를 검사하지 않고 마스킹하면 잘못된 입력이 정상 바이트로 위장한다** — 골든 벡터의 정답 자체가 오염되므로 실패시킨다.

| 검증 | 내용 |
|---|---|
| 경계값 왕복 7종 | INT `-2^31`→`80000000` / INT `-1`→`FFFFFFFF` / INT `2^31-1`→`7FFFFFFF` / UINT `0`→`00000000` / UINT `2^32-1`→`FFFFFFFF` / FLOAT `25.3`→`41CA6666` / **FLOAT 최댓값→`7F7FFFFF`** |
| 범위 밖 차단 10종 | UINT 음수 · UINT `2^32` · INT `2^31` · INT `-2^31-1` · `Value Type=0x03`(Reserved) · 정수 자리의 소수 · **FLOAT `1e39` · `-1e39` · `inf` · `nan`** (F-055) |
| 타입 해석 분리 | 동일 비트열 `FFFFFFFF` → INT `-1` / UINT `4294967295` |
| 디코딩 차단 3종 | `Value Type` = `0x03`(Reserved) · `0x04` · `0x63` (F-047) |
| **변환 차단 6종** | FLOAT `10**400` · `"abc"` · `None` / INT `inf` · `"abc"` / UINT `None` (F-058) |
| `DEVICE_PROPERTY` 적용 | USER DEPENDENT 5필드도 같은 규칙. 범위 밖 차단 + 경계값 왕복 |

INT는 2의 보수로 복원한다. **이 왕복이 성립해야 C 구현과 Python 구현이 같은 값을 뜻한다고 말할 수 있다.**

**FLOAT도 범위가 있다 (F-055).** `1e39`는 IEEE-754 single로 표현할 수 없다. 이걸 막지 않으면 `struct.pack('>f', ...)`이 `OverflowError`를 던지는데, 그건 `ValueRangeError`가 아니라서 **호출자가 잡아야 할 예외가 둘로 늘어난다.** 상한은 표현 가능한 최대 유한값 `3.4028234663852886e38`(`7F7FFFFF`)이며, `inf`·`nan`도 거부한다.

**범위 검사보다 앞선 단계가 있었다 (F-058).** `float(10**400)`은 범위를 보기도 전에 `OverflowError`를 던진다. `"abc"`는 `ValueError`, `None`은 `TypeError`다 — 같은 "32비트에 안 들어가는 값"이 입력의 **형태**에 따라 서로 다른 예외로 나온다.

```
pack_value(..., FLOAT, 1e39)    -> ValueRangeError   (범위 검사 통과 후)
pack_value(..., FLOAT, 10**400) -> OverflowError     (변환 단계에서 먼저)
```

변환도 `try`로 감싸 세 예외를 `ValueRangeError`로 정규화했다. 원인 예외는 `raise ... from e`로 보존한다. **정수 경로도 같았다** — `int(float('inf'))`·`int('abc')`·`int(None)`. 지적은 FLOAT만 짚었지만 원인이 같아 함께 고쳤다.

> **호출자 계약은 하나다**: `pack_value()`가 던지는 예외는 `ValueRangeError` 뿐이다. 이 문장이 참이어야 `siap/codec.py`가 `violations`를 채우는 경로를 단순하게 유지할 수 있다.

**인코딩만 막으면 판정 기준이 무너진다(F-047).** 디코더가 `0x03`을 UINT처럼 읽어버리면 기능 2의 위반 케이스 6(`Value Type = 0x03` → `INVALID_DATA_TYPE (0x06)`, 표 7-10)을 검출하지 못한다. 인코딩·디코딩 양쪽에서 동일하게 거부하고, 회귀 테스트도 양쪽을 분리해 둔다.

---

## 11. 다음 단계

1. `firmware/core/bitpack.c/.h` — 비트 패킹 4개 함수
2. `firmware/core/siap_types.h` — §1·§2 구조체를 C로
3. `firmware/core/siap_frame.c` — §3 메시지 34종 인코딩·디코딩, §4 N 산출
4. `siap/codec.py` — 동일 로직 Python 판 (C 먼저 작성 후 이식)
5. `contracts/vectors/golden.jsonl` — §8 예시 9건 → 당시 52건 확장(이후 F-120 으로 53건, §9)
6. `firmware/tests/` + `siap/tests/` — 동일 벡터로 양쪽 검증
