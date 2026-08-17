#ifndef SIAP_BITPACK_H
#define SIAP_BITPACK_H
/*
 * 비트 read/write — SIAP(TTAK.KO-10.0943) 프레임 코덱의 최하위 계층.
 *
 * SIAP 프레임은 Message Type(14bit) · GCG/Node ID(각 20bit) · Subtype(9~16bit)
 * 처럼 바이트 경계를 넘는 필드로 구성되므로, 구조체 캐스팅이 아니라 비트 단위
 * read/write 로만 인코딩·디코딩한다. 이 파일이 그 유일한 진입점이다.
 *
 * core/ 는 하드웨어 의존성이 없다 — Arduino.h 등 플랫폼 헤더를 include 하지
 * 않으므로 Uno · Pro Mini · ESP32 가 동일한 코덱을 공유한다. <stdint.h> ·
 * <stddef.h> · <stdbool.h> 는 C99 표준 헤더다.
 */
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

/* C++/Arduino 스케치(.ino)에서 C 링키지로 호출·링크할 수 있게 한다. */
#ifdef __cplusplus
extern "C" {
#endif

/* core/ 전용 바이트 복사. string.h 없이 객체 표현을 옮긴다(영역 비중첩 전제). */
void bp_memcpy(void *dst, const void *src, size_t len);

/* 반환값을 버리면 컴파일 경고를 내는 속성(GCC/Clang/AVR-GCC 공통). 호스트
   테스트 빌드의 -Werror=unused-result 와 결합해 "쓰기 성공 확인 누락"을
   컴파일 오류로 만든다. */
#if defined(__GNUC__)
#  define SIAP_WUR __attribute__((warn_unused_result))
#else
#  define SIAP_WUR
#endif

/*
 * bp_write — nbits 폭의 val 을 buf 의 *bitpos 위치부터 MSB-first 로 쓴다.
 *
 * 계약:
 *   비트 순서   : MSB first. bitpos==0 은 buf[0] 의 최상위 비트다.
 *   바이트 순서 : big-endian (network byte order). 0943 이 엔디안을 규정하지
 *                않아 본 구현이 network byte order 로 확정했다.
 *   nbits       : 1~32. 벗어나면 false.
 *   범위 초과   : val 이 nbits 폭을 넘으면 아무것도 기록하지 않고 false 를
 *                반환한다 — 값이 조용히 잘려 들어가는 마스킹 래핑을 구조로 막는다.
 *   성공 시     : *bitpos 가 nbits 만큼 증가한다.
 *   실패 시     : buf 와 *bitpos 어느 쪽도 바뀌지 않는다.
 *
 * 반환값(성공/실패)을 반드시 확인해야 한다(SIAP_WUR).
 */
SIAP_WUR bool bp_write(uint8_t *buf, size_t *bitpos, uint32_t val, uint8_t nbits);

/*
 * bp_read — buf 의 *bitpos 위치부터 nbits 폭을 MSB-first 로 읽어 정수로
 * 돌려준다. *bitpos 는 nbits 만큼 증가한다.
 *
 * 성공을 전제로 한다 — 상위 계층(siap_frame.c)이 Payload Length 를 먼저
 * 검증해 이 자리에 유효 데이터가 있음을 보장한 뒤에만 부른다. nbits 가 0
 * 이거나 32 를 넘는 방어적 호출에는 0 을 돌려주고 *bitpos 를 그대로 둔다.
 */
uint32_t bp_read(const uint8_t *buf, size_t *bitpos, uint8_t nbits);

/*
 * bp_write_f32 / bp_read_f32 — Value Type=FLOAT(0943 표 7-14) 전용.
 * IEEE-754 single precision, 4 byte, big-endian. 0943 이 FLOAT 표현 방식을
 * 규정하지 않아 본 구현이 IEEE-754 로 확정했다. 정수 32bit 를 경유해
 * bp_write/bp_read 와 같은 경로를 탄다(nbits==32 는 범위 검사가 없어 항상 성공).
 */
SIAP_WUR bool bp_write_f32(uint8_t *buf, size_t *bitpos, float val);
         float bp_read_f32(const uint8_t *buf, size_t *bitpos);

#ifdef __cplusplus
}
#endif

#endif /* SIAP_BITPACK_H */
