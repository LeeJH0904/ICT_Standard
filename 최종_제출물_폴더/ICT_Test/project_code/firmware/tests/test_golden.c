/*
 * 골든 벡터 53건 전량 왕복(B11 추가로 52 -> 53).
 * project_code/contracts/vectors/golden.jsonl을 직접 읽어,
 * C 스트리밍 디코더가
 * 손으로 만든 기대값(kind/n/judgement/violations)과 같은 판정을 내리는지,
 * 그리고 정상·alert 프레임은 디코드한 필드를 다시 인코드했을 때 원본 hex와
 * 바이트 단위로 같은지(round-trip)를 확인한다.
 *
 * JSON 파서를 새로 만들지 않는다 — golden.jsonl 의 필드 형태가 고정돼 있으므로
 * "key": 뒤의 값만 뽑는 얕은 스캐너로 충분하다. 이 파일 하나만 이 스캐너를
 * 쓰고 core/ 는 이 파일을 전혀 모른다(core/ 는 JSON 을 모른다).
 *
 * 실행: cd project_code/firmware/tests && make test_golden && ./test_golden
 * 종료 코드: 0 = 전부 통과, 1 = 실패 있음
 */
#include "../core/siap_frame.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define GOLDEN_PATH "../../contracts/vectors/golden.jsonl"

static int g_total = 0;
static int g_passed = 0;

static void check(const char *name, int cond)
{
    g_total++;
    if (cond) g_passed++;
    printf("  %s  %s\n", cond ? "PASS" : "FAIL", name);
}

/* ═══════════════════════════════════════════════════════════════
 *  0. 얕은 JSON 스캐너 — golden.jsonl 전용. 일반 JSON 파서가 아니다.
 * ═══════════════════════════════════════════════════════════════ */
static const char *find_key(const char *line, const char *key)
{
    char pat[64];
    snprintf(pat, sizeof(pat), "\"%s\":", key);
    return strstr(line, pat);
}

static bool extract_str(const char *line, const char *key, char *out, size_t outsz)
{
    const char *p = find_key(line, key);
    if (!p) return false;
    p = strchr(p, ':');
    if (!p) return false;
    p++;
    while (*p == ' ') p++;
    if (*p != '"') return false;
    p++;
    size_t i = 0;
    while (*p && *p != '"' && i + 1 < outsz) {
        if (*p == '\\' && p[1]) p++;   /* 이스케이프 — 다음 문자를 그대로 담는다 */
        out[i++] = *p++;
    }
    out[i] = '\0';
    return true;
}

static bool extract_int(const char *line, const char *key, long *out)
{
    const char *p = find_key(line, key);
    if (!p) return false;
    p = strchr(p, ':');
    if (!p) return false;
    p++;
    while (*p == ' ') p++;
    if (*p == 'n') return false;   /* null */
    char *end;
    long v = strtol(p, &end, 10);
    if (end == p) return false;
    *out = v;
    return true;
}

/* violations[0] 만 본다 — 위반 케이스는 전부 위반 1건짜리다(첫 위반에서
   중단, "요소 단위 즉시 적용 + 첫 위반에서 중단"). */
static bool extract_first_violation(const char *line, long *code, char *clause, size_t clause_sz)
{
    const char *v = find_key(line, "violations");
    if (!v) return false;
    const char *bracket = strchr(v, '[');
    if (!bracket) return false;
    if (bracket[1] == ']') return false;   /* violations: [] */
    if (!extract_int(bracket, "code", code)) return false;
    if (!extract_str(bracket, "clause", clause, clause_sz)) return false;
    return true;
}

static siap_clause_t parse_clause(const char *s)
{
    if (strcmp(s, "7.3.1") == 0) return SIAP_CLAUSE_7_3_1;
    if (strcmp(s, "표 7-2") == 0) return SIAP_CLAUSE_TABLE_7_2;
    if (strcmp(s, "표 7-6") == 0) return SIAP_CLAUSE_TABLE_7_6;
    if (strcmp(s, "표 7-14") == 0) return SIAP_CLAUSE_TABLE_7_14;
    if (strcmp(s, "7.3.2") == 0) return SIAP_CLAUSE_7_3_2;
    return SIAP_CLAUSE_NONE;
}

