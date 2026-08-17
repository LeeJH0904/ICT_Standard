/*
 * arduino_sensor_node — Uno 센서 노드.
 *
 * core/ 는 수정하지 않는다. 이 파일이 채우는 것은 전송 계층(UART/Serial) 바인딩과
 * 센서 바인딩뿐이며, 표준 해석·상태 머신·프레임 코덱은 전부 core/ 에 있다.
 * Uno·Pro Mini 는 전송 계층 세 함수(uart_read_byte/uart_write/uart_millis)가
 * 같고, ESP32 만 이 셋을 TCP 로 바꾼다.
 *
 * 센서: device 1(온도)·2(습도)는 DHT22(디지털 1선, 비트뱅잉), device 3(토양)은
 * 아날로그(A2). 센서 종류·읽기 방식은 보드 계층의 자유이며 core/ 는 바뀌지
 * 않는다 — "동일 응용계층" 주장은 core/ 소스가 3종 보드에서 동일함으로 증명한다.
 *
 * core/ 는 C99 로 컴파일되므로 C++ 스케치에서 부르려면 extern "C" 로 감싼다.
 */
#include <Arduino.h>

extern "C" {
#include <node_state.h>
#include <siap_types.h>
#include <subtype_registry.h>
}
#include "pins.h"

/* sensors.c(순수 C)의 변환·인코딩 함수. 온도·습도는 DHT22(디지털)가 직접 주므로
   아날로그 변환은 토양(device 3)만 남는다. */
extern "C" {
uint32_t siap_f32_bits(float v);
float    sensor_convert_soil_tension(uint16_t adc);
bool     sensor_adc_plausible(uint16_t adc);
}

static siap_dp_t   g_devices[3];
static siap_node_t g_node;

/* ── DHT22(AM2302) 1선 디지털 읽기 — 보드 계층(core 는 센서 종류를 모른다).
   비트뱅잉이라 외부 라이브러리 의존이 없다. 40bit = 습도16 + 온도16 + 체크섬8.
   비트 판정은 각 비트의 HIGH 길이를 직전 LOW 길이와 비교하는 적응식이라
   (HIGH>LOW → 1) 루프 오버헤드·클럭 편차에 강하다. 반환 false = 타임아웃/체크섬
   실패 → read_value 가 -1 을 돌려 core 가 오류알림 경로를 탄다. */
static float    g_dht_temp   = 0.0f;
static float    g_dht_humid  = 0.0f;
static bool     g_dht_ok     = false;
static uint32_t g_dht_last   = 0u;   /* 마지막 읽기 시각(ms). DHT22 최소 간격 2s */

static bool dht22_read_raw(uint8_t pin, float *temp_c, float *humid) {
    uint8_t b[5] = { 0, 0, 0, 0, 0 };

    /* 시작 신호: 데이터선을 LOW 로 ≥1ms 끌었다가 놓고 입력(풀업)으로. */
    pinMode(pin, OUTPUT);
    digitalWrite(pin, LOW);
    delay(2);
    pinMode(pin, INPUT_PULLUP);

    noInterrupts();                  /* 이후 타이밍은 us 단위 — 인터럽트를 끈다 */
    bool ok = true;
    uint16_t g;

    /* 응답 펄스: HIGH(놓임) → LOW 80us → HIGH 80us 를 통과시킨다. */
    for (g = 0; digitalRead(pin) == HIGH; g++) { if (g > 300) { ok = false; break; } }
    if (ok) for (g = 0; digitalRead(pin) == LOW;  g++) { if (g > 300) { ok = false; break; } }
    if (ok) for (g = 0; digitalRead(pin) == HIGH; g++) { if (g > 300) { ok = false; break; } }

    for (uint8_t i = 0; ok && i < 40u; i++) {
        uint16_t lc = 0, hc = 0;
        while (digitalRead(pin) == LOW)  { if (++lc > 500) { ok = false; break; } }   /* 50us LOW 통과 */
        while (ok && digitalRead(pin) == HIGH) { if (++hc > 500) { ok = false; break; } }  /* HIGH 길이 */
        b[i >> 3] = (uint8_t)(b[i >> 3] << 1);
        if (hc > lc) b[i >> 3] |= 1u;   /* 적응식 임계: HIGH 가 LOW 보다 길면 1 */
    }
    interrupts();

    if (!ok) return false;
    if ((uint8_t)(b[0] + b[1] + b[2] + b[3]) != b[4]) return false;   /* 체크섬 */

    uint16_t rh = (uint16_t)(((uint16_t)b[0] << 8) | b[1]);
    uint16_t t  = (uint16_t)(((uint16_t)(b[2] & 0x7Fu) << 8) | b[3]);
    *humid  = rh / 10.0f;
    *temp_c = t / 10.0f;
    if (b[2] & 0x80u) *temp_c = -*temp_c;   /* 부호 비트 */
    return true;
}

/* device 1·2 가 같은 스캔에서 연달아 읽으므로, 2s 캐시로 DHT22 를 한 번만 실제
   접근한다(최소 간격 준수). 첫 호출이 갱신하고 둘째는 캐시를 쓴다. */
static bool dht22_refresh() {
    uint32_t now = millis();
    if (g_dht_last != 0u && (uint32_t)(now - g_dht_last) < 2000u) return g_dht_ok;
    g_dht_ok   = dht22_read_raw(PIN_DHT, &g_dht_temp, &g_dht_humid);
    g_dht_last = now;
    return g_dht_ok;
}

