/*
 * 노드 상태 머신 호스트 유닛테스트. 펌웨어 설계서 §6 / §8.1.
 * siap_io_t/siap_dev_ops_t 를 페이크로 채워 하드웨어 없이 8상태 전이 ·
 * pending 재전송(§6.4) · due 회전 커서(§6.4-a) · RES_SET_CONNECTION 오류
 * RSC 분류(§6.5) 를 검증한다(CLAUDE.md §0 "하드웨어 없이 표준 준수를
 * 검증할 수 있다").
 *
 * 실행: cd project_code/firmware/tests && make test_node_state && ./test_node_state
 * 종료 코드: 0 = 전부 통과, 1 = 실패 있음
 */
#include "../core/node_state.h"
#include <stdio.h>

static int g_total = 0;
static int g_passed = 0;

static void check(const char *name, int cond)
{
    g_total++;
    if (cond) g_passed++;
    printf("  %s  %s\n", cond ? "PASS" : "FAIL", name);
}

/* ═══════════════════════════════════════════════════════════════
 *  페이크 하드웨어 — siap_io_t / siap_dev_ops_t
 * ═══════════════════════════════════════════════════════════════ */
#define FIO_BUF 4096u

typedef struct {
    uint8_t rx[FIO_BUF]; size_t rx_len, rx_pos;   /* 게이트웨이 -> 노드 */
    uint8_t tx[FIO_BUF]; size_t tx_len;           /* 노드 -> 게이트웨이 (마지막 프레임만 담게 매 검사 전 비운다) */
    uint32_t now;
    bool link_error_once;
    /* 재현용 — UART 포화 흉내. budget_enabled 일 때만 write() 가
       budget_left 로 제한되고(그 이하는 0 을 돌려준다), 매 poll 전 테스트가
       budget_left 를 다시 채워 "poll당 최대 N byte" 를 흉내낸다. 기본
       false 라 다른 모든 테스트의 즉시-전량-수신 가정은 그대로다. */
    bool     budget_enabled;
    uint16_t budget_left;
} fake_io_t;

static int8_t fio_read_byte(void *ctx, uint8_t *out)
{
    fake_io_t *c = (fake_io_t *)ctx;
    if (c->link_error_once) { c->link_error_once = false; return -1; }
    if (c->rx_pos >= c->rx_len) return 0;
    *out = c->rx[c->rx_pos++];
    return 1;
}
static int16_t fio_write(void *ctx, const uint8_t *buf, uint16_t len)
{
    fake_io_t *c = (fake_io_t *)ctx;
    uint16_t n = len;
    if (c->budget_enabled && n > c->budget_left) n = c->budget_left;
    if (c->tx_len + n > FIO_BUF) n = (uint16_t)(FIO_BUF - c->tx_len);
    for (uint16_t i = 0; i < n; i++) c->tx[c->tx_len++] = buf[i];
    if (c->budget_enabled) c->budget_left = (uint16_t)(c->budget_left - n);
    return (int16_t)n;
}
static uint32_t fio_millis(void *ctx) { return ((fake_io_t *)ctx)->now; }

#define SIAP_TEST_MAX_DEV 4
typedef struct {
    uint8_t  ids[SIAP_TEST_MAX_DEV];
    uint32_t values[SIAP_TEST_MAX_DEV];
    bool     fail[SIAP_TEST_MAX_DEV];
    uint8_t  n;
    uint8_t  last_write_id;
    uint32_t last_write_val;
    int      write_count;
    int      read_count;
} fake_dev_t;

static int8_t fdev_read(void *ctx, uint8_t device_id, uint32_t *raw)
{
    fake_dev_t *c = (fake_dev_t *)ctx;
    c->read_count++;
    for (uint8_t i = 0; i < c->n; i++) {
        if (c->ids[i] != device_id) continue;
        if (c->fail[i]) return -1;
        *raw = c->values[i];
        return 0;
    }
    return -1;
}
static int8_t fdev_write(void *ctx, uint8_t device_id, uint32_t raw)
{
    fake_dev_t *c = (fake_dev_t *)ctx;
    for (uint8_t i = 0; i < c->n; i++) {
        if (c->ids[i] != device_id) continue;
        c->values[i] = raw;
        c->last_write_id = device_id;
        c->last_write_val = raw;
        c->write_count++;
        return 0;
    }
    return -1;
}

/* ═══════════════════════════════════════════════════════════════
 *  프레임 조립 — "게이트웨이" 쪽 송신을 흉내낸다. siap_tx_put_xxx 와
 *  siap_encode_ack 를 그대로 재사용한다(코덱을 다시 구현하지 않는다).
 * ═══════════════════════════════════════════════════════════════ */
static void rx_append(fake_io_t *io, const siap_enc_t *e)
{
    size_t n = e->bitpos / 8u;
    for (size_t i = 0; i < n && io->rx_len < FIO_BUF; i++) io->rx[io->rx_len++] = e->win[i];
}

/* TX_WINDOW(51B, siap_frame.h)는 헤더+요소 하나분이다(§5.8) — N개 DEVICE_PROPERTY
   를 한 인코더 버퍼에 다 쌓을 수 없다. 청크(헤더+RSC+NP, 그 다음 요소마다 1개)
   단위로 리셋·재사용하며 rx 큐에 이어 붙인다. */
static void push_res_set_connection(fake_io_t *io, uint32_t gcg, uint32_t nid, uint16_t msg_id,
                                     siap_rsc_t rsc, const siap_dp_t *dps, uint8_t n)
{
    siap_enc_t e; siap_tx_reset(&e);
    uint16_t plen = (uint16_t)(SIAP_RSC_BYTES + SIAP_NP_BYTES + SIAP_DP_BYTES * n);
    siap_hdr_t h = { SIAP_VERSION, siap_wire_code(SIAP_RES_SET_CONNECTION, SIAP_MODE_STRICT),
                      SIAP_TRANS_UNICAST, msg_id, plen, gcg, nid };
    if (!siap_tx_put_hdr(&e, &h)) return;
    if (!siap_tx_put_rsc(&e, rsc)) return;
    siap_np_t np = { 0x10, gcg, nid, SIAP_STATUS_NORMAL, n };
    if (!siap_tx_put_np(&e, &np)) return;
    rx_append(io, &e);
    for (uint8_t i = 0; i < n; i++) {
        siap_tx_reset(&e);
        siap_result_t r = siap_tx_put_dp(&e, &dps[i]);
        if (!r.ok) return;
        rx_append(io, &e);
    }
}

/* 게이트웨이가 노드의 디바이스 구성 선언(REQ_SET_NODE_DEVICE_PROPERTY_ALL)
   에 돌려주는 응답. LAYOUT {RSC_BYTES,0} — 고정부에 RSC 만 있다. */
static void push_res_set_node_device_property_all(fake_io_t *io, uint32_t gcg, uint32_t nid,
                                                   uint16_t msg_id, siap_rsc_t rsc)
{
    siap_enc_t e; siap_tx_reset(&e);
    siap_hdr_t h = { SIAP_VERSION,
                      siap_wire_code(SIAP_RES_SET_NODE_DEVICE_PROPERTY_ALL, SIAP_MODE_STRICT),
                      SIAP_TRANS_UNICAST, msg_id, SIAP_RSC_BYTES, gcg, nid };
    if (!siap_tx_put_hdr(&e, &h)) return;
    if (!siap_tx_put_rsc(&e, rsc)) return;
    rx_append(io, &e);
}

