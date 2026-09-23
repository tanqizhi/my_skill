"""Smoke-test SecureCRT_REST_API.py without a SecureCRT install.

The API script only needs a `crt` object; this harness supplies a stub, runs the
script in a child process, and asserts the full HTTP contract of every endpoint.

Usage:
    python3 smoke_test.py [path/to/SecureCRT_REST_API.py]

Exit code 0 = all checks passed. Nothing is installed and no SecureCRT is needed.
"""

import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_SCRIPT = os.path.join(HERE, "SecureCRT_REST_API.py")
PORT = int(os.environ.get("SECURECRT_SMOKE_PORT", "19199"))
BASE = "http://127.0.0.1:%d" % PORT
CALL_LOG = os.path.join(HERE, "_smoke_calls.log")

# ---------------------------------------------------------------- stub server


def serve(script_path):
    """Run the SecureCRT API script with a stubbed `crt` object (child process)."""
    import time as _time

    calls = []

    class FakeSession:
        Connected = True

    class FakeScreen:
        Rows = 24
        Columns = 80
        CurrentRow = 5
        CurrentColumn = 1
        Selection = "SELECTION-TEXT"

        def Get2(self, r1, c1, r2, c2):
            return "GET2 row %s..%s" % (r1, r2)

        def Get(self, r1, c1, r2, c2):
            return "GET row %s..%s" % (r1, r2)

        def Send(self, text):
            calls.append(("send", text))

        def Clear(self):
            calls.append(("clear", None))

        def SendSpecial(self, name):
            calls.append(("special", name))

    class FakeTab:
        def __init__(self, index):
            self.index = index
            self.Screen = FakeScreen()
            self.Session = FakeSession()

        def Activate(self):
            calls.append(("activate", self.index))

    class FakeDialog:
        @staticmethod
        def MessageBox(message):
            print("[DIALOG] " + message.replace("\n", " | "), flush=True)

    class FakeCrt:
        Dialog = FakeDialog()

        def __init__(self, tabs=3):
            self.tabs = [FakeTab(i) for i in range(1, tabs + 1)]

        def GetScriptTab(self):
            return self.tabs[0]

        def GetTabCount(self):
            return len(self.tabs)

        def GetTab(self, number):
            return self.tabs[number - 1]

        def Sleep(self, milliseconds):
            _time.sleep(milliseconds / 1000.0)

    with open(script_path, "r", encoding="utf-8") as handle:
        source = handle.read()
    try:
        exec(compile(source, script_path, "exec"),
             {"__name__": "__main__", "crt": FakeCrt()})
    finally:
        with open(CALL_LOG, "w", encoding="utf-8") as handle:
            for entry in calls:
                handle.write(repr(entry) + "\n")


# ---------------------------------------------------------------- HTTP client


def request(method, path, body=None):
    data = None
    if body is not None:
        data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(BASE + path, data=data, method=method)
    if data is not None:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=5) as response:
            return response.status, json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        return error.code, json.loads(error.read().decode("utf-8"))


def wait_for_port(deadline=8.0):
    start = time.time()
    while time.time() - start < deadline:
        try:
            status, _ = request("GET", "/api/v1/health")
            if status == 200:
                return True
        except Exception:
            pass
        time.sleep(0.15)
    return False


# ---------------------------------------------------------------- assertions

RESULTS = []


def check(name, condition, detail=""):
    RESULTS.append((name, bool(condition), detail))
    print("%-4s %s%s" % ("PASS" if condition else "FAIL", name,
                         "" if condition else "  <- " + str(detail)))


