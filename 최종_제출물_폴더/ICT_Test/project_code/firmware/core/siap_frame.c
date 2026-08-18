/*
 * 스트리밍 코덱 구현. 펌웨어 설계서 §5.
 *
 * 위반 판정 지점은 설계서 §5.4 표를 그대로 따른다:
 *   1 Version              -> S_HDR   (헤더 12byte 완성 직후)
 *   2 미등록 Node ID        -> on_header 콜백 (core/ 는 "내 ID" 를 모른다 — 그건
 *                              node_state 의 몫이다. 콜백이 음수를 돌려주면 거부)
 *   3 Payload Length 불일치 -> S_HDR   (resolve_kind 가 어떤 후보의 element_count 도
 *                              만족시키지 못할 때. 즉시 탐지 가능 범위는 펌웨어
 *                              설계서 §5.5 참조 — 나머지는 표준 자체의 결함이다)
 *   4 미정의 Message Type   -> S_HDR   (resolve_kind 후보 자체가 없을 때)
 *   5 Transmission Type     -> S_HDR
 *   6 Value Type            -> S_ELEM  (DEVICE_MAIN_INFO/DEVICE_PROPERTY 디코드)
 *   7 Subtype                -> S_ELEM  (위와 동일 지점, value_type 통과 후)
 *   8 NEC                    -> 코덱 밖 (게이트웨이 전용 판정, F-060)
 */
#include "siap_frame.h"

/* ═══════════════════════════════════════════════════════════════
 *  1. N 산출 / 종류 해석
 * ═══════════════════════════════════════════════════════════════ */

/* contracts/frame.py element_count() 와 1:1 대응 (펌웨어 설계서 §5.3). */
int32_t siap_element_count(siap_kind_t k, uint16_t payload_len)
{
    const siap_layout_t *lay = &SIAP_LAYOUT[k];
    int32_t rest = (int32_t)payload_len - (int32_t)lay->fixed;
    if (rest < 0) return -1;
    if (lay->elem == 0) return (rest == 0) ? 0 : -1;
    if (rest % lay->elem) return -1;
    int32_t n = rest / lay->elem;
    if (n == 0 && lay->fixed == 0) return -1;   /* 가변부만 있는 메시지는 N>=1 */
    /* F-120 — 노드당 디바이스 상한(CLAUDE.md §3.5, contracts/frame.py 와
       동일한 MAX_DEVICES_PER_NODE=16). N=17 이상은 표준 미규정 영역을
       이 프로젝트가 자체 결정으로 닫은 것이지 표준 위반은 아니지만,
       Timeout·메모리 산정의 전제가 깨지므로 INVALID_FORMAT 으로 거부한다. */
    if (n > (int32_t)SIAP_MAX_DEVICES_PER_NODE) return -1;
    return n;
}

/* F-119 처리 중 발견 — contracts/frame.py::resolve_kind() 는 후보가
   하나뿐이면 element_count() 를 전혀 보지 않고 그 후보를 바로 확정한다
   (0943 표 7-2~7-4 코드공간이 정하는 것은 "이 코드가 무엇을 뜻하는가"이지
   "이 Payload Length 가 유효한가"가 아니다 — 후자는 호출자가 별도로
   element_count() 를 불러 판정한다). 후보가 둘 이상(0x0800 중복)일 때만
   element_count() 로 골라낸다. 이전 구현은 후보 수와 무관하게 항상
   element_count() 를 검사해, B02(REQ_SET_DEVICE_CONTROL 단일 후보,
   plen=0)에서 Python 원본과 다른 지점(resolve_kind 안)에서 실패를
   판정했다 — 최종 위반 코드/조항은 우연히 같았지만 분기 구조가 갈렸다
   (펌웨어 설계서 §5.3 "Python 원본과 분기 구조가 같아야 한다"). */
siap_kind_t siap_resolve_kind(uint16_t msg_type, uint16_t payload_len,
                               siap_mode_t mode, siap_clause_t *out_clause)
{
    const uint16_t *table = (mode == SIAP_MODE_STRICT) ? SIAP_WIRE_CODE : SIAP_WIRE_CODE_EXT;
    siap_kind_t cands[4];
    unsigned ncands = 0;
    for (unsigned k = 1; k < SIAP_KIND_COUNT; k++) {
        if (table[k] != msg_type) continue;
        if (ncands < 4) cands[ncands] = (siap_kind_t)k;
        ncands++;
    }
    if (ncands == 0) {                         /* 표 7-2 — 코드 자체가 미정의 */
        if (out_clause) *out_clause = SIAP_CLAUSE_TABLE_7_2;
        return SIAP_KIND_NONE;
    }
    if (ncands == 1) {                         /* 단일 후보 — element_count 무관하게 확정 */
        if (out_clause) *out_clause = SIAP_CLAUSE_NONE;
        return cands[0];
    }
    for (unsigned i = 0; i < ncands; i++) {    /* 다중 후보(0x0800) — 맞는 것을 고른다 */
        if (siap_element_count(cands[i], payload_len) >= 0) {
            if (out_clause) *out_clause = SIAP_CLAUSE_NONE;
            return cands[i];
        }
    }
    /* 후보가 둘 이상인데 아무도 이 Payload Length 를 못 받는다 — 7.3.1
       (위반 케이스 3번, X03). 표 7-2 는 "코드 자체가 없다"는 뜻이므로
       여기서는 쓰지 않는다. */
    if (out_clause) *out_clause = SIAP_CLAUSE_7_3_1;
    return SIAP_KIND_NONE;
}