static void push_ack_for(fake_io_t *io, uint32_t gcg, uint32_t nid, uint16_t msg_id)
{
    siap_hdr_t req = { SIAP_VERSION, 0, SIAP_TRANS_UNICAST, msg_id, 0, gcg, nid };
    siap_enc_t e;
    if (!siap_encode_ack(&req, SIAP_MODE_STRICT, &e)) return;
    rx_append(io, &e);
}

static void push_empty(fake_io_t *io, siap_kind_t kind, uint32_t gcg, uint32_t nid, uint16_t msg_id)
{
    siap_enc_t e; siap_tx_reset(&e);
    siap_hdr_t h = { SIAP_VERSION, siap_wire_code(kind, SIAP_MODE_STRICT),
                      SIAP_TRANS_UNICAST, msg_id, 0, gcg, nid };
    if (!siap_tx_put_hdr(&e, &h)) return;
    rx_append(io, &e);
}

static void push_req_set_device_control(fake_io_t *io, uint32_t gcg, uint32_t nid, uint16_t msg_id,
                                         uint8_t device_id, uint8_t dev_type, uint8_t subtype,
                                         uint8_t value_type, uint32_t value)
{
    siap_enc_t e; siap_tx_reset(&e);
    siap_hdr_t h = { SIAP_VERSION, siap_wire_code(SIAP_REQ_SET_DEVICE_CONTROL, SIAP_MODE_STRICT),
                      SIAP_TRANS_UNICAST, msg_id, SIAP_DMI_BYTES, gcg, nid };
    if (!siap_tx_put_hdr(&e, &h)) return;
    siap_dmi_t dmi = { device_id, dev_type, subtype, value_type, value };
    siap_result_t r = siap_tx_put_dmi(&e, &dmi);
    if (!r.ok) return;
    rx_append(io, &e);
}

static siap_hdr_t decode_tx_hdr(const fake_io_t *io)
{
    siap_hdr_t h; size_t bp = 0;
    siap_decode_hdr(io->tx, &bp, &h);
    return h;
}

/* pending 이 빌 때까지 매 회 즉시 ACK 를 돌려주며 poll 한다(§6.2-a(2)).
   회전 커서가 한 번에 due 소스 하나씩만 보내므로, 같은 "지금 시각"
   안에서 여러 개가 밀려 있으면 이 루프가 전부 소진시킨다. */
static void drain_pending_with_ack(siap_node_t *node, fake_io_t *io, uint32_t gcg, uint32_t nid,
                                    int *dv_count, int *ka_count, int *err_count)
{
    for (int guard = 0; guard < 8 && node->pending.kind != (uint8_t)SIAP_KIND_NONE; guard++) {
        siap_kind_t k = (siap_kind_t)node->pending.kind;
        if (dv_count && k == SIAP_NOTI_DEVICE_VALUE) (*dv_count)++;
        if (ka_count && k == SIAP_NOTI_KEEP_ALIVE) (*ka_count)++;
        if (err_count && k == SIAP_NOTI_ERROR) (*err_count)++;
        uint16_t mid = node->pending.msg_id;
        push_ack_for(io, gcg, nid, mid);
        siap_node_poll(node);
    }
}

/* ═══════════════════════════════════════════════════════════════
 *  공통 픽스처
 * ═══════════════════════════════════════════════════════════════ */
#define GCG 0x00001u
#define NID 0x00003u

static siap_dp_t make_device(uint8_t id, uint8_t dev_type, uint8_t subtype,
                              uint8_t value_type, uint8_t transfer_mode, uint16_t period)
{
    siap_dp_t d;
    d.main.device_id = id;
    d.main.dev_type = dev_type;
    d.main.subtype = subtype;
    d.main.value_type = value_type;
    d.main.value = 0;
    d.transfer_mode = transfer_mode;
    d.period = period;
    d.lower_value = 0; d.upper_value = 0; d.lower_limit = 0; d.upper_limit = 0; d.precision = 0;
    d.status = SIAP_STATUS_NORMAL;
    return d;
}

typedef struct {
    siap_node_t node;
    fake_io_t   io;
    fake_dev_t  dev;
    siap_dp_t   devices[SIAP_TEST_MAX_DEV];
} fixture_t;

/* device_count 개의 온도류 센서(Periodic, period 초)로 노드를 초기화하고
   RUNNING 까지 진행시킨다 — 개별 테스트가 여기서부터 이어 붙인다. */
static void fixture_boot(fixture_t *f, uint8_t device_count, uint16_t period)
{
    f->io.rx_len = f->io.rx_pos = f->io.tx_len = 0;
    f->io.now = 0;
    f->io.link_error_once = false;
    f->io.budget_enabled = false;
    f->io.budget_left = 0;
    f->dev.n = device_count;
    f->dev.write_count = 0; f->dev.read_count = 0;
    for (uint8_t i = 0; i < device_count; i++) {
        f->dev.ids[i] = (uint8_t)(1u + i);
        f->dev.values[i] = 100u + i;
        f->dev.fail[i] = false;
        f->devices[i] = make_device((uint8_t)(1u + i), SIAP_DEV_SENSOR, SIAP_SUBTYPE_TEMPERATURE,
                                     SIAP_VALUE_TYPE_INT, SIAP_TM_PERIODIC, period);
    }

    siap_io_t io_iface = { fio_read_byte, fio_write, fio_millis, &f->io };
    siap_dev_ops_t dev_iface = { fdev_read, fdev_write, &f->dev };
    static siap_io_t io_static; static siap_dev_ops_t dev_static;
    io_static = io_iface; dev_static = dev_iface;

    siap_node_cfg_t cfg;
    cfg.gcg_id = GCG; cfg.node_id = NID; cfg.sw_version = 0x10;
    cfg.io = &io_static; cfg.dev_ops = &dev_static;
    cfg.devices = f->devices; cfg.device_count = device_count;
    cfg.profile = SIAP_PROFILE_DEFAULT;
    cfg.mode = SIAP_MODE_STRICT;
    bool ok = siap_node_init(&f->node, &cfg);
    (void)ok;
}

/* fixture_boot 과 달리 디바이스를 그대로 넘겨받는다 — Transfer Mode ·
   Period · Lower/Upper Value 를 디바이스별로 다르게 둬야 하는
   회귀 테스트 전용(디바이스별 스캔 스케줄·Event 임계값 검증). */
