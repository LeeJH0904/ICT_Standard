/*
 * 노드 상태 머신 구현. 펌웨어 설계서 §6.
 *
 * siap_frame.c(스트리밍 코덱)의 siap_sink_t 콜백 4개(on_header/on_fixed/
 * on_element/on_end) 위에서 8상태 전이(§6.1) · pending 재전송(§6.4) ·
 * due 회전 커서(§6.4-a)를 구현한다. 이 파일은 하드웨어를 모른다 — 아는
 * 것은 siap_io_t/siap_dev_ops_t 뒤의 함수 포인터뿐이다(§2.3 소유 경계).
 *
 * §6.6 — REQ_SET_DEVICE_CONTROL 수신 → dev_ops.write_value 가 구동기를
 * 움직일 수 있는 "유일한 경로"다(CLAUDE.md §1-7). 이 파일 안에서
 * write_value 를 호출하는 곳은 _on_element() 의 SIAP_REQ_SET_DEVICE_CONTROL
 * 분기 한 군데뿐이다.
 */
#include "node_state.h"

/* §5.7 — 프레임 간 무입력을 "침묵"으로 보는 기준. 9600 baud 에서 1 byte
   = 1.04 ms 이므로 20 byte 분이다. */
#define SIAP_T_GAP_MS 20u

/* 표 7-18 기본값. 시간 3필드는 전부 sec(F-033). Num. of Retry 기본 3회
   (0937 요구사항 대조표 "배수 3의 근거" — 재전송이 전부 실패해야 미수집으로 본다). */
const siap_mcp_t SIAP_PROFILE_DEFAULT = {
    .recv_timeout        = 2,
    .num_retry           = 3,
    .noti_error_interval = 30,
    .keep_alive_interval = 60,
};

/* ═══════════════════════════════════════════════════════════════
 *  0. 내부 유틸
 * ═══════════════════════════════════════════════════════════════ */

static int _find_device(const siap_node_t *node, uint8_t device_id)
{
    for (uint8_t i = 0; i < node->cfg.device_count; i++)
        if (node->cfg.devices[i].main.device_id == device_id) return (int)i;
    return -1;
}

/* 표 7-8 헤더 필드로부터 "이 프레임이 나를 향한 것인가"를 판정한다.
   유니캐스트는 Node ID(+GCG ID) 일치를 요구하고, 멀티/브로드캐스트는
   전부 받는다(표 7-6). */
static bool _addressed_to_me(const siap_node_t *node, const siap_hdr_t *h)
{
    if (h->trans_type != SIAP_TRANS_UNICAST) return true;
    return h->node_id == node->cfg.node_id && h->gcg_id == node->cfg.gcg_id;
}

/* 7.2.2 원문 — "Message Identifier는 … '0'에서 '65535'까지 사용할 수
   있다. 일련번호는 데이터 전송 시마다 +1을 하며 만료되면 0부터 다시
   시작한다." 0 을 건너뛰는 것은 표준 위반이다(F-135) — 이전 버전은
   "0 은 미할당 표시로 예약"이라고 §6.4/펌웨어 설계서 §9 에 적었지만,
   pending 슬롯의 "비어 있음"은 pending.kind==SIAP_KIND_NONE 으로만
   판정된다(siap_node_init 참조) — msg_id==0 을 센티널로 쓰는 코드는
   어디에도 없어 그 예약 자체가 근거 없는 자체 결정이었다. uint16_t
   덧셈은 0xFFFF+1 을 자연스럽게 0 으로 감아 표준 문구와 그대로 맞다. */
static uint16_t _next_msg_id(siap_node_t *node)
{
    uint16_t id = node->next_msg_id;
    node->next_msg_id = (uint16_t)(id + 1u);
    return id;
}

/* §6.5 — 재시도 가능 2종(INVALID_GCG_ID·INVALID_NODE_ID) / 불가 7종.
   CLAUDE.md §3.5 · 펌웨어 설계서 §6.5 표와 동일하다(F-076). */
static bool _rsc_retryable(siap_rsc_t rsc)
{
    return rsc == SIAP_RSC_INVALID_GCG_ID || rsc == SIAP_RSC_INVALID_NODE_ID;
}

/* Timeout × 2ⁿ, 상한 300 s(§6.5). DISCONNECTED 진입마다 shift 를 늘리고
   CONNECTING 성공 시 0 으로 되돌린다. */
static uint32_t _backoff_ms(siap_node_t *node)
{
    uint32_t ms = (uint32_t)node->cfg.profile.recv_timeout * 1000u;
    uint8_t shift = node->backoff_shift;
    for (uint8_t i = 0; i < shift && ms < 300000u; i++) ms *= 2u;
    if (ms > 300000u) ms = 300000u;
    if (node->backoff_shift < 0xFFu) node->backoff_shift++;
    return ms;
}

static siap_hdr_t _build_hdr(const siap_node_t *node, siap_kind_t kind,
                              uint16_t msg_id, uint16_t payload_len)
{
    siap_hdr_t h;
    h.version     = SIAP_VERSION;
    h.msg_type    = siap_wire_code(kind, node->cfg.mode);
    h.trans_type  = SIAP_TRANS_UNICAST;
    h.msg_id      = msg_id;
    h.payload_len = payload_len;
    h.gcg_id      = node->cfg.gcg_id;
    h.node_id     = node->cfg.node_id;
    return h;
}

/* §3. RES_* 빌더 구역에 정의된다 — 다중 청크 시퀀서(§1)가 헤더 청크를
   만들 때 먼저 필요해 전방 선언한다. */
static siap_np_t _build_np(const siap_node_t *node);

/* siap_tx_flush(siap_frame.h)이 요구하는 콜백 시그니처(size_t 반환)와
   siap_io_t.write(펌웨어 설계서 §2.2, int16_t 반환)는 폭이 다르다 — 둘
   다 이미 확정된 인터페이스라(§2.2 는 설계서, siap_tx_flush 는 단계 2b
   에서 통과한 계약) 어느 쪽도 고치지 않고 얇은 어댑터로 잇는다. ctx 자리에
   siap_io_t* 를 그대로 넘긴다. */
static size_t _io_write_adapter(void *ctx, const uint8_t *data, size_t len)
{
    const siap_io_t *io = (const siap_io_t *)ctx;
    uint16_t chunk = (len > 0xFFFFu) ? 0xFFFFu : (uint16_t)len;
    int16_t wrote = io->write(io->ctx, data, chunk);
    if (wrote < 0) return 0;   /* siap_tx_flush 의 "지금은 못 썼다"(0)와 같은 의미로 접는다 */
    return (size_t)wrote;
}