/* ═══════════════════════════════════════════════════════════════
 *  2. 구조체 인코드/디코드 — 비트 순서는 필드를 순서대로 bp_write/bp_read 에
 *     넘기는 것만으로 정해진다. bitpos 가 바이트 경계를 넘나들어도 상관없다
 *     (bitpack.c 가 이미 그 경우를 처리한다) — 그래서 워드 단위로 묶어
 *     시프트하지 않고 표의 필드 순서를 그대로 옮긴다.
 * ═══════════════════════════════════════════════════════════════ */

bool siap_encode_hdr(uint8_t *buf, size_t *bitpos, const siap_hdr_t *h)
{
    return bp_write(buf, bitpos, h->version, 8)
        && bp_write(buf, bitpos, h->msg_type, 14)
        && bp_write(buf, bitpos, h->trans_type, 2)
        && bp_write(buf, bitpos, h->msg_id, 16)
        && bp_write(buf, bitpos, h->payload_len, 16)
        && bp_write(buf, bitpos, h->gcg_id, 20)
        && bp_write(buf, bitpos, h->node_id, 20);
}

void siap_decode_hdr(const uint8_t *buf, size_t *bitpos, siap_hdr_t *h)
{
    h->version     = (uint8_t)bp_read(buf, bitpos, 8);
    h->msg_type    = (uint16_t)bp_read(buf, bitpos, 14);
    h->trans_type  = (uint8_t)bp_read(buf, bitpos, 2);
    h->msg_id      = (uint16_t)bp_read(buf, bitpos, 16);
    h->payload_len = (uint16_t)bp_read(buf, bitpos, 16);
    h->gcg_id      = bp_read(buf, bitpos, 20);
    h->node_id     = bp_read(buf, bitpos, 20);
}

bool siap_encode_np(uint8_t *buf, size_t *bitpos, const siap_np_t *np)
{
    /* F-127 — 표 7-13 Status(0x03~0xFF)는 Reserved. bp_write 를 하나도 부르기
       전에 검사해 실패 시 아무것도 기록하지 않는다(bitpack.c 의 "범위 초과 시
       아무것도 안 씀" 계약과 같은 원칙). */
    if (!siap_status_valid(np->status)) return false;
    return bp_write(buf, bitpos, np->sw_version, 8)
        && bp_write(buf, bitpos, np->gcg_id, 20)
        && bp_write(buf, bitpos, np->node_id, 20)
        && bp_write(buf, bitpos, np->status, 8)
        && bp_write(buf, bitpos, np->num_devices, 8);
}

void siap_decode_np(const uint8_t *buf, size_t *bitpos, siap_np_t *np)
{
    np->sw_version  = (uint8_t)bp_read(buf, bitpos, 8);
    np->gcg_id      = bp_read(buf, bitpos, 20);
    np->node_id     = bp_read(buf, bitpos, 20);
    np->status      = (uint8_t)bp_read(buf, bitpos, 8);
    np->num_devices = (uint8_t)bp_read(buf, bitpos, 8);
}

siap_result_t siap_encode_dmi(uint8_t *buf, size_t *bitpos, const siap_dmi_t *dmi)
{
    /* 위반 케이스 6·7 — 인코딩 쪽도 디코딩과 동일 기준으로 거부한다
       (SIAP 메시지 명세서 §10.4 F-047: 한쪽만 막으면 판정 기준이 무너진다). */
    if (dmi->value_type > SIAP_VALUE_TYPE_FLOAT)
        return (siap_result_t){ false, SIAP_RSC_INVALID_DATA_TYPE, SIAP_CLAUSE_TABLE_7_14 };
    if (!siap_subtype_valid(dmi->subtype))
        return (siap_result_t){ false, SIAP_RSC_INVALID_DATA_SUBTYPE, SIAP_CLAUSE_TABLE_7_14 };

    bool ok = bp_write(buf, bitpos, dmi->device_id, 8)
           && bp_write(buf, bitpos, dmi->dev_type, 1)
           && bp_write(buf, bitpos, dmi->subtype, 8)
           && bp_write(buf, bitpos, dmi->value_type, 2)
           && bp_write(buf, bitpos, 0, 5)              /* Reserved — 송신 시 0 (표 7-14) */
           && bp_write(buf, bitpos, dmi->value, 32);
    if (!ok) return (siap_result_t){ false, SIAP_RSC_INVALID_FORMAT, SIAP_CLAUSE_7_3_1 };
    return (siap_result_t){ true, SIAP_RSC_SUCCESS, SIAP_CLAUSE_NONE };
}

