/*
 * esp32_node/esp32_node.ino — ESP32 노드.
 *
 * core/ 는 Uno·Pro Mini 와 **동일 파일**이다. 다른 것은 전송 계층뿐 — UART 대신
 * TCP over Wi-Fi. **같은 SIAP 바이트열이 TCP 위를 그대로 지나간다**(길이 프리앰블·
 * JSON 래핑 없음) — 이것이 3종 혼용 주장의 핵심이다. 재동기 코드도 core/ 에
 * 있고 ESP32 도 그대로 쓴다(보드별 분기를 만들지 않는다).
 *
 * 보드 지역 함수는 전부 `board_` 접두사를 쓴다 — ESP-IDF(`esp_`)·lwIP(`tcp_`)의
 * 전역 심볼과 충돌하지 않기 위해서다(예전 판의 `tcp_write` 가 lwIP `tcp_write` 와
 * 다중 정의로 링크 실패했다).
 */
#include <Arduino.h>
#include <WiFi.h>
#include "secrets.h"

extern "C" {
#include <node_state.h>
#include <siap_types.h>
#include <subtype_registry.h>
}

/* net.c(순수 C)의 변환·백오프 함수. */
extern "C" {
uint32_t siap_f32_bits(float v);
float    board_conv_temperature(uint16_t adc);
float    board_conv_co2(uint16_t adc);
uint32_t board_backoff_ms(uint8_t shift);
}

#define DEV_ID_TEMPERATURE  1
#define DEV_ID_CO2          2
#define DEV_ID_WINDOW       3
#define PIN_TEMPERATURE     34   /* ESP32 ADC1 */
#define PIN_CO2             35

static siap_dp_t   g_devices[3];
static siap_node_t g_node;
static WiFiClient  g_client;
static uint8_t     g_backoff_shift = 0;
static uint32_t    g_next_try_ms   = 0;
static uint32_t    g_window_state  = 0;   /* 창 개폐 % (구동기 현재 상태) */

/* TCP 연결을 논블로킹으로 보장 — 끊겨 있으면 백오프 간격마다 재접속 시도. */
static bool board_ensure_connected() {
    if (g_client.connected()) return true;
    uint32_t now = millis();
    if (now < g_next_try_ms) return false;
    if (g_client.connect(GATEWAY_HOST, GATEWAY_PORT)) {
        g_backoff_shift = 0;
        return true;
    }
    g_next_try_ms = now + board_backoff_ms(g_backoff_shift);
    if (g_backoff_shift < 3u) g_backoff_shift++;
    return false;
}

/* ── 전송 계층 (TCP) — Uno/Pro Mini 의 uart_* 3함수에 대응하는 유일한 차이 ── */
extern "C" int8_t board_tcp_read_byte(void *ctx, uint8_t *out) {
    (void)ctx;
    if (!board_ensure_connected()) return 0;    /* 재접속 중 — 지금은 바이트 없음 */
    if (g_client.available() <= 0) return 0;
    int c = g_client.read();
    if (c < 0) return 0;
    *out = (uint8_t)c;
    return 1;
}

extern "C" int16_t board_tcp_write(void *ctx, const uint8_t *buf, uint16_t len) {
    (void)ctx;
    if (!board_ensure_connected()) return 0;
    return (int16_t)g_client.write(buf, len);   /* TCP 는 신뢰 전송 — 바이트열 그대로 */
}

extern "C" uint32_t board_tcp_millis(void *ctx) { (void)ctx; return millis(); }

/* ── 디바이스 I/O — 센서 2종(ADC) + 구동기 1종(창 개폐) ────────────── */
extern "C" int8_t board_read_value(void *ctx, uint8_t device_id, uint32_t *raw) {
    (void)ctx;
    switch (device_id) {
        case DEV_ID_TEMPERATURE:
            *raw = siap_f32_bits(board_conv_temperature((uint16_t)analogRead(PIN_TEMPERATURE)));
            return 0;
        case DEV_ID_CO2:
            *raw = siap_f32_bits(board_conv_co2((uint16_t)analogRead(PIN_CO2)));
            return 0;
        case DEV_ID_WINDOW:
            *raw = g_window_state;              /* 구동기 현재 상태를 보고 */
            return 0;
        default:
            return -1;
    }
}

extern "C" int8_t board_write_value(void *ctx, uint8_t device_id, uint32_t raw) {
    (void)ctx;
    if (device_id != DEV_ID_WINDOW) return -1;  /* 센서엔 쓰지 않는다 */
    g_window_state = raw;                        /* 범위 검사는 core 가 이미 마쳤다 */
    return 0;
}

static const siap_io_t      g_io      = { board_tcp_read_byte, board_tcp_write, board_tcp_millis, NULL };
static const siap_dev_ops_t g_dev_ops = { board_read_value, board_write_value, NULL };

static void init_float_sensor(siap_dp_t *d, uint8_t id, uint8_t subtype, float lo, float hi, float prec) {
    d->main.device_id = id; d->main.dev_type = SIAP_DEV_SENSOR; d->main.subtype = subtype;
    d->main.value_type = SIAP_VALUE_TYPE_FLOAT; d->main.value = 0u;
    d->transfer_mode = SIAP_TM_PERIODIC; d->period = 5u;
    d->lower_value = siap_f32_bits(lo); d->upper_value = siap_f32_bits(hi);
    d->lower_limit = siap_f32_bits(lo); d->upper_limit = siap_f32_bits(hi);
    d->precision = siap_f32_bits(prec); d->status = SIAP_STATUS_NORMAL;
}

static void init_uint_actuator(siap_dp_t *d, uint8_t id, uint8_t subtype, uint32_t hi) {
    d->main.device_id = id; d->main.dev_type = SIAP_DEV_ACTUATOR; d->main.subtype = subtype;
    d->main.value_type = SIAP_VALUE_TYPE_UINT; d->main.value = 0u;
    d->transfer_mode = SIAP_TM_PERIODIC; d->period = 5u;
    d->lower_value = 0u; d->upper_value = hi;
    d->lower_limit = 0u; d->upper_limit = hi;
    d->precision = 1u; d->status = SIAP_STATUS_NORMAL;
}

void setup() {
    WiFi.mode(WIFI_STA);
    WiFi.begin(WIFI_SSID, WIFI_PSK);   /* 논블로킹 — 접속 전에도 board_ensure_connected() 가 재시도 */

    init_float_sensor(&g_devices[0], DEV_ID_TEMPERATURE, SIAP_SUBTYPE_TEMPERATURE,  -10.0f, 40.0f,   0.1f);
    init_float_sensor(&g_devices[1], DEV_ID_CO2,         SIAP_SUBTYPE_CO2,            0.0f, 2000.0f, 1.0f);
    init_uint_actuator(&g_devices[2], DEV_ID_WINDOW,     SIAP_SUBTYPE_WINDOW_OPENER, 100u);   /* 0~100 % */

    siap_node_cfg_t cfg;
    cfg.gcg_id       = 0x00001u;
    cfg.node_id      = 0x00067u;    /* 데모 노드 0x67 */
    cfg.sw_version   = 0x10u;
    cfg.io           = &g_io;
    cfg.dev_ops      = &g_dev_ops;
    cfg.devices      = g_devices;
    cfg.device_count = 3u;
    cfg.profile      = SIAP_PROFILE_DEFAULT;
    cfg.mode         = SIAP_MODE_STRICT;

    if (!siap_node_init(&g_node, &cfg)) { for (;;) { /* halt — */ } }
}

void loop() {
    siap_node_poll(&g_node);
}
