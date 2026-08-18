/*
 * arduino_actuator_node/actuators.c — 순수 C. 구동기 상태 저장·해석만 담당한다
 *. digitalWrite 는 main.ino(C++)가 부른다.
 *
 * 범위 검사는 하지 않는다 — core/ 가 DEVICE_PROPERTY.Lower/Upper Limit 로 이미
 * 마쳤다. 보드가 다시 판단하면 표준 해석이 두 곳에 생긴다.
 */
#include <stdint.h>
#include <stdbool.h>

/* 마지막으로 지시받은 값 — read_value 가 이걸 돌려줘 노드가 현재 상태를 보고한다.
 * device_id 는 1..N, SIAP 상한 16. */
static uint32_t g_state[16];

void actuator_set_state(uint8_t device_id, uint32_t raw) {
    if (device_id >= 1u && device_id <= 16u) g_state[device_id - 1u] = raw;
}

uint32_t actuator_get_state(uint8_t device_id) {
    return (device_id >= 1u && device_id <= 16u) ? g_state[device_id - 1u] : 0u;
}

/* Value != 0 을 켜짐으로 해석한다 (전원 필드 NOT NULL, Value!=0=on). */
bool actuator_is_on(uint32_t raw) { return raw != 0u; }