static void fixture_boot_devices(fixture_t *f, const siap_dp_t *devs, const uint32_t *values, uint8_t n)
{
    f->io.rx_len = f->io.rx_pos = f->io.tx_len = 0;
    f->io.now = 0;
    f->io.link_error_once = false;
    f->io.budget_enabled = false;
    f->io.budget_left = 0;
    f->dev.n = n;
    f->dev.write_count = 0; f->dev.read_count = 0;
    for (uint8_t i = 0; i < n; i++) {
        f->dev.ids[i] = devs[i].main.device_id;
        f->dev.values[i] = values[i];
        f->dev.fail[i] = false;
        f->devices[i] = devs[i];
        f->devices[i].main.value = values[i];
    }

    siap_io_t io_iface = { fio_read_byte, fio_write, fio_millis, &f->io };
    siap_dev_ops_t dev_iface = { fdev_read, fdev_write, &f->dev };
    static siap_io_t io_static2; static siap_dev_ops_t dev_static2;
    io_static2 = io_iface; dev_static2 = dev_iface;

    siap_node_cfg_t cfg;
    cfg.gcg_id = GCG; cfg.node_id = NID; cfg.sw_version = 0x10;
    cfg.io = &io_static2; cfg.dev_ops = &dev_static2;
    cfg.devices = f->devices; cfg.device_count = n;
    cfg.profile = SIAP_PROFILE_DEFAULT;
    cfg.mode = SIAP_MODE_STRICT;
    bool ok = siap_node_init(&f->node, &cfg);
    (void)ok;
}

/* BOOT->INIT->CONNECTING->(RES_SET_CONNECTION SUCCESS)->RUNNING */
static void fixture_run_to_running(fixture_t *f)
{
    siap_node_poll(&f->node);   /* BOOT->INIT->CONNECTING, REQ_SET_CONNECTION 송신 */
    uint16_t mid = f->node.pending.msg_id;
    push_res_set_connection(&f->io, GCG, NID, mid, SIAP_RSC_SUCCESS, f->devices, f->dev.n);
    siap_node_poll(&f->node);   /* -> RUNNING, 이어서 REQ_SET_NODE_DEVICE_PROPERTY_ALL 선언 */

    /* 연결 성공 직후 노드가 자기 구성을 선언한다. 게이트웨이 RES 로
       그 handshake 를 마쳐 pending 을 비운다 — 개별 테스트는 "구성 선언이
       끝난 RUNNING"(pending 빔)에서 이어 붙인다. 선언 자체의 검증은
       test_connection_declares_node_device_property_all_F198 가 담당한다. */
    if (f->node.pending.kind == (uint8_t)SIAP_REQ_SET_NODE_DEVICE_PROPERTY_ALL) {
        push_res_set_node_device_property_all(&f->io, GCG, NID, f->node.pending.msg_id,
                                              SIAP_RSC_SUCCESS);
        siap_node_poll(&f->node);
    }
}

/* ═══════════════════════════════════════════════════════════════
 *  1. 초기화 검증 — 펌웨어 설계서 §4.1-a 진입점 범위 검증표
 * ═══════════════════════════════════════════════════════════════ */
static void test_init_validation_4_1_a(void)
{
    fake_io_t io = {0}; fake_dev_t dev = {0};
    siap_io_t io_iface = { fio_read_byte, fio_write, fio_millis, &io };
    siap_dev_ops_t dev_iface = { fdev_read, fdev_write, &dev };
    siap_dp_t devs[2] = {
        make_device(1, SIAP_DEV_SENSOR, SIAP_SUBTYPE_TEMPERATURE, SIAP_VALUE_TYPE_INT, SIAP_TM_PERIODIC, 60),
        make_device(2, SIAP_DEV_SENSOR, SIAP_SUBTYPE_HUMIDITY, SIAP_VALUE_TYPE_INT, SIAP_TM_PERIODIC, 60),
    };
    siap_node_cfg_t base;
    base.gcg_id = GCG; base.node_id = NID; base.sw_version = 0x10;
    base.io = &io_iface; base.dev_ops = &dev_iface;
    base.devices = devs; base.device_count = 2;
    base.profile = SIAP_PROFILE_DEFAULT; base.mode = SIAP_MODE_STRICT;

    siap_node_t n;
    check("init_4_1_a: 정상 설정 수락", siap_node_init(&n, &base));

    siap_node_cfg_t bad = base;
    bad.gcg_id = 0x00100000u;   /* 2^20 초과 */
    check("init_4_1_a: gcg_id 20bit 초과 거부(표 7-8)", !siap_node_init(&n, &bad));

    bad = base; bad.node_id = 0x00100000u;
    check("init_4_1_a: node_id 20bit 초과 거부(표 7-8)", !siap_node_init(&n, &bad));

    bad = base; bad.device_count = 0;
    check("init_4_1_a: device_count=0 거부", !siap_node_init(&n, &bad));

    bad = base; bad.device_count = (uint8_t)(SIAP_MAX_DEVICES_PER_NODE + 1u);
    check("init_4_1_a: device_count>16 거부", !siap_node_init(&n, &bad));

    siap_dp_t devs_badtype[2] = { devs[0], devs[1] };
    devs_badtype[0].main.value_type = SIAP_VALUE_TYPE_RESERVED;
    bad = base; bad.devices = devs_badtype;
    check("init_4_1_a: value_type=RESERVED(0x03) 거부(표 7-14)", !siap_node_init(&n, &bad));

    siap_dp_t devs_badsub[2] = { devs[0], devs[1] };
    devs_badsub[0].main.subtype = 0x40;   /* 미등록 — 기능 2 위반 케이스 7번과 동일 예시값 */
    bad = base; bad.devices = devs_badsub;
    check("init_4_1_a: 미등록 subtype 거부", !siap_node_init(&n, &bad));

    siap_dp_t devs_badperiod[2] = { devs[0], devs[1] };
    devs_badperiod[0].period = 0x4000u;   /* 14bit 초과 */
    bad = base; bad.devices = devs_badperiod;
    check("init_4_1_a: period 14bit 초과 거부(표 7-15)", !siap_node_init(&n, &bad));

    siap_dp_t devs_dup[2] = { devs[0], devs[1] };
    devs_dup[1].main.device_id = devs_dup[0].main.device_id;
    bad = base; bad.devices = devs_dup;
    check("init_4_1_a: device_id 중복 거부(노드 내 유일)", !siap_node_init(&n, &bad));
}

/* ═══════════════════════════════════════════════════════════════
 *  2. 연결 설정 — 8.1.1 / §6.1 / §6.5
 * ═══════════════════════════════════════════════════════════════ */
static void test_boot_to_connecting_sends_req_8_1_1(void)
{
    fixture_t f; fixture_boot(&f, 1, 60);
    siap_node_poll(&f.node);
    check("8_1_1: 최초 poll 후 CONNECTING", f.node.state == SIAP_NS_CONNECTING);
    siap_hdr_t h = decode_tx_hdr(&f.io);
    check("8_1_1: REQ_SET_CONNECTION 송신", h.msg_type == siap_wire_code(SIAP_REQ_SET_CONNECTION, SIAP_MODE_STRICT));
    check("8_1_1: 페이로드 없음(plen=0)", h.payload_len == 0);
    check("8_1_1: 헤더의 GCG/Node ID 가 설정과 일치", h.gcg_id == GCG && h.node_id == NID);
    check("최초 Message Identifier == 0(7.2.2 원문 그대로, 0도 유효)", f.node.pending.msg_id == 0);
}

static void test_connecting_success_to_running_8_1_1(void)
{
    fixture_t f; fixture_boot(&f, 1, 60);
    fixture_run_to_running(&f);
    check("8_1_1: RES_SET_CONNECTION SUCCESS -> RUNNING", f.node.state == SIAP_NS_RUNNING);
    check("6_2: pending 해제", f.node.pending.kind == (uint8_t)SIAP_KIND_NONE);
    check("6_2: NODE_PROPERTY/DEVICE_PROPERTY 적용(디바이스 상태 보존)",
          f.node.cfg.devices[0].main.device_id == 1);
}

