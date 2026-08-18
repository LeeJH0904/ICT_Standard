/*
 * siap_frame.c/.h 호스트 유닛테스트..
 * element_count/resolve_kind, 구조체 인코드/디코드 왕복, 수신 스트리밍
 * 상태 머신, 재동기, 송신 윈도우를 검증한다.
 * 골든 52건 전량 왕복은 test_golden.c 의 몫이다 — 여기서는 코덱 내부
 * 분기를 독립적으로, 손으로 만든 값으로 확인한다.
 *
 * 실행: cd project_code/firmware/tests && make test_siap_frame && ./test_siap_frame
 * 종료 코드: 0 = 전부 통과, 1 = 실패 있음
 */
#include "../core/siap_frame.h"
#include <stdio.h>
#include <string.h>

static int g_total = 0;
static int g_passed = 0;

static void check(const char *name, int cond)
{
    g_total++;
    if (cond) g_passed++;
    printf("  %s  %s\n", cond ? "PASS" : "FAIL", name);
}

/* ═══════════════════════════════════════════════════════════════
 *  케이스 1 — element_count() : LAYOUT 을 그대로 대입해 손으로 기대값을 낸다
 * ═══════════════════════════════════════════════════════════════ */
static void case_element_count(void)
{
    /* REQ_SET_CONNECTION (0,0) — 페이로드 없음 메시지 */
    check("EC1: REQ_SET_CONNECTION plen=0 -> n=0",
          siap_element_count(SIAP_REQ_SET_CONNECTION, 0) == 0);
    check("EC1: REQ_SET_CONNECTION plen=1 -> 거부(-1)",
          siap_element_count(SIAP_REQ_SET_CONNECTION, 1) == -1);

    /* REQ_SET_DEVICE_INIT (0, 1byte요소) — 고정부 없이 가변부만 => N>=1 요구 */
    check("EC2: REQ_SET_DEVICE_INIT plen=0 -> 거부(가변부만인데 N=0)",
          siap_element_count(SIAP_REQ_SET_DEVICE_INIT, 0) == -1);
    check("EC2: REQ_SET_DEVICE_INIT plen=3 -> n=3",
          siap_element_count(SIAP_REQ_SET_DEVICE_INIT, 3) == 3);

    /* RES_SET_CONNECTION (9, 30byte요소) — 고정부 있음 => N=0 허용 */
    check("EC3: RES_SET_CONNECTION plen=9 -> n=0 (디바이스 0개 노드)",
          siap_element_count(SIAP_RES_SET_CONNECTION, 9) == 0);
    check("EC3: RES_SET_CONNECTION plen=39 -> n=1",
          siap_element_count(SIAP_RES_SET_CONNECTION, 39) == 1);
    check("EC3: RES_SET_CONNECTION plen=40 -> 거부(30의 배수 아님)",
          siap_element_count(SIAP_RES_SET_CONNECTION, 40) == -1);
    check("EC3: RES_SET_CONNECTION plen=8 -> 거부(고정부보다 짧음)",
          siap_element_count(SIAP_RES_SET_CONNECTION, 8) == -1);

    /* NOTI_ERROR / NOTI_DEVICE_VALUE — 0x0800 판별의 기반이 되는 두 계산 */
    check("EC4: NOTI_ERROR plen=1 -> n=0", siap_element_count(SIAP_NOTI_ERROR, 1) == 0);
    check("EC4: NOTI_DEVICE_VALUE plen=7 -> n=1", siap_element_count(SIAP_NOTI_DEVICE_VALUE, 7) == 1);
    check("EC4: NOTI_DEVICE_VALUE plen=24 -> 거부(7의 배수 아님)",
          siap_element_count(SIAP_NOTI_DEVICE_VALUE, 24) == -1);

    /* 노드당 디바이스 상한 N=16. 16은 허용,
       17은 거부 — 골든 B03(N=16 허용)·B11(N=17 거부)과 짝을 이룬다.
       결함 재현( 보고서)이 정확히 이 두 조합이었다: REQ_SET_DEVICE_CONTROL
       plen=119(N=17), RES_SET_CONNECTION plen=519(N=17). */
    check("EC5: REQ_SET_DEVICE_CONTROL plen=112(N=16) -> 허용",
          siap_element_count(SIAP_REQ_SET_DEVICE_CONTROL, 112) == 16);
    check("EC5: REQ_SET_DEVICE_CONTROL plen=119(N=17) -> 거부(상한 초과)",
          siap_element_count(SIAP_REQ_SET_DEVICE_CONTROL, 119) == -1);
    check("EC5: RES_SET_CONNECTION plen=489(N=16, B03) -> 허용",
          siap_element_count(SIAP_RES_SET_CONNECTION, 489) == 16);
    check("EC5: RES_SET_CONNECTION plen=519(N=17) -> 거부(상한 초과)",
          siap_element_count(SIAP_RES_SET_CONNECTION, 519) == -1);
}

/* ═══════════════════════════════════════════════════════════════
 *  케이스 2 — resolve_kind() : 0x0800 판별 + clause 구분(표 7-2 vs 7.3.1)
 * ═══════════════════════════════════════════════════════════════ */
static void case_resolve_kind(void)
{
    siap_clause_t cl;

    check("RK1: 0x0000/plen0 -> REQ_SET_CONNECTION",
          siap_resolve_kind(0x0000, 0, SIAP_MODE_STRICT, &cl) == SIAP_REQ_SET_CONNECTION);

    /*/B02 — 단일 후보 코드는 이 Payload Length 가 구조적으로 무효해도
       resolve_kind() 는 그대로 그 kind 를 확정한다(contracts/frame.py 원본과
       동일 구조 — 후보가 하나면 element_count() 를 보지 않는다). 무효성은
       "그다음에" 호출자가 별도로 element_count() 를 불러 판정한다. */
    siap_kind_t k1b = siap_resolve_kind(0x000C, 0, SIAP_MODE_STRICT, &cl);
    check("RK1b: 0x000C(REQ_SET_DEVICE_CONTROL)/plen0 -> 그래도 kind 는 확정된다(단일 후보)",
          k1b == SIAP_REQ_SET_DEVICE_CONTROL && cl == SIAP_CLAUSE_NONE);
    check("RK1b: 이어서 element_count() 를 부르면 거부된다 (B02 의 실제 판정 경로)",
          siap_element_count(SIAP_REQ_SET_DEVICE_CONTROL, 0) == -1);

    cl = SIAP_CLAUSE_NONE;
    siap_kind_t k = siap_resolve_kind(0x0800, 1, SIAP_MODE_STRICT, &cl);
    check("RK2: 0x0800/plen1 -> NOTI_ERROR", k == SIAP_NOTI_ERROR);
    check("RK2: 위반 없음 (clause=NONE)", cl == SIAP_CLAUSE_NONE);

    k = siap_resolve_kind(0x0800, 7, SIAP_MODE_STRICT, &cl);
    check("RK3: 0x0800/plen7 -> NOTI_DEVICE_VALUE", k == SIAP_NOTI_DEVICE_VALUE);

    /* 위반 3번 — 코드는 있는데 어느 후보의 N도 안 맞음(표준 원문 중복 코드) */
    k = siap_resolve_kind(0x0800, 24, SIAP_MODE_STRICT, &cl);
    check("RK4: 0x0800/plen24 -> 해석 불가", k == SIAP_KIND_NONE);
    check("RK4: clause=7.3.1 (Payload Length 형식)", cl == SIAP_CLAUSE_7_3_1);

    /* 위반 4번 — 코드 자체가 미정의(0x000E, Reserved) */
    k = siap_resolve_kind(0x000E, 0, SIAP_MODE_STRICT, &cl);
    check("RK5: 0x000E -> 해석 불가", k == SIAP_KIND_NONE);
    check("RK5: clause=표 7-2 (미정의 Message Type)", cl == SIAP_CLAUSE_TABLE_7_2);

    /* strict/extended 분기 — 0x0801 의 의미가 모드에 따라 다르다  */
    k = siap_resolve_kind(0x0801, 0, SIAP_MODE_STRICT, &cl);
    check("RK6: strict 0x0801/plen0 -> NOTI_DISCONNECT", k == SIAP_NOTI_DISCONNECT);

    /* 처리 중 발견 — 0x0801 은 extended 모드에서 단일 후보(NOTI_DEVICE_VALUE)
       이므로 resolve_kind() 는 element_count() 와 무관하게 그 후보를 그대로
       확정한다(contracts/frame.py 원본과 동일 — 후보가 하나면 N 유효성은
       별도 element_count() 호출로 판정한다, B02 와 같은 구조). plen=0 이
       구조적으로 무효라는 사실은 resolve_kind() 가 아니라 별도의
       element_count() 호출로 드러나야 한다. */
    k = siap_resolve_kind(0x0801, 0, SIAP_MODE_EXTENDED, &cl);
    check("RK6: extended 0x0801/plen0 -> NOTI_DEVICE_VALUE (단일 후보, element_count 무관하게 확정)",
          k == SIAP_NOTI_DEVICE_VALUE);
    check("RK6: 위 kind 로 element_count(.,0) 을 별도로 부르면 거부된다 (가변부만 있는 메시지 N>=1)",
          siap_element_count(SIAP_NOTI_DEVICE_VALUE, 0) == -1);

    k = siap_resolve_kind(0x0801, 7, SIAP_MODE_EXTENDED, &cl);
    check("RK6: extended 0x0801/plen7 -> NOTI_DEVICE_VALUE", k == SIAP_NOTI_DEVICE_VALUE);
}

