/*
 * bitpack.c/.h 호스트 유닛테스트. 펌웨어 설계서 §4.4 표의 케이스 1~10을
 * 그대로 옮긴다(케이스 11 "반환값을 버리면 빌드 실패"는 이 실행 파일
 * 안에서 표현할 수 없다 — 그 자체가 컴파일을 막아야 하는 코드라서다.
 * 대신 firmware/tests/Makefile 의 -Werror=unused-result 가 상시 강제하며,
 * 커밋되지 않는 임시 스니펫으로 실제 컴파일 실패를 확인했다).
 *
 * 실행: cd project_code/firmware/tests && make test_bitpack && ./test_bitpack
 * 종료 코드: 0 = 전부 통과, 1 = 실패 있음
 */
#include "../core/bitpack.h"
#include <stdio.h>
#include <string.h>

static int g_total = 0;
static int g_passed = 0;

static void check(const char *name, int cond)
{
    g_total++;
    if (cond) g_passed++;
    printf("  %s  %s\n", cond ? "PASS" : "FAIL", name);
}

/* 케이스 1 — 기본 왕복 */
static void case_basic_roundtrip(void)
{
    uint8_t buf[4] = {0};
    size_t p = 0;
    bool ok = bp_write(buf, &p, 0x2A, 14);
    check("case1: bp_write(0x2A,14) 성공", ok);
    check("case1: 쓰기 후 bitpos==14", p == 14);
    size_t rp = 0;
    uint32_t got = bp_read(buf, &rp, 14);
    check("case1: bp_read 왕복 == 0x2A", got == 0x2A);
    check("case1: 읽기 후 bitpos==14", rp == 14);
}

/* 케이스 2 — 바이트 경계를 넘는 20bit 쓰기/읽기 */
static void case_20bit_boundary_crossing(void)
{
    uint8_t buf[8] = {0};
    size_t p = 3; /* 바이트 경계가 아닌 자리에서 시작 — 경계를 반드시 넘는다 */
    uint32_t val = 0x000A5C3u; /* 20bit 안의 임의 값 */
    bool ok = bp_write(buf, &p, val, 20);
    check("case2: 20bit 경계 교차 쓰기 성공", ok);
    check("case2: bitpos 3->23", p == 23);
    size_t rp = 3;
    uint32_t got = bp_read(buf, &rp, 20);
    check("case2: 20bit 경계 교차 왕복 일치", got == val);

    /* 같은 구현의 bp_write 로 쓰고 같은 구현의 bp_read 로 되읽는
       왕복만으로는, writer 와 reader 가 함께 대칭으로 틀려도(예: 둘 다
       LSB-first 로 바꿔도) 서로 역연산이라 걸리지 않는다. 손으로 만든
       독립 상수(비트 위치를 직접 계산한 결과)와 실제 wire 바이트를
       대조해야 "MSB-first 로 나갔다"는 계약 자체를 증명한다. */
    static const uint8_t expect_msb_first[4] = {0x01, 0x4B, 0x86, 0x00};
    check("case2: 결과 바이트열이 MSB-first 독립 계산과 일치",
          memcmp(buf, expect_msb_first, sizeof(expect_msb_first)) == 0);
}

/* 케이스 2b — 바이트 경계를 넘는 9bit 쓰기/읽기 (개발_착수_지시서
   §3.2 ③이 "20bit·14bit·9bit" 세 폭을 각각 요구한다. 이전에는 9bit이
   전 폭 스윕(케이스 10)에만 있었는데, 거기서는 매 폭마다 bitpos=0에서
   시작해 9bit이 항상 바이트 정렬 위치에서만 쓰였다 — "bitpos%8!=0일
   때만 조용히 아무것도 안 쓰고 true를 반환하는" 결함은 그 경로로는
   드러나지 않는다. 여기서는 bitpos=5(비정렬)에서 명시적으로 쓴다. */