/* golden.jsonl 의 "kind" 문자열(contracts/frame.py MsgKind 이름과
   동일)을 siap_kind_t 로 되돌린다. 34종 전부를 손으로 나열한다 — 동일
   레이아웃 메시지끼리 우연히 이름이 비슷해 오매핑되는 결함( 재현
   시나리오)을 여기서부터 막는다. */
static siap_kind_t kind_from_str(const char *s)
{
    static const struct { const char *name; siap_kind_t kind; } TABLE[] = {
        { "REQ_SET_CONNECTION",               SIAP_REQ_SET_CONNECTION },
        { "REQ_SET_DEVICE_INIT",              SIAP_REQ_SET_DEVICE_INIT },
        { "REQ_SET_DEVICE_INIT_ALL",          SIAP_REQ_SET_DEVICE_INIT_ALL },
        { "REQ_SET_NODE_PROPERTY",            SIAP_REQ_SET_NODE_PROPERTY },
        { "REQ_SET_DEVICE_PROPERTY",          SIAP_REQ_SET_DEVICE_PROPERTY },
        { "REQ_SET_NODE_DEVICE_PROPERTY_ALL", SIAP_REQ_SET_NODE_DEVICE_PROPERTY_ALL },
        { "REQ_SET_MSG_FLOW_CONTROL_PROFILE", SIAP_REQ_SET_MSG_FLOW_CONTROL_PROFILE },
        { "REQ_GET_NODE_PROPERTY",            SIAP_REQ_GET_NODE_PROPERTY },
        { "REQ_GET_DEVICE_PROPERTY",          SIAP_REQ_GET_DEVICE_PROPERTY },
        { "REQ_GET_NODE_DEVICE_PROPERTY_ALL", SIAP_REQ_GET_NODE_DEVICE_PROPERTY_ALL },
        { "REQ_GET_DEVICE_VALUE",             SIAP_REQ_GET_DEVICE_VALUE },
        { "REQ_GET_MSG_FLOW_CONTROL_PROFILE", SIAP_REQ_GET_MSG_FLOW_CONTROL_PROFILE },
        { "REQ_SET_DEVICE_CONTROL",           SIAP_REQ_SET_DEVICE_CONTROL },
        { "REQ_SET_REBOOT",                   SIAP_REQ_SET_REBOOT },
        { "RES_SET_CONNECTION",               SIAP_RES_SET_CONNECTION },
        { "RES_SET_DEVICE_INIT",              SIAP_RES_SET_DEVICE_INIT },
        { "RES_SET_DEVICE_INIT_ALL",          SIAP_RES_SET_DEVICE_INIT_ALL },
        { "RES_SET_NODE_PROPERTY",            SIAP_RES_SET_NODE_PROPERTY },
        { "RES_SET_DEVICE_PROPERTY",          SIAP_RES_SET_DEVICE_PROPERTY },
        { "RES_SET_NODE_DEVICE_PROPERTY_ALL", SIAP_RES_SET_NODE_DEVICE_PROPERTY_ALL },
        { "RES_SET_MSG_FLOW_CONTROL_PROFILE", SIAP_RES_SET_MSG_FLOW_CONTROL_PROFILE },
        { "RES_GET_NODE_PROPERTY",            SIAP_RES_GET_NODE_PROPERTY },
        { "RES_GET_DEVICE_PROPERTY",          SIAP_RES_GET_DEVICE_PROPERTY },
        { "RES_GET_NODE_DEVICE_PROPERTY_ALL", SIAP_RES_GET_NODE_DEVICE_PROPERTY_ALL },
        { "RES_GET_DEVICE_VALUE",             SIAP_RES_GET_DEVICE_VALUE },
        { "RES_GET_MSG_FLOW_CONTROL_PROFILE", SIAP_RES_GET_MSG_FLOW_CONTROL_PROFILE },
        { "RES_SET_DEVICE_CONTROL",           SIAP_RES_SET_DEVICE_CONTROL },
        { "RES_SET_REBOOT",                   SIAP_RES_SET_REBOOT },
        { "NOTI_ERROR",                       SIAP_NOTI_ERROR },
        { "NOTI_DEVICE_VALUE",                SIAP_NOTI_DEVICE_VALUE },
        { "NOTI_DISCONNECT",                  SIAP_NOTI_DISCONNECT },
        { "NOTI_REBOOT",                      SIAP_NOTI_REBOOT },
        { "NOTI_KEEP_ALIVE",                  SIAP_NOTI_KEEP_ALIVE },
        { "ACK",                              SIAP_ACK },
    };
    for (size_t i = 0; i < sizeof(TABLE) / sizeof(TABLE[0]); i++)
        if (strcmp(TABLE[i].name, s) == 0) return TABLE[i].kind;
    return SIAP_KIND_NONE;
}

