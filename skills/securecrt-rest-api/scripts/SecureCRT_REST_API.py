# $language = "Python3"
# $interface = "1.0"

"""Local REST API for all tabs in the SecureCRT window.

The script is intentionally bound to 127.0.0.1.  It uses SecureCRT's scripting
API on the script thread, which avoids calling SecureCRT COM objects from an
HTTP worker thread.
"""

import json
import os
import socket
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlparse


DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 19191
MAX_BODY_BYTES = 64 * 1024


class ApiError(Exception):
    def __init__(self, status, message):
        Exception.__init__(self, message)
        self.status = status
        self.message = message


def _as_text(value):
    if isinstance(value, bytes):
        return value.decode("utf-8", "replace")
    return str(value)


def _json_bytes(value):
    """Serialize JSON as UTF-8 bytes for the HTTP server."""
    text = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    return text.encode("utf-8")


def _int_query(query, name, default):
    values = query.get(name)
    if not values:
        return default
    try:
        return int(values[0])
    except (TypeError, ValueError):
        raise ApiError(400, "query parameter '%s' must be an integer" % name)


class RestServer(HTTPServer):
    allow_reuse_address = True

    def __init__(self, address, handler, controller):
        HTTPServer.__init__(self, address, handler)
        self.controller = controller
        self.stop_requested = False
        self.timeout = 0.25


class RestHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, format_string, *args):
        # SecureCRT has no useful stdout for a long-running script.
        pass

    def _write(self, status, payload):
        data = _json_bytes(payload)
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(data)

    def _error(self, status, message):
        self._write(status, {"ok": False, "error": message})

    def _read_json(self):
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            raise ApiError(400, "invalid Content-Length")
        if length > MAX_BODY_BYTES:
            raise ApiError(413, "request body is too large")
        raw = self.rfile.read(length)
        try:
            text = raw.decode("utf-8")
            value = json.loads(text)
        except (UnicodeDecodeError, ValueError):
            raise ApiError(400, "request body must be UTF-8 JSON")
        if not isinstance(value, dict):
            raise ApiError(400, "request body must be a JSON object")
        return value

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Content-Length", "0")
        self.send_header("Connection", "close")
        self.end_headers()

    def do_GET(self):
        try:
            parsed = urlparse(self.path)
            query = parse_qs(parsed.query)
            if parsed.path == "/api/v1/health":
                tab_number = _int_query(query, "tab", None)
                tab = self.server.controller.resolve_tab(tab_number)
                self._write(200, self.server.controller.health(tab, tab_number))
                return
            if parsed.path == "/api/v1/tabs":
                self._write(200, self.server.controller.list_tabs())
                return
            if parsed.path == "/api/v1/screen":
                tab_number = _int_query(query, "tab", None)
                tab = self.server.controller.resolve_tab(tab_number)
                row_start = _int_query(query, "row_start", 1)
                row_end = _int_query(query, "row_end", None)
                self._write(200, self.server.controller.read_screen(
                    tab, row_start, row_end, tab_number))
                return
            if parsed.path == "/api/v1/output":
                tab_number = _int_query(query, "tab", None)
                tab = self.server.controller.resolve_tab(tab_number)
                self._write(200, self.server.controller.read_output(tab, tab_number))
                return
            self._error(404, "unknown endpoint")
        except ApiError as error:
            self._error(error.status, error.message)
        except Exception as error:
            self._error(500, str(error))

    def do_POST(self):
        try:
            parsed = urlparse(self.path)
            if parsed.path == "/api/v1/clear":
                query = parse_qs(parsed.query)
                tab_number = _int_query(query, "tab", None)
                tab = self.server.controller.resolve_tab(tab_number)
                result = self.server.controller.clear_screen(tab, tab_number)
                self._write(200, result)
                return
            if parsed.path == "/api/v1/input":
                result = self.server.controller.send_input(self._read_json())
                self._write(200, result)
                return
            if parsed.path == "/api/v1/stop":
                self.server.stop_requested = True
                self._write(200, {"ok": True, "stopping": True})
                return
            self._error(404, "unknown endpoint")
        except ApiError as error:
            self._error(error.status, error.message)
        except Exception as error:
            self._error(500, str(error))


