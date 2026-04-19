from __future__ import annotations

import argparse
import os
import sys
from typing import Any


def _load_fastmcp():
    try:
        from mcp.server.fastmcp import FastMCP  # type: ignore
        return FastMCP
    except ModuleNotFoundError:
        vendor_dir = os.path.join(os.path.dirname(__file__), "temp", "vendor")
        if os.path.isdir(vendor_dir) and vendor_dir not in sys.path:
            sys.path.insert(0, vendor_dir)
            from mcp.server.fastmcp import FastMCP  # type: ignore
            return FastMCP
        raise


FastMCP = _load_fastmcp()

import ga


def _error(message: str) -> dict[str, Any]:
    return {"status": "error", "msg": message}


def _session_view(session: dict[str, Any], active_tab: Any) -> dict[str, Any]:
    return {
        "id": session.get("id"),
        "title": session.get("title", ""),
        "url": session.get("url", ""),
        "active": session.get("id") == active_tab,
    }


def _ensure_driver() -> tuple[Any, list[dict[str, Any]]]:
    if ga.driver is None:
        ga.first_init_driver()
    driver = ga.driver
    if driver is None:
        raise RuntimeError("TMWebDriver 初始化失败。请先执行 web setup sop，确认浏览器扩展已连接。")
    sessions = driver.get_all_sessions()
    if not sessions:
        raise RuntimeError("没有可用的浏览器标签页。请先打开已接入 TMWebDriver 的浏览器页面。")
    if getattr(driver, "default_session_id", None) is None:
        driver.default_session_id = sessions[0]["id"]
    return driver, sessions


def _normalize_tab_id(tab_id: Any) -> Any:
    if tab_id in (None, ""):
        return None
    if isinstance(tab_id, str) and tab_id.isdigit():
        return int(tab_id)
    return tab_id


def _list_tabs_payload(driver: Any, sessions: list[dict[str, Any]]) -> dict[str, Any]:
    active_tab = getattr(driver, "default_session_id", None)
    return {
        "status": "success",
        "active_tab": active_tab,
        "tabs": [_session_view(session, active_tab) for session in sessions],
    }


server = FastMCP(
    name="genericagent-browser",
    instructions=(
        "Expose GenericAgent browser automation over MCP. "
        "Requires GenericAgent web tools to be unlocked and TMWebDriver-connected tabs to exist."
    ),
    host=os.getenv("MCP_HOST", "127.0.0.1"),
    port=int(os.getenv("MCP_PORT", "8000")),
)


@server.tool(name="list_tabs", description="List active TMWebDriver browser tabs.")
def list_tabs() -> dict[str, Any]:
    try:
        driver, sessions = _ensure_driver()
        return _list_tabs_payload(driver, sessions)
    except Exception as exc:
        return _error(str(exc))


@server.tool(
    name="select_tab",
    description="Select the active browser tab by exact tab id or by matching url substring.",
)
def select_tab(tab_id: str | int | None = None, url_pattern: str | None = None) -> dict[str, Any]:
    try:
        driver, sessions = _ensure_driver()
        normalized_tab_id = _normalize_tab_id(tab_id)

        if normalized_tab_id is None and not url_pattern:
            return _error("请提供 tab_id 或 url_pattern 之一。")

        selected = None
        if normalized_tab_id is not None:
            for session in sessions:
                if str(session.get("id")) == str(normalized_tab_id):
                    selected = session
                    break
            if selected is None:
                return _error(f"未找到 tab_id={tab_id} 对应的标签页。")
        else:
            matched = [session for session in sessions if url_pattern in session.get("url", "")]
            if not matched:
                return _error(f"未找到 URL 包含 {url_pattern!r} 的标签页。")
            selected = matched[0]

        driver.default_session_id = selected["id"]
        return {
            "status": "success",
            "active_tab": driver.default_session_id,
            "tab": _session_view(selected, driver.default_session_id),
        }
    except Exception as exc:
        return _error(str(exc))


@server.tool(name="new_tab", description="Open a new browser tab, optionally with a target URL.")
def new_tab(url: str | None = None) -> dict[str, Any]:
    try:
        driver, _ = _ensure_driver()
        result = driver.newtab(url)
        sessions = driver.get_all_sessions()
        payload = _list_tabs_payload(driver, sessions)
        payload["result"] = result
        return payload
    except Exception as exc:
        return _error(str(exc))


@server.tool(
    name="scan_page",
    description="Return simplified page content and/or current tab metadata via ga.web_scan.",
)
def scan_page(
    tabs_only: bool = False,
    switch_tab_id: str | int | None = None,
    text_only: bool = False,
) -> dict[str, Any]:
    normalized_tab_id = _normalize_tab_id(switch_tab_id)
    return ga.web_scan(
        tabs_only=tabs_only,
        switch_tab_id=normalized_tab_id,
        text_only=text_only,
    )


@server.tool(
    name="execute_js",
    description="Execute JavaScript in the active browser tab via ga.web_execute_js.",
)
def execute_js(
    script: str,
    switch_tab_id: str | int | None = None,
    no_monitor: bool = False,
) -> dict[str, Any]:
    if not script.strip():
        return _error("script 不能为空。")
    normalized_tab_id = _normalize_tab_id(switch_tab_id)
    return ga.web_execute_js(
        script=script,
        switch_tab_id=normalized_tab_id,
        no_monitor=no_monitor,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="GenericAgent browser MCP server.")
    parser.add_argument(
        "--transport",
        choices=("stdio", "sse", "streamable-http"),
        default=os.getenv("MCP_TRANSPORT", "stdio"),
        help="MCP transport to use. Defaults to stdio.",
    )
    args = parser.parse_args()
    server.run(args.transport)


if __name__ == "__main__":
    main()