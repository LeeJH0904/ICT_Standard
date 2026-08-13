// stream.js — SSE 단일 구독 + 폴링 폴백 (화면_설계서.md §3.2)
//
//   GET /api/v1/stream (화면당 1개) ── node_up/node_down/frame/violation/alert/execution
//   onerror -> 1초 폴링 폴백, 지수 백오프 1·2·4·8초(상한)로 재연결 시도
//   상태 3종: "실시간 연결됨" / "폴링 중 (1초)" / "연결 끊김" — 색 + 문자 함께(§8.2)
//
// 제어 명령이 이 경로로 들어올 자리는 없다(§3.2 — SSE 는 단방향, CLAUDE.md §1-7).
//
// F-200 — §3.2 "누락 보정" 행: "폴백 중 놓친 프레임은 재연결 직후
// listFrames?since= 로 채운다". 재연결(EventSource 가 onerror 로 끊겼다가
// 다시 onopen 하는 것)은 이 파일이 유일하게 아는 지점이라, 그 사실을
// `onReconnect` 콜백으로 호출자에게 알린다 — "언제 since= 조회를 할지"는
// 여기서 결정하고, "since= 에 어떤 시각을 넣을지"(화면이 마지막으로 받은
// 프레임의 t)는 호출자만 안다(이 모듈은 프레임 내용을 모른다). 최초 연결
// 성공은 재연결이 아니므로 호출하지 않는다 — 아직 아무 데이터도 없어
// 채울 "누락"이 없다.

const POLL_INTERVAL_MS = 1000;
const BACKOFF_STEPS_MS = [1000, 2000, 4000, 8000];

export const STATUS = {
  LIVE: { code: "live", text: "실시간 연결됨" },
  POLLING: { code: "polling", text: "폴링 중 (1초)" },
  DOWN: { code: "down", text: "연결 끊김" },
};

/**
 * @param {object} opts
 * @param {string[]} opts.events   구독할 이벤트 이름 (예: ["frame","violation"])
 * @param {(type: string, data: any) => void} opts.onEvent
 * @param {(status: {code:string, text:string}) => void} opts.onStatus
 * @param {() => Promise<void>} [opts.onPollTick]  폴링 폴백 중 1초마다 호출 (즉시 보정 없이 다음 재연결까지 미뤄도 되는 화면용)
 * @param {() => Promise<void>} [opts.onReconnect]  F-200 — 폴백을 거쳐 SSE 가 다시 열렸을 때(최초 연결 제외) 1회 호출. `listFrames?since=`로 폴백 중 놓친 프레임을 채우는 자리
 * @returns {() => void} 구독 해제 함수
 */
export function connectStream({ events, onEvent, onStatus, onPollTick, onReconnect }) {
  let es = null;
  let pollTimer = null;
  let backoffIdx = 0;
  let reconnectTimer = null;
  let stopped = false;
  let recovering = false;   // onerror 이후 true — 다음 onopen 이 "재연결"임을 표시한다

  const qs = events && events.length ? `?events=${encodeURIComponent(events.join(","))}` : "";

  function setStatus(s) {
    if (onStatus) onStatus(s);
  }

  function startPolling() {
    if (pollTimer) return;
    setStatus(STATUS.POLLING);
    pollTimer = setInterval(() => {
      if (onPollTick) onPollTick().catch(() => {});
    }, POLL_INTERVAL_MS);
  }

  function stopPolling() {
    if (pollTimer) {
      clearInterval(pollTimer);
      pollTimer = null;
    }
  }

  function scheduleReconnect() {
    if (stopped) return;
    const delay = BACKOFF_STEPS_MS[Math.min(backoffIdx, BACKOFF_STEPS_MS.length - 1)];
    backoffIdx += 1;
    reconnectTimer = setTimeout(open, delay);
  }

  function open() {
    if (stopped) return;
    try {
      es = new EventSource("/api/v1/stream" + qs);
    } catch {
      setStatus(STATUS.DOWN);
      startPolling();
      scheduleReconnect();
      return;
    }

    es.onopen = () => {
      backoffIdx = 0;
      stopPolling();
      setStatus(STATUS.LIVE);
      if (recovering) {
        recovering = false;
        if (onReconnect) onReconnect().catch(() => {});
      }
    };

    es.onerror = () => {
      recovering = true;
      setStatus(pollTimer ? STATUS.POLLING : STATUS.DOWN);
      startPolling();
      if (es) {
        es.close();
        es = null;
      }
      scheduleReconnect();
    };

    const names = events && events.length ? events : ["node_up", "node_down", "frame", "violation", "alert", "execution"];
    for (const name of names) {
      es.addEventListener(name, (ev) => {
        let data = null;
        try {
          data = JSON.parse(ev.data);
        } catch {
          return;
        }
        if (onEvent) onEvent(name, data);
      });
    }
  }

  open();

  return function disconnect() {
    stopped = true;
    stopPolling();
    if (reconnectTimer) clearTimeout(reconnectTimer);
    if (es) es.close();
  };
}