static void case_9bit_boundary_crossing(void)
{
    uint8_t buf[4] = {0};
    size_t p = 5; /* 바이트 경계가 아닌 자리 — 9bit이 byte0의 나머지 3bit +
                     byte1의 6bit에 걸쳐 반드시 경계를 넘는다 */
    uint32_t val = 0x1A5u; /* 9bit 안의 임의의 0이 아닌 값(0b1_1010_0101) */
    bool ok = bp_write(buf, &p, val, 9);
    check("case2b: 9bit 경계 교차 쓰기 성공", ok);
    check("case2b: bitpos 5->14", p == 14);
    size_t rp = 5;
    uint32_t got = bp_read(buf, &rp, 9);
    check("case2b: 9bit 경계 교차 왕복 일치", got == val);
    /* 값이 실제로 buf에 반영됐는지도 직접 확인한다 — "아무것도 안 쓰고
       bitpos만 전진시킨 뒤 true를 반환"하는 결함은 왕복 검사만으로는
       버퍼가 우연히 0으로 초기화돼 있어 못 잡을 수도 있다(쓴 값이 0이면
       읽은 값도 0이라 왕복이 "일치"해 버린다). val이 0이 아니므로
       버퍼가 실제로 바뀌었는지까지 함께 본다. */
    static const uint8_t zero4[4] = {0, 0, 0, 0};
    check("case2b: 쓰기가 실제로 buf를 바꿈(전부 0인 채로 남지 않음)",
          memcmp(buf, zero4, sizeof(buf)) != 0);

    /* 왕복(같은 구현의 write→read)과 "0이 아니다"만으로는
       writer·reader 가 함께 대칭으로 틀린 결함(예: 둘 다 LSB-first)을
       잡지 못한다. 실제로 val=0x1A5, bitpos=5 를 LSB-first 로 쓰고
       읽으면 05 2C 00 00 이 나오는데, 그 wire 바이트도 자기 자신과는
       왕복이 일치하고 0도 아니다 — 하지만 표준이 요구하는 MSB-first
       바이트는 아니다. bitpos·nbits 로부터 손으로 계산한 독립 상수와
       직접 대조해야 "그 결함이 아니다"를 증명한다. */
    static const uint8_t expect_msb_first[4] = {0x06, 0x94, 0x00, 0x00};
    check("case2b: 결과 바이트열이 MSB-first 독립 계산(06 94 00 00)과 일치",
          memcmp(buf, expect_msb_first, sizeof(expect_msb_first)) == 0);
}

/* 케이스 3 — 연속 쓰기 8+14+2+16+16+20+20=96bit, 골든 벡터 N01 과 대조
   (헤더 그림 7-1 / 표 7-5~7-8, contracts/vectors/golden.jsonl N01) */
static void case_header_96bit_matches_golden_n01(void)
{
    uint8_t buf[12] = {0};
    size_t p = 0;
    bool ok = true;
    ok &= bp_write(buf, &p, 0x12, 8);   /* Version */
    ok &= bp_write(buf, &p, 0, 14);     /* Message Type = REQ_SET_CONNECTION(0) */
    ok &= bp_write(buf, &p, 0, 2);      /* Transmission Type = UNICAST */
    ok &= bp_write(buf, &p, 1, 16);     /* Message Identifier */
    ok &= bp_write(buf, &p, 0, 16);     /* Payload Length */
    ok &= bp_write(buf, &p, 1, 20);     /* GCG ID */
    ok &= bp_write(buf, &p, 3, 20);     /* Node ID */
    check("case3: 7필드 연속 쓰기 전부 성공", ok);
    check("case3: bitpos == 96 (바이트 정렬)", p == 96 && p % 8 == 0);

    /* 골든 N01: hex "120000000100000000100003" */
    static const uint8_t golden_n01[12] = {
        0x12, 0x00, 0x00, 0x00, 0x01, 0x00, 0x00, 0x00, 0x00, 0x10, 0x00, 0x03
    };
    check("case3: 결과 바이트열이 골든 N01 과 일치",
          memcmp(buf, golden_n01, sizeof(golden_n01)) == 0);
}

/* 케이스 4 — nbits=32 최대값 */
static void case_32bit_max(void)
{
    uint8_t buf[4] = {0};
    size_t p = 0;
    bool ok = bp_write(buf, &p, 0xFFFFFFFFu, 32);
    check("case4: nbits=32 최대값 쓰기 성공", ok);
    size_t rp = 0;
    uint32_t got = bp_read(buf, &rp, 32);
    check("case4: nbits=32 최대값 왕복 일치", got == 0xFFFFFFFFu);
}