/* ═══════════════════════════════════════════════════════════════
 *  케이스 3 — 구조체 인코드/디코드 왕복
 * ═══════════════════════════════════════════════════════════════ */
static void case_struct_roundtrip(void)
{
    uint8_t buf[64] = {0};
    size_t bp;

    /* 헤더 */
    siap_hdr_t h = { SIAP_VERSION, 0x0003, SIAP_TRANS_UNICAST, 0x1234, 0x0008, 0x00001, 0x00003 };
    bp = 0;
    bool ok = siap_encode_hdr(buf, &bp, &h);
    check("ST1: 헤더 인코드 성공 + bitpos==96", ok && bp == 96);
    siap_hdr_t h2; bp = 0;
    siap_decode_hdr(buf, &bp, &h2);
    check("ST1: 헤더 왕복 일치",
          h2.version == h.version && h2.msg_type == h.msg_type && h2.trans_type == h.trans_type
          && h2.msg_id == h.msg_id && h2.payload_len == h.payload_len
          && h2.gcg_id == h.gcg_id && h2.node_id == h.node_id);

    /* NODE_PROPERTY */
    siap_np_t np = { 0x10, 0x00001, 0x00003, SIAP_STATUS_NORMAL, 2 };
    bp = 0; ok = siap_encode_np(buf, &bp, &np);
    check("ST2: NODE_PROPERTY 인코드 성공 + 64bit", ok && bp == 64);
    siap_np_t np2; bp = 0; siap_decode_np(buf, &bp, &np2);
    check("ST2: NODE_PROPERTY 왕복 일치",
          np2.sw_version == np.sw_version && np2.gcg_id == np.gcg_id && np2.node_id == np.node_id
          && np2.status == np.status && np2.num_devices == np.num_devices);

    /* DEVICE_MAIN_INFO — FLOAT 25.3 (0x41CA6666) */
    siap_dmi_t dmi = { 0x01, SIAP_DEV_SENSOR, SIAP_SUBTYPE_TEMPERATURE, SIAP_VALUE_TYPE_FLOAT,
                       siap_raw_from_float(25.3f) };
    bp = 0; siap_result_t r = siap_encode_dmi(buf, &bp, &dmi);
    check("ST3: DMI 인코드 성공 + 56bit", r.ok && bp == 56);
    check("ST3: FLOAT 25.3 -> 0x41CA6666 (IEEE-754 single, big-endian)",
          buf[3] == 0x41 && buf[4] == 0xCA && buf[5] == 0x66 && buf[6] == 0x66);
    siap_dmi_t dmi2; bp = 0; r = siap_decode_dmi(buf, &bp, &dmi2);
    check("ST3: DMI 왕복 성공", r.ok);
    check("ST3: DMI 왕복 값 일치",
          dmi2.device_id == dmi.device_id && dmi2.dev_type == dmi.dev_type
          && dmi2.subtype == dmi.subtype && dmi2.value_type == dmi.value_type);
    check("ST3: FLOAT 값 자체 왕복", siap_value_as_float(dmi2.value) == 25.3f);

    /* DEVICE_MAIN_INFO — INT 음수 (2의 보수 왕복) */
    siap_dmi_t dmi_int = { 0x02, SIAP_DEV_ACTUATOR, SIAP_SUBTYPE_IRRIGATION_VALVE,
                            SIAP_VALUE_TYPE_INT, siap_raw_from_int(-1) };
    bp = 0; r = siap_encode_dmi(buf, &bp, &dmi_int);
    siap_dmi_t dmi_int2; bp = 0; r = siap_decode_dmi(buf, &bp, &dmi_int2);
    check("ST4: INT -1 -> 0xFFFFFFFF 왕복", r.ok && siap_value_as_int(dmi_int2.value) == -1);

    /* DEVICE_PROPERTY — main(DMI) + 8필드, 240bit */
    siap_dp_t dp = { dmi, SIAP_TM_PERIODIC, 60, siap_raw_from_float(-40.0f),
                      siap_raw_from_float(80.0f), siap_raw_from_float(-40.0f),
                      siap_raw_from_float(80.0f), siap_raw_from_float(0.1f), SIAP_STATUS_NORMAL };
    bp = 0; r = siap_encode_dp(buf, &bp, &dp);
    check("ST5: DEVICE_PROPERTY 인코드 성공 + 240bit", r.ok && bp == 240);
    siap_dp_t dp2; bp = 0; r = siap_decode_dp(buf, &bp, &dp2);
    check("ST5: DEVICE_PROPERTY 왕복 성공", r.ok);
    check("ST5: Period(14bit) 왕복", dp2.period == dp.period);
    check("ST5: Precision(FLOAT USER DEPENDENT) 왕복", siap_value_as_float(dp2.precision) == 0.1f);

    /* MSG_CONTROL_PROFILE */
    siap_mcp_t mcp = { 2000, 3, 30, 60 };
    bp = 0; ok = siap_encode_mcp(buf, &bp, &mcp);
    check("ST6: MSG_CONTROL_PROFILE 인코드 성공 + 56bit", ok && bp == 56);
    siap_mcp_t mcp2; bp = 0; siap_decode_mcp(buf, &bp, &mcp2);
    check("ST6: MSG_CONTROL_PROFILE 왕복 일치",
          mcp2.recv_timeout == mcp.recv_timeout && mcp2.num_retry == mcp.num_retry
          && mcp2.noti_error_interval == mcp.noti_error_interval
          && mcp2.keep_alive_interval == mcp.keep_alive_interval);

    /* 위반 케이스 6·7 — 디코더뿐 아니라 인코더도 같은 기준으로 거부한다 */
    siap_dmi_t bad_vt = { 0x01, SIAP_DEV_SENSOR, SIAP_SUBTYPE_TEMPERATURE,
                           SIAP_VALUE_TYPE_RESERVED, 0 };
    bp = 0; r = siap_encode_dmi(buf, &bp, &bad_vt);
    check("ST7: Value Type=RESERVED 인코드 거부", !r.ok && r.rsc == SIAP_RSC_INVALID_DATA_TYPE
                                                       && r.clause == SIAP_CLAUSE_TABLE_7_14);
    siap_dmi_t bad_st = { 0x01, SIAP_DEV_SENSOR, 0x40 /* 미등록 */, SIAP_VALUE_TYPE_UINT, 0 };
    bp = 0; r = siap_encode_dmi(buf, &bp, &bad_st);
    check("ST8: 미등록 Subtype(0x40) 인코드 거부", !r.ok && r.rsc == SIAP_RSC_INVALID_DATA_SUBTYPE
                                                        && r.clause == SIAP_CLAUSE_TABLE_7_14);

    /* 표 7-10/7-12/7-13/7-15의 예약값 4종. 인코더도 같은 기준으로
       거부해야 한다(디코더만 막으면과 같은 구멍이 남는다). */
    siap_np_t bad_np = { 0x10, 0x00001, 0x00003, 0x03 /* RESERVED */, 2 };
    bp = 0; ok = siap_encode_np(buf, &bp, &bad_np);
    check("ST9: NODE_PROPERTY.Status=RESERVED(0x03) 인코드 거부", !ok);

    siap_dp_t bad_dp_tm = { dmi, 0x03 /* RESERVED Transfer Mode */, 60, siap_raw_from_float(-40.0f),
                             siap_raw_from_float(80.0f), siap_raw_from_float(-40.0f),
                             siap_raw_from_float(80.0f), siap_raw_from_float(0.1f), SIAP_STATUS_NORMAL };
    bp = 0; r = siap_encode_dp(buf, &bp, &bad_dp_tm);
    check("ST10: DEVICE_PROPERTY.Transfer Mode=RESERVED(0x03) 인코드 거부",
          !r.ok && r.rsc == SIAP_RSC_INVALID_FORMAT && r.clause == SIAP_CLAUSE_7_3_1);

    siap_dp_t bad_dp_st = { dmi, SIAP_TM_PERIODIC, 60, siap_raw_from_float(-40.0f),
                             siap_raw_from_float(80.0f), siap_raw_from_float(-40.0f),
                             siap_raw_from_float(80.0f), siap_raw_from_float(0.1f), 0x03 /* RESERVED Status */ };
    bp = 0; r = siap_encode_dp(buf, &bp, &bad_dp_st);
    check("ST11: DEVICE_PROPERTY.Status=RESERVED(0x03) 인코드 거부",
          !r.ok && r.rsc == SIAP_RSC_INVALID_FORMAT && r.clause == SIAP_CLAUSE_7_3_1);

    siap_enc_t e_rsc; siap_tx_reset(&e_rsc);
    bool rsc_ok = siap_tx_put_rsc(&e_rsc, (siap_rsc_t)0x0A);
    check("ST12: RSC=0x0A(Reserved) put 거부, bitpos 불변", !rsc_ok && e_rsc.bitpos == 0);

    siap_enc_t e_nec; siap_tx_reset(&e_nec);
    bool nec_ok = siap_tx_put_nec(&e_nec, (siap_nec_t)0x0A);
    check("ST13: NEC=0x0A(Reserved) put 거부, bitpos 불변", !nec_ok && e_nec.bitpos == 0);
}

