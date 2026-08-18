"""
siap/control.py — 송신 대기·재전송 (0943 7.2.2 매칭, 표 7-18 재전송).

`_pending`/`_match_pending`/`_drain_request_queue`/
`_expire_pending` 의 로직을 여기로 옮긴다. `link.py`의 SIAP I/O 스레드가 이
모듈의 `PendingTable`을 소유하지만, 이 파일 자체는 스레드나 실제 시리얼/소켓을
만들지 않는다 — 시간 소스와 송신 콜백을 인자로 받아 순수 로직만 담아서,
`link.py` 없이도(sleep 없이도) 단위테스트할 수 있게 한다.
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field

try:                    # 패키지로 import될 때
    from contracts.frame import Frame, MsgControlProfile, MsgKind, expected_reply
except ImportError:     # 스크립트로 직접 실행되거나 project_code 가 sys.path 밖일 때
    import pathlib
    import sys
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
    from contracts.frame import Frame, MsgControlProfile, MsgKind, expected_reply


@dataclass
class PendingRequest:
    frame: Frame
    expect: MsgKind | None
    deadline: float
    tries: int = 0
    result: Frame | None = None
    event: threading.Event = field(default_factory=threading.Event)


class PendingTable:
    """ 매칭(`Node ID` + `Message Identifier` + **`Message Type`**) ·
    재전송(`msg_id` 유지)·타임아웃(`Timeout × (Retry Count + 1)`)을
    구현한다. 시간 소스(`now_fn`)를 주입할 수 있어 재전송·타임아웃을 실제
    `sleep` 없이 테스트한다."""

    def __init__(self, profile: MsgControlProfile, now_fn=time.monotonic) -> None:
        self._profile = profile
        self._now = now_fn
        self._lock = threading.Lock()
        self._pending: dict[tuple[int, int], PendingRequest] = {}

    def update_profile(self, profile: MsgControlProfile) -> None:
        """역방향 프로파일 설정 성공 뒤 새 pending부터 즉시 적용한다.
        프로파일 교체와 register()/expire()의 판정을 같은 잠금으로 직렬화한다."""
        with self._lock:
            self._profile = profile

    def profile(self) -> MsgControlProfile:
        """현재 재전송 프로파일의 불변 사본을 반환한다."""
        with self._lock:
            return self._profile

    def register(self, frame: Frame) -> PendingRequest | None:
        """송신 직후 호출한다(`_drain_request_queue`). 기대 회신 종류가
        없으면(`RES_*`·`ACK` 송신) 대기 항목을 만들지 않고 None 을 돌려준다 —
        호출자는 즉시 완료로 본다."""
        if frame.header is None:
            return None
        expect = expected_reply(frame.kind)
        if expect is None:
            return None
        key = (frame.header.node_id, frame.header.msg_id)
        with self._lock:
            req = PendingRequest(frame=frame, expect=expect,
                                  deadline=self._now() + self._profile.recv_timeout)
            self._pending[key] = req
        return req

    def match(self, frame: Frame) -> bool:
        """수신 프레임을 대기 항목과 맞춘다(`_match_pending`). 소비했으면
        True. 기대와 다른 프레임(kind 불일치)은 대기 항목을 소비하지 않고
        흘려보낸다 — 진짜 Response 가 아직 올 수 있다. 타임아웃 판단은
        `expire()` 의 몫이다."""
        if frame.header is None:
            return False
        key = (frame.header.node_id, frame.header.msg_id)
        with self._lock:
            pend = self._pending.get(key)
            if pend is None:
                return False                          # 지연 도착·중복 — 로그만 남기고 흘린다(호출자 몫)
            if frame.kind is not pend.expect:
                return False
            del self._pending[key]
        pend.result = frame
        pend.event.set()                              # send() 의 wait() 해제
        return True

    def expire(self, write_fn) -> None:
        """타임아웃을 넘긴 대기 항목을 재전송하거나(재시도 남음, 표 7-18
        `Num. of Retry`) 포기한다(`_expire_pending`). `write_fn(frame)` 은
        재전송 바이트를 실제로 내보내는 콜백(link.py 가 주입) — `msg_id` 는
        그대로 유지한다(새로 발번하면 노드가 중복 요청으로 처리한다)."""
        now = self._now()
        with self._lock:
            items = list(self._pending.items())
        for key, pend in items:
            if now < pend.deadline:
                continue
            with self._lock:
                if self._pending.get(key) is not pend:
                    continue                          # 그 사이 match() 로 이미 소비됨
                if pend.tries < self._profile.num_retry:
                    pend.tries += 1
                    pend.deadline = now + self._profile.recv_timeout
                    do_retry = True
                else:
                    del self._pending[key]
                    do_retry = False
            if do_retry:
                write_fn(pend.frame)                  # msg_id 유지 — 재발번하지 않는다
            else:
                pend.result = None
                pend.event.set()                      # 타임아웃 → send() 가 None 반환

    def wait(self, req: PendingRequest, timeout: float | None = None) -> Frame | None:
        """`send()` 대기 상한 = `Timeout × (Retry Count + 1)`(표 7-18 두 값에서
        유도) — 호출자가 별도로 정하지 않는다.
        `timeout` 을 명시하면 그 값을 대신 쓴다(테스트·특수 호출용)."""
        upper = timeout if timeout is not None else self._profile.recv_timeout * (self._profile.num_retry + 1)
        req.event.wait(timeout=upper)
        return req.result

    def __len__(self) -> int:
        with self._lock:
            return len(self._pending)