static void test_connecting_retryable_rsc_waits_for_timeout_6_5(void)
{
    fixture_t f; fixture_boot(&f, 1, 60);
    siap_node_poll(&f.node);
    uint16_t mid1 = f.node.pending.msg_id;
    push_res_set_connection(&f.io, GCG, NID, mid1, SIAP_RSC_INVALID_NODE_ID, NULL, 0);
    siap_node_poll(&f.node);
    check("6_5: INVALID_NODE_ID(재시도 가능) 수신 직후에도 CONNECTING 유지",
          f.node.state == SIAP_NS_CONNECTING);
    check("6_5: msg_id 즉시 바뀌지 않음(Timeout 후 재송신, §6.4)",
          f.node.pending.msg_id == mid1);

    f.io.tx_len = 0;
    f.io.now += 2000u;   /* Message Receive Timeout 기본 2s 경과 */
    siap_node_poll(&f.node);
    check("6_5: Timeout 후 같은 msg_id 로 재송신", f.node.pending.msg_id == mid1);
    check("6_5: 재전송 횟수 증가", f.node.pending.retry == 1);
    siap_hdr_t h = decode_tx_hdr(&f.io);
    check("6_5: 재송신 프레임도 REQ_SET_CONNECTION", h.msg_type == siap_wire_code(SIAP_REQ_SET_CONNECTION, SIAP_MODE_STRICT));

    /* 재전송 소진 -> DISCONNECTED -> 백오프 후 새 REQ_SET_CONNECTION(새 msg_id) */
    for (uint8_t r = 0; r < SIAP_PROFILE_DEFAULT.num_retry; r++) f.io.now += 2000u, siap_node_poll(&f.node);
    check("6_4: 재전송 소진 -> DISCONNECTED", f.node.state == SIAP_NS_DISCONNECTED);
    f.io.now += 2000u;   /* backoff = Timeout*2^0 = 2s 이상 경과 */
    siap_node_poll(&f.node);
    check("6_2: 백오프 만료 -> CONNECTING 로 복귀", f.node.state == SIAP_NS_CONNECTING);
    check("6_2: 새 REQ_SET_CONNECTION 은 새 msg_id", f.node.pending.msg_id != mid1);
}

static void test_connecting_unretryable_rsc_halts_6_5_F076(void)
{
    fixture_t f; fixture_boot(&f, 1, 60);
    siap_node_poll(&f.node);
    uint16_t mid1 = f.node.pending.msg_id;
    push_res_set_connection(&f.io, GCG, NID, mid1, SIAP_RSC_INVALID_VERSION, NULL, 0);
    siap_node_poll(&f.node);
    check("6_5/재시도 불가 RSC 수신 -> HALTED", f.node.state == SIAP_NS_HALTED);

    /* HALTED — 수신 프레임을 읽어 버리고 응답하지 않는다 */
    f.io.tx_len = 0;
    push_req_set_device_control(&f.io, GCG, NID, 99, 1, SIAP_DEV_SENSOR,
                                 SIAP_SUBTYPE_TEMPERATURE, SIAP_VALUE_TYPE_INT, 1234u);
    siap_node_poll(&f.node);
    check("HALTED 는 수신 바이트를 소비만 하고", f.io.rx_pos == f.io.rx_len);
    check("어떤 응답도 보내지 않는다(상태 무관 전이의 유일한 예외)", f.io.tx_len == 0);
    check("HALTED 는 나가는 전이가 없다", f.node.state == SIAP_NS_HALTED);
}

/* ═══════════════════════════════════════════════════════════════
 *  3. 주기 알림 회전 — §6.4-a ( 재현 방지)
 * ═══════════════════════════════════════════════════════════════ */
static void test_periodic_rotation_no_starvation_6_4_a_100cycles(void)
{
    fixture_t f; fixture_boot(&f, 1, 60);   /* Period 60s == Keep Alive 60s(§6.3) */
    fixture_run_to_running(&f);
    check("6_4_a: RUNNING 진입", f.node.state == SIAP_NS_RUNNING);

    int dv = 0, ka = 0;
    for (int cyc = 0; cyc < 100; cyc++) {
        f.io.now += 60000u;
        siap_node_poll(&f.node);
        drain_pending_with_ack(&f.node, &f.io, GCG, NID, &dv, &ka, NULL);
    }
    check("6_4_a: 100주기에서 NOTI_DEVICE_VALUE 최소 45회(기아 없음)", dv >= 45);
    check("6_4_a: 100주기에서 NOTI_KEEP_ALIVE 최소 45회(기아 없음)", ka >= 45);
}

/* ═══════════════════════════════════════════════════════════════
 *  4. 디바이스 오류 — 8.2.1.1 / §6.1
 * ═══════════════════════════════════════════════════════════════ */
static void test_fault_enter_and_recover_8_2_1_1(void)
{
    fixture_t f; fixture_boot(&f, 2, 60);
    fixture_run_to_running(&f);
    f.dev.fail[0] = true;   /* device_id=1 을 오류로 만든다 */

    f.io.now += 60000u;
    siap_node_poll(&f.node);
    check("8_2_1_1: 주기 스캔 중 read_value 실패 -> FAULT", f.node.state == SIAP_NS_FAULT);
    check("8_2_1_1: 디바이스 Status = ABNORMAL", f.node.cfg.devices[0].status == SIAP_STATUS_ABNORMAL);
    check("8_2_1_1: pending = NOTI_ERROR", f.node.pending.kind == (uint8_t)SIAP_NOTI_ERROR);
    check("7_3_2: NEC = ERROR_DEVICE_INTERFACE(0x01)", f.node.pending.arg == (uint16_t)SIAP_NEC_ERROR_DEVICE_INTERFACE);

    /* 매 60s 마다 한 번만 poll 하는 이 테스트는 30s 주기의 Notify Error
       Interval 을 그 사이에서 "이미 지난" 상태로 처음 관측하므로, 같은
       due_tick 안에서 오류 알림이 한 번 더 걸릴 수 있다 — pending 이 완전히
       빌 때까지 ACK 로 소진한다(§6.2-a(2), drain_pending_with_ack 재사용). */
    int err_count = 0;
    drain_pending_with_ack(&f.node, &f.io, GCG, NID, NULL, NULL, &err_count);
    check("8_2_1_1: 오류 알림 소진 후에도 FAULT 유지(오류 미해소)", f.node.state == SIAP_NS_FAULT);
    check("8_2_1_1: pending 비어 있음", f.node.pending.kind == (uint8_t)SIAP_KIND_NONE);

    f.io.now += 30000u;   /* Notify Error Interval 만료 — 아직 미해소, 재송신 */
    siap_node_poll(&f.node);
    check("8_2_1_1: Notify Error Interval 만료 -> NOTI_ERROR 재송신", f.node.pending.kind == (uint8_t)SIAP_NOTI_ERROR);
    drain_pending_with_ack(&f.node, &f.io, GCG, NID, NULL, NULL, &err_count);
    check("8_2_1_1: 재송신 후에도 FAULT 유지", f.node.state == SIAP_NS_FAULT);

    f.dev.fail[0] = false;   /* 오류 해소 */
    f.io.now += 30000u;
    siap_node_poll(&f.node);
    check("8_2_1_1/6_2: 오류 해소 -> RUNNING", f.node.state == SIAP_NS_RUNNING);
    check("8_2_1_1: Status = NORMAL 로 갱신", f.node.cfg.devices[0].status == SIAP_STATUS_NORMAL);
}