/* 케이스 5 — FLOAT 왕복. 골든 벡터 golden_layout.py 의 FLOATS 상수 7종과 동일 */
static void case_float_roundtrip(void)
{
    static const struct { const char *label; uint32_t bits; } floats[] = {
        {"25.3",      0x41CA6666u},
        {"61.0",      0x42740000u},
        {"-40.0",     0xC2200000u},
        {"80.0",      0x42A00000u},
        {"0.1",       0x3DCCCCCDu},
        {"FLOAT_MAX", 0x7F7FFFFFu},
        {"0.0",       0x00000000u},
    };
    for (size_t i = 0; i < sizeof(floats) / sizeof(floats[0]); i++) {
        float val;
        memcpy(&val, &floats[i].bits, sizeof(val));

        uint8_t buf[4] = {0};
        size_t wp = 0;
        bool ok = bp_write_f32(buf, &wp, val);

        /* 비트 패턴 자체가 일치하는지는 buf 를 정수로 다시 읽어 확인하고
           (bp_write_f32 가 실제로 big-endian IEEE-754 를 냈는가),
           bp_read_f32 로는 float 왕복 자체가 원래 값과 같은지 확인한다 —
           서로 다른 커서를 써서 각자 버퍼 처음부터 읽는다. */
        size_t rp1 = 0;
        uint32_t got_bits = bp_read(buf, &rp1, 32);

        size_t rp2 = 0;
        float got_val = bp_read_f32(buf, &rp2);
        uint32_t got_val_bits;
        memcpy(&got_val_bits, &got_val, sizeof(got_val_bits));

        char name[64];
        snprintf(name, sizeof(name), "case5: FLOAT %s 비트 패턴 일치", floats[i].label);
        check(name, ok && got_bits == floats[i].bits && got_val_bits == floats[i].bits);
    }
}

/* 케이스 6 — 미기록 비트 불변 */
static void case_untouched_bits_stay_zero(void)
{
    uint8_t buf[4] = {0xFF, 0xFF, 0xFF, 0xFF}; /* 일부러 1로 채워 "건드리지 않음"을 검증 */
    /* buf 를 0xFF 로 채운 채, byte 1 의 중간(4bit)만 0 으로 쓴다 */
    size_t p = 12; /* byte 1 의 하위 4bit 부터 */
    bool ok = bp_write(buf, &p, 0x0, 4);
    check("case6: 부분 쓰기 성공", ok);
    check("case6: byte0 은 안 건드림(0xFF 유지)", buf[0] == 0xFF);
    check("case6: 쓴 4bit 만 0으로 바뀜(상위 4bit 은 유지)", (buf[1] & 0xF0) == 0xF0);
    check("case6: 쓴 4bit 은 정확히 0", (buf[1] & 0x0F) == 0x00);
    check("case6: byte2·3 은 안 건드림(0xFF 유지)", buf[2] == 0xFF && buf[3] == 0xFF);
}

/* 케이스 7 — 범위 초과 거부: buf·bitpos 불변 */
static void case_range_reject_no_side_effect(void)
{
    uint8_t buf[4] = {0xAA, 0xAA, 0xAA, 0xAA};
    uint8_t before[4];
    memcpy(before, buf, sizeof(buf));
    size_t p = 5;
    size_t p_before = p;

    bool ok = bp_write(buf, &p, 0x4000, 14); /* 14bit 상한 0x3FFF 초과 */
    check("case7: 14bit 상한 초과 시 false", !ok);
    check("case7: buf 불변", memcmp(buf, before, sizeof(buf)) == 0);
    check("case7: bitpos 불변", p == p_before);
}

