from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any, ClassVar

from settings import Settings


_BASE_HTML = """<!doctype html>
<html>
  <head>
    <meta charset="utf-8" />
    <style>
      html, body {
        margin: 0;
        padding: 0;
        width: 100%;
        height: 100%;
      }
      #diagram-root {
        width: 1280px;
        min-height: 720px;
      }
      #chart-root {
        width: 720px;
        height: 420px;
      }
    </style>
  </head>
  <body>
    <div id="diagram-root"></div>
    <div id="chart-root"></div>
  </body>
</html>
"""


_MERMAID_PROBE_SCRIPT = """
async (diagram) => {
  try {
    const runtime = globalThis.mermaid;
    if (!runtime) {
      return { status: "unavailable", reason: "Mermaid runtime not available in probe page." };
    }

    if (typeof runtime.initialize === "function") {
      runtime.initialize({
        startOnLoad: false,
        securityLevel: "strict",
        suppressErrorRendering: true,
      });
    }

    const root = document.getElementById("diagram-root");
    if (!root) {
      return { status: "unavailable", reason: "Mermaid probe root element not found." };
    }

    const renderId = "tier2_" + Math.random().toString(36).slice(2);
    let renderResult = null;
    try {
      if (runtime.mermaidAPI && typeof runtime.mermaidAPI.render === "function") {
        renderResult = await runtime.mermaidAPI.render(renderId, diagram);
      } else if (typeof runtime.render === "function") {
        renderResult = await runtime.render(renderId, diagram);
      } else {
        return { status: "unavailable", reason: "Mermaid render API not available." };
      }
    } catch (renderError) {
      const message = renderError && renderError.message ? String(renderError.message) : String(renderError);
      // Distinguish mermaid parse/syntax errors from unexpected infrastructure failures.
      // parse() was previously called before render(), but it is stricter than render() and
      // rejects diagrams that render() handles gracefully. Using render() as the sole test
      // matches the actual frontend behaviour.
      const isParseError = /parse\s+error|syntax\s+error|unrecognized|invalid\s+diagram|lexer|token/i.test(message);
      if (isParseError) {
        return { status: "invalid", reason: message };
      }
      // Any other exception (DOM error, JS runtime fault, browser quirk) is an
      // infrastructure failure — not a signal that the diagram itself is bad.
      return { status: "unavailable", reason: message };
    }

    const svg = renderResult && typeof renderResult.svg === "string" ? renderResult.svg : "";
    if (!svg || svg.indexOf("<svg") === -1) {
      return { status: "invalid", reason: "Mermaid render returned empty SVG output." };
    }

    root.innerHTML = svg;
    return { status: "valid" };
  } catch (error) {
    // Outer catch handles unexpected infrastructure-level failures (e.g. page unavailable,
    // asset load error). Return "unavailable" so fail_open=True can rescue the block.
    const message = error && error.message ? String(error.message) : String(error);
    return { status: "unavailable", reason: message };
  }
}
"""


_ECHARTS_PROBE_SCRIPT = """
async (option) => {
  try {
    const runtime = globalThis.echarts;
    if (!runtime || typeof runtime.init !== "function") {
      return { status: "unavailable", reason: "ECharts runtime not available in probe page." };
    }

    const root = document.getElementById("chart-root");
    if (!root) {
      return { status: "unavailable", reason: "ECharts probe root element not found." };
    }

    root.style.width = "720px";
    root.style.height = "420px";

    const chart = runtime.init(root, null, { renderer: "canvas" });
    try {
      chart.setOption(option, { notMerge: true, lazyUpdate: false, silent: true });
      chart.resize({ width: 720, height: 420 });
      const png = chart.getDataURL({
        type: "png",
        pixelRatio: 1,
        backgroundColor: "#ffffff",
      });
      if (!png || typeof png !== "string" || !png.startsWith("data:image/")) {
        return { status: "invalid", reason: "ECharts rendering produced empty output." };
      }
      return { status: "valid" };
    } catch (error) {
      const message = error && error.message ? String(error.message) : String(error);
      return { status: "invalid", reason: message };
    } finally {
      try {
        chart.dispose();
      } catch (_) {}
    }
  } catch (error) {
    const message = error && error.message ? String(error.message) : String(error);
    return { status: "unavailable", reason: message };
  }
}
"""


