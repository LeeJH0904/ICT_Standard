#ifndef ACTUATOR_PINS_H
#define ACTUATOR_PINS_H
/*
 * Pro Mini 구동기 노드 핀 매핑 — 보드 디렉터리 전용. Arduino 스케치(.ino)에서만
 * include 한다. 순수 C 인 actuators.c 는 include 하지 않는다.
 */

/* Device ID — 노드 내 유일. */
#define DEV_ID_IRRIGATION_VALVE  1
#define DEV_ID_FAN               2

/* 릴레이 디지털 출력 핀. */
#define PIN_IRRIGATION_VALVE     4
#define PIN_FAN                  5

#endif /* ACTUATOR_PINS_H */