static size_t hex_to_bytes(const char *hex, uint8_t *out, size_t cap)
{
    size_t len = strlen(hex);
    size_t n = len / 2;
    if (n > cap) n = cap;
    for (size_t i = 0; i < n; i++) {
        unsigned byte = 0;
        sscanf(hex + 2 * i, "%2x", &byte);
        out[i] = (uint8_t)byte;
    }
    return n;
}

/* ═══════════════════════════════════════════════════════════════
 *  1. 디코드 수집기 — kind 로 고정부/요소를 구분해 재인코딩용으로 보관한다.
 *     core/ 의 일부가 아니다(RAM 예산은 여기 적용되지 않는다 — host
 *     테스트에서 골든 벡터 전체를 대조하기 위한 임시 버퍼일 뿐이다).
 * ═══════════════════════════════════════════════════════════════ */
typedef struct {
    siap_hdr_t hdr;
    siap_kind_t kind;
    uint16_t n;

    bool has_rsc; siap_rsc_t rsc;
    bool has_nec; siap_nec_t nec;
    bool has_np;  siap_np_t np;
    bool has_mcp; siap_mcp_t mcp;

    uint8_t device_ids[SIAP_MAX_DEVICES_PER_NODE]; uint16_t did_count;
    siap_dmi_t dmis[SIAP_MAX_DEVICES_PER_NODE];    uint16_t dmi_count;
    siap_dp_t  dps[SIAP_MAX_DEVICES_PER_NODE];     uint16_t dp_count;

    int header_calls, fixed_calls, elem_calls, end_calls;
    siap_rsc_t end_rsc;
    siap_clause_t end_clause;

    uint32_t self_node_id;
} gcollect_t;

static int8_t g_on_header(void *ctx, const siap_hdr_t *h, siap_kind_t k, uint16_t n)
{
    gcollect_t *g = (gcollect_t *)ctx;
    g->header_calls++;
    g->hdr = *h; g->kind = k; g->n = n;
    /* 위반 케이스 2(미등록 Node ID) — core/ 는 "내 주소"를 모르므로
       node_state 역할을 이 콜백이 대신한다(siap_frame.c 상단 주석 참조). */
    if (h->node_id != g->self_node_id) return -(int8_t)SIAP_RSC_INVALID_NODE_ID;
    return 0;
}

static int8_t g_on_fixed(void *ctx, const uint8_t *buf, uint8_t len)
{
    gcollect_t *g = (gcollect_t *)ctx;
    g->fixed_calls++;
    size_t bp;
    /* 크기만으로는 NEC/RSC(둘 다 1byte), NP/RSC+MCP(둘 다 8byte)가 겹친다 —
       그 두 경우만 kind 로 먼저 갈라내고 나머지는 크기로 충분하다
       (표에서 이미 kind 별로 고정부 구성이 정해진다). */
    if (len == SIAP_NEC_BYTES && g->kind == SIAP_NOTI_ERROR) {
        g->nec = (siap_nec_t)buf[0]; g->has_nec = true;
    } else if (len == (SIAP_RSC_BYTES + SIAP_MCP_BYTES) && g->kind == SIAP_RES_GET_MSG_FLOW_CONTROL_PROFILE) {
        g->rsc = (siap_rsc_t)buf[0]; g->has_rsc = true;
        bp = 8; siap_decode_mcp(buf, &bp, &g->mcp); g->has_mcp = true;
    } else if (len == SIAP_MCP_BYTES) {
        bp = 0; siap_decode_mcp(buf, &bp, &g->mcp); g->has_mcp = true;
    } else if (len == SIAP_NP_BYTES) {
        bp = 0; siap_decode_np(buf, &bp, &g->np); g->has_np = true;
    } else if (len == (SIAP_RSC_BYTES + SIAP_NP_BYTES)) {
        g->rsc = (siap_rsc_t)buf[0]; g->has_rsc = true;
        bp = 8; siap_decode_np(buf, &bp, &g->np); g->has_np = true;
    } else if (len == SIAP_RSC_BYTES) {
        g->rsc = (siap_rsc_t)buf[0]; g->has_rsc = true;
    }
    return 0;
}