/* ═══════════════════════════════════════════════════════════════
 *  5. 연결 해제 알림 — 8.2.1.3
 * ═══════════════════════════════════════════════════════════════ */
static void test_noti_disconnect_ack_then_reconnect_8_2_1_3(void)
{
    fixture_t f; fixture_boot(&f, 1, 60);
    fixture_run_to_running(&f);

    f.io.tx_len = 0;
    push_empty(&f.io, SIAP_NOTI_DISCONNECT, GCG, NID, 500);
    siap_node_poll(&f.node);
    siap_hdr_t h = decode_tx_hdr(&f.io);
    check("8_2_1_3: NOTI_DISCONNECT 수신 -> 즉시 ACK 회신(§6.2-a(1))",
          h.msg_type == siap_wire_code(SIAP_ACK, SIAP_MODE_STRICT) && h.msg_id == 500);
    check("8_2_1_3: DISCONNECTED 로 전이", f.node.state == SIAP_NS_DISCONNECTED);

    f.io.now += 5000u;   /* 백오프(2s) 경과 */
    siap_node_poll(&f.node);
    check("8_2_1_3: 백오프 후 CONNECTING 재시도", f.node.state == SIAP_NS_CONNECTING);
}

/* §6.2-a(1)의 상태 게이트 선행 규칙을 NOTI_REBOOT에도 적용한다.
   BOOT/INIT는 한 poll 안에서 CONNECTING으로 진행하므로, 수신 가능한 안정 상태
   5종을 전부 검사하고 HALTED가 유일한 예외임을 별도로 고정한다. */
static void check_noti_reboot_ack_in_state(siap_node_state_t state, uint16_t msg_id,
                                            const char *ack_tag, const char *state_tag)
{
    fixture_t f; fixture_boot(&f, 1, 60);
    fixture_run_to_running(&f);
    f.node.state = state;
    if (state == SIAP_NS_DISCONNECTED)
        f.node.t_backoff_until = f.io.now + 1000u;

    f.io.tx_len = 0;
    push_empty(&f.io, SIAP_NOTI_REBOOT, GCG, NID, msg_id);
    siap_node_poll(&f.node);
    siap_hdr_t h = decode_tx_hdr(&f.io);
    check(ack_tag, h.msg_type == siap_wire_code(SIAP_ACK, SIAP_MODE_STRICT)
                   && h.msg_id == msg_id && h.payload_len == 0);
    check(state_tag, f.node.state == state);
}

static void test_noti_reboot_ack_state_matrix_F210(void)
{
    check_noti_reboot_ack_in_state(
        SIAP_NS_CONNECTING, 510,
        "CONNECTING에서 NOTI_REBOOT -> ACK",
        "CONNECTING 상태 유지");
    check_noti_reboot_ack_in_state(
        SIAP_NS_RUNNING, 511,
        "RUNNING에서 NOTI_REBOOT -> ACK",
        "RUNNING 상태 유지");
    check_noti_reboot_ack_in_state(
        SIAP_NS_FAULT, 512,
        "FAULT에서 NOTI_REBOOT -> ACK",
        "FAULT 상태 유지");
    check_noti_reboot_ack_in_state(
        SIAP_NS_REBOOTING, 513,
        "REBOOTING에서 NOTI_REBOOT -> ACK",
        "REBOOTING 상태 유지");
    check_noti_reboot_ack_in_state(
        SIAP_NS_DISCONNECTED, 514,
        "DISCONNECTED에서 NOTI_REBOOT -> ACK",
        "DISCONNECTED 상태 유지");

    fixture_t f; fixture_boot(&f, 1, 60);
    fixture_run_to_running(&f);
    f.node.state = SIAP_NS_HALTED;
    f.io.tx_len = 0;
    push_empty(&f.io, SIAP_NOTI_REBOOT, GCG, NID, 515);
    siap_node_poll(&f.node);
    check("HALTED에서 NOTI_REBOOT는 ACK하지 않음", f.io.tx_len == 0);
    check("HALTED 상태 유지", f.node.state == SIAP_NS_HALTED);
}

/* ═══════════════════════════════════════════════════════════════
 *  6. 리부팅 — 8.1.6 / 그림 8-56
 * ═══════════════════════════════════════════════════════════════ */
static void test_reboot_completes_on_ack_8_1_6(void)
{
    fixture_t f; fixture_boot(&f, 1, 60);
    fixture_run_to_running(&f);

    f.io.tx_len = 0;
    push_empty(&f.io, SIAP_REQ_SET_REBOOT, GCG, NID, 700);
    siap_node_poll(&f.node);
    siap_hdr_t h = decode_tx_hdr(&f.io);
    check("8_1_6: REQ_SET_REBOOT -> RES_SET_REBOOT 즉시 회신",
          h.msg_type == siap_wire_code(SIAP_RES_SET_REBOOT, SIAP_MODE_STRICT) && h.msg_id == 700);
    check("8_1_6: REBOOTING 전이", f.node.state == SIAP_NS_REBOOTING);
    check("8_1_6: NOTI_REBOOT pending 등록", f.node.pending.kind == (uint8_t)SIAP_NOTI_REBOOT);

    uint16_t mid = f.node.pending.msg_id;
    push_ack_for(&f.io, GCG, NID, mid);
    siap_node_poll(&f.node);
    check("그림 8-56: ACK 수신 -> BOOT(알림 성공)", f.node.state == SIAP_NS_BOOT);

    siap_node_poll(&f.node);
    check("그림 8-56: BOOT 이후 자동으로 CONNECTING 재진입", f.node.state == SIAP_NS_CONNECTING);
}

static void test_reboot_completes_on_retry_exhaustion_8_1_6(void)
{
    fixture_t f; fixture_boot(&f, 1, 60);
    fixture_run_to_running(&f);
    push_empty(&f.io, SIAP_REQ_SET_REBOOT, GCG, NID, 701);
    siap_node_poll(&f.node);
    check("8_1_6: REBOOTING 진입", f.node.state == SIAP_NS_REBOOTING);

    for (uint8_t r = 0; r <= SIAP_PROFILE_DEFAULT.num_retry; r++) f.io.now += 2000u, siap_node_poll(&f.node);
    check("그림 8-56: 재전송 소진으로도 BOOT 도달", f.node.state == SIAP_NS_BOOT);
}

/* ═══════════════════════════════════════════════════════════════
 *  7. 구동기 제어 — §6.6 (유일한 actuation 경로)
 * ═══════════════════════════════════════════════════════════════ */