/* ═══════════════════════════════════════════════════════════════
 *  케이스 4 — 수신 스트리밍 상태 머신
 * ═══════════════════════════════════════════════════════════════ */
typedef struct {
    int header_calls, fixed_calls, elem_calls, end_calls;
    siap_hdr_t last_hdr;
    siap_kind_t last_kind;
    uint16_t last_n;
    uint8_t fixed_buf[16]; uint8_t fixed_len;
    uint8_t elem_bufs[16][32]; uint8_t elem_lens[16]; uint16_t elem_seen;
    siap_rsc_t end_rsc;
    siap_clause_t end_clause;
    uint32_t expect_node_id;   /* 0 이면 검사하지 않는다 */
} test_ctx_t;

static int8_t cb_on_header(void *ctx, const siap_hdr_t *h, siap_kind_t k, uint16_t n)
{
    test_ctx_t *c = (test_ctx_t *)ctx;
    c->header_calls++;
    c->last_hdr = *h; c->last_kind = k; c->last_n = n;
    /* core/ 는 "내 Node ID"를 모른다 — 그 판단은 node_state 의 몫이라는 설계를
       그대로 흉내낸다 (siap_frame.c 상단 주석 참조). */
    if (c->expect_node_id != 0 && h->node_id != c->expect_node_id)
        return -(int8_t)SIAP_RSC_INVALID_NODE_ID;
    return 0;
}
static int8_t cb_on_fixed(void *ctx, const uint8_t *buf, uint8_t len)
{
    test_ctx_t *c = (test_ctx_t *)ctx;
    c->fixed_calls++;
    c->fixed_len = len;
    memcpy(c->fixed_buf, buf, len);
    return 0;
}
static int8_t cb_on_element(void *ctx, uint16_t i, const uint8_t *buf, uint8_t len)
{
    test_ctx_t *c = (test_ctx_t *)ctx;
    c->elem_calls++;
    if (i < 16) { memcpy(c->elem_bufs[i], buf, len); c->elem_lens[i] = len; }
    c->elem_seen++;
    return 0;
}
static void cb_on_end(void *ctx, siap_rsc_t rsc, siap_clause_t clause)
{
    test_ctx_t *c = (test_ctx_t *)ctx;
    c->end_calls++;
    c->end_rsc = rsc;
    c->end_clause = clause;
}

static siap_sink_t make_sink(test_ctx_t *c)
{
    siap_sink_t s;
    s.on_header = cb_on_header;
    s.on_fixed = cb_on_fixed;
    s.on_element = cb_on_element;
    s.on_end = cb_on_end;
    s.ctx = c;
    return s;
}

static void feed_bytes(siap_dec_t *d, const uint8_t *buf, size_t len)
{
    for (size_t i = 0; i < len; i++) siap_dec_feed(d, buf[i]);
}

/* siap_encode_hdr 는 SIAP_WUR — 반환값을 실제로 확인해야 (void) 캐스팅으로
   빠져나갈 수 없다(과 같은 원칙). 테스트 셋업에서 반복 호출되므로
   호출 자체를 통과 항목 하나로 세어 묻어간다. */
static void enc_hdr_ok(const char *label, uint8_t *buf, size_t *bp, const siap_hdr_t *h)
{
    check(label, siap_encode_hdr(buf, bp, h));
}

/* 헤더뿐인 메시지(ACK) 전체 왕복 — S_HDR 에서 바로 S_DONE 으로 가는 경로 */
static void case_stream_header_only(void)
{
    siap_hdr_t h = { SIAP_VERSION, siap_wire_code(SIAP_ACK, SIAP_MODE_STRICT),
                      SIAP_TRANS_UNICAST, 42, 0, 0x00001, 0x00003 };
    uint8_t buf[12]; size_t bp = 0;
    check("SM1: ACK 헤더 인코드 성공", siap_encode_hdr(buf, &bp, &h));

    test_ctx_t c = {0}; c.expect_node_id = 3;
    siap_dec_t d; siap_dec_init(&d, make_sink(&c), SIAP_MODE_STRICT);
    feed_bytes(&d, buf, 12);

    check("SM1: on_header 1회", c.header_calls == 1);
    check("SM1: kind==ACK", c.last_kind == SIAP_ACK);
    check("SM1: n==0", c.last_n == 0);
    check("SM1: on_fixed/on_element 없음", c.fixed_calls == 0 && c.elem_calls == 0);
    check("SM1: on_end SUCCESS", c.end_calls == 1 && c.end_rsc == SIAP_RSC_SUCCESS);
}

