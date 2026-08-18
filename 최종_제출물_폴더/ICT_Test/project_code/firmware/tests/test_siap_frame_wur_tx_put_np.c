/* "컴파일이 실패해야 통과"다 ( 재발 방지). siap_tx_put_np() 판 */
#include "../core/siap_frame.h"

int main(void)
{
    siap_enc_t e;
    siap_tx_reset(&e);
    siap_np_t np = {0, 0, 0, 0, 0};
    siap_tx_put_np(&e, &np); /* 반환값을 버림 */
    return 0;
}
