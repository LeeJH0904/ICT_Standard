# 펌웨어 빌드 노트 (단계 8)

> 호스트 유닛테스트(`tests/`)는 이 문서와 무관하다 — `avr-gcc` 없이 `make` 로 돈다(§8).
> 이 문서는 **실물 보드 3종**(Uno·Pro Mini·ESP32)을 아두이노 툴체인으로 올리는 방법이다.

`core/` 는 세 보드가 **하나의 소스**로 공유한다(단일 본 — `board_verify.py` A 검사가 강제).
복제하지 않으므로 아두이노 빌드가 `../core` 에 닿게 하는 설정이 필요하다.

---

## 1. `core/` 를 아두이노 라이브러리로 노출

아두이노 IDE 는 스케치 폴더 안(그리고 설치된 라이브러리)만 컴파일한다 — `../core/*.c`
를 자동으로 빌드하지 않는다. `firmware/core/` 를 라이브러리로 한 번 노출한다.

**방법 A — Add .ZIP Library (IDE, 가장 간단):**

1. `firmware/core/` **폴더 자체**를 zip 으로 압축한다 — 압축 파일 안에 `core/bitpack.c`
   처럼 **최상위에 `core` 폴더가 있어야** 한다(폴더 안 파일들만 압축하면 IDE 가
   "유효한 라이브러리가 아님"으로 거부한다).
2. Arduino IDE → **스케치 → 라이브러리 포함 → .ZIP 라이브러리 추가** → 그 zip 선택.
3. 그러면 `core` 가 라이브러리로 설치되고, 스케치의 `#include <node_state.h>` 를 IDE 가
   보고 `core` 의 `.c` 3개(`bitpack.c`·`siap_frame.c`·`node_state.c`)를 자동으로 함께
   컴파일한다(루트에 소스가 있는 레거시 플랫 라이브러리로 인식).

> 이 방식은 IDE 라이브러리 폴더에 **복사본**을 만든다. 저장소 밖이라 "3종 동일 소스"
> (저장소 기준) 주장과 무관하며 컴파일 검증에는 문제없다. `core/` 를 고치면 zip 을
> 다시 추가한다. `board_verify.py` A 검사는 **저장소 안** 보드 디렉터리의 복제만 본다.

**방법 B — 심볼릭 링크 (core 를 고치며 반복 빌드할 때):**

```bash
# Windows (관리자 명령 프롬프트)
mklink /D "%USERPROFILE%\Documents\Arduino\libraries\SiapCore" "<repo>\project_code\firmware\core"
# macOS/Linux
ln -s "<repo>/project_code/firmware/core" ~/Arduino/libraries/SiapCore
```

**방법 C — arduino-cli (헤드리스, 재현 가능):**

```bash
arduino-cli compile --fqbn arduino:avr:uno \
  --libraries project_code/firmware \
  project_code/firmware/arduino_sensor_node
```

## 2. 스케치 파일 이름 — `<폴더명>.ino`

아두이노는 **주 스케치 파일 이름 == 폴더 이름**을 요구한다. 설계서(§7.2)는 `main.ino`
로 불렀으나, 실물 툴체인 제약에 맞춰 **`<폴더명>.ino` 로 통일한다**:

| 폴더 | 주 스케치 파일 |
|---|---|
| `arduino_sensor_node/` | `arduino_sensor_node.ino` |
| `arduino_actuator_node/` | `arduino_actuator_node.ino` |
| `esp32_node/` | `esp32_node.ino` |

> 펌웨어 설계서 §7.2·부록의 "main.ino" 표기는 이 결정으로 대체한다(단계 8 실측).
> `board_verify.py` C 검사가 이 이름으로 필수 파일을 확인한다.

## 3. C / C++ 경계

| 파일 | 컴파일 | 이유 |
|---|---|---|
| `main.ino` | C++ | 아두이노 API(`Serial`·`analogRead`·`digitalWrite`·`WiFiClient`)는 C++ 다 |
| `sensors.c` · `actuators.c` · `net.c` | C | 하드웨어 API 를 부르지 않는 순수 산술·상태만 — `core/` 와 같은 C 세계 |

`main.ino` 는 `core/` 헤더(C99)를 `extern "C" { … }` 로 감싸 include 한다 — C++ 에서
C 링크로 부르기 위해서다. 하드웨어를 만지는 콜백(`uart_read_byte` 등)도 `extern "C"`
로 선언해 `core/` 의 함수 포인터 타입(C 링크)과 맞춘다.

## 4. 빌드 후 `avr-size` 실측 (출구 ①)

AVR 보드 2종은 SRAM 예산(2048B의 40% = 819B) 안이어야 한다(펌웨어 설계서 §3.5,
개발_착수_지시서 §1.5). 빌드 후 실측을 각 보드 디렉터리에 커밋한다:

```bash
avr-size <빌드된 .elf>        # 또는 arduino-cli 빌드 산출물의 .elf
#   text   data    bss    dec    hex  filename
#   9876    412    390  10678   29b6  arduino_sensor_node.ino.elf
# → project_code/firmware/arduino_sensor_node/size_report.txt 에 위 표 줄을 저장
```

`board_verify.py` F 검사가 `<board>/size_report.txt` 를 읽어 `data+bss` 를 예산과
대조한다. 파일이 없으면 `[SKIP]`(사람 실측)으로 남는다.

## 5. `board_verify.py` 로 판정

```bash
python tools/board_verify.py
```

- `avr-gcc` 가 PATH 에 있으면 E(AVR쌍 `core.o` 동일)가 실측된다. IDE 만 있고
  `avr-gcc` 가 PATH 에 없으면 IDE 번들 경로를 PATH 에 추가하거나 `[SKIP]` 로 둔다.
- `.elf`·`.hex` 는 커밋하지 않는다(`.gitignore`, CLAUDE.md §1-3). `size_report.txt`
  (텍스트)만 커밋한다.

## 6. Wi-Fi 자격증명 (ESP32)

`esp32_node/secrets.h.example` 을 `secrets.h` 로 복사해 SSID/비밀번호와 게이트웨이
IP/포트를 채운다. `secrets.h` 는 `.gitignore` 대상이다(CLAUDE.md §1-2). 예시 파일만
저장소에 둔다.
