# F-212 · xcodec이 양쪽 코덱의 같은 의미 오류를 통과시킴

| 항목 | 값 |
|---|---|
| 심각도 | 오류 |
| 분류 | 코드버그 |
| 대상 | `tools/xcodec_verify.py:L148` · `project_code/firmware/tests/dump_golden.c:L210` |
| 발견일 | 2026-08-12 |
| 상태 | 신규 |

## 근거

개발 착수 지시서 §3.3 — “C 인코더 출력 ↔ Python 인코더 출력을 골든 53건 전량에서 바이트 비교.”

CLAUDE.md §6.2 — “검증기는 검증 대상 파일 하나만 읽지 않는다. 자기 자신과의 일치만 보게 된다. 적어도 하나의 독립 입력과 대조한다.”

## 현상

`xcodec_verify.py`는 골든 `hex`를 Python이 디코드한 뒤 같은 Python이 재인코딩한다. C의 `dump_golden.c`도 같은 바이트를 C가 디코드한 뒤 같은 C가 재인코딩한다. 골든 JSON의 `header`·`fields` 의미값은 검사하지 않으므로 인코더와 디코더가 같은 방식으로 틀리면 원본 바이트가 보존되어 통과한다.

## 영향

GCG ID와 Node ID처럼 비트폭까지 같은 필드의 의미를 서로 바꾼 Python 구현도 C↔Python 53건 일치로 판정된다. 단계 3 출구와 핵심 주장 1의 CPython 상호운용성 증거가 성립하지 않는다.

## 재현

원본 파일은 수정하지 않고 Python 모듈을 메모리에서 변조했다.

```python
import json, runpy, sys, types
from pathlib import Path
p=Path.cwd(); sys.path.insert(0,str(p/'project_code')); import siap
s=(p/'project_code/siap/codec.py').read_text(encoding='utf-8')
s=s.replace('and w.write(h.gcg_id, 20) and w.write(h.node_id, 20))',
            'and w.write(h.node_id, 20) and w.write(h.gcg_id, 20))')
s=s.replace('gcg_id=r.read(20), node_id=r.read(20),',
            'node_id=r.read(20), gcg_id=r.read(20),')
m=types.ModuleType('siap.codec'); m.__package__='siap'
exec(compile(s,'<mutant>','exec'),m.__dict__)
sys.modules['siap.codec']=m; siap.codec=m
v=json.loads((p/'project_code/contracts/vectors/golden.jsonl').read_text(encoding='utf-8').splitlines()[0])
h=m.decode_frame(bytes.fromhex(v['hex']),node_known=lambda n:True).header
print(h.gcg_id,h.node_id,v['header']['GCG ID'],v['header']['Node ID'])
raise SystemExit(runpy.run_path(str(p/'tools/xcodec_verify.py'))['main']())
```

실행 결과는 `3 1 1 3`, `9/9 통과`, 종료 코드 0이다.

## 제안

골든 의미값에서 각 언어의 Frame을 독립 구성해 인코딩 결과를 `hex`와 비교하고, `hex` 디코딩 결과도 골든 의미값과 대조한다. C 덤프 역시 의미값→인코드 경로를 둔다.

---

## Claude 처리 기록

| 일시 | 상태 | 내용 |
|---|---|---|