/* 인코더 윈도우를 flush 한다. 부분 쓰기면 다음 poll 이 이어서 flush 한다
   (§5.8). 동시 대기 1건 원칙(§6.4) 위에서 새 프레임을 큐잉하기 전에는
   항상 이전 프레임이 이미 다 나갔거나(HALTED·ACK 처럼 pending 밖의 즉시
   송신) 큐를 새로 쓰는 것이 안전하다는 전제를 둔다 — 호스트 테스트의
   siap_io_t.write 는 항상 전량을 즉시 받아써 이 전제가 항상 성립한다. */
static void _tx_flush(siap_node_t *node)
{
    siap_tx_status_t st = siap_tx_flush(&node->enc, _io_write_adapter, (void *)node->cfg.io);
    node->tx_busy = (st == SIAP_TX_PENDING);
}

static void _send_ack_now(siap_node_t *node, const siap_hdr_t *req)
{
    siap_tx_reset(&node->enc);
    if (!siap_encode_ack(req, node->cfg.mode, &node->enc)) return;
    _tx_flush(node);
}

/* ═══════════════════════════════════════════════════════════════
 *  1. 다중 청크 송신 시퀀서 — §5.8, F-133.
 *
 *  이전 청크가 win 에서 완전히 빠져나가기(tx_busy==false) 전에는 절대
 *  siap_tx_reset() 을 부르지 않는다 — _tx_seq_pump() 의 while 조건이
 *  그 불변식을 강제한다. 헤더/요소를 만드는 두 헬퍼는 "이번 청크를
 *  win 에 쓴다"만 하고, 실제로 내보내는 것과 다음 청크로 넘어갈지
 *  판단하는 것은 pump 쪽 책임이다.
 * ═══════════════════════════════════════════════════════════════ */

static bool _tx_seq_build_header(siap_node_t *node)
{
    siap_tx_seq_t *s = &node->tx_seq;
    siap_tx_reset(&node->enc);
    switch ((siap_tx_seq_kind_t)s->kind) {
    case SIAP_SEQ_NOTI_DEVICE_VALUE: {
        uint16_t plen = (uint16_t)(SIAP_DMI_BYTES * s->n);
        siap_hdr_t h = _build_hdr(node, SIAP_NOTI_DEVICE_VALUE, s->msg_id, plen);
        return siap_tx_put_hdr(&node->enc, &h);
    }
    case SIAP_SEQ_RES_GET_DEVICE_PROPERTY: {
        uint16_t plen = (uint16_t)(SIAP_RSC_BYTES + SIAP_DP_BYTES * s->n);
        siap_hdr_t h = _build_hdr(node, SIAP_RES_GET_DEVICE_PROPERTY, s->msg_id, plen);
        if (!siap_tx_put_hdr(&node->enc, &h)) return false;
        return siap_tx_put_rsc(&node->enc, (siap_rsc_t)s->rsc);
    }
    case SIAP_SEQ_RES_GET_NODE_DEVICE_PROPERTY_ALL: {
        uint16_t plen = (uint16_t)(SIAP_RSC_BYTES + SIAP_NP_BYTES + SIAP_DP_BYTES * s->n);
        siap_hdr_t h = _build_hdr(node, SIAP_RES_GET_NODE_DEVICE_PROPERTY_ALL, s->msg_id, plen);
        if (!siap_tx_put_hdr(&node->enc, &h)) return false;
        if (!siap_tx_put_rsc(&node->enc, SIAP_RSC_SUCCESS)) return false;
        siap_np_t np = _build_np(node);
        return siap_tx_put_np(&node->enc, &np);
    }
    case SIAP_SEQ_RES_GET_DEVICE_VALUE: {
        uint16_t plen = (uint16_t)(SIAP_RSC_BYTES + SIAP_DMI_BYTES * s->n);
        siap_hdr_t h = _build_hdr(node, SIAP_RES_GET_DEVICE_VALUE, s->msg_id, plen);
        if (!siap_tx_put_hdr(&node->enc, &h)) return false;
        return siap_tx_put_rsc(&node->enc, (siap_rsc_t)s->rsc);
    }
    default:
        return false;
    }
}

static bool _tx_seq_build_element(siap_node_t *node, uint8_t dev_idx)
{
    siap_tx_seq_t *s = &node->tx_seq;
    siap_tx_reset(&node->enc);
    siap_dp_t *d = &node->cfg.devices[dev_idx];
    if ((siap_tx_seq_kind_t)s->kind == SIAP_SEQ_NOTI_DEVICE_VALUE) {
        uint32_t raw;
        /* 재인코딩 시점의 현재값(§6.2-a(4)). 실패하면 마지막으로 알려진
           값을 그대로 보낸다 — 새 오류감지·FAULT 진입은 due_send_next 의
           주기 스캔이 담당한다(중복 책임을 피한다). */
        if (node->cfg.dev_ops->read_value(node->cfg.dev_ops->ctx, d->main.device_id, &raw) == 0)
            d->main.value = raw;
        siap_result_t r = siap_tx_put_dmi(&node->enc, &d->main);
        return r.ok;
    }
    if ((siap_tx_seq_kind_t)s->kind == SIAP_SEQ_RES_GET_DEVICE_VALUE) {
        siap_result_t r = siap_tx_put_dmi(&node->enc, &d->main);
        return r.ok;
    }
    siap_result_t r = siap_tx_put_dp(&node->enc, d);
    return r.ok;
}

/* 진행 중인 시퀀스를 가능한 만큼 밀어낸다. 청크 하나가 완전히 flush될
   때만(tx_busy==false) 다음 청크를 만든다 — 부분 쓰기(UART 포화)면
   while 조건에서 멈추고 다음 poll() 이 이어받는다(F-133). */
static void _tx_seq_pump(siap_node_t *node)
{
    siap_tx_seq_t *s = &node->tx_seq;
    while ((siap_tx_seq_kind_t)s->kind != SIAP_SEQ_NONE && !node->tx_busy) {
        bool built;
        if (!s->hdr_done) {
            built = _tx_seq_build_header(node);
            if (built) s->hdr_done = true;
        } else if (s->next < s->n) {
            built = _tx_seq_build_element(node, s->idx[s->next]);
            if (built) s->next++;
        } else {
            s->kind = (uint8_t)SIAP_SEQ_NONE;   /* 전량 완료 */
            return;
        }
        if (!built) { s->kind = (uint8_t)SIAP_SEQ_NONE; return; }
        _tx_flush(node);
    }
}

/* ═══════════════════════════════════════════════════════════════
 *  2. pending 재인코딩 — §6.2-a(4) "재전송은 재인코딩이다"
 * ═══════════════════════════════════════════════════════════════ */