static int8_t g_on_element(void *ctx, uint16_t i, const uint8_t *buf, uint8_t len)
{
    gcollect_t *g = (gcollect_t *)ctx;
    g->elem_calls++;
    (void)i;
    size_t bp = 0;
    if (len == SIAP_DID_BYTES) {
        if (g->did_count < SIAP_MAX_DEVICES_PER_NODE) g->device_ids[g->did_count++] = buf[0];
    } else if (len == SIAP_DMI_BYTES) {
        if (g->dmi_count < SIAP_MAX_DEVICES_PER_NODE)
            (void)siap_decode_dmi(buf, &bp, &g->dmis[g->dmi_count++]);
    } else if (len == SIAP_DP_BYTES) {
        if (g->dp_count < SIAP_MAX_DEVICES_PER_NODE)
            (void)siap_decode_dp(buf, &bp, &g->dps[g->dp_count++]);
    }
    return 0;
}

static void g_on_end(void *ctx, siap_rsc_t rsc, siap_clause_t clause)
{
    gcollect_t *g = (gcollect_t *)ctx;
    g->end_calls++;
    g->end_rsc = rsc;
    g->end_clause = clause;
}

static siap_sink_t make_sink(gcollect_t *g)
{
    siap_sink_t s;
    s.on_header = g_on_header;
    s.on_fixed = g_on_fixed;
    s.on_element = g_on_element;
    s.on_end = g_on_end;
    s.ctx = g;
    return s;
}

/* ═══════════════════════════════════════════════════════════════
 *  2. 재인코딩 — 51byte 윈도우 그대로, 청크마다 flush 해 누적한다
 *     (501byte 짜리 프레임도 윈도우 크기와 무관하게 처리된다는 것 자체가
 *     스트리밍 주장의 증거다).
 * ═══════════════════════════════════════════════════════════════ */
typedef struct { uint8_t buf[600]; size_t len; } accum_t;

static size_t accum_write(void *ctx, const uint8_t *data, size_t len)
{
    accum_t *a = (accum_t *)ctx;
    memcpy(a->buf + a->len, data, len);
    a->len += len;
    return len;   /* 재인코딩 대조엔 부분 쓰기 시뮬레이션이 필요 없다(그건 test_siap_frame.c 의 몫) */
}

static bool reencode(const gcollect_t *g, siap_mode_t mode, accum_t *out)
{
    (void)mode;   /* wire_code 는 g->hdr.msg_type 에 이미 반영돼 있다(원본 그대로 재사용) */
    siap_enc_t e;
    siap_tx_reset(&e);
    if (!siap_tx_put_hdr(&e, &g->hdr)) return false;

    if (g->has_nec) {
        if (!siap_tx_put_nec(&e, g->nec)) return false;
    } else if (g->has_rsc) {
        if (!siap_tx_put_rsc(&e, g->rsc)) return false;
        if (g->has_np) { if (!siap_tx_put_np(&e, &g->np)) return false; }
        else if (g->has_mcp) { if (!siap_tx_put_mcp(&e, &g->mcp)) return false; }
    } else if (g->has_np) {
        if (!siap_tx_put_np(&e, &g->np)) return false;
    } else if (g->has_mcp) {
        if (!siap_tx_put_mcp(&e, &g->mcp)) return false;
    }
    if (siap_tx_flush(&e, accum_write, out) != SIAP_TX_DONE) return false;

    for (uint16_t i = 0; i < g->did_count; i++) {
        if (!siap_tx_put_device_id(&e, g->device_ids[i])) return false;
        if (siap_tx_flush(&e, accum_write, out) != SIAP_TX_DONE) return false;
    }
    for (uint16_t i = 0; i < g->dmi_count; i++) {
        siap_result_t r = siap_tx_put_dmi(&e, &g->dmis[i]);
        if (!r.ok) return false;
        if (siap_tx_flush(&e, accum_write, out) != SIAP_TX_DONE) return false;
    }
    for (uint16_t i = 0; i < g->dp_count; i++) {
        siap_result_t r = siap_tx_put_dp(&e, &g->dps[i]);
        if (!r.ok) return false;
        if (siap_tx_flush(&e, accum_write, out) != SIAP_TX_DONE) return false;
    }
    return true;
}

