#ifndef SIAP_BITPACK_H
#define SIAP_BITPACK_H
/*
 * 비트 read/write — SIAP 프레임 코덱의 최후 방어선.
 * 펌웨어 설계서 §4 (bitpack.c/.h) · CLAUDE.md §4.2.
 *
 * core/ 는 하드웨어 의존성 0이다 — Arduino.h, avr 계열, esp 계열 같은
 * 플랫폼 헤더를 include하지 않는다(CLAUDE.md §1-5). <stdint.h> ·
 * <stddef.h> · <stdbool.h> 는 C99 표준 헤더이지 플랫폼 헤더가 아니다.
 * `tools/core_purity_verify.py`(단계 2b)가 이를 기계로 확인한다.
 */
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

/* GCC · Clang · AVR-GCC 공통. 미지원 컴파일러에서는 빈 매크로가 되지만
   호스트 테스트(펌웨어 설계서 §4.4)가 GCC/Clang 으로 도는 한 누락은
   거기서 잡힌다 (F-078). */
#if defined(__GNUC__)
#  define SIAP_WUR __attribute__((warn_unused_result))
#else
#  define SIAP_WUR
#endif

/*
 * bp_write — nbits 폭의 val 을 buf 의 *bitpos 위치부터 MSB-first 로 쓴다.
 *
 * 계약 (펌웨어 설계서 §4.1):
 *   비트 순서   : MSB first. bitpos==0 은 buf[0] 의 최상위 비트다.
 *   바이트 순서 : big-endian (표준 미규정 → 자체 결정, CLAUDE.md §3.5).
 *   nbits       : 1~32. 벗어나면 false.
 *   범위 초과   : val 이 nbits 폭을 넘으면 아무것도 기록하지 않고 false를
 *                반환한다 — 마스킹 래핑 금지(F-044)를 구조로 강제한다.
 *   성공 시     : *bitpos 가 nbits 만큼 증가한다.
 *   실패 시     : buf 와 *bitpos 어느 쪽도 바뀌지 않는다.
 *
 * 반환값을 버리면 SIAP_WUR 때문에 컴파일 경고가 나고,
 * firmware/tests/Makefile 의 -Werror=unused-result 가 그 경고를 빌드
 * 실패로 만든다(F-078) — 검사 누락이 관습이 아니라 구조로 막힌다.
 */
SIAP_WUR bool bp_write(uint8_t *buf, size_t *bitpos, uint32_t val, uint8_t nbits);

/*
 * bp_read — buf 의 *bitpos 위치부터 nbits 폭을 MSB-first 로 읽고 정수로
 * 돌려준다. *bitpos 는 nbits 만큼 증가한다.
 *
 * 성공을 전제로 한다 — 디코더가 payload_len 을 먼저 검증해 이 자리에
 * nbits 만큼의 유효 데이터가 있음을 보장한 뒤에만 부른다. 실패를 표현할
 * 반환 채널이 없다(디코더 쪽의 형식 오류 판정은 상위 계층, 즉
 * siap_frame.c 의 몫이다 — 펌웨어 설계서 §5). nbits 가 0 이거나 32 를
 * 넘는 방어적 호출에는 0 을 돌려주고 *bitpos 를 그대로 둔다.
 */
uint32_t bp_read(const uint8_t *buf, size_t *bitpos, uint8_t nbits);

/*
 * bp_write_f32 / bp_read_f32 — FLOAT (표 7-14 Value Type=FLOAT) 전용.
 * IEEE-754 single precision, 4 byte, big-endian (표준 미규정 → 자체
 * 결정). 정수 32bit 를 경유해 bp_write/bp_read 와 같은 코드 경로를 타며,
 * 별도의 비트 배치 규칙을 두지 않는다(펌웨어 설계서 §4.3).
 * nbits==32 는 bp_write 의 범위 검사 자체가 생략되는 자리라
 * bp_write_f32 는 항상 성공한다(반환형이 bool 인 것은 SiapLink 상위
 * 계층의 호출 규약을 bp_write 와 동일하게 맞추기 위함이다).
 */
SIAP_WUR bool bp_write_f32(uint8_t *buf, size_t *bitpos, float val);
         float bp_read_f32(const uint8_t *buf, size_t *bitpos);

#endif /* SIAP_BITPACK_H */