static bool _pending_encode(siap_node_t *node)
{
    siap_kind_t kind = (siap_kind_t)node->pending.kind;

    if (kind == SIAP_NOTI_DEVICE_VALUE) {
        siap_tx_seq_t *s = &node->tx_seq;
        uint16_t mask = node->pending.arg;   /* F-130 — 보낼 devices[] 인덱스 비트마스크 */
        uint8_t n = 0;
        for (uint8_t i = 0; i < node->cfg.device_count && n < SIAP_MAX_DEVICES_PER_NODE; i++)
            if (mask & (uint16_t)(1u << i)) s->idx[n++] = i;
        s->kind = (uint8_t)SIAP_SEQ_NOTI_DEVICE_VALUE;
        s->rsc = 0;
        s->msg_id = node->pending.msg_id;
        s->n = n;
        s->next = 0;
        s->hdr_done = false;
        _tx_seq_pump(node);
        return true;
    }

    siap_tx_reset(&node->enc);
    if (kind == SIAP_REQ_SET_CONNECTION || kind == SIAP_NOTI_KEEP_ALIVE || kind == SIAP_NOTI_REBOOT) {
        siap_hdr_t h = _build_hdr(node, kind, node->pending.msg_id, 0);
        if (!siap_tx_put_hdr(&node->enc, &h)) return false;
        _tx_flush(node);
        return true;
    }
    if (kind == SIAP_NOTI_ERROR) {
        siap_hdr_t h = _build_hdr(node, kind, node->pending.msg_id, SIAP_NEC_BYTES);
        if (!siap_tx_put_hdr(&node->enc, &h)) return false;
        if (!siap_tx_put_nec(&node->enc, (siap_nec_t)node->pending.arg)) return false;
        _tx_flush(node);
        return true;
    }
    return false;
}

static void _pending_begin(siap_node_t *node, siap_kind_t kind, uint16_t arg, uint32_t now)
{
    node->pending.kind    = (uint8_t)kind;
    node->pending.msg_id  = _next_msg_id(node);
    node->pending.retry   = 0;
    node->pending.t_sent  = now;
    node->pending.arg     = arg;
    (void)_pending_encode(node);   /* flush 는 _pending_encode/_tx_seq_pump 가 담당(F-133) */
}

static void _pending_clear(siap_node_t *node)
{
    node->pending.kind = (uint8_t)SIAP_KIND_NONE;
}

/* Timeout 만료 시 재전송 또는(소진 시) 상태별 사건(§6.4 표). */
static void _pending_tick(siap_node_t *node, uint32_t now)
{
    if (node->pending.kind == (uint8_t)SIAP_KIND_NONE) return;
    uint32_t timeout_ms = (uint32_t)node->cfg.profile.recv_timeout * 1000u;
    if ((uint32_t)(now - node->pending.t_sent) < timeout_ms) return;

    if (node->pending.retry < node->cfg.profile.num_retry) {
        node->pending.retry++;
        node->pending.t_sent = now;
        (void)_pending_encode(node);   /* flush 는 _pending_encode/_tx_seq_pump 가 담당(F-133) */
        return;
    }

    _pending_clear(node);
    switch (node->state) {
    case SIAP_NS_CONNECTING:
        node->state = SIAP_NS_DISCONNECTED;
        node->t_backoff_until = now + _backoff_ms(node);
        break;
    case SIAP_NS_REBOOTING:
        /* 그림 8-56 — "재전송횟수 > numRetry" 도 리부팅 완료로 간다 */
        node->state = SIAP_NS_BOOT;
        break;
    default:
        /* 그 외 상태 — 알림 폐기 후 계속(§6.4 "소진 시" 행) */
        break;
    }
}

/* ═══════════════════════════════════════════════════════════════
 *  2. due 비트 + 회전 커서 — §6.4-a
 * ═══════════════════════════════════════════════════════════════ */

/* 만료 시각을 interval 만큼 미룬다 — 딱 한 번만 더하면, 이번 만료가 이미
   한 주기 이상 늦게 감지된 경우(예: poll 이 뜸하게 불렸다) 새 만료 시각이
   여전히 now 이하로 남아 바로 다음 호출에서 또 만료로 잡힌다("한 번만
   보낸다"는 §6.4-a 의 전제가 깨진다). now 를 넘어설 때까지만 더한다 —
   "현재 시각으로 리셋"(§6.4-a 금지)과는 다르다: 리셋은 매번 now 를 기준으로
   삼지만, 이건 원래 스케줄에 interval 의 정수배만 더해 따라잡는다. */
static uint32_t _advance_deadline(uint32_t deadline, uint32_t interval, uint32_t now)
{
    if (interval == 0u) return now + 1u;
    for (uint16_t guard = 0; guard < 4000u; guard++) {
        deadline += interval;
        if ((int32_t)(now - deadline) < 0) break;
    }
    return deadline;
}

/* Value(표준 미규정 F-022 — main.value_type 을 따른다)가 [Lower Value,
   Upper Value] 밖인가 — 표 7-15 Event/Both 전송 조건. 타입별 원시 비트열
   해석은 siap_frame.h 의 siap_value_as_*() 로 통일한다. */
static bool _dp_out_of_range(const siap_dp_t *d)
{
    switch (d->main.value_type) {
    case SIAP_VALUE_TYPE_INT: {
        int32_t v  = siap_value_as_int(d->main.value);
        int32_t lo = siap_value_as_int(d->lower_value);
        int32_t hi = siap_value_as_int(d->upper_value);
        return v < lo || v > hi;
    }
    case SIAP_VALUE_TYPE_UINT:
        return d->main.value < d->lower_value || d->main.value > d->upper_value;
    case SIAP_VALUE_TYPE_FLOAT: {
        float v  = siap_value_as_float(d->main.value);
        float lo = siap_value_as_float(d->lower_value);
        float hi = siap_value_as_float(d->upper_value);
        return v < lo || v > hi;
    }
    default:
        return false;   /* RESERVED — init 이 이미 거부했어야 한다 */
    }
}

/* 디바이스별 스캔 스케줄(F-130, 펌웨어 설계서 §6.3). Period(표 7-15)의
   표준상 의미는 "데이터 전달주기"다 — 이 재사용은 그 의미를 재정의하는
   것이 아니다. 본 구현에 샘플링 주기 전용 필드가 없어 Period 를 내부
   스캔 간격으로도 재사용할 뿐이다(표준 미규정 결정, CLAUDE.md §3.5).
   Periodic/Both/Event 전부 자기 Period 로 스캔되고, 스캔 *결과의 처리*
   만 Transfer Mode 가 가른다(_due_send_next 참조 — Both 는 이 구현에서
   Periodic 과 동일하게 동작한다, §6.3). Event-only 노드도 이 스캔으로
   오류를 감지한다(8.2.1.1) — 감지 주기를 Periodic 유무에 기대지 않는다. */
