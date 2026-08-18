/*
 * 상태 코드·메시지 코드공간 호스트 유닛테스트.
 * RSC(표 7-10)/NEC(표 7-12)/Subtype 레지스트리의
 * 값 자체와, WIRE_CODE(표 7-2~7-4)의 구조적 성질(블록 경계·Req/Res 대응·
 * 0x0800 중복)을 검증한다. 프레임 왕복은 test_siap_frame.c / test_golden.c 의
 * 몫이다 — 여기서는 "코드값이 표준과 같은가"만 본다.
 *
 * 실행: cd project_code/firmware/tests && make test_status_codes && ./test_status_codes
 * 종료 코드: 0 = 전부 통과, 1 = 실패 있음
 */
#include "../core/siap_frame.h"
#include <stdio.h>

static int g_total = 0;
static int g_passed = 0;

static void check(const char *name, int cond)
{
    g_total++;
    if (cond) g_passed++;
    printf("  %s  %s\n", cond ? "PASS" : "FAIL", name);
}

/* ═══════════════════════════════════════════════════════════════
 *  RSC — 표 7-10 (원문 표기 'SUCESS'는 오타, 코드는 SUCCESS)
 * ═══════════════════════════════════════════════════════════════ */
static void test_rsc_table_7_10(void)
{
    check("RSC_7_10: SUCCESS=0x00", SIAP_RSC_SUCCESS == 0x00);
    check("RSC_7_10: INVALID_VERSION=0x01", SIAP_RSC_INVALID_VERSION == 0x01);
    check("RSC_7_10: INVALID_GCG_ID=0x02", SIAP_RSC_INVALID_GCG_ID == 0x02);
    check("RSC_7_10: INVALID_NODE_ID=0x03", SIAP_RSC_INVALID_NODE_ID == 0x03);
    check("RSC_7_10: INVALID_DEVICE_ID=0x04", SIAP_RSC_INVALID_DEVICE_ID == 0x04);
    check("RSC_7_10: INVALID_DEVICE_TYPE=0x05", SIAP_RSC_INVALID_DEVICE_TYPE == 0x05);
    check("RSC_7_10: INVALID_DATA_TYPE=0x06", SIAP_RSC_INVALID_DATA_TYPE == 0x06);
    check("RSC_7_10: INVALID_DATA_SUBTYPE=0x07", SIAP_RSC_INVALID_DATA_SUBTYPE == 0x07);
    check("RSC_7_10: INVALID_TRANSMISSION_TYPE=0x08", SIAP_RSC_INVALID_TRANSMISSION_TYPE == 0x08);
    check("RSC_7_10: INVALID_FORMAT=0x09 (기능 2 위반 케이스 3·4의 코드)",
          SIAP_RSC_INVALID_FORMAT == 0x09);
}

/* ═══════════════════════════════════════════════════════════════
 *  NEC — 표 7-12
 * ═══════════════════════════════════════════════════════════════ */
static void test_nec_table_7_12(void)
{
    check("NEC_7_12: ERROR_DEVICE_STATUS=0x00", SIAP_NEC_ERROR_DEVICE_STATUS == 0x00);
    check("NEC_7_12: ERROR_DEVICE_INTERFACE=0x01", SIAP_NEC_ERROR_DEVICE_INTERFACE == 0x01);
    check("NEC_7_12: ERROR_RECEIVE=0x02", SIAP_NEC_ERROR_RECEIVE == 0x02);
    check("NEC_7_12: ERROR_SW_TIMER=0x03", SIAP_NEC_ERROR_SW_TIMER == 0x03);
    check("NEC_7_12: ERROR_HW_TIMER=0x04", SIAP_NEC_ERROR_HW_TIMER == 0x04);
    check("NEC_7_12: ERROR_PWR=0x05", SIAP_NEC_ERROR_PWR == 0x05);
    check("NEC_7_12: ERROR_BATTERY=0x06", SIAP_NEC_ERROR_BATTERY == 0x06);
    check("NEC_7_12: ERROR_BATTERY_LOW=0x07 (기능 2 위반 케이스 8의 코드)",
          SIAP_NEC_ERROR_BATTERY_LOW == 0x07);
    check("NEC_7_12: ERROR_BATTERY_OFF=0x08", SIAP_NEC_ERROR_BATTERY_OFF == 0x08);
    check("NEC_7_12: ERROR_UNKNOWN=0x09", SIAP_NEC_ERROR_UNKNOWN == 0x09);
}

/* ═══════════════════════════════════════════════════════════════
 *  표 7-14 — DevType / ValueType 코드값
 * ═══════════════════════════════════════════════════════════════ */