static void test_device_control_write_path_6_6(void)
{
    fixture_t f; fixture_boot(&f, 1, 60);
    fixture_run_to_running(&f);

    f.io.tx_len = 0;
    push_req_set_device_control(&f.io, GCG, NID, 800, 1, SIAP_DEV_SENSOR,
                                 SIAP_SUBTYPE_TEMPERATURE, SIAP_VALUE_TYPE_INT, 4242u);
    siap_node_poll(&f.node);
    check("6_6: dev_ops.write_value 가 정확히 그 값으로 호출됨",
          f.dev.write_count == 1 && f.dev.last_write_id == 1 && f.dev.last_write_val == 4242u);
    siap_hdr_t h = decode_tx_hdr(&f.io);
    check("6_6: RES_SET_DEVICE_CONTROL SUCCESS 회신",
          h.msg_type == siap_wire_code(SIAP_RES_SET_DEVICE_CONTROL, SIAP_MODE_STRICT));
    check("6_6: 응답 페이로드 = RSC 1byte", h.payload_len == SIAP_RSC_BYTES);
    check("6_6: 응답 RSC = SUCCESS", h.payload_len == 1 && f.io.tx[12] == (uint8_t)SIAP_RSC_SUCCESS);

    int prior_writes = f.dev.write_count;
    f.io.tx_len = 0;
    push_req_set_device_control(&f.io, GCG, NID, 801, 99 /* 미등록 device_id */, SIAP_DEV_SENSOR,
                                 SIAP_SUBTYPE_TEMPERATURE, SIAP_VALUE_TYPE_INT, 1u);
    siap_node_poll(&f.node);
    check("6_6: 미등록 device_id 는 write_value 를 부르지 않는다", f.dev.write_count == prior_writes);
    h = decode_tx_hdr(&f.io);
    check("6_6: 미등록 device_id -> INVALID_DEVICE_ID",
          f.io.tx[12] == (uint8_t)SIAP_RSC_INVALID_DEVICE_ID);

    f.io.tx_len = 0;
    push_req_set_device_control(&f.io, GCG, NID, 802, 1, SIAP_DEV_SENSOR,
                                 SIAP_SUBTYPE_TEMPERATURE, SIAP_VALUE_TYPE_FLOAT /* 실제는 INT */, 1u);
    siap_node_poll(&f.node);
    check("6_6: Value Type 불일치는 write_value 를 부르지 않는다", f.dev.write_count == prior_writes);
    h = decode_tx_hdr(&f.io);
    check("6_6: Value Type 불일치 -> INVALID_DATA_TYPE",
          f.io.tx[12] == (uint8_t)SIAP_RSC_INVALID_DATA_TYPE);
}

/* ═══════════════════════════════════════════════════════════════
 *  8. 링크 오류 — §6.2 마지막 행
 * ═══════════════════════════════════════════════════════════════ */
static void test_link_error_disconnects(void)
{
    fixture_t f; fixture_boot(&f, 1, 60);
    fixture_run_to_running(&f);
    f.io.link_error_once = true;
    siap_node_poll(&f.node);
    check("6_2: read_byte 링크 오류 -> DISCONNECTED", f.node.state == SIAP_NS_DISCONNECTED);
}

/* ═══════════════════════════════════════════════════════════════
 *  9. 디바이스별 스캔 스케줄 · Event 임계값 · Event-only 오류감지
 * ═══════════════════════════════════════════════════════════════ */
static void test_device_specific_period_scheduling_F130(void)
{
    siap_dp_t devs[2] = {
        make_device(1, SIAP_DEV_SENSOR, SIAP_SUBTYPE_TEMPERATURE, SIAP_VALUE_TYPE_INT, SIAP_TM_PERIODIC, 10),
        make_device(2, SIAP_DEV_SENSOR, SIAP_SUBTYPE_HUMIDITY,    SIAP_VALUE_TYPE_INT, SIAP_TM_PERIODIC, 60),
    };
    uint32_t values[2] = { 111u, 222u };
    fixture_t f; fixture_boot_devices(&f, devs, values, 2);
    fixture_run_to_running(&f);

    f.io.tx_len = 0;
    f.io.now += 10000u;   /* device_id=1 의 Period(10s) 만 경과 — id=2 는 60s */
    siap_node_poll(&f.node);
    check("10s 경과 -> pending = NOTI_DEVICE_VALUE", f.node.pending.kind == (uint8_t)SIAP_NOTI_DEVICE_VALUE);
    siap_hdr_t h = decode_tx_hdr(&f.io);
    check("Period=10s 디바이스 하나만 포함(공통 최소주기로 뭉치지 않는다)",
          h.payload_len == SIAP_DMI_BYTES);
    siap_dmi_t dmi; size_t bp = 0;
    siap_decode_dmi(f.io.tx + 12, &bp, &dmi);
    check("그 하나는 device_id=1", dmi.device_id == 1);

    int dv = 0;
    drain_pending_with_ack(&f.node, &f.io, GCG, NID, &dv, NULL, NULL);

    f.io.tx_len = 0;
    f.io.now = 60000u;   /* device_id=2 의 Period(60s) 도 이번엔 함께 도래 —
                             Keep Alive Interval 기본값도 60s 라 due 회전
                             커서(§6.4-a)가 그걸 먼저 집을 수 있다. due_send_next
                             는 한 poll 에 한 소스만 보내므로, DEVICE_VALUE 가
                             나올 때까지 다른 소스를 ACK 로 흘려보낸다. */
    siap_node_poll(&f.node);
    int guard;
    for (guard = 0; guard < 5 && f.node.pending.kind != (uint8_t)SIAP_NOTI_DEVICE_VALUE; guard++) {
        push_ack_for(&f.io, GCG, NID, f.node.pending.msg_id);
        f.io.tx_len = 0;
        siap_node_poll(&f.node);
    }
    check("60s 시점엔 두 디바이스가 함께 due", f.node.pending.kind == (uint8_t)SIAP_NOTI_DEVICE_VALUE);
    h = decode_tx_hdr(&f.io);
    check("이번엔 Period=60s 디바이스도 포함(요소 2개분)",
          h.payload_len == (uint16_t)(SIAP_DMI_BYTES * 2u));
}

static void test_event_mode_sends_only_out_of_range_F130(void)
{
    siap_dp_t d = make_device(5, SIAP_DEV_SENSOR, SIAP_SUBTYPE_TEMPERATURE, SIAP_VALUE_TYPE_INT, SIAP_TM_EVENT, 5);
    d.lower_value = siap_raw_from_int(0);
    d.upper_value = siap_raw_from_int(10);
    uint32_t values[1] = { siap_raw_from_int(5) };   /* [0,10] 범위 안 */
    fixture_t f; fixture_boot_devices(&f, &d, values, 1);
    fixture_run_to_running(&f);

    f.io.tx_len = 0;
    f.io.now += 5000u;   /* Period(스캔 주기) 경과 — 값은 여전히 범위 안 */
    siap_node_poll(&f.node);
    check("Event 값이 범위 안이면 스캔해도 전송하지 않는다(표 7-15)",
          f.node.pending.kind == (uint8_t)SIAP_KIND_NONE && f.io.tx_len == 0);

    f.dev.values[0] = siap_raw_from_int(100);   /* Upper Value(10) 이탈 */
    f.io.now += 5000u;
    siap_node_poll(&f.node);
    check("Upper Value 를 벗어나면 다음 스캔에서 전송한다",
          f.node.pending.kind == (uint8_t)SIAP_NOTI_DEVICE_VALUE);
    siap_hdr_t h = decode_tx_hdr(&f.io);
    check("요소 1개(Event 대상 device_id=5)", h.payload_len == SIAP_DMI_BYTES);
}