/* 고정부+요소 1개(RES_SET_CONNECTION, N=1) — S_HDR -> S_FIXED -> S_ELEM -> S_DONE */
static void case_stream_fixed_and_element(void)
{
    siap_dmi_t main_ = { 0x05, SIAP_DEV_SENSOR, SIAP_SUBTYPE_HUMIDITY, SIAP_VALUE_TYPE_FLOAT,
                          siap_raw_from_float(61.0f) };
    siap_dp_t dp = { main_, SIAP_TM_EVENT, 30, siap_raw_from_float(0.0f), siap_raw_from_float(100.0f),
                      siap_raw_from_float(0.0f), siap_raw_from_float(100.0f), siap_raw_from_float(0.1f),
                      SIAP_STATUS_NORMAL };
    uint16_t plen = (uint16_t)(SIAP_RSC_BYTES + SIAP_NP_BYTES + SIAP_DP_BYTES); /* 9 + 30 = 39 */
    siap_hdr_t h = { SIAP_VERSION, siap_wire_code(SIAP_RES_SET_CONNECTION, SIAP_MODE_STRICT),
                      SIAP_TRANS_UNICAST, 7, plen, 0x00001, 0x00003 };

    uint8_t buf[64]; size_t bp = 0;
    check("SM2: 헤더 인코드 성공", siap_encode_hdr(buf, &bp, &h));
    check("SM2: RSC 인코드 성공", bp_write(buf, &bp, SIAP_RSC_SUCCESS, 8));
    siap_np_t np = { 0x10, 0x00001, 0x00003, SIAP_STATUS_NORMAL, 1 };
    check("SM2: NODE_PROPERTY 인코드 성공", siap_encode_np(buf, &bp, &np));
    siap_result_t r = siap_encode_dp(buf, &bp, &dp);
    check("SM2: DEVICE_PROPERTY 인코드 성공", r.ok);
    size_t total_bytes = bp / 8;
    check("SM2: 총 길이 == 12+39", total_bytes == 51);

    test_ctx_t c = {0}; c.expect_node_id = 3;
    siap_dec_t d; siap_dec_init(&d, make_sink(&c), SIAP_MODE_STRICT);
    feed_bytes(&d, buf, total_bytes);

    check("SM2: on_header 1회, kind==RES_SET_CONNECTION, n==1",
          c.header_calls == 1 && c.last_kind == SIAP_RES_SET_CONNECTION && c.last_n == 1);
    check("SM2: on_fixed 1회, len==9 (RSC+NODE_PROPERTY)",
          c.fixed_calls == 1 && c.fixed_len == 9 && c.fixed_buf[0] == SIAP_RSC_SUCCESS);
    check("SM2: on_element 1회, len==30", c.elem_calls == 1 && c.elem_lens[0] == 30);
    check("SM2: on_end SUCCESS", c.end_calls == 1 && c.end_rsc == SIAP_RSC_SUCCESS);
}

/* 위반 8종 — /. 손으로 만든 바이트로
   각 지점을 독립적으로 확인한다(골든 52건과의 교차 확인은 test_golden.c). */
