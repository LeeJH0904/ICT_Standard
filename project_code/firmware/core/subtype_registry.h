#ifndef SIAP_SUBTYPE_REGISTRY_H
#define SIAP_SUBTYPE_REGISTRY_H
/*
 * Subtype 코드 레지스트리 — SIAP 메시지 명세서 §5 / contracts/frame.py Subtype.
 *
 * 0943 표 7-14 의 Subtype(8bit)은 각주에서 [RUCFS-0009] 온실 관제 데이터 규격을
 * 참조하도록 되어 있으나 해당 규격을 확보하지 못했다. 항목 집합은
 * TTAK.KO-10.1369-Part1 6.3.3(센서)/6.3.4(액추에이터)에서 도출하고 코드값만
 * 자체 할당한다 — 치환 지점 1/2 (다른 한 곳은 contracts/frame.py 의 Subtype).
 *
 * 최상위 비트로 센서(0x00~0x7F)/액추에이터(0x80~0xFF)를 구분한다.
 */
#include <stdbool.h>
#include <stdint.h>

/* C++/Arduino 스케치에서 C 링키지로 부를 수 있게 한다(bitpack.h 주석 참조) —
   C 컴파일 시엔 비활성, 언어 매크로라 core 순수성(§1-5)과 무관하다. */
#ifdef __cplusplus
extern "C" {
#endif

typedef enum {
    /* 센서 — 1369-P1 6.3.3 */
    SIAP_SUBTYPE_TEMPERATURE            = 0x01, /* 온도         ℃     6.3.3.2  */
    SIAP_SUBTYPE_HUMIDITY               = 0x02, /* 습도         %     6.3.3.3  */
    SIAP_SUBTYPE_CO2                    = 0x03, /* 이산화탄소   ppm   6.3.3.4  */
    SIAP_SUBTYPE_INSOLATION             = 0x04, /* 일사         W/㎡  6.3.3.5  */
    SIAP_SUBTYPE_WIND_DIRECTION         = 0x05, /* 풍향         degree 6.3.3.6 */
    SIAP_SUBTYPE_WIND_SPEED             = 0x06, /* 풍속         m/s   6.3.3.7  */
    SIAP_SUBTYPE_RAIN_DETECTION         = 0x07, /* 감우         ON/OFF 6.3.3.8 */
    SIAP_SUBTYPE_SOIL_MOISTURE_TENSION  = 0x08, /* 토양수분장력 kPa   6.3.3.9  */
    SIAP_SUBTYPE_EC                     = 0x09, /* 전기전도도   dS/m  6.3.3.10 */
    SIAP_SUBTYPE_PH                     = 0x0A, /* 수소이온농도 —     6.3.3.11 */
    /* 액추에이터 — 1369-P1 6.3.4 */
    SIAP_SUBTYPE_WINDOW_OPENER          = 0x81, /* 창 개폐기    %       6.3.4.2 */
    SIAP_SUBTYPE_INSULATION_COVER       = 0x82, /* 보온덮개     %       6.3.4.3 */
    SIAP_SUBTYPE_FAN                    = 0x83, /* 송풍기       ON/OFF  6.3.4.4 */
    SIAP_SUBTYPE_IRRIGATION_PUMP        = 0x84, /* 관수펌프     ON/OFF+sec 6.3.4.5 */
    SIAP_SUBTYPE_IRRIGATION_VALVE       = 0x85, /* 관수밸브     ON/OFF or % 6.3.4.6 */
    SIAP_SUBTYPE_COOLING_HEATER         = 0x86, /* 냉난방기     ON/OFF+℃  6.3.4.7 */
} siap_subtype_t;

#define SIAP_SUBTYPE_COUNT 16u

static const uint8_t SIAP_SUBTYPE_TABLE[SIAP_SUBTYPE_COUNT] = {
    SIAP_SUBTYPE_TEMPERATURE, SIAP_SUBTYPE_HUMIDITY, SIAP_SUBTYPE_CO2,
    SIAP_SUBTYPE_INSOLATION, SIAP_SUBTYPE_WIND_DIRECTION, SIAP_SUBTYPE_WIND_SPEED,
    SIAP_SUBTYPE_RAIN_DETECTION, SIAP_SUBTYPE_SOIL_MOISTURE_TENSION, SIAP_SUBTYPE_EC,
    SIAP_SUBTYPE_PH,
    SIAP_SUBTYPE_WINDOW_OPENER, SIAP_SUBTYPE_INSULATION_COVER, SIAP_SUBTYPE_FAN,
    SIAP_SUBTYPE_IRRIGATION_PUMP, SIAP_SUBTYPE_IRRIGATION_VALVE, SIAP_SUBTYPE_COOLING_HEATER,
};

/* 미등록 Subtype 수신 시 INVALID_DATA_SUBTYPE (0x07, 7.3.1 / 표 7-14 근거) —
   기능 2 위반 케이스 7번의 판정 근거. 선형 탐색이면 충분하다(16건, AVR 에서도 가볍다). */
static inline bool siap_subtype_valid(uint8_t code) {
    for (uint8_t i = 0; i < SIAP_SUBTYPE_COUNT; i++) {
        if (SIAP_SUBTYPE_TABLE[i] == code) return true;
    }
    return false;
}

/* 최상위 비트로 센서/액추에이터 구분 — DEVICE_MAIN_INFO.Type 과 중복되지만
   검증(교차 대조)에 쓸 수 있다 (SIAP 메시지 명세서 §5). */
static inline bool siap_subtype_is_actuator(uint8_t code) { return (code & 0x80u) != 0u; }

#ifdef __cplusplus
}
#endif

#endif /* SIAP_SUBTYPE_REGISTRY_H */
