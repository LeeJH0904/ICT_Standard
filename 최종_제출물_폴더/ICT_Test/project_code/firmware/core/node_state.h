#ifndef SIAP_NODE_STATE_H
#define SIAP_NODE_STATE_H
/*
 * 노드 상태 머신 — 펌웨어 설계서 §6. siap_frame.c(스트리밍 코덱) 위에
 * 8상태 전이(§6.1) · pending 재전송(§6.4) · due 회전 커서(§6.4-a) ·
 * RES_SET_CONNECTION 오류 RSC 분류(§6.5)를 얹는다.
 *
 * core/ 는 하드웨어 의존성 0이다(CLAUDE.md §1-5). 이 파일이 아는 하드웨어는
 * siap_io_t/siap_dev_ops_t(siap_types.h) 뒤에 있는 함수 포인터뿐이다.
 * "온실 관제" · "온도 센서" 같은 도메인 어휘는 여기 등장하지 않는다(§2.3).
 */
#include "siap_types.h"
#include "siap_frame.h"

/* C++/Arduino 스케치에서 C 링키지로 부를 수 있게 한다(bitpack.h 주석 참조) —
   C 컴파일 시엔 비활성, 언어 매크로라 core 순수성(§1-5)과 무관하다. */
#ifdef __cplusplus
extern "C" {
#endif

/* ═══════════════════════════════════════════════════════════════
 *  0. 상태 — §6.1 다이어그램. 노드 자신의 상태이며 게이트웨이가 보는
 *     상태(아키텍처 §6.1)와는 다른 열거형이다.
 * ═══════════════════════════════════════════════════════════════ */
typedef enum {
    SIAP_NS_BOOT = 0,     /* 디바이스 자가진단 */
    SIAP_NS_INIT,         /* REQ_SET_CONNECTION 송신 준비 */
    SIAP_NS_CONNECTING,   /* RES_SET_CONNECTION 대기 */
    SIAP_NS_RUNNING,      /* 연결 승인 후 정상 운용 */
    SIAP_NS_FAULT,        /* 디바이스 오류 — 연결 승인 이후에만 존재(F-072) */
    SIAP_NS_REBOOTING,    /* NOTI_REBOOT 알림 후 리셋 대기(그림 8-56) */
    SIAP_NS_DISCONNECTED, /* 백오프 후 재접속 대기 */
    SIAP_NS_HALTED,       /* 영구 정지. 전원 재인가로만 벗어난다(F-076) */
} siap_node_state_t;

/* ═══════════════════════════════════════════════════════════════
 *  1. pending 슬롯 — §6.4. 요청·알림 공통, 동시 대기 1건.
 *     kind 는 siap_kind_t 값을 그대로 담는다(SIAP_KIND_NONE = 비어 있음).
 *     설계서 §3.4 의 10 B 산정과 동일한 필드 구성이다.
 * ═══════════════════════════════════════════════════════════════ */
typedef struct {
    uint8_t  kind;     /* siap_kind_t. 비어 있으면 SIAP_KIND_NONE */
    uint16_t msg_id;   /* 재전송에도 유지(F-041) */
    uint8_t  retry;    /* 지금까지 재전송한 횟수 */
    uint32_t t_sent;   /* 마지막 송신 시각(ms) */
    uint16_t arg;      /* 재인코딩 인자 — NOTI_ERROR: NEC 코드,
                           NOTI_DEVICE_VALUE: 보낼 devices[] 인덱스 비트마스크(F-130) */
} siap_pending_t;

/* ═══════════════════════════════════════════════════════════════
 *  2. due 비트 + 회전 커서 — §6.4-a. 기아 방지의 핵심.
 * ═══════════════════════════════════════════════════════════════ */
#define SIAP_DUE_DEVICE_VALUE 0x01u   /* bit0 — dev_due(아래)가 하나라도 서면 선다 */
#define SIAP_DUE_KEEP_ALIVE   0x02u   /* bit1 */
#define SIAP_DUE_ERROR        0x04u   /* bit2 */

/* ═══════════════════════════════════════════════════════════════
 *  2-a. 다중 청크 송신 진행 상태 — §5.8, F-133.
 *
 *  헤더 하나에 요소(DP/DMI) 여러 개가 붙는 프레임(NOTI_DEVICE_VALUE ·
 *  RES_GET_DEVICE_PROPERTY · RES_GET_NODE_DEVICE_PROPERTY_ALL ·
 *  RES_GET_DEVICE_VALUE)은 TX_WINDOW(51B)가 헤더+요소 하나분이라 청크
 *  단위로 나눠 보낸다. siap_io_t.write 는 부분 쓰기를 허용하는 논블로킹
 *  계약이라(§2.2·§5.8), 이전 청크가 완전히 flush 되기 전에 다음 청크를
 *  만들며 같은 win 을 siap_tx_reset() 하면 미전송 잔여가 지워진다
 *  (F-133). 이 구조체가 "지금 몇 번째 청크까지 나갔는가"를 들고 있어
 *  poll() 이 이어서 마저 보낼 수 있게 한다. */
typedef enum {
    SIAP_SEQ_NONE = 0,
    SIAP_SEQ_NOTI_DEVICE_VALUE,
    SIAP_SEQ_RES_GET_DEVICE_PROPERTY,
    SIAP_SEQ_RES_GET_NODE_DEVICE_PROPERTY_ALL,
    SIAP_SEQ_RES_GET_DEVICE_VALUE,
    SIAP_SEQ_REQ_SET_NODE_DEVICE_PROPERTY_ALL,  /* F-198 — 노드→GCG 디바이스 구성 선언(8.1.3.3).
                                                   요청이라 고정부에 RSC 가 없다(NP + DP×N) */
} siap_tx_seq_kind_t;

typedef struct {
    uint8_t  kind;      /* siap_tx_seq_kind_t. NONE 이면 진행 중인 다중 청크 송신 없음 */
    uint8_t  rsc;        /* RES_* 전용 — 고정부에 실을 RSC */
    uint16_t msg_id;
    uint8_t  idx[SIAP_MAX_DEVICES_PER_NODE];  /* devices[] 인덱스, 요소 순서대로 */
    uint8_t  n;          /* 요소 개수 */
    uint8_t  next;       /* 다음에 보낼 idx[] 위치. n 이면 요소 전송 끝 */
    bool     hdr_done;   /* 헤더(+고정부) 청크가 flush 완료됐는가 */
} siap_tx_seq_t;

/* ═══════════════════════════════════════════════════════════════
 *  3. 노드 설정 — 보드가 core/ 에 넘기는 전부(펌웨어 설계서 §2.4).
 * ═══════════════════════════════════════════════════════════════ */
typedef struct {
    uint32_t gcg_id;              /* 20bit. 표 7-8 */
    uint32_t node_id;             /* 20bit */
    uint8_t  sw_version;
    const siap_io_t     *io;      /* §2.2 */
    const siap_dev_ops_t *dev_ops;/* §2.2 */
    siap_dp_t *devices;           /* 보드가 소유하는 배열 — DEVICE_PROPERTY 언팩 구조체 */
    uint8_t   device_count;       /* 1~16(F-064) */
    siap_mcp_t profile;           /* MSG_CONTROL_PROFILE. 0 이면 SIAP_PROFILE_DEFAULT 를 쓴다 */
    siap_mode_t mode;             /* strict(기본) / extended */
} siap_node_cfg_t;

/* 표 7-18 기본값 — Message Receive Timeout 2s · Num. of Retry 3회(0937
   요구사항 대조표 §"배수 3의 근거") · Notify Error Interval 30s ·
   Keep Alive Interval 60s. 전부 sec 단위다(F-033). */
extern const siap_mcp_t SIAP_PROFILE_DEFAULT;

/* ═══════════════════════════════════════════════════════════════
 *  4. 노드 상태 머신 본체
 * ═══════════════════════════════════════════════════════════════ */
typedef struct {
    siap_node_state_t state;
    siap_node_cfg_t   cfg;

    siap_dec_t dec;      /* 수신 — siap_frame.h 스트리밍 디코더 */
    siap_enc_t enc;      /* 송신 — siap_frame.h 스트리밍 인코더 */
    bool       tx_busy;  /* enc 에 flush 대기 중인 프레임이 있다 */

    uint16_t next_msg_id;      /* 0 부터. 7.2.2 그대로 — 0도 유효한 순번, 0xFFFF 다음 0 (F-135) */
    siap_pending_t pending;    /* 동시 대기 1건(§6.4). NOTI_DEVICE_VALUE 는 arg 에
                                   보낼 devices[] 인덱스 비트마스크를 담는다(F-130) */
    siap_tx_seq_t  tx_seq;     /* 다중 청크 송신 진행 상태(F-133) */

    /* §6.4-a — 3 소스 공통 회전. t_keep_alive/t_error 는 다음 만료 절대
       시각(ms). DEVICE_VALUE 는 디바이스별로 갈린다 — 아래 dev_* 참조(F-130) */
    uint32_t t_keep_alive;
    uint32_t t_error;
    uint8_t  due;
    uint8_t  cursor;      /* 0=DEVICE_VALUE 1=KEEP_ALIVE 2=ERROR, 전송마다 +1 mod 3 */

    /* 디바이스별 스캔 스케줄 — F-130, 펌웨어 설계서 §6.3. Period(표 7-15)의
       표준상 의미는 "데이터 전달주기"다 — 본 구현에 샘플링 주기 전용
       필드가 없어 이를 내부 스캔 간격으로도 재사용할 뿐이며, 표준 필드
       의미의 재정의가 아니다(표준 미규정 결정, CLAUDE.md §3.5). 스캔
       결과의 전송 여부만 Transfer Mode 가 가른다(_due_send_next 참조 —
       Both 는 이 구현에서 Periodic 과 동일하게 동작한다). dev_due 의
       비트 i 는 devices[i]가 스캔 대상이 됐고 아직 처리 전임을 뜻한다 —
       처리(전송 또는 FAULT 판정)가 pending 적체로 미뤄져도 잃지 않는다. */
    uint32_t dev_next_due[SIAP_MAX_DEVICES_PER_NODE];
    uint16_t dev_due;

    /* FAULT(8.2.1.1) — 결함은 노드 전체에 대해 하나만 추적한다(NOTI_ERROR
       는 표 7-4 상 device_id 필드가 없다 — LAYOUT 참조). */
    uint8_t fault_nec;         /* siap_nec_t. FAULT 진입 사유 */
    uint8_t fault_device_idx;  /* devices[] 인덱스. 해소 재확인 대상 */

    /* §5.7 재동기 T_gap 판정용 — 마지막 수신 바이트 시각 */
    uint32_t t_last_rx;
    bool     have_last_rx;

    /* DISCONNECTED 백오프 — Timeout × 2ⁿ, 상한 300s(§6.5) */
    uint32_t t_backoff_until;
    uint8_t  backoff_shift;

    /* REBOOTING → BOOT 완료 후 실제 재기동은 보드의 몫이다(§6.6 과 같은
       경계: core/ 는 재기동 "수단"을 모른다). 이 콜백이 NULL 이 아니면
       BOOT 전이 시 한 번 호출한다 — 호스트 테스트는 NULL 로 두고
       state==SIAP_NS_BOOT 도달만 관찰한다. */
    void (*on_soft_reset)(void *ctx);
    void *on_soft_reset_ctx;

    /* 수신 프레임 처리용 임시 저장 — 프레임 하나의 수명 안에서만 유효하다.
       siap_sink_t 콜백(on_header~on_end) 사이를 넘나드는 유일한 상태다. */
    siap_hdr_t  rx_hdr;
    siap_kind_t rx_kind;
    uint16_t    rx_n;
    bool        rx_have_hdr;   /* on_header 가 실제로 불렸는가(헤더 단계 위반과 구분) */
    siap_np_t   rx_np;         /* RES_SET_CONNECTION / REQ_SET_NODE_PROPERTY 고정부 */
    siap_mcp_t  rx_mcp;        /* REQ_SET_MSG_FLOW_CONTROL_PROFILE 고정부 */
    uint8_t     rx_ids[SIAP_MAX_DEVICES_PER_NODE];  /* REQ_GET_* 의 DEVICE_ID 목록 */
    uint8_t     rx_ids_n;
} siap_node_t;

/* 초기화 — §4.1-a 진입점 범위 검증표를 강제한다: gcg_id/node_id 는
   0~2^20-1, device_count 는 1~16, device_id 는 노드 내 유일, subtype 은
   레지스트리 등재값, value_type 은 0~2, period 는 0~2^14-1. 하나라도
   벗어나면 false — "노드가 뜨지 않는다"(§4.1-a). */
bool siap_node_init(siap_node_t *node, const siap_node_cfg_t *cfg);

/* 논블로킹 한 틱. 보드 루프가 계속 부른다(펌웨어 설계서 §2.4). 매 호출마다
   가능한 만큼 바이트를 읽고 먹이고, pending timeout 을 검사하고, RUNNING
   에서는 due 소스를 회전 송신한다. */
void siap_node_poll(siap_node_t *node);

#ifdef __cplusplus
}
#endif

#endif /* SIAP_NODE_STATE_H */