static void case_stream_violations(void)
{
    uint8_t buf[32];
    size_t bp;
    test_ctx_t c;
    siap_dec_t d;

    /* #1 Version 조작 (payload_len=0 이라 드레인 없이 바로 위반 보고) */
    siap_hdr_t h1 = { 0x99, siap_wire_code(SIAP_NOTI_KEEP_ALIVE, SIAP_MODE_STRICT),
                       SIAP_TRANS_UNICAST, 50, 0, 0x00001, 0x00003 };
    bp = 0; enc_hdr_ok("V1: 헤더 인코드 성공", buf, &bp, &h1);
    c = (test_ctx_t){0}; c.expect_node_id = 3;
    siap_dec_init(&d, make_sink(&c), SIAP_MODE_STRICT);
    feed_bytes(&d, buf, 12);
    check("V1: Version 조작 -> INVALID_VERSION/7.3.1",
          c.end_calls == 1 && c.end_rsc == SIAP_RSC_INVALID_VERSION && c.end_clause == SIAP_CLAUSE_7_3_1);
    check("V1: on_header 는 호출되지 않는다(버전 단계에서 이미 거부)", c.header_calls == 0);

    /* #2 미등록 Node ID — core/ 는 모르므로 on_header 콜백의 거부로 표현한다 */
    siap_hdr_t h2 = { SIAP_VERSION, siap_wire_code(SIAP_NOTI_KEEP_ALIVE, SIAP_MODE_STRICT),
                       SIAP_TRANS_UNICAST, 51, 0, 0x00001, 0x0ABCDE };
    bp = 0; enc_hdr_ok("V2: 헤더 인코드 성공", buf, &bp, &h2);
    c = (test_ctx_t){0}; c.expect_node_id = 3;
    siap_dec_init(&d, make_sink(&c), SIAP_MODE_STRICT);
    feed_bytes(&d, buf, 12);
    check("V2: 미등록 Node ID -> INVALID_NODE_ID/7.3.1",
          c.end_calls == 1 && c.end_rsc == SIAP_RSC_INVALID_NODE_ID && c.end_clause == SIAP_CLAUSE_7_3_1);
    check("V2: on_header 는 1회 호출된다(콜백이 판단 후 거부)", c.header_calls == 1);

    /* #3 Payload Length 형식 불일치 (0x0800, plen=24 — 어느 후보도 만족 못함) */
    siap_hdr_t h3 = { SIAP_VERSION, 0x0800, SIAP_TRANS_UNICAST, 52, 24, 0x00001, 0x00003 };
    bp = 0; enc_hdr_ok("V3: 헤더 인코드 성공", buf, &bp, &h3);
    c = (test_ctx_t){0}; c.expect_node_id = 3;
    siap_dec_init(&d, make_sink(&c), SIAP_MODE_STRICT);
    feed_bytes(&d, buf, 12);
    check("V3: Payload Length 형식 불일치 -> INVALID_FORMAT/7.3.1",
          c.end_calls == 1 && c.end_rsc == SIAP_RSC_INVALID_FORMAT && c.end_clause == SIAP_CLAUSE_7_3_1);

    /* #4 미정의 Message Type (0x000E) */
    siap_hdr_t h4 = { SIAP_VERSION, 0x000E, SIAP_TRANS_UNICAST, 53, 0, 0x00001, 0x00003 };
    bp = 0; enc_hdr_ok("V4: 헤더 인코드 성공", buf, &bp, &h4);
    c = (test_ctx_t){0}; c.expect_node_id = 3;
    siap_dec_init(&d, make_sink(&c), SIAP_MODE_STRICT);
    feed_bytes(&d, buf, 12);
    check("V4: 미정의 Message Type -> INVALID_FORMAT/표 7-2",
          c.end_calls == 1 && c.end_rsc == SIAP_RSC_INVALID_FORMAT && c.end_clause == SIAP_CLAUSE_TABLE_7_2);

    /* #5 Transmission Type = 0x03 (표 7-6 미정의) */
    siap_hdr_t h5 = { SIAP_VERSION, siap_wire_code(SIAP_NOTI_KEEP_ALIVE, SIAP_MODE_STRICT),
                       0x03, 54, 0, 0x00001, 0x00003 };
    bp = 0; enc_hdr_ok("V5: 헤더 인코드 성공", buf, &bp, &h5);
    c = (test_ctx_t){0}; c.expect_node_id = 3;
    siap_dec_init(&d, make_sink(&c), SIAP_MODE_STRICT);
    feed_bytes(&d, buf, 12);
    check("V5: Transmission Type 미정의 -> INVALID_TRANSMISSION_TYPE/표 7-6",
          c.end_calls == 1 && c.end_rsc == SIAP_RSC_INVALID_TRANSMISSION_TYPE
          && c.end_clause == SIAP_CLAUSE_TABLE_7_6);
    check("V5: on_header 는 호출되지 않는다", c.header_calls == 0);

    /* #6 Value Type = RESERVED(0x03) — NOTI_DEVICE_VALUE, N=1.
       손으로 만든 페이로드: DeviceID=01, (Type0/Subtype01/ValueType3/Reserved0)=0x00E0, Value=0 */
    siap_hdr_t h6 = { SIAP_VERSION, 0x0800, SIAP_TRANS_UNICAST, 55, 7, 0x00001, 0x00003 };
    static const uint8_t payload6[7] = {0x01, 0x00, 0xE0, 0x00, 0x00, 0x00, 0x00};
    bp = 0; enc_hdr_ok("V6: 헤더 인코드 성공", buf, &bp, &h6);
    memcpy(buf + 12, payload6, 7);
    c = (test_ctx_t){0}; c.expect_node_id = 3;
    siap_dec_init(&d, make_sink(&c), SIAP_MODE_STRICT);
    feed_bytes(&d, buf, 19);
    check("V6: Value Type=RESERVED -> INVALID_DATA_TYPE/표 7-14",
          c.end_calls == 1 && c.end_rsc == SIAP_RSC_INVALID_DATA_TYPE && c.end_clause == SIAP_CLAUSE_TABLE_7_14);
    check("V6: on_header 는 통과했으나 on_element 는 호출되지 않는다",
          c.header_calls == 1 && c.elem_calls == 0);

    /* #7 미등록 Subtype(0x40) — DeviceID=01, (Type0/Subtype0x40/ValueType2/Reserved0)=0x2040, Value=0 */
    siap_hdr_t h7 = { SIAP_VERSION, 0x0800, SIAP_TRANS_UNICAST, 56, 7, 0x00001, 0x00003 };
    static const uint8_t payload7[7] = {0x01, 0x20, 0x40, 0x00, 0x00, 0x00, 0x00};
    bp = 0; enc_hdr_ok("V7: 헤더 인코드 성공", buf, &bp, &h7);
    memcpy(buf + 12, payload7, 7);
    c = (test_ctx_t){0}; c.expect_node_id = 3;
    siap_dec_init(&d, make_sink(&c), SIAP_MODE_STRICT);
    feed_bytes(&d, buf, 19);
    check("V7: 미등록 Subtype -> INVALID_DATA_SUBTYPE/표 7-14",
          c.end_calls == 1 && c.end_rsc == SIAP_RSC_INVALID_DATA_SUBTYPE && c.end_clause == SIAP_CLAUSE_TABLE_7_14);

    /* #8 NEC=ERROR_BATTERY_LOW(0x07) — 위반이 아니다. 코덱은 정상 디코드하고
       게이트웨이가 alert 로 분류한다. */
    siap_hdr_t h8 = { SIAP_VERSION, siap_wire_code(SIAP_NOTI_ERROR, SIAP_MODE_STRICT),
                       SIAP_TRANS_UNICAST, 57, 1, 0x00001, 0x00003 };
    bp = 0; enc_hdr_ok("V8: 헤더 인코드 성공", buf, &bp, &h8);
    buf[12] = SIAP_NEC_ERROR_BATTERY_LOW;
    c = (test_ctx_t){0}; c.expect_node_id = 3;
    siap_dec_init(&d, make_sink(&c), SIAP_MODE_STRICT);
    feed_bytes(&d, buf, 13);
    check("V8: NEC=ERROR_BATTERY_LOW -> 위반 아님, SUCCESS",
          c.end_calls == 1 && c.end_rsc == SIAP_RSC_SUCCESS);
    check("V8: on_fixed 로 NEC 값 전달", c.fixed_calls == 1 && c.fixed_buf[0] == SIAP_NEC_ERROR_BATTERY_LOW);

    /* #9 (프로젝트 원칙의 8종에는 없지만 골든 B02와 같은 경계
       사례) — REQ_SET_DEVICE_CONTROL(0x000C, 단일 후보) plen=0. resolve_kind()
       는 그 자리에서 kind 를 확정하지만(위 RK1b), FSM 은 그 직후 별도
       element_count() 로 이를 거부해야 한다 — resync_check() 와 다른 코드
       경로(handle_header_complete 의 비-resync 분기)이므로 스트리밍
       수준에서 독립적으로 확인한다. */
    siap_hdr_t h9 = { SIAP_VERSION, siap_wire_code(SIAP_REQ_SET_DEVICE_CONTROL, SIAP_MODE_STRICT),
                       SIAP_TRANS_UNICAST, 58, 0, 0x00001, 0x00003 };
    bp = 0; enc_hdr_ok("V9: 헤더 인코드 성공", buf, &bp, &h9);
    c = (test_ctx_t){0}; c.expect_node_id = 3;
    siap_dec_init(&d, make_sink(&c), SIAP_MODE_STRICT);
    feed_bytes(&d, buf, 12);
    check("V9: 단일 후보 + N=0(가변부만 있음) -> INVALID_FORMAT/7.3.1 (B02)",
          c.end_calls == 1 && c.end_rsc == SIAP_RSC_INVALID_FORMAT && c.end_clause == SIAP_CLAUSE_7_3_1);
    check("V9: on_header 는 호출되지 않는다(resolve_kind 이후 element_count 단계에서 이미 거부)",
          c.header_calls == 0);

    /* #10 (프로젝트 원칙의 8종에는 없지만 표 7-13/7-16 불변식 반례) —
       RES_SET_CONNECTION 에 NODE_PROPERTY.Num. of Devices=2 를 넣고 실제
       DEVICE_PROPERTY 는 1개(Payload Length=39 -> 역산 N=1)만 보낸다.
       보고된 반례 그대로: 같은 프레임이 디바이스 수를 2 와 1 로 동시에
       주장한다. */
    {
        siap_dmi_t main10 = { 0x05, SIAP_DEV_SENSOR, SIAP_SUBTYPE_HUMIDITY, SIAP_VALUE_TYPE_FLOAT,
                               siap_raw_from_float(61.0f) };
        siap_dp_t dp10 = { main10, SIAP_TM_EVENT, 30, siap_raw_from_float(0.0f), siap_raw_from_float(100.0f),
                            siap_raw_from_float(0.0f), siap_raw_from_float(100.0f), siap_raw_from_float(0.1f),
                            SIAP_STATUS_NORMAL };
        uint16_t plen10 = (uint16_t)(SIAP_RSC_BYTES + SIAP_NP_BYTES + SIAP_DP_BYTES); /* 39 -> derived N=1 */
        siap_hdr_t h10 = { SIAP_VERSION, siap_wire_code(SIAP_RES_SET_CONNECTION, SIAP_MODE_STRICT),
                            SIAP_TRANS_UNICAST, 59, plen10, 0x00001, 0x00003 };
        siap_np_t np10 = { 0x10, 0x00001, 0x00003, SIAP_STATUS_NORMAL, 2 };  /* Num. of Devices=2, 실제는 1 */
        uint8_t buf10[64]; size_t bp10 = 0;   /* 51byte 프레임 — 공유 buf[32] 는 너무 작다 */

        enc_hdr_ok("V10: 헤더 인코드 성공", buf10, &bp10, &h10);
        check("V10: RSC 인코드 성공", bp_write(buf10, &bp10, SIAP_RSC_SUCCESS, 8));
        check("V10: NODE_PROPERTY 인코드 성공", siap_encode_np(buf10, &bp10, &np10));
        siap_result_t r10 = siap_encode_dp(buf10, &bp10, &dp10);
        check("V10: DEVICE_PROPERTY 인코드 성공", r10.ok);
        size_t total10 = bp10 / 8;

        c = (test_ctx_t){0}; c.expect_node_id = 3;
        siap_dec_init(&d, make_sink(&c), SIAP_MODE_STRICT);
        feed_bytes(&d, buf10, total10);
        check("V10: Num. of Devices(2) != 역산 N(1) -> INVALID_FORMAT/7.3.1",
              c.end_calls == 1 && c.end_rsc == SIAP_RSC_INVALID_FORMAT && c.end_clause == SIAP_CLAUSE_7_3_1);
        check("V10: 고정부 불일치이므로 on_fixed/on_element 모두 호출되지 않는다",
              c.fixed_calls == 0 && c.elem_calls == 0);
    }

    /* #11~#14 (프로젝트 원칙의 8종에는 없지만 표 7-10/7-12/7-13/7-15
       예약값 반례) — 인코더가 이제 예약값을 거부하므로(ST9~ST13), 여기서는
       bp_write 로 직접 원시 바이트를 구성해 "공격자가 이미 만든 프레임"을
       흉내낸다. */

    /* #11 RSC=0x0A(Reserved) — RES_SET_DEVICE_INIT, 고정부 RSC 1byte뿐 */
    {
        siap_hdr_t h11 = { SIAP_VERSION, siap_wire_code(SIAP_RES_SET_DEVICE_INIT, SIAP_MODE_STRICT),
                            SIAP_TRANS_UNICAST, 60, 1, 0x00001, 0x00003 };
        bp = 0; enc_hdr_ok("V11: 헤더 인코드 성공", buf, &bp, &h11);
        buf[12] = 0x0A;   /* RSC Reserved */
        c = (test_ctx_t){0}; c.expect_node_id = 3;
        siap_dec_init(&d, make_sink(&c), SIAP_MODE_STRICT);
        feed_bytes(&d, buf, 13);
        check("V11: RSC=0x0A(Reserved) -> INVALID_FORMAT/7.3.1",
              c.end_calls == 1 && c.end_rsc == SIAP_RSC_INVALID_FORMAT && c.end_clause == SIAP_CLAUSE_7_3_1);
        check("V11: on_fixed 는 호출되지 않는다", c.fixed_calls == 0);
    }

    /* #12 NEC=0x0A(Reserved) — NOTI_ERROR, 고정부 NEC 1byte뿐 */
    {
        siap_hdr_t h12 = { SIAP_VERSION, siap_wire_code(SIAP_NOTI_ERROR, SIAP_MODE_STRICT),
                            SIAP_TRANS_UNICAST, 61, 1, 0x00001, 0x00003 };
        bp = 0; enc_hdr_ok("V12: 헤더 인코드 성공", buf, &bp, &h12);
        buf[12] = 0x0A;   /* NEC Reserved */
        c = (test_ctx_t){0}; c.expect_node_id = 3;
        siap_dec_init(&d, make_sink(&c), SIAP_MODE_STRICT);
        feed_bytes(&d, buf, 13);
        check("V12: NEC=0x0A(Reserved) -> INVALID_FORMAT/7.3.1",
              c.end_calls == 1 && c.end_rsc == SIAP_RSC_INVALID_FORMAT && c.end_clause == SIAP_CLAUSE_7_3_1);
        check("V12: on_fixed 는 호출되지 않는다", c.fixed_calls == 0);
    }

    /* #13 NODE_PROPERTY.Status=0x03(Reserved) — REQ_SET_NODE_PROPERTY, 고정부 NP 8byte뿐 */
    {
        uint8_t np_bad[8]; size_t bp_np = 0;
        check("V13: 예약값 NP 페이로드 구성(테스트 보조)",
              bp_write(np_bad, &bp_np, 0x10, 8)
              && bp_write(np_bad, &bp_np, 0x00001, 20)
              && bp_write(np_bad, &bp_np, 0x00003, 20)
              && bp_write(np_bad, &bp_np, 0x03, 8)      /* Status Reserved */
              && bp_write(np_bad, &bp_np, 2, 8));

        siap_hdr_t h13 = { SIAP_VERSION, siap_wire_code(SIAP_REQ_SET_NODE_PROPERTY, SIAP_MODE_STRICT),
                            SIAP_TRANS_UNICAST, 62, 8, 0x00001, 0x00003 };
        bp = 0; enc_hdr_ok("V13: 헤더 인코드 성공", buf, &bp, &h13);
        memcpy(buf + 12, np_bad, 8);
        c = (test_ctx_t){0}; c.expect_node_id = 3;
        siap_dec_init(&d, make_sink(&c), SIAP_MODE_STRICT);
        feed_bytes(&d, buf, 20);
        check("V13: NODE_PROPERTY.Status=0x03(Reserved) -> INVALID_FORMAT/7.3.1",
              c.end_calls == 1 && c.end_rsc == SIAP_RSC_INVALID_FORMAT && c.end_clause == SIAP_CLAUSE_7_3_1);
        check("V13: on_fixed 는 호출되지 않는다", c.fixed_calls == 0);
    }

    /* #14 DEVICE_PROPERTY.Transfer Mode=0x03(Reserved) — REQ_SET_DEVICE_PROPERTY, N=1 */
    {
        uint8_t dp_bad[30]; size_t bp_dp = 0;
        siap_dmi_t dmi14 = { 0x05, SIAP_DEV_SENSOR, SIAP_SUBTYPE_HUMIDITY, SIAP_VALUE_TYPE_FLOAT,
                              siap_raw_from_float(61.0f) };
        siap_result_t r14 = siap_encode_dmi(dp_bad, &bp_dp, &dmi14);
        check("V14: DMI 부분 인코드 성공(테스트 보조)", r14.ok);
        check("V14: 나머지 필드 구성 — Transfer Mode Reserved(테스트 보조)",
              bp_write(dp_bad, &bp_dp, 0x03, 2)          /* Transfer Mode Reserved */
              && bp_write(dp_bad, &bp_dp, 30, 14)
              && bp_write(dp_bad, &bp_dp, siap_raw_from_float(0.0f), 32)
              && bp_write(dp_bad, &bp_dp, siap_raw_from_float(100.0f), 32)
              && bp_write(dp_bad, &bp_dp, siap_raw_from_float(0.0f), 32)
              && bp_write(dp_bad, &bp_dp, siap_raw_from_float(100.0f), 32)
              && bp_write(dp_bad, &bp_dp, siap_raw_from_float(0.1f), 32)
              && bp_write(dp_bad, &bp_dp, SIAP_STATUS_NORMAL, 8));

        uint8_t buf14[64];
        siap_hdr_t h14 = { SIAP_VERSION, siap_wire_code(SIAP_REQ_SET_DEVICE_PROPERTY, SIAP_MODE_STRICT),
                            SIAP_TRANS_UNICAST, 63, 30, 0x00001, 0x00003 };
        size_t bp14 = 0;
        enc_hdr_ok("V14: 헤더 인코드 성공", buf14, &bp14, &h14);
        memcpy(buf14 + 12, dp_bad, 30);
        c = (test_ctx_t){0}; c.expect_node_id = 3;
        siap_dec_init(&d, make_sink(&c), SIAP_MODE_STRICT);
        feed_bytes(&d, buf14, 42);
        check("V14: DEVICE_PROPERTY.Transfer Mode=0x03(Reserved) -> INVALID_FORMAT/7.3.1",
              c.end_calls == 1 && c.end_rsc == SIAP_RSC_INVALID_FORMAT && c.end_clause == SIAP_CLAUSE_7_3_1);
        check("V14: on_element 는 호출되지 않는다", c.elem_calls == 0);
    }
}

