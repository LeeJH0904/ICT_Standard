/*
 * 골든 벡터 53건 전량 교차비교 덤프 — tools/xcodec_verify.py 전용 (단계 3 출구②).
 *
 * test_golden.c 와 같은 얕은 JSON 스캐너·디코드·재인코딩 경로를 쓴다(그
 * 로직을 다시 검증하지 않는다 — test_golden.c 가 이미 53/53 왕복을
 * 확인한다). 이 파일이 새로 하는 일은 그 결과를 stdout 으로 내보내는
 * 것뿐이다 — Python(siap/codec.py) 출력과 대조하기 위해서다.
 *
 * F-136/F-212 — judgement=normal/alert 는 재인코딩한 hex와 디코드 구조체의
 * 의미값 서명을, judgement=violation 은 C 디코더의 거부 판정(RSC+clause)을
 * 낸다. 예전에는 violation 9건을
 * 아예 건너뛰고 "44+9=53"이라는 항등식에만 포함시켜, xcodec_verify.py 가
 * 53건 전량을 대조한다는 개발_착수_지시서 §3.5 출구 문구를 실제로는
 * 충족하지 못했다.
 *
 * F-246 — 제출본(최종_제출물_폴더/ICT_Test) 블라인드 주석 정리 과정에서 위
 * "F-136/F-212 — " 줄이 `*(/)judgement=…` 로 뭉개지며 이 블록 주석이 조기
 * 종료돼 컴파일이 깨졌다(제출본 전용 결함). dev 원본인 이 파일은 정상이며,
 * 제출본 사본만 별도로 정정했다.
 *
 * 실행: cd project_code/firmware/tests && make dump_golden && ./dump_golden
 * 출력 형식(셋 중 하나, 공백으로 구분):
 *   "<id> <hex>"                  — normal/alert, 재인코딩된 바이트열
 *   "<id> SEMANTIC <bits:value,...>" — normal/alert, 디코드 의미값
 *   "<id> VIOLATION <rsc> <clause>" — violation, 거부 판정
 * 실패한 벡터는 stderr 에 "SKIP <id> <이유>" 로 남기고 stdout 에는 내지 않는다.
 */
#include "../core/siap_frame.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define GOLDEN_PATH "../../contracts/vectors/golden.jsonl"

/* ═══ 아래 세 구획(얕은 JSON 스캐너 · gcollect_t 수집기 · reencode())은
   test_golden.c 와 의도적으로 같은 모양이다 — 같은 골든 파일을 같은
   방식으로 읽어야 "재인코딩"이라는 절차 자체가 두 파일 사이에서 갈리지
   않는다. 로직을 공유 헤더로 뽑지 않은 이유는 이 프로젝트의 다른 test_*.c
   들도 각자 자기 완결적이기 때문이다(빌드 단위를 독립적으로 유지). */

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
        if (*p == '\\' && p[1]) p++;
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

/* violations[0] 의 code 만 본다 — 위반 벡터는 전부 위반 1건짜리다. F-136 —
   X02(unregistered_node)를 올바르게 재현하려면 이 code 로 self_node_id
   시뮬레이션을 결정해야 한다(test_golden.c::run_vector 와 동일 원칙). */
static bool extract_first_violation_code(const char *line, long *code)
{
    const char *v = find_key(line, "violations");
    if (!v) return false;
    const char *bracket = strchr(v, '[');
    if (!bracket) return false;
    if (bracket[1] == ']') return false;   /* violations: [] */
    return extract_int(bracket, "code", code);
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
    int end_calls;
    siap_rsc_t end_rsc;
    siap_clause_t end_clause;   /* F-136 — 위반 벡터 교차비교에 쓴다 */
    uint32_t self_node_id;      /* F-136 — X02(INVALID_NODE_ID) 재현용 */
} gcollect_t;

static int8_t g_on_header(void *ctx, const siap_hdr_t *h, siap_kind_t k, uint16_t n)
{
    gcollect_t *g = (gcollect_t *)ctx;
    g->hdr = *h; g->kind = k; g->n = n;
    /* F-136 — 위반 2(미등록 Node ID)는 test_golden.c::g_on_header 와 동일한
       원칙으로 재현한다: dump_vector() 가 벡터별로 self_node_id 를 정해
       주입한다. 나머지 벡터는 프레임 자신의 Node ID 를 그대로 "내 주소"로
       인정해 이 판정에 걸리지 않는다. */
    if (h->node_id != g->self_node_id) return -(int8_t)SIAP_RSC_INVALID_NODE_ID;
    return 0;
}

