/*
 * arduino_actuator_node — Pro Mini 구동기 노드.
 *
 * 전송 계층(UART 9600)은 Uno 센서 노드와 **동일 3함수**다 — 다른 것은 디바이스
 * I/O 뿐이며, write_value 가 digitalWrite 한 줄이다. core/ 는 수정하지 않는다.
 */
#include <Arduino.h>

extern "C" {
#include <node_state.h>
#include <siap_types.h>
#include <subtype_registry.h>
}
#include "pins.h"

/* actuators.c(순수 C)의 상태 저장·해석 함수. */
extern "C" {
void     actuator_set_state(uint8_t device_id, uint32_t raw);
uint32_t actuator_get_state(uint8_t device_id);
bool     actuator_is_on(uint32_t raw);
}

static siap_dp_t   g_devices[2];
static siap_node_t g_node;

/* ── 전송 계층 (UART 9600) — Uno 와 동일 ──────────────────────────── */
extern "C" int8_t uart_read_byte(void *ctx, uint8_t *out) {
    (void)ctx;
    if (Serial.available() <= 0) return 0;
    int c = Serial.read();
    if (c < 0) return 0;
    *out = (uint8_t)c;
    return 1;
}

extern "C" int16_t uart_write(void *ctx, const uint8_t *buf, uint16_t len) {
    (void)ctx;
    /* 논블로킹 부분 쓰기. 여유 0이면 0을 돌려준다 — 가드가 없으면 avail==0 에서
       n=len 으로 떨어져 포화 버퍼에 블로킹 쓰기가 된다. */
    int avail = Serial.availableForWrite();
    if (avail <= 0) return 0;
    uint16_t n = ((uint16_t)avail < len) ? (uint16_t)avail : len;
    return (int16_t)Serial.write(buf, n);
}

extern "C" uint32_t uart_millis(void *ctx) { (void)ctx; return millis(); }

/* ── 디바이스 I/O — 구동기 2종 ────────────────────────────────────── */
static uint8_t pin_of(uint8_t device_id) {
    switch (device_id) {
        case DEV_ID_IRRIGATION_VALVE: return PIN_IRRIGATION_VALVE;
        case DEV_ID_FAN:              return PIN_FAN;
        default:                      return 0xFFu;
    }
}

extern "C" int8_t actuator_write_value(void *ctx, uint8_t device_id, uint32_t raw) {
    (void)ctx;
    uint8_t pin = pin_of(device_id);
    if (pin == 0xFFu) return -1;
    /* 범위 검사는 core/ 가 이미 마쳤다. 여기서는 반영만 한다. */
    digitalWrite(pin, actuator_is_on(raw) ? HIGH : LOW);
    actuator_set_state(device_id, raw);
    return 0;
}

extern "C" int8_t actuator_read_value(void *ctx, uint8_t device_id, uint32_t *raw) {
    (void)ctx;
    if (pin_of(device_id) == 0xFFu) return -1;
    *raw = actuator_get_state(device_id);   /* 현재 지시 상태를 보고 */
    return 0;
}

static const siap_io_t      g_io      = { uart_read_byte, uart_write, uart_millis, NULL };
static const siap_dev_ops_t g_dev_ops = { actuator_read_value, actuator_write_value, NULL };

/* on/off UINT 구동기 하나를 채운다. value_type=UINT, 유효범위 0~1. */
static void init_switch_actuator(siap_dp_t *d, uint8_t id, uint8_t subtype) {
    d->main.device_id  = id;
    d->main.dev_type   = SIAP_DEV_ACTUATOR;
    d->main.subtype    = subtype;
    d->main.value_type = SIAP_VALUE_TYPE_UINT;
    d->main.value      = 0u;
    d->transfer_mode   = SIAP_TM_PERIODIC;   /* 상태를 주기 보고 */
    d->period          = 5u;
    d->lower_value     = 0u;
    d->upper_value     = 1u;
    d->lower_limit     = 0u;
    d->upper_limit     = 1u;
    d->precision       = 1u;
    d->status          = SIAP_STATUS_NORMAL;
}

void setup() {
    Serial.begin(9600);
    pinMode(PIN_IRRIGATION_VALVE, OUTPUT); digitalWrite(PIN_IRRIGATION_VALVE, LOW);
    pinMode(PIN_FAN,              OUTPUT); digitalWrite(PIN_FAN,              LOW);

    init_switch_actuator(&g_devices[0], DEV_ID_IRRIGATION_VALVE, SIAP_SUBTYPE_IRRIGATION_VALVE);
    init_switch_actuator(&g_devices[1], DEV_ID_FAN,              SIAP_SUBTYPE_FAN);

    siap_node_cfg_t cfg;
    cfg.gcg_id       = 0x00001u;
    cfg.node_id      = 0x00066u;    /* 데모 노드 0x66 (index.html) */
    cfg.sw_version   = 0x10u;
    cfg.io           = &g_io;
    cfg.dev_ops      = &g_dev_ops;
    cfg.devices      = g_devices;
    cfg.device_count = 2u;
    cfg.profile      = SIAP_PROFILE_DEFAULT;
    cfg.mode         = SIAP_MODE_STRICT;

    if (!siap_node_init(&g_node, &cfg)) { for (;;) { /* halt — 진입점 범위 검증 실패 */ } }
}

void loop() {
    siap_node_poll(&g_node);
}