/* 재동기 — 위반으로 어긋난 뒤 다음 유효한 헤더를 슬라이딩으로 되찾는다  */
static void case_resync(void)
{
    test_ctx_t c = {0}; c.expect_node_id = 3;
    siap_dec_t d;
    siap_dec_init(&d, make_sink(&c), SIAP_MODE_STRICT);

    /* 1단계 — Version 위반(payload_len=0)으로 resync 모드에 자연스럽게 진입시킨다. */
    uint8_t bad[12]; size_t bp = 0;
    siap_hdr_t hbad = { 0x99, siap_wire_code(SIAP_NOTI_KEEP_ALIVE, SIAP_MODE_STRICT),
                         SIAP_TRANS_UNICAST, 1, 0, 0x00001, 0x00003 };
    enc_hdr_ok("RS1: 위반용 헤더 인코드 성공", bad, &bp, &hbad);
    feed_bytes(&d, bad, 12);
    check("RS1: 1단계 — Version 위반 보고", c.end_calls == 1 && c.end_rsc == SIAP_RSC_INVALID_VERSION);

    /* 2단계 — 잡음 11byte. 아직 12byte 가 안 모였으므로 콜백은 안 온다. */
    uint8_t noise[11]; memset(noise, 0x00, sizeof(noise));
    feed_bytes(&d, noise, 11);
    check("RS2: 잡음 11byte 동안 콜백 없음(아직 창이 안 참)", c.end_calls == 1 && c.header_calls == 0);

    /* 3단계 — 유효한 ACK 헤더 12byte. 슬라이딩이 앞의 잡음 11byte 를 한 바이트씩
       밀어내며, 이 12byte 가 온전히 도착하는 순간 창이 정확히 이 헤더와
       일치해 인식된다. */
    uint8_t good[12]; bp = 0;
    siap_hdr_t hgood = { SIAP_VERSION, siap_wire_code(SIAP_ACK, SIAP_MODE_STRICT),
                          SIAP_TRANS_UNICAST, 99, 0, 0x00001, 0x00003 };
    enc_hdr_ok("RS3: 유효 ACK 헤더 인코드 성공", good, &bp, &hgood);
    feed_bytes(&d, good, 12);
    check("RS3: 재동기 후 유효 프레임 인식 — on_header 1회, kind==ACK",
          c.header_calls == 1 && c.last_kind == SIAP_ACK);
    check("RS3: 슬라이딩 도중 추가 위반 보고 없음(end_calls 1->2, SUCCESS 만 추가)",
          c.end_calls == 2 && c.end_rsc == SIAP_RSC_SUCCESS);
}