static void test_table_7_14_codes(void)
{
    check("7_14: SENSOR=0x00", SIAP_DEV_SENSOR == 0x00);
    check("7_14: ACTUATOR=0x01", SIAP_DEV_ACTUATOR == 0x01);
    check("7_14: ValueType INT=0x00", SIAP_VALUE_TYPE_INT == 0x00);
    check("7_14: ValueType UINT=0x01", SIAP_VALUE_TYPE_UINT == 0x01);
    check("7_14: ValueType FLOAT=0x02", SIAP_VALUE_TYPE_FLOAT == 0x02);
    check("7_14: ValueType RESERVED=0x03 (기능 2 위반 케이스 6의 트리거값)",
          SIAP_VALUE_TYPE_RESERVED == 0x03);
}

/* ═══════════════════════════════════════════════════════════════
 *  Subtype 레지스트리 — / 1369-P1 6.3.3·6.3.4
 * ═══════════════════════════════════════════════════════════════ */
static void test_subtype_registry(void)
{
    check("SUBTYPE: 등록 개수 16종", SIAP_SUBTYPE_COUNT == 16);

    /* 중복 없음 — 선형 탐색 O(n^2) 이지만 16건뿐이라 host 테스트엔 무해하다 */
    bool dup = false;
    for (unsigned i = 0; i < SIAP_SUBTYPE_COUNT; i++)
        for (unsigned j = i + 1; j < SIAP_SUBTYPE_COUNT; j++)
            if (SIAP_SUBTYPE_TABLE[i] == SIAP_SUBTYPE_TABLE[j]) dup = true;
    check("SUBTYPE: 코드 전량 고유", !dup);

    /* 센서 10 / 액추에이터 6 (표) */
    unsigned sensors = 0, actuators = 0;
    for (unsigned i = 0; i < SIAP_SUBTYPE_COUNT; i++) {
        if (siap_subtype_is_actuator(SIAP_SUBTYPE_TABLE[i])) actuators++;
        else sensors++;
    }
    check("SUBTYPE: 센서 10종", sensors == 10);
    check("SUBTYPE: 액추에이터 6종", actuators == 6);

    check("SUBTYPE: 0x01(온도) 유효", siap_subtype_valid(SIAP_SUBTYPE_TEMPERATURE));
    check("SUBTYPE: 0x86(냉난방기) 유효", siap_subtype_valid(SIAP_SUBTYPE_COOLING_HEATER));
    check("SUBTYPE: 0x00 미등록", !siap_subtype_valid(0x00));
    check("SUBTYPE: 0x0B 미등록(센서 구간 공백)", !siap_subtype_valid(0x0B));
    check("SUBTYPE: 0x40 미등록 (기능 2 위반 케이스 7의 예시값)", !siap_subtype_valid(0x40));
    check("SUBTYPE: 0x7F 미등록", !siap_subtype_valid(0x7F));
    check("SUBTYPE: 0x87 미등록(액추에이터 구간 공백)", !siap_subtype_valid(0x87));
    check("SUBTYPE: 0xFF 미등록", !siap_subtype_valid(0xFF));
}

/* ═══════════════════════════════════════════════════════════════
 *  WIRE_CODE — 표 7-2~7-4 코드공간·블록 경계·Req/Res 대응·0x0800 중복
 * ═══════════════════════════════════════════════════════════════ */
