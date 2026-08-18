/* "컴파일이 실패해야 통과"다 ( 재발 방지). siap_encode_np() 판 */
#include "../core/siap_frame.h"

int main(void)
{
    uint8_t buf[16] = {0};
    size_t p = 0;
    siap_np_t np = {0, 0, 0, 0, 0};
    siap_encode_np(buf, &p, &np); /* 반환값을 버림 */
    return 0;
}
