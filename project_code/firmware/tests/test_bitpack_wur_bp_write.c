/*
 * 이 파일은 "컴파일이 실패해야 통과"다 (F-113).
 *
 * bp_write() 반환값을 일부러 버린다. SIAP_WUR(bitpack.h)와
 * -Werror=unused-result(Makefile) 가 둘 다 살아 있으면 이 파일은
 * 컴파일 자체가 실패한다. `firmware/tests/Makefile` 의 `check_wur`
 * 타깃이 이 실패를 "정상"으로 판정하고, 반대로 경고 없이 컴파일되면
 * "회귀"로 판정해 `make test_bitpack` 전체를 실패시킨다.
 *
 * 이전에는 이 계약을 커밋되지 않는 임시 스니펫으로만 수동 확인했다
 * (단계 2a 처리 기록) — SIAP_WUR 를 헤더에서 지워도 test_bitpack.c 는
 * 반환값을 절대 버리지 않으므로 자동 출구가 그 회귀를 잡지 못했다.
 */
#include "../core/bitpack.h"

int main(void)
{
    uint8_t buf[4] = {0};
    size_t p = 0;
    bp_write(buf, &p, 1, 4); /* 반환값을 버림 — 여기가 컴파일을 막아야 한다 */
    return 0;
}
