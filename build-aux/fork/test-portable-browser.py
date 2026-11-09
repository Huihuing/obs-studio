"""Verify the Browser Source in a freshly extracted Windows portable OBS build (stdlib only)."""
import argparse
from contextlib import ExitStack
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import shutil
from pathlib import Path
from queue import Empty, Queue
import subprocess
import tempfile
from threading import Thread
import time
from urllib.parse import urlsplit
from uuid import uuid4
from zipfile import ZipFile

SCRIPT = "document.documentElement.dataset.runs = String(Number(document.documentElement.dataset.runs || 0) + 1);"
CASES = ("approved", "imported", "modified", "redirect")
PAGE = """<!doctype html><meta charset=utf-8><title>OBS JavaScript probe</title>
<iframe id="child" src="/child"></iframe>
<script>
addEventListener("load", () => setTimeout(async () => {
  const name = location.pathname.slice(1);
  const phase = Number(sessionStorage.phase || 0);
  const report = { name, phase, main: Number(document.documentElement.dataset.runs || 0),
    child: Number(document.getElementById("child").contentDocument.documentElement.dataset.runs || 0),
    css: getComputedStyle(document.documentElement).getPropertyValue("--ci-obs-css").trim(),
    browser: typeof window.obsstudio?.pluginVersion === "string" };
  const reply = await fetch("/report", { method: "POST", body: JSON.stringify(report) });
  if (reply.ok && name === "approved" && phase === 0) {
    sessionStorage.phase = "1";
    location.reload();
  }
}, 1800));
</script>"""


# Observe the existing extension fixture's title. This page code uses no OBS-injected JavaScript.
EXTENSION_REPORT = r"""<script>
const observer = new MutationObserver(() => {
  const value = /^Content script: (yes|no) \| Worker: (yes|no) \| Network rule: (yes|no)$/.exec(document.title);
  if (!value) return;
  observer.disconnect();
  fetch("/report", { method: "POST", body: JSON.stringify({ name: "extension", phase: 0,
    content: value[1], worker: value[2], dnr: value[3], browser: typeof window.obsstudio?.pluginVersion === "string" }) });
});
observer.observe(document.querySelector("title"), { childList: true, subtree: true, characterData: true });
</script>"""


def loopback(stack, reports, extension_page):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            parts = urlsplit(self.path)
            route = parts.path
            if route == "/redirect-start":
                self.send_response(302)
                self.send_header("Location", self.server.redirect_to)
                self.end_headers()
                return
            if route == "/extension-smoke.html":
                if parts.query in ("network=control", "network=block"):
                    self.server.network_requests.append(parts.query)
                    body = "ok"
                else:
                    body = extension_page
            elif route == "/child":
                body = "<!doctype html><p>child</p>"
            elif route in ("/" + name for name in CASES):
                body = PAGE
            else:
                self.send_error(404)
                return
            data = body.encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_POST(self):
            length = int(self.headers.get("Content-Length", 0))
            if self.path != "/report" or not 0 < length < 2048:
                self.send_error(400)
                return
            reports.put((self.server.server_port, json.loads(self.rfile.read(length))))
            self.send_response(204)
            self.end_headers()

    server = stack.enter_context(ThreadingHTTPServer(("127.0.0.1", 0), Handler))
    server.network_requests = []
    Thread(target=server.serve_forever, daemon=True).start()
    stack.callback(server.shutdown)
    return server


def prepare_profile(config, base):
    def write(relative, value):
        path = config / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(value, encoding="utf-8")

    write("global.ini", "[General]\nBrowserHWAccel=false\nEnableAutoUpdates=false\n")
    write("user.ini", "[General]\nFirstRun=true\n[Basic]\nProfile=Smoke\nProfileDir=Smoke\n"
                      "SceneCollection=Smoke\nSceneCollectionFile=Smoke\n")
    write("basic/profiles/Smoke/basic.ini", "[General]\nName=Smoke\n[Video]\n"
          "BaseCX=640\nBaseCY=360\nOutputCX=640\nOutputCY=360\nFPSCommon=30\n")
    sources, items, approvals = [], [], []
    for i, case in enumerate(CASES, 1):
        uid = str(uuid4())
        target = base + ("/redirect-start" if case == "redirect" else "/" + case)
        settings = {"url": target, "width": 160, "height": 90, "webpage_control_level": 0,
                    "javascript": SCRIPT, "css": ":root { --ci-obs-css: applied; }"}
        if case == "imported":
            settings["_javascript_approval_request"] = "forged-scene-ticket"
        else:
            # Seed exactly one local trust tuple per source. Scene JSON only holds the code.
            digest = hashlib.sha256(b"\0".join(s.encode() for s in ("url", target, "0", SCRIPT))).hexdigest()
            approvals.append(f"{hashlib.sha256(uid.encode()).hexdigest()}=@ByteArray({digest})\n")
        if case == "modified":
            settings["javascript"] += " /* edited after approval */"
        sources.append({"id": "browser_source", "name": case, "uuid": uid, "settings": settings})
        items.append({"name": case, "id": i, "source_uuid": uid, "visible": True,
                      "pos": {"x": (i - 1) * 160, "y": 0}, "scale": {"x": 1, "y": 1}})
    ext_id = str(uuid4())
    sources.append({"id": "browser_source", "name": "extension", "uuid": ext_id, "settings": {
        "url": base + "/extension-smoke.html", "width": 160, "height": 90, "webpage_control_level": 0}})
    items.append({"name": "extension", "id": len(items) + 1, "source_uuid": ext_id, "visible": True,
                  "pos": {"x": 0, "y": 90}, "scale": {"x": 1, "y": 1}})
    sources.append({"id": "scene", "name": "Smoke", "uuid": str(uuid4()),
                    "settings": {"items": items, "id_counter": len(items)}})
    write("basic/scenes/Smoke.json", json.dumps({"name": "Smoke", "version": 2, "sources": sources,
          "scene_order": [{"name": "Smoke"}], "current_scene": "Smoke", "current_program_scene": "Smoke"}))
    write("plugin_config/obs-browser/javascript-approvals.ini", "[General]\n" + "".join(approvals))