/* RS1(위 case_resync)의 위반 헤더는 payload_len=0이라 우연히 이
   결함을 가리지 못했다(begin_drain(remaining=0)은 고친 뒤에도 전과 동일하게
   동작한다). payload_len 이 0이 아닌 헤더 위반을 재현한다: Version=0x99에
   payload_len=12(뒤따르는 정상 ACK 프레임과 우연히 같은 길이)를 실어 보내면,
   옛 구현은 그 12byte 를 S_DRAIN 으로 그대로 삼켜 뒤의 정상 ACK 를
   완전히 잃는다. */
static void case_resync_header_violation_nonzero_payload_len_f141(void)
{
    test_ctx_t c = {0}; c.expect_node_id = 3;
    siap_dec_t d;
    siap_dec_init(&d, make_sink(&c), SIAP_MODE_STRICT);

    uint8_t bad[12]; size_t bp = 0;
    siap_hdr_t hbad = { 0x99, siap_wire_code(SIAP_ACK, SIAP_MODE_STRICT),
                         SIAP_TRANS_UNICAST, 1, 12, 0x00001, 0x00003 };
    enc_hdr_ok("RSN1: 위반용 헤더(payload_len=12) 인코드 성공", bad, &bp, &hbad);
    feed_bytes(&d, bad, 12);
    check("RSN1: Version 위반 보고", c.end_calls == 1 && c.end_rsc == SIAP_RSC_INVALID_VERSION);
    check("RSN1: 신뢰할 수 없는 payload_len 으로 S_DRAIN 에 들어가지 않고 즉시 재동기(HDR/resync)",
          d.state == SIAP_DEC_ST_HDR && d.resync == true && d.drain_remaining == 0);

    uint8_t good[12]; bp = 0;
    siap_hdr_t hgood = { SIAP_VERSION, siap_wire_code(SIAP_ACK, SIAP_MODE_STRICT),
                          SIAP_TRANS_UNICAST, 99, 0, 0x00001, 0x00003 };
    enc_hdr_ok("RSN2: 뒤따르는 정상 ACK 헤더 인코드 성공", good, &bp, &hgood);
    feed_bytes(&d, good, 12);
    check("RSN2: 위반 헤더 바로 뒤 정상 프레임이 드레인으로 삼켜지지 않고 인식된다",
          c.header_calls == 1 && c.last_kind == SIAP_ACK
          && c.end_calls == 2 && c.end_rsc == SIAP_RSC_SUCCESS);
}

/* on_gap — T_gap 경과 알림이 헤더 대기 상태를 재동기 모드로 돌린다 */
static void case_on_gap(void)
{
    test_ctx_t c = {0}; c.expect_node_id = 3;
    siap_dec_t d;
    siap_dec_init(&d, make_sink(&c), SIAP_MODE_STRICT);

    uint8_t good[12]; size_t bp = 0;
    siap_hdr_t hgood = { SIAP_VERSION, siap_wire_code(SIAP_ACK, SIAP_MODE_STRICT),
                          SIAP_TRANS_UNICAST, 1, 0, 0x00001, 0x00003 };
    enc_hdr_ok("GAP1: 유효 ACK 헤더 인코드 성공", good, &bp, &hgood);

    /* 이 유효한 헤더의 앞 5byte 만 도착한 채 침묵(T_gap)이 걸린 상황을
       흉내낸다. 이 원칙은 "1byte 씩 전진하며 다음 12byte 를 헤더로 시험한다"고만
       적는다 — 이미 모으던 5byte 를 버리라는 규정은 없다. 헤더 대기 중의
       gap 은 resync 모드만 켜고 지금까지 모은 바이트는 재동기 후보의
       앞부분으로 그대로 남긴다(버리는 쪽은 FIXED/ELEM 도중의 gap 뿐이다 —
       그건 페이로드 중간이라 이어붙일 수 없는 불완전 프레임이기 때문). */
    feed_bytes(&d, good, 5);
    siap_dec_on_gap(&d);
    check("GAP1: 헤더 대기 중 T_gap -> resync 모드만 켜지고 수집분은 유지",
          d.state == SIAP_DEC_ST_HDR && d.buf_len == 5 && d.resync == true);

    /* 나머지 7byte 를 마저 먹이면 buf 가 정확히 원래의 유효한 헤더 12byte 로
       완성된다 — resync 4조건 검사가 슬라이딩 한 번 없이 바로 통과해야 한다. */
    feed_bytes(&d, good + 5, 7);
    check("GAP2: gap 이후 이어붙인 프레임이 슬라이딩 없이 즉시 인식",
          c.header_calls == 1 && c.last_kind == SIAP_ACK && c.end_calls == 1
          && c.end_rsc == SIAP_RSC_SUCCESS);
}

/* ═══════════════════════════════════════════════════════════════
 *  케이스 5 — 송신 윈도우: flush 부분 쓰기 / ACK 빌더
 * ═══════════════════════════════════════════════════════════════ */
/* budget = "지금 이 순간 받아줄 수 있는 byte 수". 0 이면 진짜 논블로킹 I/O 처럼
   0을 돌려준다(siap_tx_flush 가 PENDING 을 내는 유일한 조건) — len 을 그냥
   잘라 받아주기만 하면 매 라운드 wrote>0 이 보장돼 PENDING 이 결코 나오지
   않는다(부분 쓰기와 "지금은 하나도 못 쓴다"는 다른 상황이다). */
typedef struct { uint8_t out[128]; size_t out_len; size_t budget; } tx_sim_t;

static size_t sim_write(void *ctx, const uint8_t *data, size_t len)
{
    tx_sim_t *s = (tx_sim_t *)ctx;
    size_t n = len;
    if (n > s->budget) n = s->budget;
    s->budget -= n;
    memcpy(s->out + s->out_len, data, n);
    s->out_len += n;
    return n;
}

