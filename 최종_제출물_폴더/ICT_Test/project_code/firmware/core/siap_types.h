#ifndef SIAP_TYPES_H
#define SIAP_TYPES_H
/*
 * SIAP 프레임 계약의 C 대응 — TTAK.KO-10.0943 7장.
 * contracts/frame.py 의 열거형·구조체·LAYOUT 을 그대로 옮긴다 (Frame 구조 명세서 §7
 * "firmware/core/siap_types.h — 본 계약의 C 대응").
 *
 * core/ 는 하드웨어 의존성 0이다 (CLAUDE.md §1-5) — Arduino.h, avr/esp 계열 플랫폼
 * 헤더를 include하지 않는다. <stdint.h>/<stdbool.h> 는 C99 표준 헤더다.
 *
 * 엔디안 : big-endian (network byte order)   — 표준 미규정, 자체 결정 (CLAUDE.md §3.5)
 * FLOAT  : IEEE-754 single precision, 4byte  — 표준 미규정, 자체 결정 (CLAUDE.md §3.5)
 *
 * 설계서와의 알려진 차이 한 가지 — 펌웨어 설계서 §5.3 pseudocode 는
 * `pgm_read_byte(&LAYOUT[k].fixed)` 로 LAYOUT 을 AVR PROGMEM 에서 읽는 모습을
 * 보인다. 그러나 pgm_read_byte 는 <avr/pgmspace.h> 없이 쓸 수 없고, 그 헤더를
 * core/ 가 include하면 CLAUDE.md §1-5(하드웨어 의존성 0)와 정면 충돌하며 ESP32
 * 빌드가 깨진다. 그래서 아래 SIAP_WIRE_CODE / SIAP_WIRE_CODE_EXT / SIAP_LAYOUT
 * 은 평범한 `static const` 배열로 둔다 — 플랫폼 무관을 우선한 것이며, AVR 에서는
 * 이 상수 테이블(각 70 byte 안팎) 이 .data/.rodata 로 RAM 에 얹힐 수 있다.
 * 개발_착수_지시서 §1.5 에 따라 단계 8 의 avr-size 실측이 전체-globals SRAM 예산
 * (55%)을 넘으면 그때 보드별 바인딩 계층에서 PROGMEM 접근을 얹는 것으로 재검토한다.
 * 단계 8 Uno 실측은 50.0%(< 55%)라 재검토는 발동하지 않았다 — core/ 순수성을 유지한다
 * (2026-08-16, 펌웨어 설계서 §3.4·§3.5). 지금은 core/ 순수성이 우선한다.
 */
#include <stdbool.h>
#include <stdint.h>

/* C++/Arduino 스케치에서 C 링키지로 부를 수 있게 한다(bitpack.h 주석 참조) —
   C 컴파일 시엔 비활성, 언어 매크로라 core 순수성(§1-5)과 무관하다. */