siap_result_t siap_decode_dmi(const uint8_t *buf, size_t *bitpos, siap_dmi_t *dmi)
{
    dmi->device_id  = (uint8_t)bp_read(buf, bitpos, 8);
    dmi->dev_type   = (uint8_t)bp_read(buf, bitpos, 1);
    dmi->subtype    = (uint8_t)bp_read(buf, bitpos, 8);
    dmi->value_type = (uint8_t)bp_read(buf, bitpos, 2);
    (void)bp_read(buf, bitpos, 5);                      /* Reserved — 수신 시 무시 */
    dmi->value      = bp_read(buf, bitpos, 32);

    /* 순서가 결과에 영향을 준다: 위반 케이스 6(Value Type=RESERVED)과 7(미등록
       Subtype)이 같은 요소에 동시에 있을 수는 없지만(값 하나만 조작), Value
       Type을 먼저 판정한다 — SIAP 메시지 명세서 §10.4 F-047. */
    if (dmi->value_type == SIAP_VALUE_TYPE_RESERVED)
        return (siap_result_t){ false, SIAP_RSC_INVALID_DATA_TYPE, SIAP_CLAUSE_TABLE_7_14 };
    if (!siap_subtype_valid(dmi->subtype))
        return (siap_result_t){ false, SIAP_RSC_INVALID_DATA_SUBTYPE, SIAP_CLAUSE_TABLE_7_14 };
    return (siap_result_t){ true, SIAP_RSC_SUCCESS, SIAP_CLAUSE_NONE };
}

siap_result_t siap_encode_dp(uint8_t *buf, size_t *bitpos, const siap_dp_t *dp)
{
    /* F-127 — 표 7-15 Transfer Mode(0x03)·Status(0x03~0xFF)는 Reserved.
       main(DMI) 인코딩보다 먼저 검사해, 실패 시 main 의 7byte 도 쓰지 않는다
       (요소 전체가 all-or-nothing). */
    if (!siap_transfer_mode_valid(dp->transfer_mode))
        return (siap_result_t){ false, SIAP_RSC_INVALID_FORMAT, SIAP_CLAUSE_7_3_1 };
    if (!siap_status_valid(dp->status))
        return (siap_result_t){ false, SIAP_RSC_INVALID_FORMAT, SIAP_CLAUSE_7_3_1 };

    siap_result_t r = siap_encode_dmi(buf, bitpos, &dp->main);
    if (!r.ok) return r;
    bool ok = bp_write(buf, bitpos, dp->transfer_mode, 2)
           && bp_write(buf, bitpos, dp->period, 14)
           && bp_write(buf, bitpos, dp->lower_value, 32)
           && bp_write(buf, bitpos, dp->upper_value, 32)
           && bp_write(buf, bitpos, dp->lower_limit, 32)
           && bp_write(buf, bitpos, dp->upper_limit, 32)
           && bp_write(buf, bitpos, dp->precision, 32)
           && bp_write(buf, bitpos, dp->status, 8);
    if (!ok) return (siap_result_t){ false, SIAP_RSC_INVALID_FORMAT, SIAP_CLAUSE_7_3_1 };
    return r;
}

siap_result_t siap_decode_dp(const uint8_t *buf, size_t *bitpos, siap_dp_t *dp)
{
    siap_result_t r = siap_decode_dmi(buf, bitpos, &dp->main);
    if (!r.ok) {
        /* main 이 위반이어도 나머지 184bit(23byte)는 그대로 소비한다 — 그래야
           *bitpos 가 30byte 요소 경계에 정확히 맞고, 다음 요소/DRAIN 계산이
           어긋나지 않는다. 값 자체는 이 요소를 버릴 것이므로 의미가 없다. */
        (void)bp_read(buf, bitpos, 2);  (void)bp_read(buf, bitpos, 14);
        (void)bp_read(buf, bitpos, 32); (void)bp_read(buf, bitpos, 32);
        (void)bp_read(buf, bitpos, 32); (void)bp_read(buf, bitpos, 32);
        (void)bp_read(buf, bitpos, 32); (void)bp_read(buf, bitpos, 8);
        return r;
    }
    dp->transfer_mode = (uint8_t)bp_read(buf, bitpos, 2);
    dp->period        = (uint16_t)bp_read(buf, bitpos, 14);
    dp->lower_value   = bp_read(buf, bitpos, 32);
    dp->upper_value   = bp_read(buf, bitpos, 32);
    dp->lower_limit   = bp_read(buf, bitpos, 32);
    dp->upper_limit   = bp_read(buf, bitpos, 32);
    dp->precision     = bp_read(buf, bitpos, 32);
    dp->status        = (uint8_t)bp_read(buf, bitpos, 8);
    /* F-127 — 표 7-15 Transfer Mode(0x03)·Status(0x03~0xFF)는 Reserved.
       30byte 를 전부 읽은 뒤 판정한다 — 요소는 자기완결적이고 고정폭이므로
       (§5.6) 실패해도 *bitpos 는 이미 정확한 요소 경계에 있다. */
    if (!siap_transfer_mode_valid(dp->transfer_mode))
        return (siap_result_t){ false, SIAP_RSC_INVALID_FORMAT, SIAP_CLAUSE_7_3_1 };
    if (!siap_status_valid(dp->status))
        return (siap_result_t){ false, SIAP_RSC_INVALID_FORMAT, SIAP_CLAUSE_7_3_1 };
    return r;
}