static void test_event_only_fault_detection_F130(void)
{
    siap_dp_t d = make_device(7, SIAP_DEV_SENSOR, SIAP_SUBTYPE_TEMPERATURE, SIAP_VALUE_TYPE_INT, SIAP_TM_EVENT, 15);
    d.lower_value = siap_raw_from_int(0);
    d.upper_value = siap_raw_from_int(100);
    uint32_t values[1] = { siap_raw_from_int(50) };
    fixture_t f; fixture_boot_devices(&f, &d, values, 1);
    fixture_run_to_running(&f);

    f.dev.fail[0] = true;
    f.io.now += 15000u;   /* Event-only 디바이스도 자기 Period 로 스캔된다 */
    siap_node_poll(&f.node);
    check("Event-only 디바이스도 자기 Period 로 오류를 감지한다(8.2.1.1, Periodic 유무에 기대지 않는다)",
          f.node.state == SIAP_NS_FAULT);
    check("pending = NOTI_ERROR", f.node.pending.kind == (uint8_t)SIAP_NOTI_ERROR);
}

/* ═══════════════════════════════════════════════════════════════
 *  10. RES_SET_CONNECTION 오류 RSC 9종 전량(§6.5 표 전체)
 * ═══════════════════════════════════════════════════════════════ */
static void _check_rsc_outcome(const char *tag, siap_rsc_t rsc, bool retryable)
{
    fixture_t f; fixture_boot(&f, 1, 60);
    siap_node_poll(&f.node);
    uint16_t mid = f.node.pending.msg_id;
    push_res_set_connection(&f.io, GCG, NID, mid, rsc, NULL, 0);
    siap_node_poll(&f.node);
    if (retryable)
        check(tag, f.node.state == SIAP_NS_CONNECTING && f.node.pending.kind == (uint8_t)SIAP_REQ_SET_CONNECTION);
    else
        check(tag, f.node.state == SIAP_NS_HALTED);
}

static void test_res_set_connection_rsc_matrix_6_5_F131(void)
{
    _check_rsc_outcome("6_5/INVALID_VERSION(0x01) -> HALTED", SIAP_RSC_INVALID_VERSION, false);
    _check_rsc_outcome("6_5/INVALID_GCG_ID(0x02) -> CONNECTING 유지(재시도 가능)", SIAP_RSC_INVALID_GCG_ID, true);
    _check_rsc_outcome("6_5/INVALID_NODE_ID(0x03) -> CONNECTING 유지(재시도 가능)", SIAP_RSC_INVALID_NODE_ID, true);
    _check_rsc_outcome("6_5/INVALID_DEVICE_ID(0x04) -> HALTED", SIAP_RSC_INVALID_DEVICE_ID, false);
    _check_rsc_outcome("6_5/INVALID_DEVICE_TYPE(0x05) -> HALTED", SIAP_RSC_INVALID_DEVICE_TYPE, false);
    _check_rsc_outcome("6_5/INVALID_DATA_TYPE(0x06) -> HALTED", SIAP_RSC_INVALID_DATA_TYPE, false);
    _check_rsc_outcome("6_5/INVALID_DATA_SUBTYPE(0x07) -> HALTED", SIAP_RSC_INVALID_DATA_SUBTYPE, false);
    _check_rsc_outcome("6_5/INVALID_TRANSMISSION_TYPE(0x08) -> HALTED", SIAP_RSC_INVALID_TRANSMISSION_TYPE, false);
    _check_rsc_outcome("6_5/INVALID_FORMAT(0x09) -> HALTED", SIAP_RSC_INVALID_FORMAT, false);
}

/* ═══════════════════════════════════════════════════════════════
 *  11. ACK 는 응답 종류가 일치할 때만 pending 을 해제한다
 * ═══════════════════════════════════════════════════════════════ */
static void test_ack_does_not_clear_connection_request_pending_F132(void)
{
    fixture_t f; fixture_boot(&f, 1, 60);
    siap_node_poll(&f.node);   /* BOOT->INIT->CONNECTING, REQ_SET_CONNECTION 송신 */
    uint16_t mid = f.node.pending.msg_id;
    check("pending = REQ_SET_CONNECTION", f.node.pending.kind == (uint8_t)SIAP_REQ_SET_CONNECTION);

    push_ack_for(&f.io, GCG, NID, mid);   /* 같은 msg_id 지만 잘못된 응답 종류(ACK) */
    siap_node_poll(&f.node);
    check("ACK 는 REQ_SET_CONNECTION pending 을 해제하지 않는다( 3조건: Node ID+msg_id+Message Type)",
          f.node.pending.kind == (uint8_t)SIAP_REQ_SET_CONNECTION && f.node.pending.msg_id == mid);
    check("상태는 CONNECTING 유지", f.node.state == SIAP_NS_CONNECTING);

    f.io.tx_len = 0;
    f.io.now += 2000u;   /* Timeout 경과 — 정상 재전송 경로가 살아있는지 확인 */
    siap_node_poll(&f.node);
    check("이후 Timeout 재전송도 정상 동작(같은 msg_id)",
          f.node.pending.retry == 1 && f.node.pending.msg_id == mid);
}

/* ═══════════════════════════════════════════════════════════════
 *  12. 다중 청크 송신은 부분 쓰기(UART 포화)에서도 유실되지 않는다
 * ═══════════════════════════════════════════════════════════════ */
static void test_multi_chunk_send_survives_partial_write_F133(void)
{
    fixture_t f; fixture_boot(&f, 1, 10);   /* Period=10s, 1 디바이스 */
    fixture_run_to_running(&f);

    f.io.tx_len = 0;
    f.io.now += 10000u;
    f.io.budget_enabled = true;
    f.io.budget_left = 4;   /* poll 당 최대 4 byte 만 받아쓴다 */
    siap_node_poll(&f.node);   /* 헤더(12B) + DMI(7B) = 19B 프레임을 트리거 */
    check("첫 poll — 부분 쓰기라 아직 프레임 미완성", f.io.tx_len < 19u);

    int guard;
    for (guard = 0; guard < 10 && f.node.tx_seq.kind != (uint8_t)SIAP_SEQ_NONE; guard++) {
        f.io.budget_left = 4;
        siap_node_poll(&f.node);
    }
    check("유한 번의 poll 안에 시퀀스가 끝난다(무한 대기 아님)", guard < 10);

    f.io.budget_enabled = false;
    check("헤더(12)+요소 1개(7) = 19 byte 전량 보존(미전송 잔여가 덮어써지지 않는다)",
          f.io.tx_len == 19u);
    siap_hdr_t h = decode_tx_hdr(&f.io);
    check("헤더도 손상 없이 디코드된다(payload_len=DMI 1개분)", h.payload_len == SIAP_DMI_BYTES);
    siap_dmi_t dmi; size_t bp = 0;
    siap_decode_dmi(f.io.tx + 12, &bp, &dmi);
    check("요소도 손상 없이 디코드된다(device_id=1)", dmi.device_id == 1);
}

/* Message Identifier 는 0943 7.2.2 원문 그대로 0을 건너뛰지 않고
   0xFFFF 다음 0으로 순환해야 한다(이전엔 "0은 미할당 표시로 예약"이라며
   1로 돌아갔다 — 표준 문구와 직접 어긋났다). */