#ifdef __cplusplus
extern "C" {
#endif

/* ═══════════════════════════════════════════════════════════════
 *  0. 헤더 상수 — 그림 7-1
 * ═══════════════════════════════════════════════════════════════ */
#define SIAP_VERSION 0x12u   /* v1.2. 7.2.1 */

/* ═══════════════════════════════════════════════════════════════
 *  1. 메시지 종류 — MsgKind 의 C 대응.
 *     SIAP_KIND_NONE(0) 은 Python 의 `MsgKind | None` 중 None 에 대응하는
 *     센티널이다. 열거 순서는 contracts/frame.py 의 정의 순서와 같다.
 * ═══════════════════════════════════════════════════════════════ */
typedef enum {
    SIAP_KIND_NONE = 0,   /* 해석 불가 — 미정의 Message Type 또는 Payload Length 불일치 */

    /* Request 14종 (표 7-2) */
    SIAP_REQ_SET_CONNECTION,
    SIAP_REQ_SET_DEVICE_INIT,
    SIAP_REQ_SET_DEVICE_INIT_ALL,
    SIAP_REQ_SET_NODE_PROPERTY,
    SIAP_REQ_SET_DEVICE_PROPERTY,
    SIAP_REQ_SET_NODE_DEVICE_PROPERTY_ALL,
    SIAP_REQ_SET_MSG_FLOW_CONTROL_PROFILE,
    SIAP_REQ_GET_NODE_PROPERTY,
    SIAP_REQ_GET_DEVICE_PROPERTY,
    SIAP_REQ_GET_NODE_DEVICE_PROPERTY_ALL,
    SIAP_REQ_GET_DEVICE_VALUE,
    SIAP_REQ_GET_MSG_FLOW_CONTROL_PROFILE,
    SIAP_REQ_SET_DEVICE_CONTROL,
    SIAP_REQ_SET_REBOOT,

    /* Response 14종 (표 7-3). Request + 0x0400 = Response (14쌍) */
    SIAP_RES_SET_CONNECTION,
    SIAP_RES_SET_DEVICE_INIT,
    SIAP_RES_SET_DEVICE_INIT_ALL,
    SIAP_RES_SET_NODE_PROPERTY,
    SIAP_RES_SET_DEVICE_PROPERTY,
    SIAP_RES_SET_NODE_DEVICE_PROPERTY_ALL,
    SIAP_RES_SET_MSG_FLOW_CONTROL_PROFILE,
    SIAP_RES_GET_NODE_PROPERTY,
    SIAP_RES_GET_DEVICE_PROPERTY,
    SIAP_RES_GET_NODE_DEVICE_PROPERTY_ALL,
    SIAP_RES_GET_DEVICE_VALUE,
    SIAP_RES_GET_MSG_FLOW_CONTROL_PROFILE,
    SIAP_RES_SET_DEVICE_CONTROL,
    SIAP_RES_SET_REBOOT,

    /* Notify / ACK 6종 (표 7-4). 0x0800 이 NOTI_ERROR/NOTI_DEVICE_VALUE 에 중복
       할당된 표준 원문의 결함은 여기서는 소실되지 않는다 — WIRE_CODE 값이
       중복될 뿐 열거형 멤버는 항상 고유하다 (Frame 구조 명세서 §2). */
    SIAP_NOTI_ERROR,
    SIAP_NOTI_DEVICE_VALUE,
    SIAP_NOTI_DISCONNECT,
    SIAP_NOTI_REBOOT,
    SIAP_NOTI_KEEP_ALIVE,
    SIAP_ACK,

    SIAP_KIND_COUNT   /* = 35 (SIAP_KIND_NONE 포함) */
} siap_kind_t;

typedef enum { SIAP_MODE_STRICT = 0, SIAP_MODE_EXTENDED = 1 } siap_mode_t;

/* ═══════════════════════════════════════════════════════════════
 *  2. 표준 정의 열거형
 * ═══════════════════════════════════════════════════════════════ */

/* 표 7-6. 미정의값(0x03)은 열거형 밖이므로 raw uint8_t 로 다루고
   siap_trans_type_valid() 로만 판정한다 (Header.trans_type 과 동일 원칙,
   Frame 구조 명세서 §3.2 F-014). */
#define SIAP_TRANS_UNICAST   0x00u
#define SIAP_TRANS_MULTICAST 0x01u
#define SIAP_TRANS_BROADCAST 0x02u
static inline bool siap_trans_type_valid(uint8_t t) { return t <= SIAP_TRANS_BROADCAST; }

typedef enum {                    /* 표 7-10. 원문 표기는 'SUCESS'(오타) */
    SIAP_RSC_SUCCESS                   = 0x00,
    SIAP_RSC_INVALID_VERSION           = 0x01,
    SIAP_RSC_INVALID_GCG_ID            = 0x02,
    SIAP_RSC_INVALID_NODE_ID           = 0x03,
    SIAP_RSC_INVALID_DEVICE_ID         = 0x04,
    SIAP_RSC_INVALID_DEVICE_TYPE       = 0x05,
    SIAP_RSC_INVALID_DATA_TYPE         = 0x06,
    SIAP_RSC_INVALID_DATA_SUBTYPE      = 0x07,
    SIAP_RSC_INVALID_TRANSMISSION_TYPE = 0x08,
    SIAP_RSC_INVALID_FORMAT            = 0x09,
} siap_rsc_t;

/* F-127 — 0x0A~0xFF 는 Reserved(표 7-10). 열거형 밖 raw 값이 들어올 수 있으므로
   trans_type 과 같은 원칙으로 별도 판정 함수를 둔다. */
static inline bool siap_rsc_valid(uint8_t v) { return v <= (uint8_t)SIAP_RSC_INVALID_FORMAT; }

typedef enum {                    /* 표 7-12 */
    SIAP_NEC_ERROR_DEVICE_STATUS    = 0x00,
    SIAP_NEC_ERROR_DEVICE_INTERFACE = 0x01,
    SIAP_NEC_ERROR_RECEIVE          = 0x02,
    SIAP_NEC_ERROR_SW_TIMER         = 0x03,
    SIAP_NEC_ERROR_HW_TIMER         = 0x04,
    SIAP_NEC_ERROR_PWR              = 0x05,
    SIAP_NEC_ERROR_BATTERY          = 0x06,
    SIAP_NEC_ERROR_BATTERY_LOW      = 0x07,
    SIAP_NEC_ERROR_BATTERY_OFF      = 0x08,
    SIAP_NEC_ERROR_UNKNOWN          = 0x09,
} siap_nec_t;

/* F-127 — 0x0A~0xFF 는 Reserved(표 7-12). */
static inline bool siap_nec_valid(uint8_t v) { return v <= (uint8_t)SIAP_NEC_ERROR_UNKNOWN; }

typedef enum { SIAP_DEV_SENSOR = 0x00, SIAP_DEV_ACTUATOR = 0x01 } siap_dev_type_t;   /* 표 7-14 */

/* 표 7-14. RESERVED(0x03)는 열거형 밖이라 raw uint8_t 필드에 담고
   SIAP_VALUE_TYPE_RESERVED 로만 비교한다 — Value Type=0x03 수신을
   INVALID_DATA_TYPE 로 판정하는 것 자체가 기능 2 위반 케이스 6번이다. */
#define SIAP_VALUE_TYPE_INT      0x00u
#define SIAP_VALUE_TYPE_UINT     0x01u
#define SIAP_VALUE_TYPE_FLOAT    0x02u
#define SIAP_VALUE_TYPE_RESERVED 0x03u

typedef enum { SIAP_TM_PERIODIC = 0x00, SIAP_TM_EVENT = 0x01, SIAP_TM_BOTH = 0x02 } siap_transfer_mode_t; /* 표 7-15 */
typedef enum { SIAP_STATUS_NORMAL = 0x00, SIAP_STATUS_ABNORMAL = 0x01, SIAP_STATUS_UNKNOWN = 0x02 } siap_status_t; /* 표 7-13/7-15 */

/* F-127 — Transfer Mode 0x03, Status 0x03~0xFF 는 Reserved(표 7-15, NODE_PROPERTY
   에서는 표 7-13). 2bit/8bit 필드라 raw 로 담고 이 함수로만 판정한다. */
static inline bool siap_transfer_mode_valid(uint8_t v) { return v <= (uint8_t)SIAP_TM_BOTH; }
static inline bool siap_status_valid(uint8_t v)        { return v <= (uint8_t)SIAP_STATUS_UNKNOWN; }

/* ═══════════════════════════════════════════════════════════════
 *  3. 구조체 크기 상수 (7.3.3) — 코덱이 참조하는 정본
 * ═══════════════════════════════════════════════════════════════ */
#define SIAP_HEADER_BYTES 12u   /* 96 bit  그림 7-1 */
#define SIAP_NP_BYTES      8u   /* 64 bit  표 7-13 */
#define SIAP_DMI_BYTES     7u   /* 56 bit  표 7-14 */
#define SIAP_DP_BYTES     30u   /* 240 bit 표 7-15 */
#define SIAP_MCP_BYTES     7u   /* 56 bit  표 7-18 */
#define SIAP_RSC_BYTES     1u
#define SIAP_NEC_BYTES     1u
#define SIAP_DID_BYTES     1u

/* 노드당 디바이스 상한 — 표준 미규정, 자체 결정 (CLAUDE.md §3.5, F-064).
   RX/TX 스트리밍 윈도우 크기의 근거이기도 하다 (펌웨어 설계서 §3.4/§5.1). */
#define SIAP_MAX_DEVICES_PER_NODE 16u

/* ═══════════════════════════════════════════════════════════════
 *  4. 헤더 — 그림 7-1 / 표 7-5 ~ 7-8
 *     "바이트 정렬 없음" — Message Type(14bit)이 바이트 경계를 넘고
 *     GCG/Node ID(각 20bit)는 9번째 바이트를 반씩 나눠 쓴다.
 * ═══════════════════════════════════════════════════════════════ */
typedef struct {
    uint8_t  version;       /* 8   0x12 = v1.2 */
    uint16_t msg_type;      /* 14  전송된 원본 코드 (0..0x3FFF) */
    uint8_t  trans_type;    /* 2   전송된 원본값 (0..3, 3=표 7-6 미정의) */
    uint16_t msg_id;        /* 16 */
    uint16_t payload_len;   /* 16 */
    uint32_t gcg_id;        /* 20 */
    uint32_t node_id;       /* 20 */
} siap_hdr_t;

typedef struct {              /* 표 7-13 — 64 bit */
    uint8_t  sw_version;
    uint32_t gcg_id;         /* 20 */
    uint32_t node_id;        /* 20 */
    uint8_t  status;         /* siap_status_t */
    uint8_t  num_devices;
} siap_np_t;

typedef struct {              /* 표 7-14 — 56 bit.
                                  value 는 32bit 원시 비트열이다. INT 는 2의 보수,
                                  UINT 는 그대로, FLOAT 는 IEEE-754 비트패턴을 담는다
                                  — 해석은 value_type 을 보고 siap_value_as_*() 로 한다. */
    uint8_t  device_id;
    uint8_t  dev_type;       /* siap_dev_type_t */
    uint8_t  subtype;        /* Subtype 레지스트리 — subtype_registry.h */
    uint8_t  value_type;     /* 0/1/2 또는 3(RESERVED, 위반) */
    uint32_t value;
} siap_dmi_t;

typedef struct {              /* 표 7-15 — 240 bit.
                                  F-022: Lower/Upper Value·Limit·Precision(USER DEPENDENT)은
                                  main.value_type 을 따른다 (표준 미규정 → 구현 결정). */
    siap_dmi_t main;
    uint8_t  transfer_mode;  /* siap_transfer_mode_t */
    uint16_t period;         /* 14bit, sec */
    uint32_t lower_value;
    uint32_t upper_value;
    uint32_t lower_limit;
    uint32_t upper_limit;
    uint32_t precision;
    uint8_t  status;         /* siap_status_t */
} siap_dp_t;

typedef struct {              /* 표 7-18 — 56 bit. 시간 3필드 전부 sec (F-033) */
    uint16_t recv_timeout;
    uint8_t  num_retry;
    uint16_t noti_error_interval;
    uint16_t keep_alive_interval;
} siap_mcp_t;

/* ═══════════════════════════════════════════════════════════════
 *  5. WIRE_CODE — 논리 종류 → 전송 코드.
 *     strict = 표준 원문 그대로 (0x0800 중복 포함, 고유 코드 33개).
 *     extended = 중복 해소 제안안 (고유 코드 34개). Frame 구조 명세서 §2.
 * ═══════════════════════════════════════════════════════════════ */
static const uint16_t SIAP_WIRE_CODE[SIAP_KIND_COUNT] = {
    [SIAP_KIND_NONE] = 0xFFFFu,
    /* Request — 표 7-2, 0x0000~0x000D */
    [SIAP_REQ_SET_CONNECTION]               = 0x0000,
    [SIAP_REQ_SET_DEVICE_INIT]              = 0x0001,
    [SIAP_REQ_SET_DEVICE_INIT_ALL]          = 0x0002,
    [SIAP_REQ_SET_NODE_PROPERTY]            = 0x0003,
    [SIAP_REQ_SET_DEVICE_PROPERTY]          = 0x0004,
    [SIAP_REQ_SET_NODE_DEVICE_PROPERTY_ALL] = 0x0005,
    [SIAP_REQ_SET_MSG_FLOW_CONTROL_PROFILE] = 0x0006,
    [SIAP_REQ_GET_NODE_PROPERTY]            = 0x0007,
    [SIAP_REQ_GET_DEVICE_PROPERTY]          = 0x0008,
    [SIAP_REQ_GET_NODE_DEVICE_PROPERTY_ALL] = 0x0009,
    [SIAP_REQ_GET_DEVICE_VALUE]             = 0x000A,
    [SIAP_REQ_GET_MSG_FLOW_CONTROL_PROFILE] = 0x000B,
    [SIAP_REQ_SET_DEVICE_CONTROL]           = 0x000C,
    [SIAP_REQ_SET_REBOOT]                   = 0x000D,
    /* Response — 표 7-3, 0x0400~0x040D (Request + 0x0400) */
    [SIAP_RES_SET_CONNECTION]               = 0x0400,
    [SIAP_RES_SET_DEVICE_INIT]              = 0x0401,
    [SIAP_RES_SET_DEVICE_INIT_ALL]          = 0x0402,
    [SIAP_RES_SET_NODE_PROPERTY]            = 0x0403,
    [SIAP_RES_SET_DEVICE_PROPERTY]          = 0x0404,
    [SIAP_RES_SET_NODE_DEVICE_PROPERTY_ALL] = 0x0405,
    [SIAP_RES_SET_MSG_FLOW_CONTROL_PROFILE] = 0x0406,
    [SIAP_RES_GET_NODE_PROPERTY]            = 0x0407,
    [SIAP_RES_GET_DEVICE_PROPERTY]          = 0x0408,
    [SIAP_RES_GET_NODE_DEVICE_PROPERTY_ALL] = 0x0409,
    [SIAP_RES_GET_DEVICE_VALUE]             = 0x040A,
    [SIAP_RES_GET_MSG_FLOW_CONTROL_PROFILE] = 0x040B,
    [SIAP_RES_SET_DEVICE_CONTROL]           = 0x040C,
    [SIAP_RES_SET_REBOOT]                   = 0x040D,
    /* Notify / ACK — 표 7-4 */
    [SIAP_NOTI_ERROR]                       = 0x0800,
    [SIAP_NOTI_DEVICE_VALUE]                = 0x0800,  /* ★ 표준 원문 중복 */
    [SIAP_NOTI_DISCONNECT]                  = 0x0801,
    [SIAP_NOTI_REBOOT]                      = 0x0802,
    [SIAP_NOTI_KEEP_ALIVE]                  = 0x0803,
    [SIAP_ACK]                              = 0x0C00,
};

static const uint16_t SIAP_WIRE_CODE_EXT[SIAP_KIND_COUNT] = {
    [SIAP_KIND_NONE] = 0xFFFFu,
    [SIAP_REQ_SET_CONNECTION]               = 0x0000,
    [SIAP_REQ_SET_DEVICE_INIT]              = 0x0001,
    [SIAP_REQ_SET_DEVICE_INIT_ALL]          = 0x0002,
    [SIAP_REQ_SET_NODE_PROPERTY]            = 0x0003,
    [SIAP_REQ_SET_DEVICE_PROPERTY]          = 0x0004,
    [SIAP_REQ_SET_NODE_DEVICE_PROPERTY_ALL] = 0x0005,
    [SIAP_REQ_SET_MSG_FLOW_CONTROL_PROFILE] = 0x0006,
    [SIAP_REQ_GET_NODE_PROPERTY]            = 0x0007,
    [SIAP_REQ_GET_DEVICE_PROPERTY]          = 0x0008,
    [SIAP_REQ_GET_NODE_DEVICE_PROPERTY_ALL] = 0x0009,
    [SIAP_REQ_GET_DEVICE_VALUE]             = 0x000A,
    [SIAP_REQ_GET_MSG_FLOW_CONTROL_PROFILE] = 0x000B,
    [SIAP_REQ_SET_DEVICE_CONTROL]           = 0x000C,
    [SIAP_REQ_SET_REBOOT]                   = 0x000D,
    [SIAP_RES_SET_CONNECTION]               = 0x0400,
    [SIAP_RES_SET_DEVICE_INIT]              = 0x0401,
    [SIAP_RES_SET_DEVICE_INIT_ALL]          = 0x0402,
    [SIAP_RES_SET_NODE_PROPERTY]            = 0x0403,
    [SIAP_RES_SET_DEVICE_PROPERTY]          = 0x0404,
    [SIAP_RES_SET_NODE_DEVICE_PROPERTY_ALL] = 0x0405,
    [SIAP_RES_SET_MSG_FLOW_CONTROL_PROFILE] = 0x0406,
    [SIAP_RES_GET_NODE_PROPERTY]            = 0x0407,
    [SIAP_RES_GET_DEVICE_PROPERTY]          = 0x0408,
    [SIAP_RES_GET_NODE_DEVICE_PROPERTY_ALL] = 0x0409,
    [SIAP_RES_GET_DEVICE_VALUE]             = 0x040A,
    [SIAP_RES_GET_MSG_FLOW_CONTROL_PROFILE] = 0x040B,
    [SIAP_RES_SET_DEVICE_CONTROL]           = 0x040C,
    [SIAP_RES_SET_REBOOT]                   = 0x040D,
    [SIAP_NOTI_ERROR]                       = 0x0800,
    [SIAP_NOTI_DEVICE_VALUE]                = 0x0801,  /* 재배치 (개정 제안) */
    [SIAP_NOTI_DISCONNECT]                  = 0x0802,
    [SIAP_NOTI_REBOOT]                      = 0x0803,
    [SIAP_NOTI_KEEP_ALIVE]                  = 0x0804,
    [SIAP_ACK]                              = 0x0C00,
};

static inline uint16_t siap_wire_code(siap_kind_t k, siap_mode_t mode) {
    return (mode == SIAP_MODE_STRICT ? SIAP_WIRE_CODE : SIAP_WIRE_CODE_EXT)[k];
}

/* ═══════════════════════════════════════════════════════════════
 *  6-a. 하드웨어 추상화 — 함수 포인터 구조체 2종 (펌웨어 설계서 §2.2).
 *     node_state.c 가 아는 하드웨어의 전부다. 보드 디렉터리가 채워 넘긴다.
 *     ctx 도 멤버 하나이므로 크기 산정에서 별도로 더하지 않는다(§2.2).
 * ═══════════════════════════════════════════════════════════════ */
typedef struct {
    /* 1 byte 를 읽는다. 1 = 읽음 / 0 = 지금은 없음 / -1 = 링크 오류 */
    int8_t   (*read_byte)(void *ctx, uint8_t *out);
    /* len byte 를 쓴다. 쓴 개수 반환(논블로킹, 부분 쓰기 허용) */
    int16_t  (*write)(void *ctx, const uint8_t *buf, uint16_t len);
    /* 부팅 후 경과 ms. 롤오버 허용(§6.4) */
    uint32_t (*millis)(void *ctx);
    void     *ctx;
} siap_io_t;

typedef struct {
    /* 디바이스 1개의 현재값을 32bit 원시 비트열로 읽는다. 0 = 성공, -1 = 오류
       (합성 데이터 금지 — 실패 시 값을 지어내지 않는다, CLAUDE.md §1-1) */
    int8_t (*read_value)(void *ctx, uint8_t device_id, uint32_t *raw);
    /* 디바이스 1개에 제어값을 쓴다. 0 = 성공 */
    int8_t (*write_value)(void *ctx, uint8_t device_id, uint32_t raw);
    void  *ctx;
} siap_dev_ops_t;

/* ═══════════════════════════════════════════════════════════════
 *  6. LAYOUT — (고정부 byte, 요소 byte). N 산출의 정본.
 *     contracts/frame.py 의 LAYOUT 과 줄 단위로 대응한다 (펌웨어 설계서 §5.3).
 * ═══════════════════════════════════════════════════════════════ */
typedef struct { uint8_t fixed; uint8_t elem; } siap_layout_t;

static const siap_layout_t SIAP_LAYOUT[SIAP_KIND_COUNT] = {
    [SIAP_KIND_NONE]                         = {0, 0},
    [SIAP_REQ_SET_CONNECTION]                = {0, 0},
    [SIAP_REQ_SET_DEVICE_INIT]               = {0, SIAP_DID_BYTES},
    [SIAP_REQ_SET_DEVICE_INIT_ALL]           = {0, 0},
    [SIAP_REQ_SET_NODE_PROPERTY]             = {SIAP_NP_BYTES, 0},
    [SIAP_REQ_SET_DEVICE_PROPERTY]           = {0, SIAP_DP_BYTES},
    [SIAP_REQ_SET_NODE_DEVICE_PROPERTY_ALL]  = {SIAP_NP_BYTES, SIAP_DP_BYTES},
    [SIAP_REQ_SET_MSG_FLOW_CONTROL_PROFILE]  = {SIAP_MCP_BYTES, 0},
    [SIAP_REQ_GET_NODE_PROPERTY]             = {0, 0},
    [SIAP_REQ_GET_DEVICE_PROPERTY]           = {0, SIAP_DID_BYTES},
    [SIAP_REQ_GET_NODE_DEVICE_PROPERTY_ALL]  = {0, 0},
    [SIAP_REQ_GET_DEVICE_VALUE]              = {0, SIAP_DID_BYTES},
    [SIAP_REQ_GET_MSG_FLOW_CONTROL_PROFILE]  = {0, 0},
    [SIAP_REQ_SET_DEVICE_CONTROL]            = {0, SIAP_DMI_BYTES},
    [SIAP_REQ_SET_REBOOT]                    = {0, 0},
    [SIAP_RES_SET_CONNECTION]                = {SIAP_RSC_BYTES + SIAP_NP_BYTES, SIAP_DP_BYTES},
    [SIAP_RES_SET_DEVICE_INIT]               = {SIAP_RSC_BYTES, 0},
    [SIAP_RES_SET_DEVICE_INIT_ALL]           = {SIAP_RSC_BYTES, 0},
    [SIAP_RES_SET_NODE_PROPERTY]             = {SIAP_RSC_BYTES, 0},
    [SIAP_RES_SET_DEVICE_PROPERTY]           = {SIAP_RSC_BYTES, 0},
    [SIAP_RES_SET_NODE_DEVICE_PROPERTY_ALL]  = {SIAP_RSC_BYTES, 0},
    [SIAP_RES_SET_MSG_FLOW_CONTROL_PROFILE]  = {SIAP_RSC_BYTES, 0},
    [SIAP_RES_GET_NODE_PROPERTY]             = {SIAP_RSC_BYTES + SIAP_NP_BYTES, 0},
    [SIAP_RES_GET_DEVICE_PROPERTY]           = {SIAP_RSC_BYTES, SIAP_DP_BYTES},
    [SIAP_RES_GET_NODE_DEVICE_PROPERTY_ALL]  = {SIAP_RSC_BYTES + SIAP_NP_BYTES, SIAP_DP_BYTES},
    [SIAP_RES_GET_DEVICE_VALUE]              = {SIAP_RSC_BYTES, SIAP_DMI_BYTES},
    [SIAP_RES_GET_MSG_FLOW_CONTROL_PROFILE]  = {SIAP_RSC_BYTES + SIAP_MCP_BYTES, 0},
    [SIAP_RES_SET_DEVICE_CONTROL]            = {SIAP_RSC_BYTES, 0},
    [SIAP_RES_SET_REBOOT]                    = {SIAP_RSC_BYTES, 0},
    [SIAP_NOTI_ERROR]                        = {SIAP_NEC_BYTES, 0},
    [SIAP_NOTI_DEVICE_VALUE]                 = {0, SIAP_DMI_BYTES},
    [SIAP_NOTI_DISCONNECT]                   = {0, 0},
    [SIAP_NOTI_REBOOT]                       = {0, 0},
    [SIAP_NOTI_KEEP_ALIVE]                   = {0, 0},
    [SIAP_ACK]                               = {0, 0},
};

#ifdef __cplusplus
}
#endif

#endif /* SIAP_TYPES_H */