bool siap_encode_mcp(uint8_t *buf, size_t *bitpos, const siap_mcp_t *mcp)
{
    return bp_write(buf, bitpos, mcp->recv_timeout, 16)
        && bp_write(buf, bitpos, mcp->num_retry, 8)
        && bp_write(buf, bitpos, mcp->noti_error_interval, 16)
        && bp_write(buf, bitpos, mcp->keep_alive_interval, 16);
}

void siap_decode_mcp(const uint8_t *buf, size_t *bitpos, siap_mcp_t *mcp)
{
    mcp->recv_timeout         = (uint16_t)bp_read(buf, bitpos, 16);
    mcp->num_retry            = (uint8_t)bp_read(buf, bitpos, 8);
    mcp->noti_error_interval  = (uint16_t)bp_read(buf, bitpos, 16);
    mcp->keep_alive_interval  = (uint16_t)bp_read(buf, bitpos, 16);
}

/* ═══════════════════════════════════════════════════════════════
 *  3. 수신 스트리밍 상태 머신 — 펌웨어 설계서 §5.1/§5.7
 * ═══════════════════════════════════════════════════════════════ */

/* 재동기 4조건 (펌웨어 설계서 §5.7). Node ID 는 포함하지 않는다 — core/ 는
   "내 주소"를 모르므로 순수 구조적 유효성만 본다. */
static bool resync_check(const uint8_t *hdrbuf, siap_mode_t mode,
                          siap_hdr_t *out_h, siap_kind_t *out_k, int32_t *out_n)
{
    size_t bp = 0;
    siap_hdr_t h;
    siap_decode_hdr(hdrbuf, &bp, &h);
    if (h.version != SIAP_VERSION) return false;                 /* (a) */
    if (!siap_trans_type_valid(h.trans_type)) return false;      /* (c) */
    siap_clause_t cl;
    siap_kind_t k = siap_resolve_kind(h.msg_type, h.payload_len, mode, &cl); /* (b) */
    if (k == SIAP_KIND_NONE) return false;
    int32_t n = siap_element_count(k, h.payload_len);             /* (d) */
    if (n < 0) return false;
    *out_h = h; *out_k = k; *out_n = n;
    return true;
}

/* 위반 프레임의 잔여 payload 를 폐기 상태로 넘긴다. remaining==0 이면 버릴
   것이 없으므로 바로 다음 헤더 대기로 간다 (X01/X02/X04/X05 처럼
   payload_len=0인 위반이 대부분이다 — 헤더만으로 끝나는 메시지가 많아서). */
static void begin_drain(siap_dec_t *d, uint16_t remaining)
{
    d->buf_len = 0;
    d->resync = true;   /* §5.7 — 위반 후에는 항상 재동기 모드로 */
    if (remaining == 0) {
        d->state = SIAP_DEC_ST_HDR;
    } else {
        d->state = SIAP_DEC_ST_DRAIN;
        d->drain_remaining = remaining;
    }
}

/* F-127 — 고정부 안에 RSC/NODE_PROPERTY 가 있는지는 opaque byte 크기만으로는
   판정할 수 없다(예: RSC+MCP 도 우연히 8byte). 종류로 직접 식별한다. */
static bool _kind_has_leading_rsc(siap_kind_t k)
{
    switch (k) {
    case SIAP_RES_SET_CONNECTION: case SIAP_RES_SET_DEVICE_INIT:
    case SIAP_RES_SET_DEVICE_INIT_ALL: case SIAP_RES_SET_NODE_PROPERTY:
    case SIAP_RES_SET_DEVICE_PROPERTY: case SIAP_RES_SET_NODE_DEVICE_PROPERTY_ALL:
    case SIAP_RES_SET_MSG_FLOW_CONTROL_PROFILE: case SIAP_RES_GET_NODE_PROPERTY:
    case SIAP_RES_GET_DEVICE_PROPERTY: case SIAP_RES_GET_NODE_DEVICE_PROPERTY_ALL:
    case SIAP_RES_GET_DEVICE_VALUE: case SIAP_RES_GET_MSG_FLOW_CONTROL_PROFILE:
    case SIAP_RES_SET_DEVICE_CONTROL: case SIAP_RES_SET_REBOOT:
        return true;
    default:
        return false;
    }
}