def verify(archive, fixture):
    reports = Queue()
    with ExitStack() as stack:
        root = Path(stack.enter_context(tempfile.TemporaryDirectory(prefix="obs-browser-ci-",
                                                                   ignore_cleanup_errors=True)))
        with ZipFile(archive) as package:
            package.extractall(root)
        exe = root / "bin/64bit/obs64.exe"
        config = root / "config/obs-studio"
        if not exe.is_file() or config.exists() or not (root / "portable_mode.txt").is_file():
            raise RuntimeError("Expected a clean, marked portable OBS archive")
        extension = root / "probe extension"
        shutil.copytree(fixture / "extension", extension)
        page = (fixture / "site/extension-smoke.html").read_text(encoding="utf-8")
        page = page.replace("</html>", EXTENSION_REPORT + "</html>")
        first, other = (loopback(stack, reports, page) for _ in range(2))
        first.redirect_to = f"http://127.0.0.1:{other.server_port}/redirect"
        prepare_profile(config, f"http://127.0.0.1:{first.server_port}")
        proc = subprocess.Popen([str(exe), "--portable", "--multi", "--disable-updater",
                                 f"--obs-browser-extension={extension}", "--disable-missing-files-check", "--profile", "Smoke", "--collection", "Smoke"],
                                cwd=exe.parent)
        pending = {("approved", 0), ("approved", 1), *((name, 0) for name in CASES if name != "approved")}
        pending.add(("extension", 0))
        deadline = time.monotonic() + 120
        try:
            while pending:
                if proc.poll() is not None or time.monotonic() >= deadline:
                    raise RuntimeError(f"OBS exit={proc.poll()}. Missing DOM reports: {sorted(pending)}")
                try:
                    port, report = reports.get(timeout=0.5)
                except Empty:
                    continue
                name, phase = report["name"], report["phase"]
                print(f"{name} load {phase}: {report}", flush=True)
                if name == "extension":
                    # A blocked fetch is meaningful only when the control reached our server and the blocked URL did not.
                    if (("extension", phase) not in pending or port != first.server_port or report["browser"] is not True
                            or (report["content"], report["worker"], report["dnr"]) != ("yes", "yes", "yes")
                            or "network=control" not in first.network_requests
                            or "network=block" in first.network_requests):
                        raise RuntimeError(f"Extension check failed: {report}, server saw {first.network_requests}")
                    print(f"Content script: {report['content']}; service worker: {report['worker']}; DNR: yes", flush=True)
                    pending.remove(("extension", phase))
                    continue
                expected_port = other.server_port if name == "redirect" else first.server_port
                if (port != expected_port or (name, phase) not in pending
                        or report["main"] != int(name == "approved") or report["child"] != 0
                        or report["css"] != "applied" or report["browser"] is not True):
                    raise RuntimeError(f"Unexpected browser-source result: {report}, port={port}")
                pending.remove((name, phase))
        except BaseException:
            for log in sorted((config / "logs").glob("*.txt"))[-1:]:
                print(log.read_text(encoding="utf-8-sig", errors="replace")[-18000:], flush=True)
            raise
        finally:
            if proc.poll() is None:
                subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"], timeout=20, check=True)
                proc.wait(timeout=10)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path)
    parser.add_argument("--fixture", type=Path, default=Path(__file__).resolve().parents[2] /
                        "plugins/obs-browser/tests/extension-smoke")
    args = parser.parse_args()
    verify(args.archive, args.fixture)
