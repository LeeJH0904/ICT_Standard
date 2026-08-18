/*
 * arduino_sensor_node/sensors.c — 순수 C. ADC 카운트 → 물리량 변환과
 * IEEE-754 비트 인코딩만 담당한다.
 *
 * Arduino API(analogRead 등)를 부르지 않는다 — 그건 main.ino(C++)의 read_value
 * 가 부르고, 이 파일은 그 결과 카운트를 물리량으로 옮기는 산술만 한다. 그래서
 * 플랫폼 헤더가 없고 C 로 컴파일된다(Arduino 는 .c 를 C 컴파일러로 빌드한다).
 *
 * 합성 데이터 금지는 "값을 지어내는 것"을 금지한다 — 실측 ADC
 * 를 물리량으로 옮기는 변환은 금지 대상이 아니다. read_value 는 언제나 실제
 * analogRead 결과를 이 함수들에 넣는다.
 */
#include <stdint.h>
#include <stdbool.h>
#include <string.h>

/* IEEE-754 single 비트열로 인코딩 — core 가 value_type=FLOAT 로 그대로 싣는다
 * (FLOAT 결정). 캐스팅/마스킹이 아니라 비트 복사여야 한다. */
uint32_t siap_f32_bits(float v) {
    uint32_t bits;
    memcpy(&bits, &v, sizeof bits);
    return bits;
}

/* Uno ADC 는 10bit(0~1023), AREF 5.0V 가정. 온도·습도(device 1·2)는 이제
 * DHT22(디지털)가 물리량 float 를 직접 주므로 아날로그 변환이 필요 없다 —
 * 해당 변환식은 제거했다. 토양(device 3)만 아날로그로 남는다. 변환식 교체는
 * 보드 계층의 자유이며 core/ 는 바뀌지 않는다. */
#define ADC_MAX 1023.0f

float sensor_convert_soil_tension(uint16_t adc) {
    return (adc / ADC_MAX) * 100.0f;       /* kPa (0~100 선형) */
}

/* 미연결/레일 판정 — 센서가 물리적으로 빠지면 입력이 레일에 붙는다. read_value
 * 는 이게 false 면 -1 을 반환하고, core/ 가 그 디바이스 Status 를 ABNORMAL 로
 * 두고 NOTI_ERROR(ERROR_DEVICE_INTERFACE)를 보낸다. 임계는 배선 의존이며
 * 여기서는 완전 레일(0 또는 1023)만 미연결로 본다 — 실제 배선의 풀업/풀다운에
 * 맞춰 조정한다. */
bool sensor_adc_plausible(uint16_t adc) {
    return adc != 0u && adc < 1023u;
}