static void test_wire_code_table_7_2_to_7_4(void)
{
    /* 모든 코드가 14bit 범위(<0x4000) 안 */
    bool all_in_range = true;
    for (int k = 1; k < SIAP_KIND_COUNT; k++)
        if (siap_wire_code((siap_kind_t)k, SIAP_MODE_STRICT) >= 0x4000u) all_in_range = false;
    check("WIRE: strict 전량 14bit 범위 안(<0x4000)", all_in_range);

    /* Request 14종 — 0x0000~0x000D */
    bool req_ok = true;
    for (int i = 0; i < 14; i++) {
        uint16_t code = siap_wire_code((siap_kind_t)(SIAP_REQ_SET_CONNECTION + i), SIAP_MODE_STRICT);
        if (code != (uint16_t)i) req_ok = false;
    }
    check("WIRE: Request 14종 == 0x0000~0x000D (표 7-2)", req_ok);

    /* Request + 0x0400 = Response — 14쌍 전량 (표 7-2/7-3) */
    bool pairs_ok = true;
    for (int i = 0; i < 14; i++) {
        uint16_t req_code = siap_wire_code((siap_kind_t)(SIAP_REQ_SET_CONNECTION + i), SIAP_MODE_STRICT);
        uint16_t res_code = siap_wire_code((siap_kind_t)(SIAP_RES_SET_CONNECTION + i), SIAP_MODE_STRICT);
        if (res_code != (uint16_t)(req_code + 0x0400)) pairs_ok = false;
    }
    check("WIRE: Request+0x0400==Response, 14쌍 전량 성립", pairs_ok);

    /* strict — 0x0800 중복 1건, 그 외 32종은 서로 다른 코드 (표 7-4 결함) */
    check("WIRE: strict NOTI_ERROR==NOTI_DEVICE_VALUE==0x0800 (표준 원문 중복)",
          siap_wire_code(SIAP_NOTI_ERROR, SIAP_MODE_STRICT) == 0x0800
          && siap_wire_code(SIAP_NOTI_DEVICE_VALUE, SIAP_MODE_STRICT) == 0x0800);
    {
        int dup_count = 0;
        for (int i = 1; i < SIAP_KIND_COUNT; i++)
            for (int j = i + 1; j < SIAP_KIND_COUNT; j++)
                if (siap_wire_code((siap_kind_t)i, SIAP_MODE_STRICT)
                    == siap_wire_code((siap_kind_t)j, SIAP_MODE_STRICT))
                    dup_count++;
        check("WIRE: strict 중복은 정확히 1건 (고유 코드 33개)",
              dup_count == 1);
    }

    /* extended — 중복 해소, 34종 전량 고유 + NOTI 재배치 (표준 개정 제안) */
    {
        int dup_count = 0;
        for (int i = 1; i < SIAP_KIND_COUNT; i++)
            for (int j = i + 1; j < SIAP_KIND_COUNT; j++)
                if (siap_wire_code((siap_kind_t)i, SIAP_MODE_EXTENDED)
                    == siap_wire_code((siap_kind_t)j, SIAP_MODE_EXTENDED))
                    dup_count++;
        check("WIRE: extended 중복 0건 (고유 코드 34개)", dup_count == 0);
    }
    check("WIRE: extended NOTI_DEVICE_VALUE=0x0801로 재배치",
          siap_wire_code(SIAP_NOTI_DEVICE_VALUE, SIAP_MODE_EXTENDED) == 0x0801);
    check("WIRE: extended NOTI_KEEP_ALIVE=0x0804 (재배치 마지막 자리)",
          siap_wire_code(SIAP_NOTI_KEEP_ALIVE, SIAP_MODE_EXTENDED) == 0x0804);

    /* 블록 경계 — REQ/RES/NOTI/ACK (표 7-2~7-4) */
    check("WIRE: NOTI 블록은 0x0800~0x0803 (strict)",
          siap_wire_code(SIAP_NOTI_ERROR, SIAP_MODE_STRICT) == 0x0800
          && siap_wire_code(SIAP_NOTI_KEEP_ALIVE, SIAP_MODE_STRICT) == 0x0803);
    check("WIRE: ACK == 0x0C00", siap_wire_code(SIAP_ACK, SIAP_MODE_STRICT) == 0x0C00);
}

/* ═══════════════════════════════════════════════════════════════
 *  LAYOUT — RAM 예산 전제가 실제로 지켜지는가
 * ═══════════════════════════════════════════════════════════════ */
static void test_layout_memory_budget(void)
{
    uint8_t max_fixed = 0, max_elem = 0;
    for (int k = 1; k < SIAP_KIND_COUNT; k++) {
        if (SIAP_LAYOUT[k].fixed > max_fixed) max_fixed = SIAP_LAYOUT[k].fixed;
        if (SIAP_LAYOUT[k].elem > max_elem) max_elem = SIAP_LAYOUT[k].elem;
    }
    check("LAYOUT: 고정부 최대 9byte (RSC+NODE_PROPERTY, RES_SET_CONNECTION)", max_fixed == 9);
    check("LAYOUT: 요소 최대 30byte (DEVICE_PROPERTY)", max_elem == 30);
    check("LAYOUT: 헤더+고정부 최대가 SIAP_RX_WINDOW(51) 안",
          (unsigned)(SIAP_HEADER_BYTES + max_fixed) <= SIAP_RX_WINDOW);
    check("LAYOUT: 요소 최대가 SIAP_RX_WINDOW(51) 안", (unsigned)max_elem <= SIAP_RX_WINDOW);
}

/* ═══════════════════════════════════════════════════════════════
 *  clause_id — "판정에는 반드시 clause 를 채운다"
 * ═══════════════════════════════════════════════════════════════ */
static void test_clause_ids_distinct(void)
{
    siap_clause_t values[] = { SIAP_CLAUSE_NONE, SIAP_CLAUSE_7_3_1, SIAP_CLAUSE_TABLE_7_2,
                                SIAP_CLAUSE_TABLE_7_6, SIAP_CLAUSE_TABLE_7_14, SIAP_CLAUSE_7_3_2 };
    bool dup = false;
    for (int i = 0; i < 6; i++)
        for (int j = i + 1; j < 6; j++)
            if (values[i] == values[j]) dup = true;
    check("CLAUSE: 6종 조항 코드 전량 고유", !dup);
}

int main(void)
{
    printf("상태 코드 · 메시지 코드공간 호스트 유닛테스트\n\n");

    test_rsc_table_7_10();
    test_nec_table_7_12();
    test_table_7_14_codes();
    test_subtype_registry();
    test_wire_code_table_7_2_to_7_4();
    test_layout_memory_budget();
    test_clause_ids_distinct();

    printf("\n  %d/%d 통과\n", g_passed, g_total);
    return (g_passed == g_total) ? 0 : 1;
}