static void case_tx_ack_and_flush(void)
{
    siap_hdr_t req = { SIAP_VERSION, 0x0003, SIAP_TRANS_UNICAST, 0x00AB, 0, 0x00001, 0x00003 };
    siap_enc_t e;
    check("TX1: ACK 빌드 성공", siap_encode_ack(&req, SIAP_MODE_STRICT, &e));

    tx_sim_t sim = {0}; sim.budget = sizeof(sim.out); /* 전부 받아주는 쓰기 */
    siap_tx_status_t st = siap_tx_flush(&e, sim_write, &sim);
    check("TX1: flush 즉시 완료", st == SIAP_TX_DONE && sim.out_len == 12);

    siap_hdr_t got; size_t bp = 0; siap_decode_hdr(sim.out, &bp, &got);
    check("TX1: msg_id/GCG ID/Node ID 가 원 요청에서 복사됨",
          got.msg_id == req.msg_id && got.gcg_id == req.gcg_id && got.node_id == req.node_id);
    check("TX1: msg_type == ACK wire code", got.msg_type == siap_wire_code(SIAP_ACK, SIAP_MODE_STRICT));
    check("TX1: payload_len == 0 (ACK 는 페이로드 없음, 7.2/표 7-1)", got.payload_len == 0);

    /* 부분 쓰기 — 매 라운드 1byte 만 받아주는 논블로킹 IO 를 흉내낸다
       ("블로킹하지 않는다"). budget 을 매 flush 호출 전에 1로 다시
       채운다 — "이번 틱엔 1byte 여유가 생겼다"는 뜻이다. */
    siap_enc_t e2;
    check("TX2: ACK 재빌드 성공", siap_encode_ack(&req, SIAP_MODE_STRICT, &e2));
    tx_sim_t sim2 = {0};
    int pending_rounds = 0;
    siap_tx_status_t st2;
    do {
        sim2.budget = 1;
        st2 = siap_tx_flush(&e2, sim_write, &sim2);
        if (st2 == SIAP_TX_PENDING) pending_rounds++;
    } while (st2 == SIAP_TX_PENDING && pending_rounds < 20);
    check("TX2: 부분 쓰기를 여러 번 반복해 결국 완료", st2 == SIAP_TX_DONE && sim2.out_len == 12);
    check("TX2: 부분 쓰기가 실제로 여러 라운드 걸렸다(11번 PENDING)", pending_rounds == 11);
    check("TX2: 부분 쓰기로도 최종 바이트열은 한 번에 쓴 것과 동일",
          memcmp(sim.out, sim2.out, 12) == 0);
}

/* ═══════════════════════════════════════════════════════════════
 *  케이스 6 — 51byte 송신 윈도우 용량 강제
 * ═══════════════════════════════════════════════════════════════ */
/* 헤더 12 + RSC 1 + NODE_PROPERTY 8 + DEVICE_PROPERTY 30 = 51byte 로 윈도우를
   정확히 채운 뒤, 그 이상은 어떤 put 도 실패해야 하고(false/ok==false)
   win[] 밖으로 실제 메모리 쓰기가 있어서도 안 된다. bitpos 를 사후에
   되돌리는 것만으로는 이미 일어난 배열 밖 쓰기를 되돌릴 수 없으므로,
   win[] 바로 뒤(구조체 패딩)에 카나리를 심어 오염 여부를 직접 확인한다. */
static void case_tx_window_capacity(void)
{
    siap_dmi_t main_ = { 0x05, SIAP_DEV_SENSOR, SIAP_SUBTYPE_HUMIDITY, SIAP_VALUE_TYPE_FLOAT,
                          siap_raw_from_float(61.0f) };
    siap_dp_t dp = { main_, SIAP_TM_EVENT, 30, siap_raw_from_float(0.0f), siap_raw_from_float(100.0f),
                      siap_raw_from_float(0.0f), siap_raw_from_float(100.0f), siap_raw_from_float(0.1f),
                      SIAP_STATUS_NORMAL };
    uint16_t plen = (uint16_t)(SIAP_RSC_BYTES + SIAP_NP_BYTES + SIAP_DP_BYTES); /* 39 */
    siap_hdr_t h = { SIAP_VERSION, siap_wire_code(SIAP_RES_SET_CONNECTION, SIAP_MODE_STRICT),
                      SIAP_TRANS_UNICAST, 7, plen, 0x00001, 0x00003 };
    siap_np_t np = { 0x10, 0x00001, 0x00003, SIAP_STATUS_NORMAL, 1 };

    siap_enc_t e;
    siap_tx_reset(&e);
    check("TXCAP1: 헤더 put 성공", siap_tx_put_hdr(&e, &h));
    check("TXCAP1: RSC put 성공", siap_tx_put_rsc(&e, SIAP_RSC_SUCCESS));
    check("TXCAP1: NODE_PROPERTY put 성공", siap_tx_put_np(&e, &np));
    siap_result_t r1 = siap_tx_put_dp(&e, &dp);
    check("TXCAP1: 첫 DEVICE_PROPERTY put 성공, 정확히 51byte 소진",
          r1.ok && e.bitpos == (size_t)SIAP_TX_WINDOW * 8u);

    /* win[] 바로 뒤 구조체 패딩에 카나리를 심는다 — 패딩도 &e 가 가리키는
       객체의 일부이므로 unsigned char* 로 쓰고 읽는 것은 항상 유효하다. */
    unsigned char *raw = (unsigned char *)&e;
    raw[sizeof(e.win)] = 0xA5;
    unsigned char canary = raw[sizeof(e.win)];
    size_t bitpos_before = e.bitpos;

    bool over_device_id = siap_tx_put_device_id(&e, 0x5A);
    check("TXCAP2: 꽉 찬 윈도우에 1byte 추가 put 은 false", !over_device_id);
    check("TXCAP2: 실패한 put 후 bitpos 불변", e.bitpos == bitpos_before);
    check("TXCAP2: 실패한 put 후 윈도우 밖 카나리 불변(배열 밖 쓰기 없음)",
          raw[sizeof(e.win)] == canary);

    /* N=2 통합 속성 — flush 없이 두 번째 DEVICE_PROPERTY(30byte)를 이어
       붙이려는 재현. 보고된 반례와 동일한 경로다. */
    siap_result_t r2 = siap_tx_put_dp(&e, &dp);
    check("TXCAP3: 두 번째 DEVICE_PROPERTY put 은 실패(N=2 flush 누락 재현)", !r2.ok);
    check("TXCAP3: 실패한 put 후 bitpos 불변", e.bitpos == bitpos_before);
    check("TXCAP3: 실패한 put 후 윈도우 밖 카나리 불변", raw[sizeof(e.win)] == canary);

    /* 헤더 put 도 동일 계약이어야 한다 — dmi/dp 뿐 아니라 bool 반환 진입점도. */
    siap_enc_t e2;
    siap_tx_reset(&e2);
    check("TXCAP4: 두 번째 헤더 put 준비 성공", siap_tx_put_hdr(&e2, &h));
    /* NODE_PROPERTY(8) 없이 곧장 DEVICE_PROPERTY(30) 를 시도해도 나머지
       계산은 동일 — 12+30=42 로 아직 여유 있음을 먼저 확인하고, 그 뒤
       51byte 를 넘기는 두 번째 DEVICE_PROPERTY 로 같은 경계를 재확인한다. */
    siap_result_t e2r1 = siap_tx_put_dp(&e2, &dp);
    check("TXCAP4: 42byte 까지는 정상 put", e2r1.ok && e2.bitpos == 42u * 8u);
    siap_result_t e2r2 = siap_tx_put_dp(&e2, &dp);
    check("TXCAP4: 72byte 는 51byte 윈도우를 넘어 실패", !e2r2.ok && e2.bitpos == 42u * 8u);
}

int main(void)
{
    printf("siap_frame 호스트 유닛테스트\n\n");

    case_element_count();
    case_resolve_kind();
    case_struct_roundtrip();
    case_stream_header_only();
    case_stream_fixed_and_element();
    case_stream_violations();
    case_resync();
    case_resync_header_violation_nonzero_payload_len_f141();
    case_on_gap();
    case_tx_ack_and_flush();
    case_tx_window_capacity();

    printf("\n  %d/%d 통과\n", g_passed, g_total);
    return (g_passed == g_total) ? 0 : 1;
}
