const rawBaseUrl = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";
export const API_BASE_URL = rawBaseUrl.replace(/\/+$/, "");

const DEFAULT_TIMEOUT_MS = 30_000;

function isBodyPresent(body) {
  return body !== undefined && body !== null;
}

function shouldUseJsonContentType(body) {
  if (!isBodyPresent(body)) return false;
  if (typeof FormData !== "undefined" && body instanceof FormData) return false;
  if (typeof URLSearchParams !== "undefined" && body instanceof URLSearchParams) return false;
  if (typeof Blob !== "undefined" && body instanceof Blob) return false;
  if (typeof ArrayBuffer !== "undefined" && body instanceof ArrayBuffer) return false;
  return true;
}

export async function apiRequest(path, options = {}) {
  const {
    timeoutMs = DEFAULT_TIMEOUT_MS,
    signal: externalSignal,
    headers: customHeaders = {},
    ...requestOptions
  } = options;

  const headers = {
    ...(customHeaders || {}),
  };

  if (!Object.keys(headers).some((key) => key.toLowerCase() === "content-type")) {
    if (shouldUseJsonContentType(requestOptions.body)) {
      headers["Content-Type"] = "application/json";
    }
  }

  const controller = new AbortController();
  let timeoutId = null;
  let timedOut = false;
  let removeExternalAbortListener = null;

  if (Number.isFinite(Number(timeoutMs)) && Number(timeoutMs) > 0) {
    timeoutId = setTimeout(() => {
      timedOut = true;
      controller.abort();
    }, Number(timeoutMs));
  }

  if (externalSignal) {
    if (externalSignal.aborted) {
      controller.abort(externalSignal.reason);
    } else {
      const onAbort = () => controller.abort(externalSignal.reason);
      externalSignal.addEventListener("abort", onAbort, { once: true });
      removeExternalAbortListener = () => externalSignal.removeEventListener("abort", onAbort);
    }
  }

  let response;
  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      credentials: "include",
      headers,
      signal: controller.signal,
      ...requestOptions,
    });
  } catch (error) {
    if (timedOut) {
      throw new Error(`Request timed out after ${Number(timeoutMs)}ms`);
    }
    if (error?.name === "AbortError") {
      throw new Error("Request was cancelled.");
    }
    throw error;
  } finally {
    if (timeoutId !== null) {
      clearTimeout(timeoutId);
    }
    if (removeExternalAbortListener) {
      removeExternalAbortListener();
    }
  }

  if (response.status === 204) {
    return null;
  }

  const contentType = response.headers.get("content-type") || "";
  let payload = null;
  if (contentType.includes("application/json")) {
    payload = await response.json();
  } else {
    const text = await response.text();
    payload = text || null;
  }

  if (!response.ok) {
    const detail =
      (payload &&
        typeof payload === "object" &&
        (
          (typeof payload?.error === "object" && payload?.error?.message) ||
          (typeof payload?.error === "string" && payload?.error) ||
          payload?.detail
        )) ||
      `Request failed with status ${response.status}`;
    throw new Error(String(detail));
  }

  return payload;
}
