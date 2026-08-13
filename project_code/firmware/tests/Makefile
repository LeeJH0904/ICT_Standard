# firmware/tests/Makefile — 호스트 유닛테스트 빌드 (GCC/Clang, 보드 무관).
#
# 개발_착수_지시서 §3.2 출구: `make test_bitpack && ./test_bitpack`.
# 이후 단계(2b·2c)가 test_siap_frame · test_status_codes · test_golden ·
# test_node_state 를 TARGETS 에 추가한다 — 각 단계에서 그 단계 몫만 더한다.
#
# CLAUDE.md §4.2 — "쓰기 2종은 범위 초과 시 false 를 반환하고 아무것도
# 기록하지 않는다... 반환값을 버리면 -Werror=unused-result 로 빌드가
# 실패한다(F-075·F-078)." SIAP_WUR 만으로는 부족하고(경고일 뿐이다)
# 이 -Werror 가 있어야 "검사 누락이 컴파일을 막는다"는 계약이 실제로
# 강제된다(펌웨어 설계서 §4.1).
#
# 레시피는 셸 고유 문법(if/then/fi, 파이프, 리다이렉션)을 쓰지 않는다
# (F-113 처리 중 발견) — mingw32-make 는 POSIX sh 를 못 찾으면 조용히
# cmd.exe 로 떨어지고, cmd.exe 는 sh 문법을 모른다. `tools/where.py` 가
# PowerShell 에서 `make` 를 부르는 경로가 정확히 그 상황이라, sh 문법이
# 섞인 레시피는 거기서만 깨진다. 대신 check_wur.py·clean.py 로 옮겨
# "python <스크립트> <인자...>" 한 줄짜리 레시피만 쓴다 — 단어 분리
# 말고는 셸이 무엇이든 동일하게 해석된다.

# `?=` 는 GNU Make 내장 기본값(CC=cc)이 이미 "설정된" 것으로 쳐서 무시된다
# (환경변수와 다른 함정). `:=` 로 명시하고, 다른 컴파일러가 필요하면
# `make CC=clang test_bitpack` 처럼 커맨드라인에서 넘긴다 — 커맨드라인
# 할당은 항상 이 파일의 할당을 이긴다.
CC     := gcc
PYTHON := python
CORE   := ../core
CFLAGS := -std=c99 -O2 -Wall -Wextra -Wconversion -Wshift-count-overflow \
          -Werror=unused-result -I$(CORE)

# 단계 2b — siap_frame.c/.h (인코더·디코더·N 산출·스트리밍) 의 호스트 테스트 3종.
# 개발_착수_지시서 §3.3 출구: ./test_siap_frame ./test_status_codes ./test_golden.
SIAP_SRC := $(CORE)/siap_frame.c $(CORE)/bitpack.c
SIAP_DEP := $(CORE)/siap_frame.h $(CORE)/siap_types.h $(CORE)/subtype_registry.h $(CORE)/bitpack.h

# 단계 2c — node_state.c/.h (8상태 전이·pending 재전송·due 회전 커서) 의
# 호스트 테스트. 개발_착수_지시서 §3.4 출구: ./test_node_state.
NODE_SRC := $(CORE)/node_state.c $(SIAP_SRC)
NODE_DEP := $(CORE)/node_state.h $(SIAP_DEP)

TARGETS := test_bitpack test_siap_frame test_status_codes test_golden test_node_state
CLEAN_FILES := test_bitpack test_bitpack.exe \
               test_siap_frame test_siap_frame.exe \
               test_status_codes test_status_codes.exe \
               test_golden test_golden.exe \
               test_node_state test_node_state.exe \
               dump_golden dump_golden.exe

.PHONY: all clean check_wur

all: $(TARGETS)

# F-113 — SIAP_WUR(bitpack.h)나 -Werror=unused-result(위 CFLAGS) 어느
# 한쪽이 빠져도, test_bitpack.c 는 반환값을 절대 버리지 않으므로 그
# 회귀를 스스로 드러내지 못한다. "반환값을 버리면 컴파일이 실패한다"는
# 계약 자체가 검사 대상이라, 컴파일이 실패해야 통과인 별도 타깃을 둔다.
#
# F-114 재발(단계 2b) — SIAP_WUR 가 siap_frame.h 로도 9개 옮겨갔는데
# check_wur 는 test_bitpack 의 선행조건으로만 걸려 있었다. siap_frame.h
# 쪽 회귀는 어느 자동 출구도 잡지 못했다 — check_wur.py 자체는 SNIPPETS
# 에 그 9개를 추가해 고쳤지만(check_wur.py 참조), 이 타깃도 test_siap_frame
# 의 선행조건으로 걸어야 실제로 실행된다.
check_wur:
	$(PYTHON) check_wur.py $(CC) $(CFLAGS)

test_bitpack: check_wur test_bitpack.c $(CORE)/bitpack.c $(CORE)/bitpack.h
	$(CC) $(CFLAGS) -o $@ test_bitpack.c $(CORE)/bitpack.c

test_siap_frame: check_wur test_siap_frame.c $(SIAP_SRC) $(SIAP_DEP)
	$(CC) $(CFLAGS) -o $@ test_siap_frame.c $(SIAP_SRC)

test_status_codes: test_status_codes.c $(SIAP_SRC) $(SIAP_DEP)
	$(CC) $(CFLAGS) -o $@ test_status_codes.c $(SIAP_SRC)

# test_golden 은 project_code/contracts/vectors/golden.jsonl 을 실행 디렉터리
# 기준 상대경로로 읽는다(../../contracts/vectors/golden.jsonl) — 반드시
# firmware/tests 에서 실행해야 한다(다른 테스트 3종과 동일한 관례).
test_golden: test_golden.c $(SIAP_SRC) $(SIAP_DEP)
	$(CC) $(CFLAGS) -o $@ test_golden.c $(SIAP_SRC)

test_node_state: check_wur test_node_state.c $(NODE_SRC) $(NODE_DEP)
	$(CC) $(CFLAGS) -o $@ test_node_state.c $(NODE_SRC)

# 단계 3 — tools/xcodec_verify.py 전용 덤프 유틸리티. TARGETS(= `make all`)에는
# 넣지 않는다 — 이건 회귀 테스트가 아니라 C 인코더 출력을 stdout 으로 내는
# 도구다(테스트 자체는 test_golden 이 이미 53/53 로 진다).
dump_golden: dump_golden.c $(SIAP_SRC) $(SIAP_DEP)
	$(CC) $(CFLAGS) -o $@ dump_golden.c $(SIAP_SRC)

# F-111 — `-o test_bitpack` 로 지정해도 Windows(MinGW GCC)는 실제로
# `test_bitpack.exe` 를 만든다. 어느 이름이 실제로 생겼는지 셸에 맡기지
# 않고 CLEAN_FILES 에 두 이름을 전부 명시한다. 그렇지 않으면
# `tools/offline_verify.py`의 실행파일 스캔·`tools/run_all.py`·
# `tools/where.py` 단계 판정이 잔여 파일 하나로 깨진다.
clean:
	$(PYTHON) clean.py $(CLEAN_FILES)