/* ── 전송 계층 (UART 9600 8N1) — Uno/Pro Mini 공통 3함수 ───────────── */
extern "C" int8_t uart_read_byte(void *ctx, uint8_t *out) {
    (void)ctx;
    if (Serial.available() <= 0) return 0;          /* 지금은 없음 */
    int c = Serial.read();
    if (c < 0) return 0;
    *out = (uint8_t)c;
    return 1;
}

extern "C" int16_t uart_write(void *ctx, const uint8_t *buf, uint16_t len) {
    (void)ctx;
    /* 논블로킹 부분 쓰기 — 버퍼에 들어갈 만큼만 쓴다. 여유가 0이면 한 바이트도
       쓰지 않고 0을 돌려준다. 이 가드가 없으면 avail==0 일 때 n=len 으로 떨어져
       포화된 버퍼에 Serial.write(buf,len) 을 호출, 공간이 빌 때까지 블로킹해
       그동안 수신·ACK·타이머가 지연된다. */
    int avail = Serial.availableForWrite();
    if (avail <= 0) return 0;
    uint16_t n = ((uint16_t)avail < len) ? (uint16_t)avail : len;
    return (int16_t)Serial.write(buf, n);
}

extern "C" uint32_t uart_millis(void *ctx) { (void)ctx; return millis(); }

/* ── 디바이스 I/O — device 1·2 는 DHT22(디지털), device 3 은 토양(아날로그).
   센서 노드엔 구동기가 없다. 읽기 실패 시 -1 → core 가 Status ABNORMAL +
   NOTI_ERROR(ERROR_DEVICE_INTERFACE) 를 보낸다. 값을 지어내지 않는다. */
extern "C" int8_t sensor_read_value(void *ctx, uint8_t device_id, uint32_t *raw) {
    (void)ctx;
    switch (device_id) {
        case DEV_ID_TEMPERATURE:
            if (!dht22_refresh()) return -1;
            *raw = siap_f32_bits(g_dht_temp);
            return 0;
        case DEV_ID_HUMIDITY:
            if (!dht22_refresh()) return -1;
            *raw = siap_f32_bits(g_dht_humid);
            return 0;
        case DEV_ID_SOIL: {
            uint16_t adc = (uint16_t)analogRead(PIN_SOIL);
            if (!sensor_adc_plausible(adc)) return -1;   /* 미연결/GND — 오류알림 */
            *raw = siap_f32_bits(sensor_convert_soil_tension(adc));
            return 0;
        }
        default:
            return -1;
    }
}

extern "C" int8_t sensor_write_value(void *ctx, uint8_t device_id, uint32_t raw) {
    (void)ctx; (void)device_id; (void)raw;
    return -1;   /* 센서 노드에는 구동기가 없다 */
}

static const siap_io_t      g_io      = { uart_read_byte, uart_write, uart_millis, NULL };
static const siap_dev_ops_t g_dev_ops = { sensor_read_value, sensor_write_value, NULL };

/* FLOAT 디바이스 하나를 채운다. 물리 특성(Limit·Precision)은 설치 시 확정값
 * (1369-P1 6.3.2), 수집 정책은 기본값. value_type=FLOAT. */
static void init_float_device(siap_dp_t *d, uint8_t id, uint8_t subtype,
                              float lo, float hi, float precision) {
    d->main.device_id  = id;
    d->main.dev_type   = SIAP_DEV_SENSOR;
    d->main.subtype    = subtype;
    d->main.value_type = SIAP_VALUE_TYPE_FLOAT;
    d->main.value      = 0u;
    d->transfer_mode   = SIAP_TM_PERIODIC;
    d->period          = 5u;                        /* sec — 데모 수집 주기 */
    d->lower_value     = siap_f32_bits(lo);
    d->upper_value     = siap_f32_bits(hi);
    d->lower_limit     = siap_f32_bits(lo);
    d->upper_limit     = siap_f32_bits(hi);
    d->precision       = siap_f32_bits(precision);
    d->status          = SIAP_STATUS_NORMAL;
}

void setup() {
    Serial.begin(9600);

    init_float_device(&g_devices[0], DEV_ID_TEMPERATURE, SIAP_SUBTYPE_TEMPERATURE,           -10.0f, 60.0f,  0.1f);
    init_float_device(&g_devices[1], DEV_ID_HUMIDITY,    SIAP_SUBTYPE_HUMIDITY,                0.0f, 100.0f, 1.0f);
    init_float_device(&g_devices[2], DEV_ID_SOIL,        SIAP_SUBTYPE_SOIL_MOISTURE_TENSION,   0.0f, 100.0f, 0.1f);

    siap_node_cfg_t cfg;
    cfg.gcg_id       = 0x00001u;
    cfg.node_id      = 0x00003u;    /* 데모 노드 3 (index.html 의 Node 0x3) */
    cfg.sw_version   = 0x10u;
    cfg.io           = &g_io;
    cfg.dev_ops      = &g_dev_ops;
    cfg.devices      = g_devices;
    cfg.device_count = 3u;
    cfg.profile      = SIAP_PROFILE_DEFAULT;
    cfg.mode         = SIAP_MODE_STRICT;

    /* 진입점 범위 검증에 실패하면 노드가 뜨지 않는다. 로컬 정지만 — 게이트웨이에
     * 알릴 수단이 없으므로 지어낸 프레임을 보내지 않는다. */
    if (!siap_node_init(&g_node, &cfg)) {
        for (;;) { /* halt */ }
    }
}

void loop() {
    siap_node_poll(&g_node);   /* 논블로킹 한 틱 */
}