/* 고정부에서 NODE_PROPERTY(8byte)가 시작하는 byte 오프셋. 없으면 -1.
   RSC(1byte)가 앞에 오면 그만큼 밀린다 — RSC 는 항상 NP 보다 앞이다(7.2). */
static int _np_offset_in_fixed(siap_kind_t k)
{
    switch (k) {
    case SIAP_REQ_SET_NODE_PROPERTY:
    case SIAP_REQ_SET_NODE_DEVICE_PROPERTY_ALL:
        return 0;
    case SIAP_RES_SET_CONNECTION:
    case SIAP_RES_GET_NODE_PROPERTY:
    case SIAP_RES_GET_NODE_DEVICE_PROPERTY_ALL:
        return (int)SIAP_RSC_BYTES;
    default:
        return -1;
    }
}

static void handle_header_complete(siap_dec_t *d)
{
    siap_hdr_t h;
    siap_kind_t k;
    int32_t n;

    if (d->resync) {
        if (!resync_check(d->buf, d->mode, &h, &k, &n)) {
            /* 4조건 불만족 — 1byte 슬라이딩. 위반으로 보고하지 않는다(잡음
               구간을 스캔 중일 뿐이다). */
            for (size_t i = 0; i < SIAP_HEADER_BYTES - 1u; i++) {
                d->buf[i] = d->buf[i + 1u];
            }
            d->buf_len = SIAP_HEADER_BYTES - 1;
            return;
        }
        /* 통과 — 이제부터는 정상 경로와 동일하게 처리한다 (resync 는 아래에서 해제). */
    } else {
        size_t bp = 0;
        siap_decode_hdr(d->buf, &bp, &h);

        /* F-141 — 아래 다섯 위반은 전부 "헤더 자체가 위반"인 경우다. 이 헤더의
           payload_len 은 아직 어떤 구조로도 확인되지 않았으므로(잡음·손상
           바이트가 우연히 헤더 형태로 보인 것일 수도 있다) 그 값만큼
           `S_DRAIN` 으로 선폐기하면 안 된다 — 잡음이 아니라 마침 뒤따라온
           정상 프레임을 삼켜 버린다(재현: Version=0x99, payload_len=12 뒤에
           정상 ACK 12byte). `begin_drain(d, 0)` 은 아무것도 버리지 않고 바로
           §5.7 의 1byte 슬라이딩 재동기로 넘어간다. 이는 이미 구조가
           확인된 뒤(S_FIXED/S_ELEM 이후) 잔여를 payload_len 만큼 정확히
           버리는 것과는 다른 경우다 — 그쪽은 그대로 둔다. */
        if (h.version != SIAP_VERSION) {                          /* 위반 1 */
            begin_drain(d, 0);
            d->sink.on_end(d->sink.ctx, SIAP_RSC_INVALID_VERSION, SIAP_CLAUSE_7_3_1);
            return;
        }
        siap_clause_t cl;
        k = siap_resolve_kind(h.msg_type, h.payload_len, d->mode, &cl);
        if (k == SIAP_KIND_NONE) {                                 /* 위반 3(다중 후보 전부 실패)·4 */
            begin_drain(d, 0);                                     /* F-141 */
            d->sink.on_end(d->sink.ctx, SIAP_RSC_INVALID_FORMAT, cl);
            return;
        }
        /* B02(F-116/F-119) — 단일 후보 코드는 resolve_kind() 가 element_count
           를 보지 않고 확정하므로(Python 원본과 동일), 그 유효성은 여기서
           별도로 확인해야 한다. 고정부 없이 가변부만 있는 메시지의 N=0 이
           바로 이 경로로 걸린다(Frame 구조 명세서 §4.1, 7.3.1). */
        n = siap_element_count(k, h.payload_len);
        if (n < 0) {                                                /* 위반 3(단일 후보, B02 류) */
            begin_drain(d, 0);                                     /* F-141 */
            d->sink.on_end(d->sink.ctx, SIAP_RSC_INVALID_FORMAT, SIAP_CLAUSE_7_3_1);
            return;
        }
        if (!siap_trans_type_valid(h.trans_type)) {                /* 위반 5 */
            begin_drain(d, 0);                                     /* F-141 */
            d->sink.on_end(d->sink.ctx, SIAP_RSC_INVALID_TRANSMISSION_TYPE, SIAP_CLAUSE_TABLE_7_6);
            return;
        }
        /* n 은 위에서 이미 구했다(resync 분기는 resync_check() 안에서 같은
           일을 한다) — 여기서 다시 계산하지 않는다. */
    }

    d->resync = false;
    d->buf_len = 0;

    /* 위반 2(미등록 Node ID) 는 여기서 콜백으로 위임한다 — core/ 는 "내
       주소"를 모른다(node_state.c 의 몫). 콜백이 -(rsc) 를 돌려주면 거부.
       F-141 — 이 시점에는 Version·resolve_kind·element_count·Transmission
       Type 4조건이 전부 통과해 h.payload_len 이 구조적으로 검증된
       뒤이지만, "헤더 위반은 payload_len 을 신뢰하지 않는다"는 규칙을
       위반 종류로 나누지 않고 5종 전부 동일하게 적용한다 — 검증·추론이
       더 단순하고, 놓치는 낮은 확률의 프레임 하나를 아끼려고 재동기
       로직을 두 갈래로 쪼개는 비용이 더 크다. */
    int8_t hr = d->sink.on_header(d->sink.ctx, &h, k, (uint16_t)n);
    if (hr < 0) {
        begin_drain(d, 0);                                         /* F-141 */
        d->sink.on_end(d->sink.ctx, (siap_rsc_t)(-hr), SIAP_CLAUSE_7_3_1);
        return;
    }

    d->kind      = k;
    d->n         = (uint16_t)n;
    d->fixed_len = SIAP_LAYOUT[k].fixed;
    d->elem_len  = SIAP_LAYOUT[k].elem;
    d->elem_i    = 0;

    if (d->fixed_len > 0) {
        d->state = SIAP_DEC_ST_FIXED;
    } else if (d->elem_len > 0 && d->n > 0) {
        d->state = SIAP_DEC_ST_ELEM;
    } else {
        d->state = SIAP_DEC_ST_HDR;   /* 페이로드 없음 — 즉시 성공 종료 */
        d->sink.on_end(d->sink.ctx, SIAP_RSC_SUCCESS, SIAP_CLAUSE_NONE);
    }
}