static void _dev_due_tick(siap_node_t *node, uint32_t now)
{
    for (uint8_t i = 0; i < node->cfg.device_count; i++) {
        if ((int32_t)(now - node->dev_next_due[i]) >= 0) {
            node->dev_due = (uint16_t)(node->dev_due | (uint16_t)(1u << i));
            node->dev_next_due[i] = _advance_deadline(node->dev_next_due[i],
                (uint32_t)node->cfg.devices[i].period * 1000u, now);
        }
    }
    if (node->dev_due != 0u) node->due |= SIAP_DUE_DEVICE_VALUE;
}

static void _due_tick(siap_node_t *node, uint32_t now)
{
    _dev_due_tick(node, now);
    if ((int32_t)(now - node->t_keep_alive) >= 0) {
        node->due |= SIAP_DUE_KEEP_ALIVE;
        node->t_keep_alive = _advance_deadline(node->t_keep_alive,
            (uint32_t)node->cfg.profile.keep_alive_interval * 1000u, now);
    }
    if ((int32_t)(now - node->t_error) >= 0) {
        node->due |= SIAP_DUE_ERROR;
        node->t_error = _advance_deadline(node->t_error,
            (uint32_t)node->cfg.profile.noti_error_interval * 1000u, now);
    }
}

/* pending 이 비어 있을 때만 불린다(동시 대기 1건, §6.4). due 소스를
   cursor 순서로 최대 3번 훑어 이번 poll 에서 보낼 하나를 고른다. */
static void _due_send_next(siap_node_t *node, uint32_t now)
{
    for (uint8_t tries = 0; tries < 3u; tries++) {
        uint8_t bit = (uint8_t)(1u << node->cursor);
        node->cursor = (uint8_t)((node->cursor + 1u) % 3u);
        if (!(node->due & bit)) continue;

        if (bit == SIAP_DUE_DEVICE_VALUE) {
            if (node->state != SIAP_NS_RUNNING) continue;   /* FAULT 중엔 건너뛴다 */
            node->due = (uint8_t)(node->due & (uint8_t)~SIAP_DUE_DEVICE_VALUE);

            /* 이번 스캔에서 due 로 표시된 디바이스를 순서대로 처리한다.
               읽기 실패 첫 건에서 즉시 FAULT 로 멈춘다(8.2.1.1, 결함은
               노드당 하나만 추적) — 그 시점까지 성공한 디바이스는 값·
               Status 만 갱신되고 이번 회차엔 전송되지 않는다(다음 스캔에
               다시 due 로 잡힌다. 데이터 유실이 아니라 한 주기 지연이다). */
            uint16_t send_mask = 0;
            bool faulted = false;
            for (uint8_t i = 0; i < node->cfg.device_count; i++) {
                uint16_t bit_i = (uint16_t)(1u << i);
                if (!(node->dev_due & bit_i)) continue;
                node->dev_due = (uint16_t)(node->dev_due & (uint16_t)~bit_i);

                siap_dp_t *d = &node->cfg.devices[i];
                uint32_t raw;
                if (node->cfg.dev_ops->read_value(node->cfg.dev_ops->ctx, d->main.device_id, &raw) != 0) {
                    d->status = SIAP_STATUS_ABNORMAL;
                    node->fault_device_idx = i;
                    node->fault_nec = (uint8_t)SIAP_NEC_ERROR_DEVICE_INTERFACE;   /* CLAUDE.md §1-1 인용문 근거 */
                    faulted = true;
                    break;
                }
                d->main.value = raw;
                d->status = SIAP_STATUS_NORMAL;

                uint8_t tm = d->transfer_mode;
                if (tm == SIAP_TM_PERIODIC || tm == SIAP_TM_BOTH || _dp_out_of_range(d))
                    send_mask = (uint16_t)(send_mask | bit_i);
            }
            if (node->dev_due != 0u) node->due |= SIAP_DUE_DEVICE_VALUE;   /* 남은 디바이스는 다음 기회에 */

            if (faulted) {
                node->state = SIAP_NS_FAULT;
                _pending_begin(node, SIAP_NOTI_ERROR, node->fault_nec, now);
                return;
            }
            if (send_mask != 0u) {
                _pending_begin(node, SIAP_NOTI_DEVICE_VALUE, send_mask, now);
                return;
            }
            continue;   /* 이번 스캔의 디바이스가 전부 Event-in-range — 보낼 것 없음 */
        }
        if (bit == SIAP_DUE_KEEP_ALIVE) {
            if (node->state != SIAP_NS_RUNNING) continue;
            node->due = (uint8_t)(node->due & (uint8_t)~SIAP_DUE_KEEP_ALIVE);
            _pending_begin(node, SIAP_NOTI_KEEP_ALIVE, 0, now);
            return;
        }
        if (bit == SIAP_DUE_ERROR) {
            if (node->state != SIAP_NS_FAULT) continue;
            node->due = (uint8_t)(node->due & (uint8_t)~SIAP_DUE_ERROR);
            {
                siap_dp_t *fd = &node->cfg.devices[node->fault_device_idx];
                uint32_t raw;
                if (node->cfg.dev_ops->read_value(node->cfg.dev_ops->ctx, fd->main.device_id, &raw) == 0) {
                    fd->main.value = raw;
                    fd->status = SIAP_STATUS_NORMAL;
                    node->state = SIAP_NS_RUNNING;   /* 오류 해소(§6.2) */
                    return;
                }
            }
            _pending_begin(node, SIAP_NOTI_ERROR, node->fault_nec, now);
            return;
        }
    }
}

/* ═══════════════════════════════════════════════════════════════
 *  3. RES_* 응답 빌더 — RUNNING 의 "G→N 요청 수신 → RES_* 회신" 행
 * ═══════════════════════════════════════════════════════════════ */

static siap_np_t _build_np(const siap_node_t *node)
{
    siap_np_t np;
    np.sw_version = node->cfg.sw_version;
    np.gcg_id     = node->cfg.gcg_id;
    np.node_id    = node->cfg.node_id;
    np.status     = SIAP_STATUS_NORMAL;
    for (uint8_t i = 0; i < node->cfg.device_count; i++)
        if (node->cfg.devices[i].status == SIAP_STATUS_ABNORMAL) { np.status = SIAP_STATUS_ABNORMAL; break; }
    np.num_devices = node->cfg.device_count;
    return np;
}