def run_checks():
    status, body = request("GET", "/api/v1/tabs")
    check("GET /tabs -> 200", status == 200, status)
    check("GET /tabs count/tabs", body.get("count") == 3 and len(body.get("tabs", [])) == 3, body)

    status, body = request("GET", "/api/v1/health")
    check("GET /health -> 200 + connected",
          status == 200 and body.get("connected") is True and body.get("tab") is None, body)

    status, body = request("GET", "/api/v1/screen?tab=2")
    check("GET /screen?tab=2 -> visible_screen",
          status == 200 and body.get("scope") == "visible_screen"
          and body.get("rows") == 24 and body.get("columns") == 80, body)
    check("GET /screen?tab=2 echoes tab", body.get("tab") == 2, body)

    status, body = request("GET", "/api/v1/output")
    check("GET /output -> screen_and_scrollback",
          status == 200 and body.get("scope") == "screen_and_scrollback"
          and body.get("text") == "SELECTION-TEXT", body)

    status, body = request("POST", "/api/v1/input",
                           {"tab": 2, "text": "show version", "append_enter": True})
    check("POST /input append_enter adds CR",
          status == 200 and body.get("sent_length") == len("show version") + 1, body)

    status, body = request("POST", "/api/v1/input", {"text": "ping 1.1.1.1"})
    check("POST /input without tab uses script tab",
          status == 200 and body.get("tab") is None
          and body.get("sent_length") == len("ping 1.1.1.1"), body)

    status, body = request("GET", "/api/v1/screen?tab=99")
    check("tab out of range -> 404", status == 404 and body.get("ok") is False, (status, body))

    status, body = request("POST", "/api/v1/input", {"tab": True, "text": "x"})
    check("boolean tab rejected -> 400", status == 400 and body.get("ok") is False, (status, body))

    status, body = request("POST", "/api/v1/input", {"tab": 2})
    check("missing text rejected -> 400", status == 400 and body.get("ok") is False, (status, body))

    status, body = request("GET", "/api/v1/screen?row_start=30&row_end=40")
    check("bad row range -> 400", status == 400 and body.get("ok") is False, (status, body))

    status, body = request("GET", "/api/v1/does-not-exist")
    check("unknown endpoint -> 404", status == 404 and body.get("ok") is False, (status, body))

    status, body = request("POST", "/api/v1/clear?tab=1")
    check("POST /clear?tab=1 -> ok", status == 200 and body.get("ok") is True, body)

    # raw non-JSON body must be rejected with 400
    req = urllib.request.Request(BASE + "/api/v1/input", data=b"not-json", method="POST")
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=5) as response:
            status, body = response.status, json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        status, body = error.code, json.loads(error.read().decode("utf-8"))
    check("non-JSON body -> 400", status == 400 and body.get("ok") is False, (status, body))

    status, body = request("POST", "/api/v1/stop")
    check("POST /stop -> stopping", status == 200 and body.get("stopping") is True, body)


def check_call_log():
    try:
        with open(CALL_LOG, "r", encoding="utf-8") as handle:
            log = handle.read()
    except OSError as error:
        check("call log captured", False, error)
        return
    check("stub saw CR-terminated send", "('send', 'show version\\r')" in log, log)
    check("stub saw raw send without CR", "('send', 'ping 1.1.1.1')" in log, log)
    check("output selected scrollback",
          "('activate', 1)" in log and "('special', 'MENU_SELECT_ALL')" in log, log)
    check("clear reached the screen", "('clear', None)" in log, log)


def main():
    script = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_SCRIPT
    if not os.path.isfile(script):
        print("script not found: %s" % script)
        return 2
    env = dict(os.environ, SECURECRT_API_PORT=str(PORT))
    child = subprocess.Popen([sys.executable, os.path.abspath(__file__), "--serve", script],
                             env=env, stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)
    try:
        if not wait_for_port():
            print("FAIL listener never came up on port %d" % PORT)
            return 1
        run_checks()
        time.sleep(0.4)
        check_call_log()
    finally:
        if child.poll() is None:
            try:
                request("POST", "/api/v1/stop")
            except Exception:
                pass
            time.sleep(0.4)
            if child.poll() is None:
                child.terminate()
        child.wait(timeout=5)
    failed = [name for name, ok, _ in RESULTS if not ok]
    print("\n%d checks, %d failed" % (len(RESULTS), len(failed)))
    return 1 if failed else 0


if __name__ == "__main__":
    if len(sys.argv) > 2 and sys.argv[1] == "--serve":
        serve(sys.argv[2])
    else:
        sys.exit(main())
