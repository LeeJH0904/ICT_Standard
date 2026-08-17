/* "컴파일이 실패해야 통과"다 (F-113/F-114 재발 방지). siap_tx_put_mcp() 판 */
#include "../core/siap_frame.h"

int main(void)
{
    siap_enc_t e;
    siap_tx_reset(&e);
    siap_mcp_t mcp = {0, 0, 0, 0};
    siap_tx_put_mcp(&e, &mcp); /* 반환값을 버림 */
    return 0;
}