/* 케이스 8 — 20bit 필드에 2^20 기록 시도 (GCG ID / Node ID 경계, 표 7-8) */
static void case_20bit_exact_overflow(void)
{
    uint8_t buf[8] = {0};
    size_t p = 0;
    bool ok_max = bp_write(buf, &p, 0x000FFFFFu, 20); /* 2^20-1 은 허용 */
    check("case8: 20bit 최댓값(2^20-1)은 허용", ok_max);

    /* 반례 2 — "20bit 초과값이면 buf[0]을 변경하고 false 반환"하는
       결함은 !ok_over 와 bitpos 불변만으로는 안 잡힌다. 버퍼 전체를
       미리 임의값(0xAA)으로 채우고 스냅샷을 떠서, 거부 후 단 1비트도
       바뀌지 않았는지 케이스 7 과 같은 방식으로 확인한다. */
    uint8_t buf2[8] = {0xAA, 0xAA, 0xAA, 0xAA, 0xAA, 0xAA, 0xAA, 0xAA};
    uint8_t before2[8];
    memcpy(before2, buf2, sizeof(buf2));
    size_t p2 = 0;
    bool ok_over = bp_write(buf2, &p2, 0x00100000u, 20); /* 2^20 은 거부 */
    check("case8: 20bit 초과값(2^20)은 거부", !ok_over);
    check("case8: 거부 시 bitpos 불변", p2 == 0);
    check("case8: 거부 시 buf 전체 불변", memcmp(buf2, before2, sizeof(buf2)) == 0);
}

/* 케이스 9 — nbits=0 / 33 */
static void case_nbits_out_of_domain(void)
{
    uint8_t buf[8] = {0};
    size_t p = 0;
    check("case9: nbits=0 은 거부", !bp_write(buf, &p, 0, 0));
    check("case9: nbits=33 은 거부", !bp_write(buf, &p, 0, 33));
    check("case9: 거부 후 bitpos 불변", p == 0);
}

/* 케이스 10 — 전 폭 스윕: nbits=1~32 각각 최대값 기록·왕복, 최대값+1 거부 */
static void case_full_width_sweep(void)
{
    int all_ok = 1;
    for (uint8_t nbits = 1; nbits <= 32; nbits++) {
        uint32_t max_val = (nbits == 32) ? 0xFFFFFFFFu : ((1u << nbits) - 1u);

        uint8_t buf[8] = {0};
        size_t p = 0;
        bool ok = bp_write(buf, &p, max_val, nbits);
        if (!ok || p != nbits) { all_ok = 0; continue; }

        size_t rp = 0;
        uint32_t got = bp_read(buf, &rp, nbits);
        if (got != max_val) { all_ok = 0; continue; }

        if (nbits < 32) {
            /* 반례 2 와 같은 종류 — 폭마다 거부 시 buf·bitpos 전체
               불변까지 확인한다. 케이스 8 은 20bit 하나만 봤다; 여기서는
               1~31bit 전 폭에서 같은 불변식을 확인한다. */
            uint8_t buf2[8] = {0xAA, 0xAA, 0xAA, 0xAA, 0xAA, 0xAA, 0xAA, 0xAA};
            uint8_t before2[8];
            memcpy(before2, buf2, sizeof(buf2));
            size_t p2 = 0;
            bool over_ok = bp_write(buf2, &p2, max_val + 1u, nbits);
            if (over_ok) { all_ok = 0; continue; } /* 최대값+1 은 반드시 거부되어야 한다 */
            if (p2 != 0) { all_ok = 0; continue; }
            if (memcmp(buf2, before2, sizeof(buf2)) != 0) { all_ok = 0; continue; }
        }
    }
    check("case10: nbits 1~32 전 폭 스윕 32종 전량 왕복+경계 거부 통과", all_ok);
}

int main(void)
{
    printf("bitpack 호스트 유닛테스트\n\n");

    case_basic_roundtrip();
    case_20bit_boundary_crossing();
    case_9bit_boundary_crossing();
    case_header_96bit_matches_golden_n01();
    case_32bit_max();
    case_float_roundtrip();
    case_untouched_bits_stay_zero();
    case_range_reject_no_side_effect();
    case_20bit_exact_overflow();
    case_nbits_out_of_domain();
    case_full_width_sweep();

    printf("\n  %d/%d 통과\n", g_passed, g_total);
    return (g_passed == g_total) ? 0 : 1;
}