/* ═══════════════════════════════════════════════════════════════
 *  3. 벡터 하나 처리
 * ═══════════════════════════════════════════════════════════════ */
static void run_vector(const char *line)
{
    char id[16] = "?", judgement[16] = "?", hex[2048] = "", clause_str[32] = "";
    long violation_code = -1;

    if (!extract_str(line, "id", id, sizeof(id))) { check("(id 없는 행 — 스캐너 실패)", false); return; }
    if (!extract_str(line, "judgement", judgement, sizeof(judgement))
        || !extract_str(line, "hex", hex, sizeof(hex))) {
        char label[64]; snprintf(label, sizeof(label), "%s: 필드 추출 실패", id);
        check(label, false);
        return;
    }

    bool has_violation = extract_first_violation(line, &violation_code, clause_str, sizeof(clause_str));

    uint8_t bytes[600];
    size_t nbytes = hex_to_bytes(hex, bytes, sizeof(bytes));

    char label[128];

    /* 스트리밍 콜백이 넘겨준 kind/n(g.kind/g.n) 만 보고 끝내지 않는다.
       그건 "디코더 전체가 무언가는 반환했다"만 증명할 뿐, 그 값이 골든이
       기대하는 kind/n과 같은지는 별도로 대조해야 한다. siap_resolve_kind()·
       siap_element_count() 를 헤더 바이트에서 직접, FSM과 독립적으로 다시
       불러 JSON의 기대값과 비교한다 — 동일 레이아웃 메시지끼리 잘못
       매핑해도( 재현: msg_type=0x0007 을 REQ_GET_NODE_DEVICE_PROPERTY_ALL
       로 잘못 반환) 이 대조가 없으면 상위 계층 테스트 전부가 녹색이었다. */
    if (nbytes >= SIAP_HEADER_BYTES) {
        char expect_kind_str[40] = "";
        bool has_kind = extract_str(line, "kind", expect_kind_str, sizeof(expect_kind_str));
        long expect_n = 0;
        bool has_n = extract_int(line, "n", &expect_n);

        siap_hdr_t h; size_t bp = 0;
        siap_decode_hdr(bytes, &bp, &h);
        siap_clause_t rk_clause;
        siap_kind_t actual_kind = siap_resolve_kind(h.msg_type, h.payload_len, SIAP_MODE_STRICT, &rk_clause);

        snprintf(label, sizeof(label), "%s: siap_resolve_kind() 가 골든의 기대 kind와 일치", id);
        if (has_kind)
            check(label, actual_kind == kind_from_str(expect_kind_str));
        else
            check(label, actual_kind == SIAP_KIND_NONE);

        if (has_kind && has_n && actual_kind != SIAP_KIND_NONE) {
            int32_t actual_n = siap_element_count(actual_kind, h.payload_len);
            snprintf(label, sizeof(label), "%s: siap_element_count() 가 골든의 기대 N과 일치", id);
            check(label, actual_n == (int32_t)expect_n);
        }
    }

    /* on_header 콜백은 "내 Node ID" 를 몰라 호출자가 흉내내야 한다
       (siap_frame.c 상단 주석). 골든 벡터 대부분은 공통 Node ID(0x00003)를
       쓰지만 경계값 벡터(B06 등)는 20bit 최댓값 같은 다른 값을 정당하게
       싣는다 — 그 값을 그대로 "내 주소"로 인정해야 정상 판정이 유지된다.
       유일한 예외는 위반 케이스 2(미등록 Node ID) 로, 그 벡터만 프레임의
       Node ID 와 다른 값을 "내 주소"로 세팅해 의도적으로 불일치시킨다. */
    long header_node_id = 3;
    (void)extract_int(line, "Node ID", &header_node_id);
    gcollect_t g = {0};
    g.self_node_id = (violation_code == SIAP_RSC_INVALID_NODE_ID)
                          ? 3u : (uint32_t)header_node_id;
    siap_dec_t d;
    siap_dec_init(&d, make_sink(&g), SIAP_MODE_STRICT);
    for (size_t i = 0; i < nbytes; i++) siap_dec_feed(&d, bytes[i]);

    if (strcmp(judgement, "normal") == 0 || strcmp(judgement, "alert") == 0) {
        snprintf(label, sizeof(label), "%s: 디코드 SUCCESS (judgement=%s)", id, judgement);
        check(label, g.end_calls == 1 && g.end_rsc == SIAP_RSC_SUCCESS);

        accum_t out = {0};
        bool enc_ok = reencode(&g, SIAP_MODE_STRICT, &out);
        snprintf(label, sizeof(label), "%s: 재인코딩 성공", id);
        check(label, enc_ok);

        snprintf(label, sizeof(label), "%s: 재인코딩 바이트열이 원본 hex와 일치 (왕복)", id);
        check(label, enc_ok && out.len == nbytes && memcmp(out.buf, bytes, nbytes) == 0);
    } else if (strcmp(judgement, "violation") == 0) {
        siap_rsc_t expect_rsc = (siap_rsc_t)violation_code;
        siap_clause_t expect_clause = parse_clause(clause_str);
        snprintf(label, sizeof(label), "%s: 위반 판정 RSC 일치 (기대 0x%02lX)", id, violation_code);
        check(label, has_violation && g.end_calls == 1 && g.end_rsc == expect_rsc);
        snprintf(label, sizeof(label), "%s: 위반 판정 clause 일치 (기대 \"%s\")", id, clause_str);
        check(label, has_violation && g.end_clause == expect_clause);
    } else {
        snprintf(label, sizeof(label), "%s: 알 수 없는 judgement \"%s\"", id, judgement);
        check(label, false);
    }
}

