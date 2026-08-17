// api.js — fetch 래퍼 · 오류 정규화
//
// 서버는 같은 오리진(uvicorn 이 web/ 을 함께 서빙한다, run.py --serve)에서
// 뜬다 — 상대 경로만 쓰고 CORS 를 가정하지 않는다.
// 이 모듈은 오퍼레이션 이름 -> HTTP 호출만 감싼다. 표준 해석·판정 로직은
// 없다 — 화면은 서버가 준 값을 그대로 옮긴다.

const BASE = "/api/v1";

/** API 오류를 하나의 형태로 정규화한다. Problem(RFC 9457) 이 오면 그대로 담는다. */
export class ApiError extends Error {
  constructor(status, problem) {
    super(problem?.title || `HTTP ${status}`);
    this.status = status;
    this.problem = problem || null; // {title, status, detail, clause, constraint, siap_rsc}
  }
}

async function request(method, path, { params, body, userId, signal } = {}) {
  const url = new URL(BASE + path, window.location.origin);
  if (params) {
    for (const [k, v] of Object.entries(params)) {
      if (v !== undefined && v !== null && v !== "") url.searchParams.set(k, v);
    }
  }
  const headers = {};
  if (body !== undefined) headers["Content-Type"] = "application/json";
  if (userId) headers["X-User-Id"] = userId;

  let res;
  try {
    res = await fetch(url.toString(), {
      method,
      headers,
      body: body !== undefined ? JSON.stringify(body) : undefined,
      signal,
    });
  } catch (netErr) {
    throw new ApiError(0, {
      title: "서버에 연결할 수 없습니다",
      status: 0,
      detail: String(netErr && netErr.message ? netErr.message : netErr),
    });
  }

  if (res.status === 204) return null;

  const ct = res.headers.get("content-type") || "";
  const payload = ct.includes("json") ? await res.json().catch(() => null) : await res.text();

  if (!res.ok) {
    throw new ApiError(res.status, typeof payload === "object" ? payload : { title: String(payload), status: res.status });
  }
  return payload;
}

// 동일한 필터의 페이지를 응답 total까지 모두 소비한다.
//
// SSE 재연결 누락 복구는 100건을 넘을 수 있으므로 첫 페이지만 가져와서는
// 안 된다. fetchPage는 listFrames 또는 listViolations처럼 Page를
// 반환하는 함수이고, params에는 복구 구간의 since/until 스냅샷이 들어간다.
export async function collectAllPages(fetchPage, params = {}, limit = 100) {
  const items = [];
  let offset = 0;
  let total = Number.POSITIVE_INFINITY;
  while (offset < total) {
    const page = await fetchPage({ ...params, limit, offset });
    const batch = Array.isArray(page?.items) ? page.items : [];
    total = Number.isInteger(page?.total) ? page.total : offset + batch.length;
    items.push(...batch);
    if (!batch.length) break;
    offset += batch.length;
  }
  return items;
}

export const api = {
  // ── ems (기능 1 · 설정) ──
  // 화면별 읽기·쓰기만 감싼다 — 어느 화면도 쓰지 않는 오퍼레이션은 래퍼를 두지
  // 않는다(쓰지 않는 래퍼는 "화면이 쓰는 오퍼레이션만 있다"는 대조를 흐린다).
  listNodes: (params) => request("GET", "/nodes", { params }),
  listNodeDevices: (nodeId) => request("GET", `/nodes/${nodeId}/devices`),
  setDeviceProperty: (selector, property, userId) =>
    request("PATCH", "/device-property", { body: { selector, property }, userId }),

  // ── fms (기능 1) ──
  listTelemetry: (params) => request("GET", "/telemetry", { params }),
  listDeviceStates: (params) => request("GET", "/device-states", { params }),
  listAlerts: (params) => request("GET", "/alerts", { params }),

  // ── conformance (기능 2) ──
  listFrames: (params) => request("GET", "/frames", { params }),
  listViolations: (params) => request("GET", "/frames/violations", { params }),
  getFrame: (frameId) => request("GET", `/frames/${frameId}`),
  injectVector: (vectorId, userId) => request("POST", "/sim/inject", { body: { vector_id: vectorId }, userId }),

  // ── dms (기능 3 입력) ──
  listPublicDataSources: () => request("GET", "/publicdata/sources"),
  listPublicDataRecords: (params) => request("GET", "/publicdata/records", { params }),

  // ── mms · fcs (기능 3) ──
  listRules: (params) => request("GET", "/rules", { params }),
  getRule: (ruleId) => request("GET", `/rules/${ruleId}`),
  createRuleDraft: (bodyReq) => request("POST", "/rules", { body: bodyReq }),
  approveRule: (ruleId, bodyReq, userId) => request("POST", `/rules/${ruleId}/approve`, { body: bodyReq, userId }),
  rejectRule: (ruleId, reason, userId) => request("POST", `/rules/${ruleId}/reject`, { body: { reason }, userId }),
  executeRule: (ruleId) => request("POST", `/rules/${ruleId}/execute`, {}),
  manualControl: (bodyReq, userId) => request("POST", "/control", { body: bodyReq, userId }),
  listExecutions: (params) => request("GET", "/executions", { params }),
};

/** Problem -> 화면 표기 문자열. 위반 코드는 서버가 준 code_name·clause 그대로. */
export function describeProblem(problem) {
  if (!problem) return "알 수 없는 오류";
  const parts = [problem.title || "오류"];
  if (problem.siap_rsc) parts.push(`(${problem.siap_rsc})`);
  if (problem.clause) parts.push(`— ${problem.clause}`);
  if (problem.detail) parts.push(`: ${problem.detail}`);
  return parts.join(" ");
}