class Controller(object):
    def __init__(self, crt_object, script_tab):
        self.crt = crt_object
        self.script_tab = script_tab

    def resolve_tab(self, tab_number=None):
        if tab_number is None:
            return self.script_tab
        count = int(self.crt.GetTabCount())
        if tab_number < 1 or tab_number > count:
            raise ApiError(404, "tab index %d does not exist" % tab_number)
        return self.crt.GetTab(tab_number)

    def list_tabs(self):
        tabs = []
        count = int(self.crt.GetTabCount())
        for index in range(1, count + 1):
            tab = self.crt.GetTab(index)
            tabs.append({
                "tab": index,
                "connected": bool(tab.Session.Connected),
            })
        return {"ok": True, "count": len(tabs), "tabs": tabs}

    def health(self, tab, tab_number=None):
        return {
            "ok": True,
            "service": "securecrt-rest-api",
            "tab": tab_number,
            "connected": bool(tab.Session.Connected),
        }

    def read_screen(self, tab, row_start=1, row_end=None, tab_number=None):
        if not bool(tab.Session.Connected):
            raise ApiError(409, "the SecureCRT tab is not connected")
        screen = tab.Screen
        rows = int(screen.Rows)
        columns = int(screen.Columns)
        if row_end is None:
            row_end = rows
        if row_start < 1 or row_end < row_start or row_end > rows:
            raise ApiError(400, "row range is outside the visible screen")
        try:
            text = screen.Get2(row_start, 1, row_end, columns)
        except Exception:
            text = screen.Get(row_start, 1, row_end, columns)
        return {
            "ok": True,
            "scope": "visible_screen",
            "tab": tab_number,
            "text": _as_text(text),
            "row_start": row_start,
            "row_end": row_end,
            "rows": rows,
            "columns": columns,
            "current_row": int(screen.CurrentRow),
            "current_column": int(screen.CurrentColumn),
        }

    def read_output(self, tab, tab_number=None):
        if not bool(tab.Session.Connected):
            raise ApiError(409, "the SecureCRT tab is not connected")
        # Selecting scrollback is a UI operation, so activate the requested
        # tab before using MENU_SELECT_ALL.
        tab.Activate()
        screen = tab.Screen
        screen.SendSpecial("MENU_SELECT_ALL")
        return {
            "ok": True,
            "scope": "screen_and_scrollback",
            "tab": tab_number,
            "text": _as_text(screen.Selection),
        }

    def clear_screen(self, tab, tab_number=None):
        if not bool(tab.Session.Connected):
            raise ApiError(409, "the SecureCRT tab is not connected")
        tab.Screen.Clear()
        return {"ok": True, "tab": tab_number}

    def send_input(self, payload):
        tab_number = payload.get("tab")
        if tab_number is not None:
            if isinstance(tab_number, bool):
                raise ApiError(400, "'tab' must be an integer")
            try:
                tab_number = int(tab_number)
            except (TypeError, ValueError):
                raise ApiError(400, "'tab' must be an integer")
        tab = self.resolve_tab(tab_number)
        if not bool(tab.Session.Connected):
            raise ApiError(409, "the SecureCRT tab is not connected")
        text = payload.get("text")
        if not isinstance(text, str):
            raise ApiError(400, "'text' must be a string")
        if len(text) > MAX_BODY_BYTES:
            raise ApiError(413, "input text is too long")
        if payload.get("append_enter", False):
            text += "\r"
        tab.Screen.Send(text)
        return {"ok": True, "tab": tab_number, "sent_length": len(text)}


def _get_port():
    value = os.environ.get("SECURECRT_API_PORT", str(DEFAULT_PORT))
    try:
        port = int(value)
    except ValueError:
        raise ValueError("SECURECRT_API_PORT must be an integer")
    if port < 1 or port > 65535:
        raise ValueError("SECURECRT_API_PORT must be between 1 and 65535")
    return port


def Main():
    tab = crt.GetScriptTab()
    try:
        port = _get_port()
    except ValueError as error:
        crt.Dialog.MessageBox(str(error))
        return
    controller = Controller(crt, tab)
    try:
        server = RestServer((DEFAULT_HOST, port), RestHandler, controller)
    except socket.error as error:
        crt.Dialog.MessageBox("Could not bind 127.0.0.1:%d\n\n%s" % (port, error))
        return

    crt.Dialog.MessageBox(
        "SecureCRT REST API is listening on http://127.0.0.1:%d\n\n"
        "Use GET /api/v1/tabs to list tabs, then pass tab=<index> "
        "to control any tab.\n\n"
        "The service is intentionally limited to this computer." % port)

    try:
        while not server.stop_requested:
            server.handle_request()
            crt.Sleep(50)
    finally:
        server.server_close()


Main()