void siap_dec_init(siap_dec_t *d, siap_sink_t sink, siap_mode_t mode)
{
    d->sink = sink;
    d->mode = mode;
    d->buf_len = 0;
    d->state = SIAP_DEC_ST_HDR;
    d->resync = false;   /* 최초 진입은 정상 정렬을 가정한다 (§5.7 트리거 미발생) */
    d->kind = SIAP_KIND_NONE;
    d->n = 0;
    d->fixed_len = 0;
    d->elem_len = 0;
    d->elem_i = 0;
    d->drain_remaining = 0;
}

void siap_dec_feed(siap_dec_t *d, uint8_t byte)
{
    switch (d->state) {
    case SIAP_DEC_ST_HDR:
        d->buf[d->buf_len++] = byte;
        if (d->buf_len == SIAP_HEADER_BYTES) handle_header_complete(d);
        break;

    case SIAP_DEC_ST_FIXED:
        d->buf[d->buf_len++] = byte;
        if (d->buf_len == d->fixed_len) {
            uint8_t flen = d->buf_len;

            /* F-126 — COMBINED_PROPERTY 3종(REQ_SET_NODE_DEVICE_PROPERTY_ALL·
               RES_SET_CONNECTION·RES_GET_NODE_DEVICE_PROPERTY_ALL, 0943
               §7.3.3.4)은 디바이스 개수를 두 번 주장한다: 고정부
               NODE_PROPERTY.Num. of Devices(표 7-13)와 Payload Length 로
               역산한 N(표 7-16, DEVICE_PROPERTY 는 N*240bit). 이 조합은
               "고정부에 NODE_PROPERTY 가 있고(fixed_len>=NP_BYTES) 가변부가
               DEVICE_PROPERTY(elem_len==DP_BYTES)" 로만 식별되며, NP 는
               언제나 고정부의 마지막 8byte 이므로 그 마지막 byte 가 바로
               num_devices 다. 둘이 다르면 같은 프레임이 디바이스 수를
               동시에 두 값으로 주장하는 것이므로 7.3.1/INVALID_FORMAT 로
               거부한다 — on_fixed 콜백에 넘기기 전에 걸러야 한다(그 뒤로는
               "유효한 고정부"로 취급되기 때문). */
            if (d->elem_len == SIAP_DP_BYTES && d->fixed_len >= SIAP_NP_BYTES) {
                uint8_t num_devices = d->buf[d->fixed_len - 1];
                if (num_devices != (uint8_t)d->n) {
                    d->buf_len = 0;
                    uint16_t remaining = (uint16_t)(d->elem_len * d->n);
                    begin_drain(d, remaining);
                    d->sink.on_end(d->sink.ctx, SIAP_RSC_INVALID_FORMAT, SIAP_CLAUSE_7_3_1);
                    break;
                }
            }

            /* F-127 — 표 7-10(RSC)·표 7-12(NEC)·표 7-13(NODE_PROPERTY.Status)의
               예약값을 고정부 완료 시점에 거부한다. on_fixed 는 원시 바이트만
               받으므로 여기서 걸러야 한다 — F-126 과 같은 이유. */
            if (_kind_has_leading_rsc(d->kind) && !siap_rsc_valid(d->buf[0])) {
                d->buf_len = 0;
                uint16_t remaining = (uint16_t)(d->elem_len * d->n);
                begin_drain(d, remaining);
                d->sink.on_end(d->sink.ctx, SIAP_RSC_INVALID_FORMAT, SIAP_CLAUSE_7_3_1);
                break;
            }
            if (d->kind == SIAP_NOTI_ERROR && !siap_nec_valid(d->buf[0])) {
                d->buf_len = 0;
                begin_drain(d, 0);   /* NOTI_ERROR 는 가변부가 없다 */
                d->sink.on_end(d->sink.ctx, SIAP_RSC_INVALID_FORMAT, SIAP_CLAUSE_7_3_1);
                break;
            }
            {
                int np_off = _np_offset_in_fixed(d->kind);
                if (np_off >= 0 && !siap_status_valid(d->buf[np_off + 6])) {
                    d->buf_len = 0;
                    uint16_t remaining = (uint16_t)(d->elem_len * d->n);
                    begin_drain(d, remaining);
                    d->sink.on_end(d->sink.ctx, SIAP_RSC_INVALID_FORMAT, SIAP_CLAUSE_7_3_1);
                    break;
                }
            }

            int8_t fr = d->sink.on_fixed(d->sink.ctx, d->buf, flen);
            d->buf_len = 0;
            if (fr < 0) {
                uint16_t remaining = (uint16_t)(d->elem_len * d->n);
                begin_drain(d, remaining);
                d->sink.on_end(d->sink.ctx, (siap_rsc_t)(-fr), SIAP_CLAUSE_7_3_1);
                break;
            }
            if (d->elem_len > 0 && d->n > 0) {
                d->state = SIAP_DEC_ST_ELEM;
                d->elem_i = 0;
            } else {
                d->state = SIAP_DEC_ST_HDR;
                d->sink.on_end(d->sink.ctx, SIAP_RSC_SUCCESS, SIAP_CLAUSE_NONE);
            }
        }
        break;

    case SIAP_DEC_ST_ELEM:
        d->buf[d->buf_len++] = byte;
        if (d->buf_len == d->elem_len) {
            siap_result_t r = { true, SIAP_RSC_SUCCESS, SIAP_CLAUSE_NONE };
            /* 요소 크기로 내용을 구분한다 — DID_BYTES(1) 는 검증할 필드가 없고,
               DMI_BYTES(7)/DP_BYTES(30) 는 서로 다른 크기라 겹치지 않는다. */
            if (d->elem_len == SIAP_DMI_BYTES) {
                siap_dmi_t dmi; size_t bp = 0;
                r = siap_decode_dmi(d->buf, &bp, &dmi);
            } else if (d->elem_len == SIAP_DP_BYTES) {
                siap_dp_t dp; size_t bp = 0;
                r = siap_decode_dp(d->buf, &bp, &dp);
            }
            if (!r.ok) {                                            /* 위반 6·7 */
                uint16_t remaining = (uint16_t)(d->elem_len * (d->n - d->elem_i - 1));
                uint8_t elen = d->buf_len;
                d->buf_len = 0;
                (void)elen;
                begin_drain(d, remaining);
                d->sink.on_end(d->sink.ctx, r.rsc, r.clause);
                break;
            }
            uint8_t elen = d->buf_len;
            int8_t er = d->sink.on_element(d->sink.ctx, d->elem_i, d->buf, elen);
            d->buf_len = 0;
            if (er < 0) {
                uint16_t remaining = (uint16_t)(d->elem_len * (d->n - d->elem_i - 1));
                begin_drain(d, remaining);
                d->sink.on_end(d->sink.ctx, (siap_rsc_t)(-er), SIAP_CLAUSE_7_3_1);
                break;
            }
            d->elem_i++;
            if (d->elem_i == d->n) {
                d->state = SIAP_DEC_ST_HDR;
                d->sink.on_end(d->sink.ctx, SIAP_RSC_SUCCESS, SIAP_CLAUSE_NONE);
            }
        }
        break;

    case SIAP_DEC_ST_DRAIN:
        if (d->drain_remaining > 0) d->drain_remaining--;
        if (d->drain_remaining == 0) d->state = SIAP_DEC_ST_HDR;
        break;
    }
}

