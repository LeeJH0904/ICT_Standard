#ifndef SIAP_FRAME_H
#define SIAP_FRAME_H
/*
 * 스트리밍 코덱 — 펌웨어 설계서 §5. siap_types.h(구조체) 위에 인코딩·디코딩·
 * N 산출을 얹는다. core/ 는 하드웨어 의존성 0 이다 (CLAUDE.md §1-5).
 *
 * RAM 예산: 수신 버퍼 51 byte(헤더 12 + 고정부 최대 9 + 요소 최대 30) 하나로
 * 프레임 크기와 무관하게 동작한다 (펌웨어 설계서 §3.4/§5.1) — 501 byte 위반
 * 프레임이 들어와도 이 버퍼 크기는 변하지 않는다(S_DRAIN).
 */
#include <string.h>   /* memcpy — 표준 라이브러리 헤더, 타입 펀닝에만 쓴다(bitpack.c 와 동일 원칙) */
#include "siap_types.h"
#include "subtype_registry.h"
#include "bitpack.h"  /* bp_* 4개 함수, SIAP_WUR */

/* ═══════════════════════════════════════════════════════════════
 *  0. 위반 조항 코드 — CLAUDE.md §3.3 "판정에는 반드시 clause 를 채운다"의
 *     펌웨어 대응. 문자열을 두면 flash 를 먹으므로 코드값만 두고 매핑표는
 *     docs/standard-mapping.md 에 둔다 (펌웨어 설계서 §5.2).
 * ═══════════════════════════════════════════════════════════════ */
typedef enum {
    SIAP_CLAUSE_NONE = 0,
    SIAP_CLAUSE_7_3_1,       /* 7.3.1      — Version / Node ID / Payload Length 형식 */
    SIAP_CLAUSE_TABLE_7_2,   /* 표 7-2     — 미정의 Message Type */
    SIAP_CLAUSE_TABLE_7_6,   /* 표 7-6     — 미정의 Transmission Type */
    SIAP_CLAUSE_TABLE_7_14,  /* 표 7-14    — Value Type / Subtype */
    SIAP_CLAUSE_7_3_2,       /* 7.3.2      — NEC. 코덱은 생성하지 않는다(게이트웨이 전용, F-060) */
} siap_clause_t;

/* ═══════════════════════════════════════════════════════════════
 *  1. N 산출 / 종류 해석 — contracts/frame.py element_count()/resolve_kind() 의
 *     C 대응. 분기 구조를 줄 단위로 대응시킨다 (펌웨어 설계서 §5.3).
 * ═══════════════════════════════════════════════════════════════ */

/* N 산출. 규격에 맞지 않으면 음수(-1) — INVALID_FORMAT(7.3.1)의 근거.
   고정부 없이 가변부만 갖는 메시지는 N>=1 을 요구한다(표준 미규정 → 구현 결정,
   Frame 구조 명세서 §4.1). */
int32_t siap_element_count(siap_kind_t k, uint16_t payload_len);

/* 전송 코드 + Payload Length → 논리 종류. 실패 시 SIAP_KIND_NONE 을 돌려주고
   *out_clause 에 원인을 채운다 — 미정의 코드(표 7-2)와 형식 불일치(7.3.1)를
   구분해야 기능 2 위반 케이스 3번/4번이 서로 다른 clause 로 표시된다. */
siap_kind_t siap_resolve_kind(uint16_t msg_type, uint16_t payload_len,
                               siap_mode_t mode, siap_clause_t *out_clause);

/* ═══════════════════════════════════════════════════════════════
 *  2. 구조체 인코드/디코드 — bitpack.h 4개 함수만 경유한다.
 *     헤더/NODE_PROPERTY/MSG_CONTROL_PROFILE 은 위반이 없으므로 bool(성공여부)만.
 *     DEVICE_MAIN_INFO/DEVICE_PROPERTY 는 Value Type·Subtype 위반이 있을 수
 *     있어 siap_result_t 를 돌려준다.
 * ═══════════════════════════════════════════════════════════════ */
