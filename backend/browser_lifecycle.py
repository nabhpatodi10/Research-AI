import asyncio
import logging
from typing import Any

from playwright.async_api import Browser, async_playwright


logger = logging.getLogger(__name__)


class BrowserLifecycleManager:
    def __init__(self, *, headless: bool = True, launch_kwargs: dict[str, Any] | None = None):
        self._headless = headless
        self._launch_kwargs = dict(launch_kwargs or {})
        self._lock = asyncio.Lock()
        self._playwright = None
        self._browser: Browser | None = None
        self._generation = 0
        self._relaunch_count = 0

    @staticmethod
    def _is_browser_connected(browser: Browser | None) -> bool:
        if browser is None:
            return False
        try:
            return bool(browser.is_connected())
        except Exception:
            return False

    def is_connected(self) -> bool:
        return self._is_browser_connected(self._browser)

    @property
    def generation(self) -> int:
        return self._generation

    @property
    def relaunch_count(self) -> int:
        return self._relaunch_count

    def _attach_disconnect_hook(self, browser: Browser, generation: int) -> None:
        def _on_disconnected(_browser: Browser) -> None:
            logger.warning("Playwright browser disconnected (generation=%s).", generation)

        try:
            browser.once("disconnected", _on_disconnected)
        except Exception:
            pass

    async def start(self) -> Browser:
        return await self.relaunch(reason="startup", force=True)

    async def get_browser(self) -> Browser:
        browser = self._browser
        if self._is_browser_connected(browser):
            return browser  # type: ignore[return-value]
        return await self.relaunch(reason="health_check", force=False)

    async def relaunch(self, *, reason: str, force: bool = False) -> Browser:
        async with self._lock:
            current = self._browser
            if not force and self._is_browser_connected(current):
                return current  # type: ignore[return-value]

            old_browser = self._browser
            self._browser = None
            if old_browser is not None:
                try:
                    await old_browser.close()
                except Exception:
                    pass

            if self._playwright is None:
                self._playwright = await async_playwright().start()

            launch_options = {"headless": self._headless, **self._launch_kwargs}
            new_browser = await self._playwright.chromium.launch(**launch_options)
            self._browser = new_browser
            self._generation += 1
            if reason != "startup":
                self._relaunch_count += 1
            self._attach_disconnect_hook(new_browser, self._generation)

            logger.warning(
                "Playwright browser launched (generation=%s, reason=%s, relaunch_count=%s).",
                self._generation,
                reason,
                self._relaunch_count,
            )
            return new_browser

    async def stop(self) -> None:
        async with self._lock:
            browser = self._browser
            playwright = self._playwright
            self._browser = None
            self._playwright = None

        if browser is not None:
            try:
                await browser.close()
            except Exception:
                pass

        if playwright is not None:
            try:
                await playwright.stop()
            except Exception:
                pass


class ManagedBrowser:
    """Lightweight browser facade that auto-heals through BrowserLifecycleManager."""

    def __init__(self, manager: BrowserLifecycleManager):
        self._manager = manager

    async def new_context(self, *args: Any, **kwargs: Any):
        browser = await self._manager.get_browser()
        return await browser.new_context(*args, **kwargs)

    def is_connected(self) -> bool:
        return self._manager.is_connected()

    async def relaunch(self, *, reason: str = "manual_relaunch"):
        return await self._manager.relaunch(reason=reason, force=True)