static int8_t g_on_fixed(void *ctx, const uint8_t *buf, uint8_t len)
{
    gcollect_t *g = (gcollect_t *)ctx;
    size_t bp;
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

/* parse_clause()(test_golden.c)의 역함수 — clause 를 golden.jsonl 의
   "clause" 필드와 같은 문자열로 되돌린다. F-136. */
static const char *clause_to_str(siap_clause_t c)
{
    switch (c) {
    case SIAP_CLAUSE_7_3_1:      return "7.3.1";
    case SIAP_CLAUSE_TABLE_7_2:  return "\xed\x91\x9c 7-2";   /* "표 7-2" (UTF-8) */
    case SIAP_CLAUSE_TABLE_7_6:  return "\xed\x91\x9c 7-6";   /* "표 7-6" */
    case SIAP_CLAUSE_TABLE_7_14: return "\xed\x91\x9c 7-14";  /* "표 7-14" */
    case SIAP_CLAUSE_7_3_2:      return "7.3.2";
    default:                     return "";
    }
}

/* F-212 — 디코드한 C 구조체의 의미값을 wire 필드 순서의 `bits:value`
   서명으로 내보낸다. 원본 hex를 다시 인코드하는 것만으로는 C의 encode와
   decode가 같은 방식으로 틀린 경우를 잡지 못한다. 이 서명은 Python이
   golden.jsonl의 독립 fields 의미값으로 만든 서명과 대조한다. */
static void semantic_field(bool *first, unsigned bits, uint32_t value)
{
    printf("%s%u:%lu", *first ? "" : ",", bits, (unsigned long)value);
    *first = false;
}

static void semantic_dmi(bool *first, const siap_dmi_t *d)
{
    semantic_field(first, 8, d->device_id);
    semantic_field(first, 1, d->dev_type);
    semantic_field(first, 8, d->subtype);
    semantic_field(first, 2, d->value_type);
    semantic_field(first, 5, 0);
    semantic_field(first, 32, d->value);
}

static void semantic_dp(bool *first, const siap_dp_t *d)
{
    semantic_dmi(first, &d->main);
    semantic_field(first, 2, d->transfer_mode);
    semantic_field(first, 14, d->period);
    semantic_field(first, 32, d->lower_value);
    semantic_field(first, 32, d->upper_value);
    semantic_field(first, 32, d->lower_limit);
    semantic_field(first, 32, d->upper_limit);
    semantic_field(first, 32, d->precision);
    semantic_field(first, 8, d->status);
}

static void dump_semantic(const char *id, const gcollect_t *g)
{
    bool first = true;
    printf("%s SEMANTIC ", id);
    semantic_field(&first, 8, g->hdr.version);
    semantic_field(&first, 14, g->hdr.msg_type);
    semantic_field(&first, 2, g->hdr.trans_type);
    semantic_field(&first, 16, g->hdr.msg_id);
    semantic_field(&first, 16, g->hdr.payload_len);
    semantic_field(&first, 20, g->hdr.gcg_id);
    semantic_field(&first, 20, g->hdr.node_id);
    if (g->has_nec) semantic_field(&first, 8, (uint32_t)g->nec);
    if (g->has_rsc) semantic_field(&first, 8, (uint32_t)g->rsc);
    if (g->has_np) {
        semantic_field(&first, 8, g->np.sw_version);
        semantic_field(&first, 20, g->np.gcg_id);
        semantic_field(&first, 20, g->np.node_id);
        semantic_field(&first, 8, g->np.status);
        semantic_field(&first, 8, g->np.num_devices);
    }
    if (g->has_mcp) {
        semantic_field(&first, 16, g->mcp.recv_timeout);
        semantic_field(&first, 8, g->mcp.num_retry);
        semantic_field(&first, 16, g->mcp.noti_error_interval);
        semantic_field(&first, 16, g->mcp.keep_alive_interval);
    }
    for (uint16_t i = 0; i < g->did_count; i++)
        semantic_field(&first, 8, g->device_ids[i]);
    for (uint16_t i = 0; i < g->dmi_count; i++) semantic_dmi(&first, &g->dmis[i]);
    for (uint16_t i = 0; i < g->dp_count; i++) semantic_dp(&first, &g->dps[i]);
    printf("\n");
}

static siap_sink_t make_sink(gcollect_t *g)
{
    siap_sink_t s;
    s.on_header = g_on_header; s.on_fixed = g_on_fixed;
    s.on_element = g_on_element; s.on_end = g_on_end; s.ctx = g;
    return s;
}

typedef struct { uint8_t buf[600]; size_t len; } accum_t;

static size_t accum_write(void *ctx, const uint8_t *data, size_t len)
{
    accum_t *a = (accum_t *)ctx;
    memcpy(a->buf + a->len, data, len);
    a->len += len;
    return len;
}

static bool reencode(const gcollect_t *g, accum_t *out)
{
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

static void dump_vector(const char *line)
{
    char id[16] = "?", judgement[16] = "?", hex[2048] = "";
    if (!extract_str(line, "id", id, sizeof(id))) return;
    if (!extract_str(line, "judgement", judgement, sizeof(judgement))
        || !extract_str(line, "hex", hex, sizeof(hex))) {
        fprintf(stderr, "SKIP %s 필드 추출 실패\n", id);
        return;
    }

    uint8_t bytes[600];
    size_t nbytes = hex_to_bytes(hex, bytes, sizeof(bytes));

    /* F-136 — Node ID 시뮬레이션. 위반 2(INVALID_NODE_ID, X02)만 "내 주소"를
       프레임의 Node ID 와 다르게 세팅해 의도적으로 불일치시킨다. 그 외
       전부는 프레임 자신의 Node ID 를 그대로 "내 주소"로 인정한다
       (test_golden.c::run_vector 와 동일 원칙). */
    long violation_code = -1;
    bool has_violation = extract_first_violation_code(line, &violation_code);
    long header_node_id = 3;
    (void)extract_int(line, "Node ID", &header_node_id);

    gcollect_t g = {0};
    g.self_node_id = (has_violation && violation_code == SIAP_RSC_INVALID_NODE_ID)
                          ? 3u : (uint32_t)header_node_id;
    siap_dec_t d;
    siap_dec_init(&d, make_sink(&g), SIAP_MODE_STRICT);
    for (size_t i = 0; i < nbytes; i++) siap_dec_feed(&d, bytes[i]);

    /* F-136 — violation 벡터는 재인코딩 대상이 아니지만(고의로 망가뜨린
       바이트열), C 디코더의 거부 판정(RSC+clause)만은 Python 과 대조할 수
       있고 대조해야 한다. "44+9=53"이라는 항등식에만 기대지 않는다. */
    if (strcmp(judgement, "violation") == 0) {
        if (g.end_calls != 1 || g.end_rsc == SIAP_RSC_SUCCESS) {
            fprintf(stderr, "SKIP %s 위반이 재현되지 않음(end_calls=%d, end_rsc=%d)\n",
                    id, g.end_calls, (int)g.end_rsc);
            return;
        }
        printf("%s VIOLATION %d %s\n", id, (int)g.end_rsc, clause_to_str(g.end_clause));
        return;
    }
    if (strcmp(judgement, "normal") != 0 && strcmp(judgement, "alert") != 0) {
        fprintf(stderr, "SKIP %s 알 수 없는 judgement \"%s\"\n", id, judgement);
        return;
    }

    if (g.end_calls != 1 || g.end_rsc != SIAP_RSC_SUCCESS) {
        fprintf(stderr, "SKIP %s 디코드 실패\n", id);
        return;
    }
    dump_semantic(id, &g);
    accum_t out = {0};
    if (!reencode(&g, &out)) {
        fprintf(stderr, "SKIP %s 재인코딩 실패\n", id);
        return;
    }
    printf("%s ", id);
    for (size_t i = 0; i < out.len; i++) printf("%02X", out.buf[i]);
    printf("\n");
}

int main(void)
{
    FILE *f = fopen(GOLDEN_PATH, "rb");
    if (!f) {
        fprintf(stderr, "골든 벡터 파일을 열 수 없다: %s\n", GOLDEN_PATH);
        return 1;
    }
    fseek(f, 0, SEEK_END);
    long fsize = ftell(f);
    fseek(f, 0, SEEK_SET);
    char *content = (char *)malloc((size_t)fsize + 1);
    if (!content) { fclose(f); fprintf(stderr, "메모리 할당 실패\n"); return 1; }
    size_t rd = fread(content, 1, (size_t)fsize, f);
    content[rd] = '\0';
    fclose(f);

    char *cursor = content;
    while (*cursor) {
        char *nl = strchr(cursor, '\n');
        if (nl) *nl = '\0';
        size_t l = strlen(cursor);
        if (l > 0 && cursor[l - 1] == '\r') cursor[l - 1] = '\0';
        if (strlen(cursor) > 0) dump_vector(cursor);
        if (!nl) break;
        cursor = nl + 1;
    }
    free(content);
    return 0;
}