class PlaywrightVisualTier2Validator:
    _asset_cache: ClassVar[dict[str, str]] = {}
    _asset_cache_lock: ClassVar[asyncio.Lock] = asyncio.Lock()
    _session_limiters: ClassVar[dict[str, asyncio.Semaphore]] = {}
    _session_limiters_lock: ClassVar[asyncio.Lock] = asyncio.Lock()

    def __init__(
        self,
        settings: Settings,
        *,
        session_id: str,
        browser: Any,
    ) -> None:
        self._enabled = bool(settings.visual_tier2_enabled)
        self._timeout_seconds = max(0.5, float(settings.visual_tier2_timeout_seconds))
        self._concurrency_per_session = max(
            1,
            int(settings.visual_tier2_concurrency_per_session),
        )
        self._session_id = str(session_id or "").strip() or "default"
        self._browser = browser
        self._mermaid_max_bytes = max(512, int(settings.visual_tier2_mermaid_max_bytes))
        self._chart_max_bytes = max(512, int(settings.visual_tier2_chart_max_bytes))
        self._base_dir = Path(__file__).resolve().parent.parent
        self._mermaid_asset_path = self._resolve_asset_path(settings.visual_tier2_mermaid_asset_path)
        self._echarts_asset_path = self._resolve_asset_path(settings.visual_tier2_echarts_asset_path)

    @staticmethod
    def _short_reason(reason: str | None, limit: int = 220) -> str | None:
        if reason is None:
            return None
        normalized = " ".join(str(reason).split())
        if not normalized:
            return None
        if len(normalized) <= limit:
            return normalized
        return normalized[:limit] + "..."

    def _resolve_asset_path(self, configured_path: str) -> Path:
        raw = str(configured_path or "").strip()
        path = Path(raw)
        if path.is_absolute():
            return path
        return (self._base_dir / path).resolve()

    @classmethod
    async def _get_session_limiter(cls, session_id: str, concurrency: int) -> asyncio.Semaphore:
        async with cls._session_limiters_lock:
            limiter = cls._session_limiters.get(session_id)
            if limiter is None:
                limiter = asyncio.Semaphore(concurrency)
                cls._session_limiters[session_id] = limiter
            return limiter

    @classmethod
    async def clear_session_limiters(cls) -> None:
        async with cls._session_limiters_lock:
            cls._session_limiters.clear()

    @classmethod
    async def _load_asset(cls, asset_path: Path) -> str | None:
        cache_key = str(asset_path)
        cached = cls._asset_cache.get(cache_key)
        if cached is not None:
            return cached

        async with cls._asset_cache_lock:
            cached = cls._asset_cache.get(cache_key)
            if cached is not None:
                return cached
            if not asset_path.exists():
                return None
            try:
                content = await asyncio.to_thread(asset_path.read_text, encoding="utf-8")
            except Exception:
                return None
            cls._asset_cache[cache_key] = content
            return content

    def _normalize_probe_result(self, value: Any) -> tuple[str, str | None]:
        if not isinstance(value, dict):
            return ("unavailable", "Tier-2 probe returned malformed response.")

        status_raw = str(value.get("status") or "").strip().lower()
        reason = self._short_reason(value.get("reason"))
        if status_raw == "valid":
            return ("valid", None)
        if status_raw == "invalid":
            return ("invalid", reason or "Visualization probe rejected the block.")
        if status_raw == "unavailable":
            return ("unavailable", reason or "Visualization probe is unavailable.")
        return ("unavailable", reason or "Visualization probe returned unknown status.")

    async def _run_browser_probe(
        self,
        *,
        asset_source: str,
        evaluate_script: str,
        evaluate_arg: Any,
    ) -> tuple[str, str | None]:
        if self._browser is None or not hasattr(self._browser, "new_context"):
            return ("unavailable", "Playwright browser is not available for Tier-2 validation.")

        context = None
        try:
            context = await self._browser.new_context(
                java_script_enabled=True,
                viewport={"width": 1280, "height": 720},
            )
            page = await context.new_page()
            await page.set_content(_BASE_HTML, wait_until="domcontentloaded")
            await page.add_script_tag(content=asset_source)
            probe_value = await page.evaluate(evaluate_script, evaluate_arg)
            return self._normalize_probe_result(probe_value)
        except asyncio.CancelledError:
            raise
        except Exception as error:
            return ("unavailable", self._short_reason(f"Playwright Tier-2 probe failed: {error}"))
        finally:
            if context is not None:
                try:
                    await context.close()
                except Exception:
                    pass

    async def _run_with_session_limit(
        self,
        *,
        asset_source: str,
        evaluate_script: str,
        evaluate_arg: Any,
    ) -> tuple[str, str | None]:
        limiter = await self._get_session_limiter(
            session_id=self._session_id,
            concurrency=self._concurrency_per_session,
        )
        async with limiter:
            try:
                return await asyncio.wait_for(
                    self._run_browser_probe(
                        asset_source=asset_source,
                        evaluate_script=evaluate_script,
                        evaluate_arg=evaluate_arg,
                    ),
                    timeout=self._timeout_seconds,
                )
            except asyncio.TimeoutError:
                return (
                    "unavailable",
                    f"Tier-2 validation timed out after {self._timeout_seconds:.1f}s.",
                )

    async def validate_mermaid(self, definition: str) -> tuple[str, str | None]:
        if not self._enabled:
            return ("unavailable", "Tier-2 validation is disabled.")

        source = str(definition or "").strip()
        if not source:
            return ("invalid", "Empty mermaid block.")

        source_bytes = source.encode("utf-8", errors="ignore")
        if len(source_bytes) > self._mermaid_max_bytes:
            return (
                "unavailable",
                (
                    "Mermaid block exceeds Tier-2 size limit "
                    f"({len(source_bytes)} bytes > {self._mermaid_max_bytes} bytes)."
                ),
            )

        asset_source = await self._load_asset(self._mermaid_asset_path)
        if not asset_source:
            return (
                "unavailable",
                f"Mermaid asset could not be loaded from {self._mermaid_asset_path}.",
            )

        return await self._run_with_session_limit(
            asset_source=asset_source,
            evaluate_script=_MERMAID_PROBE_SCRIPT,
            evaluate_arg=source,
        )

    async def validate_chartjson_option(self, option: dict[str, Any]) -> tuple[str, str | None]:
        if not self._enabled:
            return ("unavailable", "Tier-2 validation is disabled.")

        if not isinstance(option, dict):
            return ("invalid", "chartjson option must be an object.")

        try:
            normalized_json = json.dumps(option, ensure_ascii=False, separators=(",", ":"))
        except (TypeError, ValueError) as error:
            return ("invalid", f"chartjson option is not JSON-serializable: {error}.")

        option_bytes = normalized_json.encode("utf-8", errors="ignore")
        if len(option_bytes) > self._chart_max_bytes:
            return (
                "unavailable",
                (
                    "chartjson option exceeds Tier-2 size limit "
                    f"({len(option_bytes)} bytes > {self._chart_max_bytes} bytes)."
                ),
            )

        asset_source = await self._load_asset(self._echarts_asset_path)
        if not asset_source:
            return (
                "unavailable",
                f"ECharts asset could not be loaded from {self._echarts_asset_path}.",
            )

        return await self._run_with_session_limit(
            asset_source=asset_source,
            evaluate_script=_ECHARTS_PROBE_SCRIPT,
            evaluate_arg=option,
        )
