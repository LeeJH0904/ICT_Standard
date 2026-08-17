// a11y.js — 라이브 리전 · 포커스 관리 (WCAG 2.1 AA)

/** #live(aria-live="polite")에 문장을 넣어 스크린리더에 알린다. §3.1 공통 셸. */
export function announce(text) {
  const el = document.getElementById("live");
  if (!el) return;
  el.textContent = "";
  // 같은 문장이 연달아 와도 다시 읽히도록 한 틱 비웠다가 채운다.
  window.setTimeout(() => {
    el.textContent = text;
  }, 30);
}

/** #conn(role="status")에 연결 상태 문장을 넣는다. 색은 CSS 클래스가 맡는다. */
export function setConnStatus(status) {
  const el = document.getElementById("conn");
  if (!el) return;
  el.textContent = status.text;
  el.className = "conn-" + status.code;
}

/** 화면 상태 모델(loading/empty/error/ready) 넷 다 화면에 표시한다 (§3.3). */
export function setViewState(root, state, message) {
  if (!root) return;
  root.setAttribute("aria-busy", state === "loading" ? "true" : "false");
  root.dataset.state = state;
  const slot = root.querySelector("[data-state-message]");
  if (slot) slot.textContent = message || "";
}

/** 포커스 이동 헬퍼 — 모달·패널 전환 시 첫 상호작용 요소로 포커스를 옮긴다. */
export function focusFirst(container) {
  if (!container) return;
  const target = container.querySelector(
    'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])'
  );
  if (target) target.focus();
}