/* {RSC 만} 응답 — RES_SET_* 8종 공통 형태(LAYOUT 참조). */
static void _reply_rsc_only(siap_node_t *node, siap_kind_t res_kind, siap_rsc_t rsc)
{
    siap_tx_reset(&node->enc);
    siap_hdr_t h = _build_hdr(node, res_kind, node->rx_hdr.msg_id, SIAP_RSC_BYTES);
    h.trans_type = node->rx_hdr.trans_type;
    if (!siap_tx_put_hdr(&node->enc, &h)) return;
    if (!siap_rsc_valid((uint8_t)rsc)) rsc = SIAP_RSC_INVALID_FORMAT;
    if (!siap_tx_put_rsc(&node->enc, rsc)) return;
    _tx_flush(node);
}

static void _reply_get_node_property(siap_node_t *node)
{
    siap_tx_reset(&node->enc);
    uint16_t plen = (uint16_t)(SIAP_RSC_BYTES + SIAP_NP_BYTES);
    siap_hdr_t h = _build_hdr(node, SIAP_RES_GET_NODE_PROPERTY, node->rx_hdr.msg_id, plen);
    if (!siap_tx_put_hdr(&node->enc, &h)) return;
    if (!siap_tx_put_rsc(&node->enc, SIAP_RSC_SUCCESS)) return;
    siap_np_t np = _build_np(node);
    if (!siap_tx_put_np(&node->enc, &np)) return;
    _tx_flush(node);
}

/* REQ_GET_DEVICE_PROPERTY/REQ_GET_DEVICE_VALUE 가 rx_ids[] 에 모아둔
   device_id 들 중 실제 등록된 것만 골라 idx[] 에 채운다. */
static uint8_t _resolve_requested_ids(const siap_node_t *node, uint8_t idx[SIAP_MAX_DEVICES_PER_NODE])
{
    uint8_t n = 0;
    for (uint8_t i = 0; i < node->rx_ids_n; i++) {
        int f = _find_device(node, node->rx_ids[i]);
        if (f >= 0 && n < SIAP_MAX_DEVICES_PER_NODE) idx[n++] = (uint8_t)f;
    }
    return n;
}

static void _reply_get_device_property(siap_node_t *node)
{
    uint8_t idx[SIAP_MAX_DEVICES_PER_NODE];
    uint8_t n = _resolve_requested_ids(node, idx);
    siap_rsc_t rsc = (node->rx_ids_n > 0 && n == 0) ? SIAP_RSC_INVALID_DEVICE_ID : SIAP_RSC_SUCCESS;

    siap_tx_seq_t *s = &node->tx_seq;
    s->kind = (uint8_t)SIAP_SEQ_RES_GET_DEVICE_PROPERTY;
    s->rsc = (uint8_t)rsc;
    s->msg_id = node->rx_hdr.msg_id;
    s->n = n;
    s->next = 0;
    s->hdr_done = false;
    for (uint8_t j = 0; j < n; j++) s->idx[j] = idx[j];
    _tx_seq_pump(node);   /* TX_WINDOW(51B)는 요소 하나분 — 청크마다 완전히 flush 후 진행(§5.8, F-133) */
}

static void _reply_get_node_device_property_all(siap_node_t *node)
{
    siap_tx_seq_t *s = &node->tx_seq;
    s->kind = (uint8_t)SIAP_SEQ_RES_GET_NODE_DEVICE_PROPERTY_ALL;
    s->rsc = (uint8_t)SIAP_RSC_SUCCESS;
    s->msg_id = node->rx_hdr.msg_id;
    s->n = node->cfg.device_count;
    s->next = 0;
    s->hdr_done = false;
    for (uint8_t i = 0; i < node->cfg.device_count; i++) s->idx[i] = i;
    _tx_seq_pump(node);   /* TX_WINDOW(51B)는 요소 하나분 — 청크마다 완전히 flush 후 진행(§5.8, F-133) */
}

static void _reply_get_device_value(siap_node_t *node)
{
    uint8_t idx[SIAP_MAX_DEVICES_PER_NODE];
    uint8_t n = _resolve_requested_ids(node, idx);
    siap_rsc_t rsc = (node->rx_ids_n > 0 && n == 0) ? SIAP_RSC_INVALID_DEVICE_ID : SIAP_RSC_SUCCESS;

    for (uint8_t j = 0; j < n; j++) {
        siap_dp_t *d = &node->cfg.devices[idx[j]];
        uint32_t raw;
        if (node->cfg.dev_ops->read_value(node->cfg.dev_ops->ctx, d->main.device_id, &raw) == 0) {
            d->main.value = raw;
            d->status = SIAP_STATUS_NORMAL;
        } else {
            d->status = SIAP_STATUS_ABNORMAL;
        }
    }

    siap_tx_seq_t *s = &node->tx_seq;
    s->kind = (uint8_t)SIAP_SEQ_RES_GET_DEVICE_VALUE;
    s->rsc = (uint8_t)rsc;
    s->msg_id = node->rx_hdr.msg_id;
    s->n = n;
    s->next = 0;
    s->hdr_done = false;
    for (uint8_t j = 0; j < n; j++) s->idx[j] = idx[j];
    _tx_seq_pump(node);   /* TX_WINDOW(51B)는 요소 하나분 — 청크마다 완전히 flush 후 진행(§5.8, F-133) */
}

static void _reply_get_mcp(siap_node_t *node)
{
    siap_tx_reset(&node->enc);
    uint16_t plen = (uint16_t)(SIAP_RSC_BYTES + SIAP_MCP_BYTES);
    siap_hdr_t h = _build_hdr(node, SIAP_RES_GET_MSG_FLOW_CONTROL_PROFILE, node->rx_hdr.msg_id, plen);
    if (!siap_tx_put_hdr(&node->enc, &h)) return;
    if (!siap_tx_put_rsc(&node->enc, SIAP_RSC_SUCCESS)) return;
    if (!siap_tx_put_mcp(&node->enc, &node->cfg.profile)) return;
    _tx_flush(node);
}

/* ═══════════════════════════════════════════════════════════════
 *  4. siap_sink_t 콜백 — siap_frame.c 스트리밍 디코더가 바이트 단위로 부른다
 * ═══════════════════════════════════════════════════════════════ */

static int8_t _on_header(void *ctx, const siap_hdr_t *h, siap_kind_t k, uint16_t n)
{
    siap_node_t *node = (siap_node_t *)ctx;
    node->rx_hdr      = *h;
    node->rx_kind      = k;
    node->rx_n          = n;
    node->rx_have_hdr  = true;
    node->rx_ids_n      = 0;
    /* 라우팅·상태 게이팅은 on_fixed/on_element/on_end 에서 node->state 를
       직접 보고 결정한다(§6.2 "표에 없으면 무시") — 여기서는 항상 수락해
       스트리밍 파싱 자체는 계속 진행시킨다(요소 단위 즉시 적용, §5.6). */
    return 0;
}

