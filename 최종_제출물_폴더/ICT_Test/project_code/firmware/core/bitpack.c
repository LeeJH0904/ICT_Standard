/*
 * 비트 read/write 구현. 펌웨어 설계서 §4.
 *
 * 구조체 캐스팅을 쓰지 않는 이유(§4.2): 비트필드 배치 순서가 C99 상
 * 구현 정의(§6.7.2.1p11)라 AVR-GCC(LSB-first)와 Xtensa-GCC의 결과가
 * 다를 수 있고, 이 프로젝트는 "같은 바이트가 나오는 것 자체가 주장"이라
 * 허용할 수 없다. 그래서 여기서는 바이트·비트 인덱스를 직접 계산한다.
 */
#include "bitpack.h"

void bp_memcpy(void *dst, const void *src, size_t len)
{
    uint8_t *d = (uint8_t *)dst;
    const uint8_t *s = (const uint8_t *)src;
    for (size_t i = 0; i < len; i++) d[i] = s[i];
}

bool bp_write(uint8_t *buf, size_t *bitpos, uint32_t val, uint8_t nbits)
{
    /* 범위 검사식 — 시프트를 쓰지 않는다.
       nbits==32 는 uint32_t 전 범위이므로 검사가 필요 없다.
       1..31 은 마스크로 상한을 만든다 — (1u << nbits) 를 쓰지 않는다:
         · AVR 의 unsigned int 는 16bit 라 nbits>=16 에서 시프트 폭 초과(UB)
         · 호스트에서도 1u << 32 는 UB 이고 -Wshift-count-overflow 가 잡는다 */
    if (nbits == 0 || nbits > 32) return false;
    if (nbits < 32 && val > ((uint32_t)0xFFFFFFFFul >> (32 - nbits))) return false;

    size_t pos = *bitpos;
    for (uint8_t i = 0; i < nbits; i++) {
        uint32_t bit = (val >> (uint8_t)(nbits - 1u - i)) & 1u;
        size_t byte_idx = pos / 8;
        uint8_t bit_idx = (uint8_t)(pos % 8); /* 0 = 그 바이트의 최상위 비트 */
        uint8_t mask = (uint8_t)(0x80u >> bit_idx);
        if (bit) buf[byte_idx] = (uint8_t)(buf[byte_idx] | mask);
        else     buf[byte_idx] = (uint8_t)(buf[byte_idx] & (uint8_t)~mask);
        pos++;
    }
    *bitpos = pos;
    return true;
}

uint32_t bp_read(const uint8_t *buf, size_t *bitpos, uint8_t nbits)
{
    if (nbits == 0 || nbits > 32) return 0;

    size_t pos = *bitpos;
    uint32_t val = 0;
    for (uint8_t i = 0; i < nbits; i++) {
        size_t byte_idx = pos / 8;
        uint8_t bit_idx = (uint8_t)(pos % 8);
        uint8_t mask = (uint8_t)(0x80u >> bit_idx);
        uint32_t bit = (buf[byte_idx] & mask) ? 1u : 0u;
        val = (val << 1) | bit;
        pos++;
    }
    *bitpos = pos;
    return val;
}

bool bp_write_f32(uint8_t *buf, size_t *bitpos, float val)
{
    uint32_t bits;
    bp_memcpy(&bits, &val, sizeof(bits)); /* strict-aliasing 안전한 타입 펀닝 */
    return bp_write(buf, bitpos, bits, 32); /* nbits==32 → 범위 검사 생략 */
}

float bp_read_f32(const uint8_t *buf, size_t *bitpos)
{
    uint32_t bits = bp_read(buf, bitpos, 32);
    float val;
    bp_memcpy(&val, &bits, sizeof(val));
    return val;
}
