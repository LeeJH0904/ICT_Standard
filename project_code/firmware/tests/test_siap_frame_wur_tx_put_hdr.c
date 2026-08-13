/* "컴파일이 실패해야 통과"다 (F-113/F-114 재발 방지). siap_tx_put_hdr() 판 */
#include "../core/siap_frame.h"

int main(void)
{
    siap_enc_t e;
    siap_tx_reset(&e);
    siap_hdr_t h = {0x12, 0, 0, 0, 0, 0, 0};
    siap_tx_put_hdr(&e, &h); /* 반환값을 버림 */
    return 0;
}