static int8_t _on_fixed(void *ctx, const uint8_t *buf, uint8_t len)
{
    siap_node_t *node = (siap_node_t *)ctx;
    (void)len;
    if (!_addressed_to_me(node, &node->rx_hdr)) return 0;

    if (node->rx_kind == SIAP_RES_SET_CONNECTION) {
        if (node->state != SIAP_NS_CONNECTING || node->pending.kind != (uint8_t)SIAP_REQ_SET_CONNECTION
            || node->rx_hdr.msg_id != node->pending.msg_id)
            return 0;
        siap_rsc_t rsc = (siap_rsc_t)buf[0];
        size_t bp = 8;
        siap_decode_np(buf, &bp, &node->rx_np);
        if (rsc != SIAP_RSC_SUCCESS) return -(int8_t)rsc;
        return 0;
    }
    if (node->rx_kind == SIAP_REQ_SET_NODE_PROPERTY) {
        if (node->state != SIAP_NS_RUNNING) return 0;
        size_t bp = 0;
        siap_decode_np(buf, &bp, &node->rx_np);
        return 0;
    }
    if (node->rx_kind == SIAP_REQ_SET_MSG_FLOW_CONTROL_PROFILE) {
        if (node->state != SIAP_NS_RUNNING) return 0;
        size_t bp = 0;
        siap_decode_mcp(buf, &bp, &node->rx_mcp);
        return 0;
    }
    return 0;
}

static int8_t _on_element(void *ctx, uint16_t i, const uint8_t *buf, uint8_t len)
{
    siap_node_t *node = (siap_node_t *)ctx;
    (void)i; (void)len;
    if (!_addressed_to_me(node, &node->rx_hdr)) return 0;

    switch (node->rx_kind) {
    case SIAP_RES_SET_CONNECTION: {
        if (node->state != SIAP_NS_CONNECTING) return 0;
        siap_dp_t dp; size_t bp = 0;
        siap_decode_dp(buf, &bp, &dp);
        int idx = _find_device(node, dp.main.device_id);
        if (idx >= 0) node->cfg.devices[idx] = dp;
        return 0;
    }
    /* §6.6 — 구동기를 움직이는 유일한 경로 */
    case SIAP_REQ_SET_DEVICE_CONTROL: {
        if (node->state != SIAP_NS_RUNNING) return 0;
        siap_dmi_t dmi; size_t bp = 0;
        siap_decode_dmi(buf, &bp, &dmi);
        int idx = _find_device(node, dmi.device_id);
        if (idx < 0) return -(int8_t)SIAP_RSC_INVALID_DEVICE_ID;
        siap_dp_t *d = &node->cfg.devices[idx];
        if (d->main.value_type != dmi.value_type) return -(int8_t)SIAP_RSC_INVALID_DATA_TYPE;
        if (node->cfg.dev_ops->write_value(node->cfg.dev_ops->ctx, dmi.device_id, dmi.value) == 0)
            d->main.value = dmi.value;
        return 0;
    }
    case SIAP_REQ_SET_DEVICE_PROPERTY:
    case SIAP_REQ_SET_NODE_DEVICE_PROPERTY_ALL: {
        if (node->state != SIAP_NS_RUNNING) return 0;
        siap_dp_t dp; size_t bp = 0;
        siap_decode_dp(buf, &bp, &dp);
        int idx = _find_device(node, dp.main.device_id);
        if (idx < 0) return -(int8_t)SIAP_RSC_INVALID_DEVICE_ID;
        node->cfg.devices[idx] = dp;
        return 0;
    }
    case SIAP_REQ_SET_DEVICE_INIT: {
        if (node->state != SIAP_NS_RUNNING) return 0;
        uint8_t device_id = buf[0];
        int idx = _find_device(node, device_id);
        if (idx < 0) return -(int8_t)SIAP_RSC_INVALID_DEVICE_ID;
        uint32_t raw;
        if (node->cfg.dev_ops->read_value(node->cfg.dev_ops->ctx, device_id, &raw) == 0) {
            node->cfg.devices[idx].main.value = raw;
            node->cfg.devices[idx].status = SIAP_STATUS_NORMAL;
        } else {
            node->cfg.devices[idx].status = SIAP_STATUS_ABNORMAL;
        }
        return 0;
    }
    case SIAP_REQ_GET_DEVICE_PROPERTY:
    case SIAP_REQ_GET_DEVICE_VALUE: {
        if (node->state != SIAP_NS_RUNNING) return 0;
        if (node->rx_ids_n < SIAP_MAX_DEVICES_PER_NODE) node->rx_ids[node->rx_ids_n++] = buf[0];
        return 0;
    }
    default:
        return 0;
    }
}