/* ═══════════════════════════════════════════════════════════════
 *  4. 파일 로딩 — 전체를 메모리에 올리고 줄 단위로 순회한다
 * ═══════════════════════════════════════════════════════════════ */
int main(void)
{
    printf("골든 벡터 53건 전량 왕복 호스트 유닛테스트\n");
    printf("(%s)\n\n", GOLDEN_PATH);

    FILE *f = fopen(GOLDEN_PATH, "rb");
    if (!f) {
        printf("  FAIL  골든 벡터 파일을 열 수 없다: %s\n", GOLDEN_PATH);
        printf("        (cd project_code/firmware/tests 에서 실행했는지 확인)\n");
        return 1;
    }
    fseek(f, 0, SEEK_END);
    long fsize = ftell(f);
    fseek(f, 0, SEEK_SET);
    char *content = (char *)malloc((size_t)fsize + 1);
    if (!content) { fclose(f); printf("  FAIL  메모리 할당 실패\n"); return 1; }
    size_t rd = fread(content, 1, (size_t)fsize, f);
    content[rd] = '\0';
    fclose(f);

    int vector_count = 0;
    char *cursor = content;
    while (*cursor) {
        char *nl = strchr(cursor, '\n');
        if (nl) *nl = '\0';
        size_t l = strlen(cursor);
        if (l > 0 && cursor[l - 1] == '\r') cursor[l - 1] = '\0';   /* CRLF 방어 */
        if (strlen(cursor) > 0) {
            run_vector(cursor);
            vector_count++;
        }
        if (!nl) break;
        cursor = nl + 1;
    }
    free(content);

    check("골든 벡터 53건 전량을 읽었다", vector_count == 53);

    printf("\n  %d/%d 통과 (벡터 %d건 처리)\n", g_passed, g_total, vector_count);
    return (g_passed == g_total) ? 0 : 1;
}
