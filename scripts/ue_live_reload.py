#!/usr/bin/env python3
"""Recompile and hot-reload the project's C++ gameplay modules into the running editor.

Usage:  python3 Scripts/live_reload.py [--status]
        (shared install: python3 ~/"Documents/Unreal Projects/_Shared/ue_live_reload.py")

Requires the editor to be running with the Unreal MCP server up (Auto Start Server).
Only function-body changes in .cpp files can be applied this way; header, UCLASS /
USTRUCT / UFUNCTION / UPROPERTY and class-layout changes need a full build and an
editor restart.

Env: UNREAL_MCP_URL overrides the endpoint (default http://127.0.0.1:8000/mcp).
"""
import json
import os
import sys
import urllib.request

URL = os.environ.get("UNREAL_MCP_URL", "http://127.0.0.1:8000/mcp")


class Client:
    def __init__(self, url=URL):
        self.url = url
        self.sid = None

    def _post(self, payload):
        req = urllib.request.Request(self.url, data=json.dumps(payload).encode(), method="POST")
        req.add_header("Content-Type", "application/json")
        req.add_header("Accept", "application/json, text/event-stream")
        if self.sid:
            req.add_header("Mcp-Session-Id", self.sid)
        with urllib.request.urlopen(req, timeout=600) as r:
            sid = r.headers.get("Mcp-Session-Id")
            if sid:
                self.sid = sid
            raw = r.read().decode()
        if raw.startswith(("event:", "data:")):
            raw = "\n".join(line[5:].strip() for line in raw.splitlines() if line.startswith("data:"))
        return json.loads(raw) if raw.strip() else None

    def connect(self):
        self._post({
            "jsonrpc": "2.0", "id": 1, "method": "initialize",
            "params": {"protocolVersion": "2025-03-26", "capabilities": {},
                       "clientInfo": {"name": "live_reload", "version": "1"}},
        })
        self._post({"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}})
        return self

    def _tool(self, name, arguments):
        resp = self._post({
            "jsonrpc": "2.0", "id": 1, "method": "tools/call",
            "params": {"name": name, "arguments": arguments},
        })
        if resp is None:
            return ""
        if (resp.get("result") or {}).get("isError"):
            raise RuntimeError(text(resp))
        return text(resp)

    def call(self, toolset, tool, **args):
        out = self._tool("call_tool", {"toolset_name": toolset, "tool_name": tool, "arguments": args})
        try:
            return json.loads(out).get("returnValue")
        except (ValueError, AttributeError):
            return out

    def toolsets(self):
        return self._tool("list_toolsets", {})


def text(resp):
    content = (resp.get("result") or {}).get("content") or []
    return "\n".join(part.get("text", "") for part in content)


def find_toolset(client):
    for line in client.toolsets().splitlines():
        if "livereload" in line.lower():
            return line.split(":", 1)[0].lstrip("- ").strip()
    return None


def main():
    status_only = "--status" in sys.argv[1:]
    client = Client().connect()

    toolset = find_toolset(client)
    if not toolset:
        print("LiveReload toolset not found - is the LiveReload plugin enabled and the editor restarted?")
        return 2

    tool = "GetLiveReloadStatus" if status_only else "ReloadGameCode"
    result = client.call(toolset, tool)
    print(result)
    if status_only:
        return 0
    return 0 if result and "FAILED" not in result and not result.startswith("Error") and not result.startswith("Refused") else 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        print("live_reload failed: %s" % exc)
        sys.exit(2)