static void _on_end(void *ctx, siap_rsc_t rsc, siap_clause_t clause)
{
    siap_node_t *node = (siap_node_t *)ctx;
    (void)clause;

    bool have_hdr = node->rx_have_hdr;
    node->rx_have_hdr = false;   /* 다음 프레임을 위해 즉시 리셋 */
    if (!have_hdr) return;       /* 헤더 단계에서 걸러진 프레임 — 답할 정보가 없다 */
    if (!_addressed_to_me(node, &node->rx_hdr)) return;
    if (node->state == SIAP_NS_HALTED) return;   /* poll() 이 이미 막지만 방어적으로 한 번 더 */

    uint32_t now = node->cfg.io->millis(node->cfg.io->ctx);

    switch (node->rx_kind) {
    case SIAP_RES_SET_CONNECTION:
        if (node->state != SIAP_NS_CONNECTING || node->pending.kind != (uint8_t)SIAP_REQ_SET_CONNECTION
            || node->rx_hdr.msg_id != node->pending.msg_id)
            return;
        if (rsc == SIAP_RSC_SUCCESS) {
            _pending_clear(node);
            node->state = SIAP_NS_RUNNING;
            node->backoff_shift = 0;
            node->due = 0;
            node->dev_due = 0;
            for (uint8_t i = 0; i < node->cfg.device_count; i++)   /* F-130 — 디바이스별 스캔 스케줄 */
                node->dev_next_due[i] = now + (uint32_t)node->cfg.devices[i].period * 1000u;
            node->t_keep_alive   = now + (uint32_t)node->cfg.profile.keep_alive_interval * 1000u;
            node->t_error        = now + (uint32_t)node->cfg.profile.noti_error_interval * 1000u;
        } else if (_rsc_retryable(rsc)) {
            /* 표 §6.2 — "Timeout 후 재송신, msg_id 유지". 응답을 받았어도
               즉시 재송신하지 않는다 — pending 을 그대로 두어 기존 재전송
               타이머(§6.4)가 Timeout 뒤에 같은 msg_id 로 재시도하게 한다. */
        } else {
            _pending_clear(node);
            node->state = SIAP_NS_HALTED;   /* 재시도 불가 7종 → HALTED(F-076) */
        }
        return;

    case SIAP_ACK: {
        /* F-132/F-046 — 응답 매칭은 Node ID + Message Identifier + Message
           Type 셋 다 맞아야 한다. msg_id 만 같다고 아무 pending 이나
           해제하면 안 된다: pending 이 REQ_SET_CONNECTION(응답은 ACK 가
           아니라 RES_SET_CONNECTION)일 때 msg_id 가 우연히 같은 ACK 가
           와도 무시해야 한다 — 그렇지 않으면 pending 이 사라진 채
           CONNECTING 에 남아 재전송도 못 하고 영구 정지한다. ACK 를
           기대하는 pending 은 Notify 4종뿐이다(§6.2-a(1)). */
        siap_kind_t was = (siap_kind_t)node->pending.kind;
        bool expects_ack = (was == SIAP_NOTI_KEEP_ALIVE || was == SIAP_NOTI_REBOOT ||
                             was == SIAP_NOTI_ERROR || was == SIAP_NOTI_DEVICE_VALUE);
        if (!expects_ack || node->rx_hdr.msg_id != node->pending.msg_id)
            return;
        _pending_clear(node);
        if (was == SIAP_NOTI_REBOOT && node->state == SIAP_NS_REBOOTING)
            node->state = SIAP_NS_BOOT;   /* 그림 8-56 — 알림 성공 */
        return;
    }

    case SIAP_NOTI_DISCONNECT:
        if (rsc != SIAP_RSC_SUCCESS) return;
        _send_ack_now(node, &node->rx_hdr);   /* 상태 무관 즉시 ACK(§6.2-a(1)) */
        _pending_clear(node);
        node->due = 0;
        node->dev_due = 0;
        node->state = SIAP_NS_DISCONNECTED;
        node->t_backoff_until = now + _backoff_ms(node);
        return;

    case SIAP_NOTI_REBOOT:
        if (rsc != SIAP_RSC_SUCCESS) return;
        /* 0943 §6.1.2/§8.2.1.4 — 게이트웨이발 리부팅 알림도 정상
           수신하면 상태 게이트보다 먼저 ACK한다. 수신 알림은 노드 자신의
           리부팅 명령이 아니므로 현재 상태와 송신 pending은 유지한다(F-210). */
        _send_ack_now(node, &node->rx_hdr);
        return;

    /* ── 이하 RUNNING 전용 — "G→N 요청 수신 → RES_* 회신"(§6.2) ── */
    case SIAP_REQ_SET_DEVICE_CONTROL:
        if (node->state != SIAP_NS_RUNNING) return;
        _reply_rsc_only(node, SIAP_RES_SET_DEVICE_CONTROL, rsc);
        return;
    case SIAP_REQ_SET_REBOOT:
        if (node->state != SIAP_NS_RUNNING) return;
        _reply_rsc_only(node, SIAP_RES_SET_REBOOT, SIAP_RSC_SUCCESS);
        node->state = SIAP_NS_REBOOTING;
        _pending_begin(node, SIAP_NOTI_REBOOT, 0, now);
        return;
    case SIAP_REQ_SET_DEVICE_INIT:
        if (node->state != SIAP_NS_RUNNING) return;
        _reply_rsc_only(node, SIAP_RES_SET_DEVICE_INIT, rsc);
        return;
    case SIAP_REQ_SET_DEVICE_INIT_ALL:
        if (node->state != SIAP_NS_RUNNING) return;
        for (uint8_t i = 0; i < node->cfg.device_count; i++) {
            uint32_t raw;
            if (node->cfg.dev_ops->read_value(node->cfg.dev_ops->ctx,
                                               node->cfg.devices[i].main.device_id, &raw) == 0) {
                node->cfg.devices[i].main.value = raw;
                node->cfg.devices[i].status = SIAP_STATUS_NORMAL;
            } else {
                node->cfg.devices[i].status = SIAP_STATUS_ABNORMAL;
            }
        }
        _reply_rsc_only(node, SIAP_RES_SET_DEVICE_INIT_ALL, SIAP_RSC_SUCCESS);
        return;
    case SIAP_REQ_SET_NODE_PROPERTY:
        if (node->state != SIAP_NS_RUNNING) return;
        _reply_rsc_only(node, SIAP_RES_SET_NODE_PROPERTY, rsc);
        return;
    case SIAP_REQ_SET_DEVICE_PROPERTY:
        if (node->state != SIAP_NS_RUNNING) return;
        _reply_rsc_only(node, SIAP_RES_SET_DEVICE_PROPERTY, rsc);
        return;
    case SIAP_REQ_SET_NODE_DEVICE_PROPERTY_ALL:
        if (node->state != SIAP_NS_RUNNING) return;
        _reply_rsc_only(node, SIAP_RES_SET_NODE_DEVICE_PROPERTY_ALL, rsc);
        return;
    case SIAP_REQ_SET_MSG_FLOW_CONTROL_PROFILE:
        if (node->state != SIAP_NS_RUNNING) return;
        if (rsc == SIAP_RSC_SUCCESS) node->cfg.profile = node->rx_mcp;
        _reply_rsc_only(node, SIAP_RES_SET_MSG_FLOW_CONTROL_PROFILE, rsc);
        return;
    case SIAP_REQ_GET_NODE_PROPERTY:
        if (node->state != SIAP_NS_RUNNING) return;
        _reply_get_node_property(node);
        return;
    case SIAP_REQ_GET_DEVICE_PROPERTY:
        if (node->state != SIAP_NS_RUNNING) return;
        _reply_get_device_property(node);
        return;
    case SIAP_REQ_GET_NODE_DEVICE_PROPERTY_ALL:
        if (node->state != SIAP_NS_RUNNING) return;
        _reply_get_node_device_property_all(node);
        return;
    case SIAP_REQ_GET_DEVICE_VALUE:
        if (node->state != SIAP_NS_RUNNING) return;
        _reply_get_device_value(node);
        return;
    case SIAP_REQ_GET_MSG_FLOW_CONTROL_PROFILE:
        if (node->state != SIAP_NS_RUNNING) return;
        _reply_get_mcp(node);
        return;

    default:
        return;   /* REQ_SET_CONNECTION·RES_*·다른 NOTI_* 는 노드가 받을 일이 없다 — 무시 */
    }
}

/* ═══════════════════════════════════════════════════════════════
 *  5. 공개 API
 * ═══════════════════════════════════════════════════════════════ */

