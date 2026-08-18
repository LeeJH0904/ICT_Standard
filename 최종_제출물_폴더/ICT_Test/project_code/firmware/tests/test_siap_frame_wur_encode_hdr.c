/*
 * "컴파일이 실패해야 통과"다 ( 재발 방지).
 * siap_encode_hdr() 반환값을 일부러 버린다 — SIAP_WUR(siap_frame.h)와
 * -Werror=unused-result 가 둘 다 살아 있으면 컴파일 자체가 실패한다.
 * test_bitpack_wur_bp_write.c 와 같은 계약을 siap_frame.h 의 새 WUR
 * 함수들에 대해서도 각각 검사한다 — bitpack.h 의 두 함수만 검사하던
 * check_wur.py 는 siap_frame.h 로 옮겨간 SIAP_WUR 회귀를 잡지 못했다.
 */
#include "../core/siap_frame.h"

int main(void)
{
    uint8_t buf[16] = {0};
    size_t p = 0;
    siap_hdr_t h = {0x12, 0, 0, 0, 0, 0, 0};
    siap_encode_hdr(buf, &p, &h); /* 반환값을 버림 — 여기가 컴파일을 막아야 한다 */
    return 0;
}
