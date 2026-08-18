#ifndef SENSOR_PINS_H
#define SENSOR_PINS_H
/*
 * Uno 센서 노드 핀 매핑. 보드 디렉터리 전용이다.
 * core/ 는 이 파일을 모른다(하드웨어 의존성 0은 core/ 에만 적용).
 *
 * 이 헤더는 Arduino 스케치(main.ino)에서만 include 한다 — A0 류 상수는
 * Arduino.h 가 정의한다. 순수 C 인 sensors.c 는 이 파일을 include 하지 않는다.
 */

/* Device ID — 노드 내 유일해야 한다(진입점 범위 검증). */
#define DEV_ID_TEMPERATURE  1
#define DEV_ID_HUMIDITY     2
#define DEV_ID_SOIL         3

/* DHT22(AM2302) 1선 디지털 센서 — device 1(온도)·2(습도)를 한 핀으로 읽는다.
 * 아날로그 변환 곡선을 실제 디지털 센서로 교체한 예이며, core/ 는 바뀌지 않는다
 * (센서 종류는 보드 계층의 몫). */
#define PIN_DHT             2       /* D2 — DHT22 데이터 핀 (풀업 저항 권장) */

/* ADC 핀 — device 3(토양)은 아날로그. 센서 미연결 시 이 핀을 GND 에 붙이면
 * ADC=0 이 되어 read 가 실패하고 core 가 NOTI_ERROR 를 보낸다(오류알림 시연). */
#define PIN_SOIL            A2

#endif /* SENSOR_PINS_H */