static void _boot_self_check(siap_node_t *node)
{
    /* §6.1 — 자가진단 실패는 연결을 막지 않는다. 실패분만 ABNORMAL 로 두고
       계속 진행한다(합성 데이터 금지 — 실패 시 값을 지어내지 않는다). */
    for (uint8_t i = 0; i < node->cfg.device_count; i++) {
        siap_dp_t *d = &node->cfg.devices[i];
        uint32_t raw;
        if (node->cfg.dev_ops->read_value(node->cfg.dev_ops->ctx, d->main.device_id, &raw) == 0) {
            d->main.value = raw;
            d->status = SIAP_STATUS_NORMAL;
        } else {
            d->status = SIAP_STATUS_ABNORMAL;
        }
    }
}

bool siap_node_init(siap_node_t *node, const siap_node_cfg_t *cfg)
{
    if (!node || !cfg || !cfg->io || !cfg->dev_ops || !cfg->devices) return false;
    if (!cfg->io->read_byte || !cfg->io->write || !cfg->io->millis) return false;
    if (!cfg->dev_ops->read_value || !cfg->dev_ops->write_value) return false;
    /* §4.1-a 진입점 범위 검증표 */
    if (cfg->gcg_id > 0x000FFFFFu || cfg->node_id > 0x000FFFFFu) return false;
    if (cfg->device_count < 1u || cfg->device_count > SIAP_MAX_DEVICES_PER_NODE) return false;
    for (uint8_t i = 0; i < cfg->device_count; i++) {
        const siap_dp_t *d = &cfg->devices[i];
        if (d->main.value_type > SIAP_VALUE_TYPE_FLOAT) return false;      /* 0~2, 3=RESERVED 거부 */
        if (!siap_subtype_valid(d->main.subtype)) return false;
        if (d->period > 0x3FFFu) return false;                             /* 14bit(표 7-15) */
        for (uint8_t j = 0; j < i; j++)
            if (cfg->devices[j].main.device_id == d->main.device_id) return false;   /* 노드 내 유일 */
    }

    node->state = SIAP_NS_BOOT;
    node->cfg = *cfg;
    {
        const siap_mcp_t *p = &node->cfg.profile;
        if (p->recv_timeout == 0 && p->num_retry == 0 && p->noti_error_interval == 0
            && p->keep_alive_interval == 0)
            node->cfg.profile = SIAP_PROFILE_DEFAULT;
    }

    siap_sink_t sink;
    sink.on_header  = _on_header;
    sink.on_fixed   = _on_fixed;
    sink.on_element = _on_element;
    sink.on_end     = _on_end;
    sink.ctx        = node;
    siap_dec_init(&node->dec, sink, node->cfg.mode);
    siap_tx_reset(&node->enc);
    node->tx_busy = false;
    node->tx_seq.kind = (uint8_t)SIAP_SEQ_NONE;

    node->next_msg_id = 0;   /* 7.2.2 — 0 도 유효한 순번이다(F-135) */
    node->pending.kind = (uint8_t)SIAP_KIND_NONE;
    node->pending.msg_id = 0;
    node->pending.retry = 0;
    node->pending.t_sent = 0;
    node->pending.arg = 0;

    node->t_keep_alive = 0;
    node->t_error = 0;
    node->due = 0;
    node->cursor = 0;
    node->dev_due = 0;
    for (uint8_t i = 0; i < SIAP_MAX_DEVICES_PER_NODE; i++) node->dev_next_due[i] = 0;

    node->fault_nec = 0;
    node->fault_device_idx = 0;

    node->t_last_rx = 0;
    node->have_last_rx = false;

    node->t_backoff_until = 0;
    node->backoff_shift = 0;

    node->on_soft_reset = NULL;
    node->on_soft_reset_ctx = NULL;

    node->rx_have_hdr = false;
    node->rx_kind = SIAP_KIND_NONE;
    node->rx_n = 0;
    node->rx_ids_n = 0;

    return true;
}

void siap_node_poll(siap_node_t *node)
{
    if (!node) return;
    uint32_t now = node->cfg.io->millis(node->cfg.io->ctx);

    if (node->state == SIAP_NS_HALTED) {
        /* §6.1/§6.2 — 수신 프레임을 읽어 버리고 응답하지 않는다. 전원
           재인가로만 벗어난다(F-076, 상태 무관 전이의 유일한 예외). */
        uint8_t b;
        while (node->cfg.io->read_byte(node->cfg.io->ctx, &b) == 1) { /* discard */ }
        return;
    }

    if (node->state == SIAP_NS_BOOT) {
        _boot_self_check(node);
        node->state = SIAP_NS_INIT;
    }
    if (node->state == SIAP_NS_INIT) {
        node->state = SIAP_NS_CONNECTING;
        _pending_begin(node, SIAP_REQ_SET_CONNECTION, 0, now);
    }

    /* 수신 — 이번 poll 에서 가능한 만큼 바이트를 먹인다. */
    {
        uint8_t b;
        bool got_any = false;
        for (;;) {
            int8_t rb = node->cfg.io->read_byte(node->cfg.io->ctx, &b);
            if (rb == 1) {
                siap_dec_feed(&node->dec, b);
                node->t_last_rx = now;
                node->have_last_rx = true;
                got_any = true;
                continue;
            }
            if (rb < 0) {
                /* 링크 오류 — NOTI_DISCONNECT 수신과 같은 취급(§6.2 마지막 행) */
                if (node->state != SIAP_NS_DISCONNECTED) {
                    _pending_clear(node);
                    node->due = 0;
                    node->dev_due = 0;
                    node->state = SIAP_NS_DISCONNECTED;
                    node->t_backoff_until = now + _backoff_ms(node);
                }
            }
            break;
        }
        if (!got_any && node->have_last_rx
            && (uint32_t)(now - node->t_last_rx) >= SIAP_T_GAP_MS) {
            siap_dec_on_gap(&node->dec);
            node->have_last_rx = false;
        }
    }

    /* 이전에 못 다 내보낸 프레임 이어서 flush(§5.8) */
    if (node->tx_busy) _tx_flush(node);
    /* 청크 하나가 방금 완전히 나갔으면 다중 청크 시퀀스의 다음 청크로
       이어간다(F-133) — tx_busy 인 동안은 절대 부르지 않는다. */
    if (!node->tx_busy) _tx_seq_pump(node);

    _pending_tick(node, now);

    switch (node->state) {
    case SIAP_NS_RUNNING:
    case SIAP_NS_FAULT:
        _due_tick(node, now);
        if (node->pending.kind == (uint8_t)SIAP_KIND_NONE) _due_send_next(node, now);
        break;
    case SIAP_NS_DISCONNECTED:
        if ((int32_t)(now - node->t_backoff_until) >= 0) {
            node->state = SIAP_NS_CONNECTING;
            _pending_begin(node, SIAP_REQ_SET_CONNECTION, 0, now);
        }
        break;
    default:
        break;
    }
}
