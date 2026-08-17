/*
 * esp32_node/net.c — 순수 C. f32 비트 인코딩 · ADC 변환 · 재접속 백오프 산술만.
 * WiFi/WiFiClient API(C++)는 esp32_node.ino 가 부른다. 그래서 플랫폼 헤더가 없고
 * C 로 컴파일된다.
 *
 * 함수 이름은 board_/siap_ 접두사만 쓴다 — ESP-IDF 는 `esp_` 를, lwIP 는 `tcp_`/
 * `lwip_` 를 전역 심볼로 예약하므로, 그 예약 영역과 이름이 겹치면 링커 충돌이 난다.
 */
#include <stdint.h>
#include <string.h>

/* IEEE-754 single 비트열 인코딩. */
uint32_t siap_f32_bits(float v) {
    uint32_t bits;
    memcpy(&bits, &v, sizeof bits);
    return bits;
}

/* ESP32 ADC 는 12bit(0~4095). 데모용 선형 변환 — 실제 센서 특성으로 교체 가능. */
#define ESP_ADC_MAX 4095.0f

float board_conv_temperature(uint16_t adc) {
    return (adc / ESP_ADC_MAX) * 50.0f - 10.0f;   /* -10 ~ 40 ℃ */
}

float board_conv_co2(uint16_t adc) {
    return (adc / ESP_ADC_MAX) * 2000.0f;         /* 0 ~ 2000 ppm */
}

/* 물리 재접속 백오프 — 1·2·4·8s, 상한 8s. board 의 TCP 재시도 간격이며, core
 * 상태 머신의 DISCONNECTED 백오프(프로토콜 타이머)와는 계층이 다르다. */
uint32_t board_backoff_ms(uint8_t shift) {
    uint32_t s = (shift >= 3u) ? 8u : (1u << shift);
    return s * 1000u;
}
