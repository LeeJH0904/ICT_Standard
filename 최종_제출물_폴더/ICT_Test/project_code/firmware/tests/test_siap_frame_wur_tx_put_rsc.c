/* "컴파일이 실패해야 통과"다 ( 재발 방지). siap_tx_put_rsc() 판 */
#include "../core/siap_frame.h"

int main(void)
{
    siap_enc_t e;
    siap_tx_reset(&e);
    siap_tx_put_rsc(&e, SIAP_RSC_SUCCESS); /* 반환값을 버림 */
    return 0;
}
