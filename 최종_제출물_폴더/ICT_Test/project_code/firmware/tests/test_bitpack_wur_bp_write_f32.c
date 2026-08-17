/*
 * 이 파일도 "컴파일이 실패해야 통과"다 (F-113).
 * test_bitpack_wur_bp_write.c 와 같은 계약을 bp_write_f32() 에 대해
 * 별도로 검사한다 — 한 함수의 SIAP_WUR 만 남고 다른 함수에서 빠지는
 * 부분 회귀는 두 파일을 각각 컴파일해야만 갈라 잡을 수 있다.
 */
#include "../core/bitpack.h"

int main(void)
{
    uint8_t buf[4] = {0};
    size_t p = 0;
    bp_write_f32(buf, &p, 1.0f); /* 반환값을 버림 — 여기가 컴파일을 막아야 한다 */
    return 0;
}