typedef struct {
    bool          ok;
    siap_rsc_t    rsc;      /* ok==false 일 때만 유효 */
    siap_clause_t clause;   /* ok==false 일 때만 유효 */
} siap_result_t;

SIAP_WUR bool siap_encode_hdr(uint8_t *buf, size_t *bitpos, const siap_hdr_t *h);
         void siap_decode_hdr(const uint8_t *buf, size_t *bitpos, siap_hdr_t *h);

SIAP_WUR bool siap_encode_np(uint8_t *buf, size_t *bitpos, const siap_np_t *np);
         void siap_decode_np(const uint8_t *buf, size_t *bitpos, siap_np_t *np);

siap_result_t siap_encode_dmi(uint8_t *buf, size_t *bitpos, const siap_dmi_t *dmi);
siap_result_t siap_decode_dmi(const uint8_t *buf, size_t *bitpos, siap_dmi_t *dmi);

siap_result_t siap_encode_dp(uint8_t *buf, size_t *bitpos, const siap_dp_t *dp);
siap_result_t siap_decode_dp(const uint8_t *buf, size_t *bitpos, siap_dp_t *dp);

SIAP_WUR bool siap_encode_mcp(uint8_t *buf, size_t *bitpos, const siap_mcp_t *mcp);
         void siap_decode_mcp(const uint8_t *buf, size_t *bitpos, siap_mcp_t *mcp);

/* Value(32bit 원시 비트열) 해석 — 표 7-14. INT 는 2의 보수. */
static inline int32_t  siap_value_as_int(uint32_t raw)   { int32_t v; memcpy(&v, &raw, 4); return v; }
static inline uint32_t siap_value_as_uint(uint32_t raw)  { return raw; }
static inline float    siap_value_as_float(uint32_t raw) { float v; memcpy(&v, &raw, 4); return v; }
static inline uint32_t siap_raw_from_int(int32_t v)      { uint32_t r; memcpy(&r, &v, 4); return r; }
static inline uint32_t siap_raw_from_uint(uint32_t v)    { return v; }
static inline uint32_t siap_raw_from_float(float v)      { uint32_t r; memcpy(&r, &v, 4); return r; }

/* ═══════════════════════════════════════════════════════════════
 *  3. 수신 — 스트리밍 상태 머신 (펌웨어 설계서 §5.1/§5.2/§5.7)
 * ═══════════════════════════════════════════════════════════════ */
#define SIAP_RX_WINDOW 51u   /* 12(헤더) + 9(고정부 최대) + 30(요소 최대) */

typedef struct {
    /* 헤더 파싱 완료. 0 반환 시 계속, 음수 반환 시 -(rsc) 로 거부(예: 등록되지
       않은 Node ID — 그 판단은 core/ 가 아니라 호출자(node_state 등)의 몫이다). */
    int8_t (*on_header)(void *ctx, const siap_hdr_t *h, siap_kind_t k, uint16_t n);
    /* 고정부 (RSC / NODE_PROPERTY / MSG_CONTROL_PROFILE / NEC) */
    int8_t (*on_fixed)(void *ctx, const uint8_t *buf, uint8_t len);
    /* 가변 요소 i번째 (0-based). Value Type/Subtype 위반은 core/ 가 이 콜백보다
       먼저 걸러내므로, 여기 도달한 요소는 그 두 가지에 한해서는 유효하다. */
    int8_t (*on_element)(void *ctx, uint16_t i, const uint8_t *buf, uint8_t len);
    /* 프레임 종료. rsc=SIAP_RSC_SUCCESS 면 정상, 아니면 첫 위반 코드(§5.6 —
       요소 단위 즉시 적용 + 첫 위반에서 중단). */
    void (*on_end)(void *ctx, siap_rsc_t rsc, siap_clause_t clause);
    void *ctx;
} siap_sink_t;

typedef enum {
    SIAP_DEC_ST_HDR = 0,   /* 헤더 12 byte 수집 (S_SYNC + S_HDR) */
    SIAP_DEC_ST_FIXED,     /* 고정부 수집 */
    SIAP_DEC_ST_ELEM,      /* 요소 수집 */
    SIAP_DEC_ST_DRAIN,     /* 위반 프레임의 잔여 payload 폐기 */
} siap_dec_state_t;