static void test_msg_id_wraps_to_zero_not_one_F135(void)
{
    fixture_t f; fixture_boot(&f, 1, 60);
    f.node.next_msg_id = 0xFFFF;              /* 다음 발번이 0xFFFF 이도록 강제 */
    siap_node_poll(&f.node);                  /* REQ_SET_CONNECTION 발번 */
    check("0xFFFF 발번 확인", f.node.pending.msg_id == 0xFFFF);
    check("다음 next_msg_id 는 0으로 감긴다(1이 아니다)", f.node.next_msg_id == 0);
}

/* 연결 성공 직후 노드가 REQ_SET_NODE_DEVICE_PROPERTY_ALL(8.1.3.3)로
   자기 디바이스 구성을 선언한다. REQ_SET_CONNECTION(8.1.1)은 페이로드가 없어
   (LAYOUT (0,0)) 이 역할을 못 한다. pending 에 실려 RES 수신까지 §6.4 재전송
   타이머가 재시도하고, RES_SET_NODE_DEVICE_PROPERTY_ALL(SUCCESS) 로 멈춘다.
   DP/NP 의 바이트 폭·순서 자체는 test_golden.c(C↔골든 벡터)와
   xcodec_verify(C↔Python sim/_wire) 가 이미 대조한다 — 여기서는 "선언이
   올바른 구조로 나가고 handshake 가 성립하는가"만 본다. */
static void test_connection_declares_node_device_property_all_F198(void)
{
    fixture_t f; fixture_boot(&f, 2, 30);   /* 디바이스 2종 — 다중 요소 경로 */

    /* fixture_run_to_running 은 선언까지 드레인하므로, 여기서는 직접
       연결만 성립시켜 선언 프레임을 검사한다. */
    siap_node_poll(&f.node);                              /* -> CONNECTING, REQ_SET_CONNECTION */
    uint16_t cmid = f.node.pending.msg_id;
    push_res_set_connection(&f.io, GCG, NID, cmid, SIAP_RSC_SUCCESS, f.devices, f.dev.n);
    f.io.tx_len = 0;
    siap_node_poll(&f.node);                              /* -> RUNNING + 선언 송신 */

    check("RUNNING 진입", f.node.state == SIAP_NS_RUNNING);
    check("연결 성공 직후 pending = REQ_SET_NODE_DEVICE_PROPERTY_ALL",
          f.node.pending.kind == (uint8_t)SIAP_REQ_SET_NODE_DEVICE_PROPERTY_ALL);

    /* 송신 프레임 구조 검사: 헤더 msg_type · payload_len = NP + DP×N. */
    siap_hdr_t h = decode_tx_hdr(&f.io);
    check("송신 msg_type = REQ_SET_NODE_DEVICE_PROPERTY_ALL",
          h.msg_type == siap_wire_code(SIAP_REQ_SET_NODE_DEVICE_PROPERTY_ALL, SIAP_MODE_STRICT));
    check("payload_len = NODE_PROPERTY + DEVICE_PROPERTY×2 (RSC 없음)",
          h.payload_len == (uint16_t)(SIAP_NP_BYTES + SIAP_DP_BYTES * 2u));

    /* 고정부 NODE_PROPERTY 의 num_devices 가 device_count 와 같다. */
    siap_np_t np; size_t bp = 0;
    siap_decode_np(f.io.tx + 12, &bp, &np);
    check("NODE_PROPERTY.num_devices = 2", np.num_devices == 2);
    check("NODE_PROPERTY.node_id = 노드 자신", np.node_id == NID);

    /* 첫 DEVICE_PROPERTY 요소가 devices[0] 로 라운드트립된다(요소 경로 실행 증거). */
    siap_dp_t dp0; bp = 0;
    siap_decode_dp(f.io.tx + 12 + SIAP_NP_BYTES, &bp, &dp0);
    check("첫 DEVICE_PROPERTY.device_id = devices[0]",
          dp0.main.device_id == f.devices[0].main.device_id);

    /* 재전송 — Timeout 경과 후 같은 msg_id 로 재인코딩. */
    uint16_t dmid = f.node.pending.msg_id;
    f.io.tx_len = 0;
    f.io.now += (uint32_t)f.node.cfg.profile.recv_timeout * 1000u;
    siap_node_poll(&f.node);
    check("재전송해도 pending 유지 · msg_id 동일",
          f.node.pending.kind == (uint8_t)SIAP_REQ_SET_NODE_DEVICE_PROPERTY_ALL
          && f.node.pending.msg_id == dmid && f.node.pending.retry == 1);
    siap_hdr_t h2 = decode_tx_hdr(&f.io);
    check("재전송 프레임도 REQ_SET_NODE_DEVICE_PROPERTY_ALL",
          h2.msg_type == siap_wire_code(SIAP_REQ_SET_NODE_DEVICE_PROPERTY_ALL, SIAP_MODE_STRICT));

    /* 실패 RSC 는 pending 을 해제하지 않는다 — 계속 재시도한다. */
    push_res_set_node_device_property_all(&f.io, GCG, NID, dmid, SIAP_RSC_INVALID_DEVICE_ID);
    siap_node_poll(&f.node);
    check("실패 RSC 수신 시 pending 유지(재시도 계속)",
          f.node.pending.kind == (uint8_t)SIAP_REQ_SET_NODE_DEVICE_PROPERTY_ALL);

    /* SUCCESS RSC 로 handshake 완료 — pending 해제. */
    push_res_set_node_device_property_all(&f.io, GCG, NID, dmid, SIAP_RSC_SUCCESS);
    siap_node_poll(&f.node);
    check("SUCCESS 수신 시 pending 해제(선언 완료)",
          f.node.pending.kind == (uint8_t)SIAP_KIND_NONE);
}

int main(void)
{
    printf("노드 상태 머신 호스트 유닛테스트 (펌웨어 설계서 §6)\n\n");

    test_init_validation_4_1_a();
    test_boot_to_connecting_sends_req_8_1_1();
    test_connecting_success_to_running_8_1_1();
    test_connecting_retryable_rsc_waits_for_timeout_6_5();
    test_connecting_unretryable_rsc_halts_6_5_F076();
    test_periodic_rotation_no_starvation_6_4_a_100cycles();
    test_fault_enter_and_recover_8_2_1_1();
    test_noti_disconnect_ack_then_reconnect_8_2_1_3();
    test_noti_reboot_ack_state_matrix_F210();
    test_reboot_completes_on_ack_8_1_6();
    test_reboot_completes_on_retry_exhaustion_8_1_6();
    test_device_control_write_path_6_6();
    test_link_error_disconnects();
    test_device_specific_period_scheduling_F130();
    test_event_mode_sends_only_out_of_range_F130();
    test_event_only_fault_detection_F130();
    test_res_set_connection_rsc_matrix_6_5_F131();
    test_ack_does_not_clear_connection_request_pending_F132();
    test_connection_declares_node_device_property_all_F198();
    test_multi_chunk_send_survives_partial_write_F133();
    test_msg_id_wraps_to_zero_not_one_F135();

    printf("\n  %d/%d 통과\n", g_passed, g_total);
    return (g_passed == g_total) ? 0 : 1;
}
