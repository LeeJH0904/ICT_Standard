// fmt.js — hex · 시각 · 단위 포맷
//
// 이 모듈은 표시 형식만 다룬다. 값의 의미(어느 필드가 무엇인지)는 서버가
// FieldSlice(name, bit_offset, bit_width, raw, display, element, clause)로
// 이미 판정해 준다 — 여기서는 그 값을 hex 문자열 위에 배치하기 위한 순수
// 표시용 위치 계산(니블 인덱스)만 하며, 비트 값을 해석하지 않는다
// (화면 계층은 비트 언팩·프레임 디코딩을 하지 않는다 — 프로토콜 계층의 몫).

/** raw_hex 문자열(2자리 대문자 hex 연속)을 바이트 배열로 나눈다. */
export function hexBytes(rawHex) {
  const s = rawHex || "";
  const out = [];
  for (let i = 0; i < s.length; i += 2) out.push(s.slice(i, i + 2));
  return out;
}

/** 8 byte 씩 줄바꿈 + 오프셋 표기로 hex 뷰용 행 배열을 만든다 (§5.4). */
export function hexLines(rawHex) {
  const bytes = hexBytes(rawHex);
  const lines = [];
  for (let i = 0; i < bytes.length; i += 8) {
    lines.push({ offset: i, bytes: bytes.slice(i, i + 8) });
  }
  return lines;
}

/**
 * 필드의 (bit_offset, bit_width)를 니블(4bit) 인덱스 범위로 바꾼다.
 * 바이트 절반(니블) 단위까지만 표시를 나눈다 — §5.4 "바이트를 반씩 쓰는
 * 필드는 반쪽만 칠한다"의 구현. 값 자체를 읽거나 시프트/마스크하지 않는다.
 */
export function nibbleRange(bitOffset, bitWidth) {
  const startNibble = Math.floor(bitOffset / 4);
  const endNibble = Math.ceil((bitOffset + bitWidth) / 4); // 배타적 끝
  return { startNibble, endNibble };
}

/** epoch seconds -> "N초 전" / "N분 전" 상대 시각. 그래프 aria-label 등에 쓴다. */
export function relativeTime(epochSeconds, nowMs = Date.now()) {
  if (epochSeconds == null) return "시각 없음";
  const diffSec = Math.max(0, Math.round(nowMs / 1000 - epochSeconds));
  if (diffSec < 60) return `${diffSec}초 전`;
  if (diffSec < 3600) return `${Math.floor(diffSec / 60)}분 전`;
  if (diffSec < 86400) return `${Math.floor(diffSec / 3600)}시간 전`;
  return `${Math.floor(diffSec / 86400)}일 전`;
}

/** ISO 8601 문자열 -> epoch seconds. */
export function isoToEpoch(iso) {
  if (!iso) return null;
  const t = Date.parse(iso);
  return Number.isNaN(t) ? null : t / 1000;
}

/** epoch seconds -> ISO 8601 문자열. `listFrames?since=`(ISO 8601) 에 넘길 값을
 * 만드는 용도로, isoToEpoch 의 반대 방향이다. */
export function epochToIso(epochSeconds) {
  if (epochSeconds == null || Number.isNaN(epochSeconds)) return null;
  return new Date(epochSeconds * 1000).toISOString();
}

/** ISO 8601 문자열 -> 사람이 읽는 로컬 시각. */
export function formatDateTime(iso) {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString("ko-KR", { hour12: false });
}

/** 정수 -> "0x" + 대문자 hex. 자릿수를 지정할 수 있다(패딩). */
export function hex(n, digits = 0) {
  if (n == null) return "—";
  const s = Number(n).toString(16).toUpperCase();
  return "0x" + s.padStart(digits, "0");
}

/** 숫자 + 단위를 사람이 읽는 형태로. 소수 1자리까지만 보인다. */
export function formatValue(value, unit) {
  if (value == null) return "—";
  const v = typeof value === "number" ? value.toFixed(1).replace(/\.0$/, ".0") : value;
  return unit ? `${v} ${unit}` : `${v}`;
}

/**
 * 서버가 돌려준 자유 텍스트를 innerHTML 템플릿 문자열에 안전하게 넣는다
 * (규칙 초안 draft_text 등을 이스케이프 없이 innerHTML 에 넣으면
 * 저장형 DOM 주입이 가능했다). 텍스트 노드·속성값(따옴표 포함) 양쪽
 * 컨텍스트에서 다 안전하도록 5문자를 전부 치환한다.
 */
export function escapeHtml(value) {
  if (value == null) return "";
  return String(value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}
