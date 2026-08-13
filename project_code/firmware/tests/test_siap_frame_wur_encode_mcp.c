/* "컴파일이 실패해야 통과"다 (F-113/F-114 재발 방지). siap_encode_mcp() 판 */
#include "../core/siap_frame.h"

int main(void)
{
    uint8_t buf[16] = {0};
    size_t p = 0;
    siap_mcp_t mcp = {0, 0, 0, 0};
    siap_encode_mcp(buf, &p, &mcp); /* 반환값을 버림 */
    return 0;
}