typedef struct {
    siap_sink_t sink;
    siap_mode_t mode;

    uint8_t buf[SIAP_RX_WINDOW];
    uint8_t buf_len;
    siap_dec_state_t state;
    bool    resync;          /* true 면 다음 헤더 후보에 §5.7 4조건 사전검사 적용 */

    siap_kind_t kind;
    uint16_t    n;
    uint8_t     fixed_len;
    uint8_t     elem_len;
    uint16_t    elem_i;
    uint16_t    drain_remaining;
} siap_dec_t;

void siap_dec_init(siap_dec_t *d, siap_sink_t sink, siap_mode_t mode);
/* 바이트 하나를 먹인다 — UART/TCP 수신 콜백에서 바이트마다 호출한다. */
void siap_dec_feed(siap_dec_t *d, uint8_t byte);
/* T_gap(20ms, §5.7) 이상 무입력을 관측했을 때 호출한다. 헤더 대기 중이 아니면
   방어적으로 그 자리에서도 재동기 모드로 되돌린다(불완전 프레임 포기). */
void siap_dec_on_gap(siap_dec_t *d);

/* ═══════════════════════════════════════════════════════════════
 *  4. 송신 — Payload Length 선산출 + 윈도우 버퍼 (펌웨어 설계서 §5.8)
 * ═══════════════════════════════════════════════════════════════ */
#define SIAP_TX_WINDOW 51u

typedef struct {
    uint8_t win[SIAP_TX_WINDOW];
    size_t  bitpos;   /* win 안에서 다음에 쓸 위치. 반드시 8의 배수에서 flush */
    size_t  sent;     /* win[0..bitpos/8) 중 이미 io 로 내보낸 바이트 수 */
} siap_enc_t;

typedef enum { SIAP_TX_DONE = 0, SIAP_TX_PENDING = 1 } siap_tx_status_t;

/* 논블로킹 쓰기. 실제로 쓴 바이트 수(0 이면 지금은 못 쓴다)를 돌려준다.
   siap_io_t.write 와 동일한 부분 쓰기 계약(펌웨어 설계서 §5.8). */
typedef size_t (*siap_io_write_fn)(void *io_ctx, const uint8_t *data, size_t len);

void siap_tx_reset(siap_enc_t *e);
SIAP_WUR bool siap_tx_put_hdr(siap_enc_t *e, const siap_hdr_t *h);
SIAP_WUR bool siap_tx_put_rsc(siap_enc_t *e, siap_rsc_t rsc);
SIAP_WUR bool siap_tx_put_nec(siap_enc_t *e, siap_nec_t nec);
SIAP_WUR bool siap_tx_put_np(siap_enc_t *e, const siap_np_t *np);
SIAP_WUR bool siap_tx_put_mcp(siap_enc_t *e, const siap_mcp_t *mcp);
SIAP_WUR bool siap_tx_put_device_id(siap_enc_t *e, uint8_t device_id);
/* dmi/dp 는 값 자체가 위반(Value Type=RESERVED 등)일 수 있어 siap_result_t. */
siap_result_t siap_tx_put_dmi(siap_enc_t *e, const siap_dmi_t *dmi);
siap_result_t siap_tx_put_dp(siap_enc_t *e, const siap_dp_t *dp);

/* 윈도우에 쌓인 것을 내보낸다. 부분 쓰기면 SIAP_TX_PENDING 을 돌려주고 잔여를
   윈도우에 남긴다 — 블로킹하지 않는다(그래야 그동안 수신 바이트가 안 새지 않는다). */
siap_tx_status_t siap_tx_flush(siap_enc_t *e, siap_io_write_fn write, void *io_ctx);

/* ACK — F-040 계약. msg_id·GCG ID·Node ID 를 원 요청에서 복사한다 (7.2.2). */
SIAP_WUR bool siap_encode_ack(const siap_hdr_t *req, siap_mode_t mode, siap_enc_t *e);

#endif /* SIAP_FRAME_H */