void siap_dec_on_gap(siap_dec_t *d)
{
    if (d->state == SIAP_DEC_ST_HDR) {
        d->resync = true;   /* 이미 모으던 바이트가 있으면 그대로 재동기 후보에 포함 */
    } else {
        /* 프레임 중간 침묵 — 불완전 프레임으로 보고 포기한다. */
        d->state = SIAP_DEC_ST_HDR;
        d->buf_len = 0;
        d->resync = true;
    }
}

/* ═══════════════════════════════════════════════════════════════
 *  4. 송신 — Payload Length 선산출 + 51byte 윈도우 (펌웨어 설계서 §5.8)
 * ═══════════════════════════════════════════════════════════════ */

/* F-123 — bp_write/siap_encode_* 는 버퍼 크기를 모른다(bitpack.c 의 4개
   함수 계약에 capacity 인자가 없다, CLAUDE.md §4.2). 그래서 각 진입점을
   부르기 *전에* 여기서 남은 용량을 확인해야 한다 — 쓰고 나서 bitpos 만
   되돌리는 방식은 이미 win[] 배열 밖에 발생한 메모리 쓰기 자체를 되돌리지
   못해 소용없다. siap_types.h 의 표준 유래 바이트 폭 상수(SIAP_*_BYTES)를
   그대로 재사용한다 — 폭을 여기 새로 정의하지 않는다(정본은 그쪽 하나). */
static bool _tx_has_room(const siap_enc_t *e, size_t need_bytes)
{
    return e->bitpos + (need_bytes * 8u) <= (size_t)SIAP_TX_WINDOW * 8u;
}

void siap_tx_reset(siap_enc_t *e)
{
    e->bitpos = 0;
    e->sent = 0;
}

bool siap_tx_put_hdr(siap_enc_t *e, const siap_hdr_t *h)
{
    if (!_tx_has_room(e, SIAP_HEADER_BYTES)) return false;
    return siap_encode_hdr(e->win, &e->bitpos, h);
}

bool siap_tx_put_rsc(siap_enc_t *e, siap_rsc_t rsc)
{
    if (!_tx_has_room(e, SIAP_RSC_BYTES)) return false;
    /* F-127 — 표 7-10 0x0A~0xFF 는 Reserved. 호출자가 enum 밖 값을 캐스팅해
       넘겨도 여기서 막는다. */
    if (!siap_rsc_valid((uint8_t)rsc)) return false;
    return bp_write(e->win, &e->bitpos, (uint32_t)rsc, 8);
}

bool siap_tx_put_nec(siap_enc_t *e, siap_nec_t nec)
{
    if (!_tx_has_room(e, SIAP_NEC_BYTES)) return false;
    /* F-127 — 표 7-12 0x0A~0xFF 는 Reserved. */
    if (!siap_nec_valid((uint8_t)nec)) return false;
    return bp_write(e->win, &e->bitpos, (uint32_t)nec, 8);
}

bool siap_tx_put_np(siap_enc_t *e, const siap_np_t *np)
{
    if (!_tx_has_room(e, SIAP_NP_BYTES)) return false;
    return siap_encode_np(e->win, &e->bitpos, np);
}

bool siap_tx_put_mcp(siap_enc_t *e, const siap_mcp_t *mcp)
{
    if (!_tx_has_room(e, SIAP_MCP_BYTES)) return false;
    return siap_encode_mcp(e->win, &e->bitpos, mcp);
}

bool siap_tx_put_device_id(siap_enc_t *e, uint8_t device_id)
{
    if (!_tx_has_room(e, SIAP_DID_BYTES)) return false;
    return bp_write(e->win, &e->bitpos, device_id, 8);
}

siap_result_t siap_tx_put_dmi(siap_enc_t *e, const siap_dmi_t *dmi)
{
    /* 용량 부족은 프레임 형식 위반이 아니라 호출자가 flush 없이 계속 쌓은
       내부 오류다 — 그래도 네트워크로 나가지 않는 siap_result_t 채널이므로
       기존 인코드 실패(bp_write 범위 초과)와 같은 코드를 재사용한다. 호출자는
       .ok 만 보고 flush 후 재시도해야 한다(펌웨어 설계서 §5.8). */
    if (!_tx_has_room(e, SIAP_DMI_BYTES))
        return (siap_result_t){ false, SIAP_RSC_INVALID_FORMAT, SIAP_CLAUSE_7_3_1 };
    return siap_encode_dmi(e->win, &e->bitpos, dmi);
}

siap_result_t siap_tx_put_dp(siap_enc_t *e, const siap_dp_t *dp)
{
    if (!_tx_has_room(e, SIAP_DP_BYTES))
        return (siap_result_t){ false, SIAP_RSC_INVALID_FORMAT, SIAP_CLAUSE_7_3_1 };
    return siap_encode_dp(e->win, &e->bitpos, dp);
}

siap_tx_status_t siap_tx_flush(siap_enc_t *e, siap_io_write_fn write, void *io_ctx)
{
    size_t total = e->bitpos / 8;
    while (e->sent < total) {
        size_t wrote = write(io_ctx, e->win + e->sent, total - e->sent);
        if (wrote == 0) return SIAP_TX_PENDING;   /* 논블로킹 — 나중에 다시 flush */
        e->sent += wrote;
    }
    e->bitpos = 0;
    e->sent = 0;
    return SIAP_TX_DONE;
}

bool siap_encode_ack(const siap_hdr_t *req, siap_mode_t mode, siap_enc_t *e)
{
    /* F-040 — msg_id·GCG ID·Node ID 를 원 요청에서 복사한다 (7.2.2). */
    siap_hdr_t h;
    h.version     = SIAP_VERSION;
    h.msg_type    = siap_wire_code(SIAP_ACK, mode);
    h.trans_type  = req->trans_type;
    h.msg_id      = req->msg_id;
    h.payload_len = 0;
    h.gcg_id      = req->gcg_id;
    h.node_id     = req->node_id;
    siap_tx_reset(e);
    return siap_tx_put_hdr(e, &h);
}
