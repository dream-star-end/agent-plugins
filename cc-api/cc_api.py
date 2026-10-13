#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
cc-api: Anthropic-compatible API shell around a persistent Claude Code session.

What it is
----------
A thin "shell" (壳) around the `claude` CLI. Inside the shell lives a real,
stateful Claude Code interactive session (same session engine + on-disk
transcript as the TUI; multi-turn via --resume; resumable from the TUI with
`claude --resume <session-id>`). The shell translates the Anthropic Messages
API into turns of that session and streams the results back as Anthropic SSE.

Upgrade-safety contract (不影响壳内 cc 升级)
--------------------------------------------
* Only public CLI surface is used: -p/--print, --verbose,
  --output-format stream-json, --session-id, --resume, --model,
  --append-system-prompt, --plugin-dir, --max-budget-usd, --mcp-config,
  --add-dir.  No binary patching, no private-protocol stdio driving
  (the persistent `--input-format stream-json` control protocol is marked
  SDK-internal by upstream and is deliberately NOT used), no writes to
  Claude Code's private state files.
* `claude` is located via PATH at runtime (`shutil.which`), never hardcoded.
* `cc-api doctor` validates the installed version: binary presence, required
  flags still advertised in `--help`, and the stream-json envelope shape via
  a credential-free probe. Run it after every `claude update`.

Reverse-engineering notes (REA)
-------------------------------
* REA 6.4.0 `rea doctor`: no disassembler provider in this environment
  (no Hopper/Ghidra/IDA), so analysis was static string/context extraction
  from the Bun-compiled single-file binary
  (`/usr/lib/node_modules/@anthropic-ai/claude-code/bin/claude.exe`).
* Findings used by this shell:
  - "mods" are UI/interactive extensions shipped as plugins; a mod folder
    loads into a session via the PUBLIC `--plugin-dir <dir>` flag or the
    `CLAUDE_CODE_PLUGIN_DIRS` env var (per the embedded cc-plugin-mods-guide).
    The shell exposes this as `mods_dirs` in its config.
  - `-p --output-format stream-json` REQUIRES `--verbose`.
  - The multi-turn stdio control protocol (`--input-format stream-json` +
    `--await-initialize`) is SDK-internal; avoided for upgrade safety.
  - stream-json envelope (verified live with a credential-free probe):
    {"type":"system","subtype":"init",...},
    {"type":"assistant","message":{...},"session_id":...},
    {"type":"result","subtype":"success","result":"...",...}.

Stdlib only. No third-party dependencies.
"""

import argparse
import json
import os
import queue
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import urllib.parse
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

VERSION = "0.1.0"
DEFAULT_PORT = 8765
DEFAULT_HOST = "127.0.0.1"
CONFIG_DIR = os.path.expanduser("~/.ccshell")
CONFIG_PATH = os.path.join(CONFIG_DIR, "config.json")
SESSIONS_PATH = os.path.join(CONFIG_DIR, "sessions.json")

# Public CLI flags the shell depends on. doctor verifies each is still
# advertised by `claude --help` after upgrades.
REQUIRED_FLAGS = [
    "--session-id", "--resume", "--output-format", "--plugin-dir",
    "--verbose", "--model", "--append-system-prompt", "--max-budget-usd",
    "--mcp-config", "--add-dir",
]

DEFAULT_CONFIG = {
    "host": DEFAULT_HOST,
    "port": DEFAULT_PORT,
    "api_key": "",              # empty = no auth (bind to 127.0.0.1 only then)
    "default_model": "",        # empty = let claude decide; request model passed through
    "models": ["opus", "sonnet", "haiku"],  # advertised by GET /v1/models
    "mods_dirs": [],            # folders loaded via --plugin-dir (cc "mods")
    "workdir": os.path.join(CONFIG_DIR, "work"),
    "turn_timeout_s": 1800,
    "permission_mode": "",      # e.g. "plan"; empty = claude default
    "max_budget_usd": 0,        # 0 = no cap; passed as --max-budget-usd
    "mcp_config": "",           # path or JSON string for --mcp-config
    "add_dirs": [],             # extra dirs for --add-dir
}


# --------------------------------------------------------------------------- #
# config / session store
# --------------------------------------------------------------------------- #

_store_lock = threading.Lock()


def ensure_dirs():
    os.makedirs(CONFIG_DIR, exist_ok=True)
    cfg = load_config()
    os.makedirs(cfg.get("workdir") or os.path.join(CONFIG_DIR, "work"), exist_ok=True)


def load_config():
    cfg = dict(DEFAULT_CONFIG)
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            user = json.load(f)
        if isinstance(user, dict):
            cfg.update(user)
    except (FileNotFoundError, json.JSONDecodeError):
        pass
    return cfg


def save_config(cfg):
    ensure_dirs()
    tmp = CONFIG_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)
    os.replace(tmp, CONFIG_PATH)


def load_sessions():
    with _store_lock:
        try:
            with open(SESSIONS_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data if isinstance(data, dict) else {}
        except (FileNotFoundError, json.JSONDecodeError):
            return {}


def save_sessions(sessions):
    with _store_lock:
        ensure_dirs()
        tmp = SESSIONS_PATH + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(sessions, f, ensure_ascii=False, indent=2)
        os.replace(tmp, SESSIONS_PATH)


_session_locks = {}
_session_locks_guard = threading.Lock()


def session_lock(name):
    with _session_locks_guard:
        return _session_locks.setdefault(name, threading.Lock())


def get_or_create_session(name, cfg):
    """Return (session_dict, is_new). session_dict has cc_session_id (uuid)."""
    sessions = load_sessions()
    s = sessions.get(name)
    if s and s.get("cc_session_id"):
        s["last_active"] = time.time()
        save_sessions(sessions)
        return s, False
    s = {
        "cc_session_id": str(uuid.uuid4()),
        "created_at": time.time(),
        "last_active": time.time(),
        "turns": 0,
        "model": cfg.get("default_model") or "",
    }
    sessions[name] = s
    save_sessions(sessions)
    return s, True


# --------------------------------------------------------------------------- #
# claude runner
# --------------------------------------------------------------------------- #

class ShellError(Exception):
    """Maps to an Anthropic-style error response."""
    def __init__(self, http_status, err_type, message):
        super().__init__(message)
        self.http_status = http_status
        self.err_type = err_type
        self.message = message


def find_claude():
    return shutil.which("claude")


def claude_version(claude_bin):
    try:
        p = subprocess.run([claude_bin, "--version"], capture_output=True,
                           text=True, timeout=30)
        m = re.search(r"(\d+\.\d+\.\d+)", p.stdout or "")
        return m.group(1) if m else (p.stdout or "").strip()
    except Exception as e:
        return "error: %s" % e


def build_argv(claude_bin, sess, prompt, req, cfg, first_turn):
    # NOTE (verified 2026-10-14 against claude 2.1.296): --session-id may only
    # be combined with --resume/--continue together with --fork-session, so a
    # resume turn passes ONLY --resume <id>; the id pins the session.
    argv = [claude_bin, "-p", "--verbose", "--output-format", "stream-json"]
    if first_turn:
        argv += ["--session-id", sess["cc_session_id"]]
    else:
        argv += ["--resume", sess["cc_session_id"]]
    model = req.get("model") or cfg.get("default_model") or sess.get("model") or ""
    if model:
        argv += ["--model", model]
    if first_turn:
        system = req.get("system")
        stext = render_system(system)
        if stext:
            # append: keep claude's own agentic system prompt intact
            argv += ["--append-system-prompt", stext]
        for d in cfg.get("mods_dirs") or []:
            argv += ["--plugin-dir", d]
        if cfg.get("mcp_config"):
            argv += ["--mcp-config", cfg["mcp_config"]]
        for d in cfg.get("add_dirs") or []:
            argv += ["--add-dir", d]
        if cfg.get("permission_mode"):
            argv += ["--permission-mode", cfg["permission_mode"]]
    if cfg.get("max_budget_usd"):
        argv += ["--max-budget-usd", str(cfg["max_budget_usd"])]
    argv.append(prompt)
    return argv


def render_system(system):
    if not system:
        return ""
    if isinstance(system, str):
        return system
    if isinstance(system, list):
        parts = []
        for b in system:
            if isinstance(b, dict) and b.get("type") == "text":
                parts.append(b.get("text", ""))
            elif isinstance(b, str):
                parts.append(b)
        return "\n\n".join(p for p in parts if p)
    return ""


def extract_user_text(messages):
    """v1: only the LAST message must be a user message with text blocks."""
    if not isinstance(messages, list) or not messages:
        raise ShellError(400, "invalid_request_error", "messages must be a non-empty array")
    last = messages[-1]
    if not isinstance(last, dict) or last.get("role") != "user":
        raise ShellError(400, "invalid_request_error",
                         "cc-api v1: the last message must have role 'user'")
    texts = []
    content = last.get("content", "")
    blocks = content if isinstance(content, list) else [{"type": "text", "text": content}]
    for b in blocks:
        if isinstance(b, dict) and b.get("type") == "text":
            texts.append(b.get("text", ""))
        elif isinstance(b, str):
            texts.append(b)
        elif isinstance(b, dict):
            raise ShellError(400, "invalid_request_error",
                             "cc-api v1: only text content blocks are supported, got '%s'"
                             % b.get("type"))
    text = "\n\n".join(t for t in texts if t).strip()
    if not text:
        raise ShellError(400, "invalid_request_error", "last user message has no text")
    return text


def check_tools_unsupported(req):
    if req.get("tools"):
        raise ShellError(
            400, "invalid_request_error",
            "cc-api v1 does not support client-executed tools: the wrapped Claude Code "
            "session executes its own tools (Bash/Read/Edit/Write/... plus loaded mods) "
            "server-side. Send text-only requests; the session's tool activity is part "
            "of its transcript.")
    if req.get("tool_choice"):
        raise ShellError(400, "invalid_request_error",
                         "cc-api v1: tool_choice is not supported (no client tools).")


def run_turn(claude_bin, argv, workdir, timeout_s):
    """Run one turn. Yields parsed stream-json envelope dicts.

    Raises ShellError on spawn failure / timeout. Non-zero exit is NOT
    necessarily an error (claude reports API errors inside the envelope).
    """
    try:
        proc = subprocess.Popen(
            argv, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, text=True, bufsize=1, cwd=workdir)
    except FileNotFoundError:
        raise ShellError(500, "api_error", "claude binary not found at %s" % claude_bin)
    except Exception as e:
        raise ShellError(500, "api_error", "failed to spawn claude: %s" % e)

    q = queue.Queue()

    def pump(stream, kind):
        try:
            for line in stream:
                q.put((kind, line))
        finally:
            q.put((kind, None))

    threading.Thread(target=pump, args=(proc.stdout, "out"), daemon=True).start()
    threading.Thread(target=pump, args=(proc.stderr, "err"), daemon=True).start()

    stderr_tail = []
    outs_done = errs_done = False
    deadline = time.time() + timeout_s
    exit_code = None
    try:
        while True:
            remaining = deadline - time.time()
            if remaining <= 0:
                proc.kill()
                raise ShellError(504, "api_error",
                                 "turn timed out after %ss" % timeout_s)
            try:
                kind, line = q.get(timeout=min(remaining, 1.0))
            except queue.Empty:
                if proc.poll() is not None and outs_done and errs_done:
                    break
                continue
            if kind == "out":
                if line is None:
                    outs_done = True
                else:
                    line = line.strip()
                    if line:
                        try:
                            yield json.loads(line)
                        except json.JSONDecodeError:
                            yield {"type": "_raw", "line": line}
            else:
                if line is None:
                    errs_done = True
                elif line.strip():
                    stderr_tail.append(line.strip()[-500:])
                    if len(stderr_tail) > 20:
                        stderr_tail.pop(0)
            if outs_done and errs_done:
                break
            if proc.poll() is not None and q.empty():
                # process exited; drain quickly then stop
                try:
                    while True:
                        kind, line = q.get_nowait()
                        if kind == "out" and line:
                            line = line.strip()
                            if line:
                                try:
                                    yield json.loads(line)
                                except json.JSONDecodeError:
                                    yield {"type": "_raw", "line": line}
                except queue.Empty:
                    pass
                break
        exit_code = proc.wait(timeout=10)
    finally:
        if proc.poll() is None:
            proc.kill()
    if exit_code not in (0, None):
        # claude usually reports errors inside the envelope; a hard crash is rare
        detail = " ".join(stderr_tail[-5:])
        raise ShellError(500, "api_error",
                         "claude exited with code %s%s" % (
                             exit_code, (": " + detail) if detail else ""))


# --------------------------------------------------------------------------- #
# Anthropic mapping
# --------------------------------------------------------------------------- #

UPSTREAM_ERROR_MAP = {
    "authentication_failed": (401, "authentication_error"),
    "api_key_invalid": (401, "authentication_error"),
    "rate_limit_error": (429, "rate_limit_error"),
    "overloaded_error": (529, "overloaded_error"),
    "billing_error": (400, "billing_error"),
    "permission_error": (403, "permission_error"),
}


def envelope_error(env):
    """Return (http_status, type, message) if envelope carries an error."""
    err = env.get("error")
    if err and env.get("type") == "assistant" and env.get("is_api_error_message"):
        status, etype = UPSTREAM_ERROR_MAP.get(err, (500, "api_error"))
        msg = ""
        for b in (env.get("message") or {}).get("content") or []:
            if isinstance(b, dict) and b.get("type") == "text":
                msg += b.get("text", "")
        return status, etype, msg or err
    if env.get("type") == "result" and env.get("is_error"):
        msg = env.get("result") or "turn failed"
        # try to classify from embedded hints
        for key, (status, etype) in UPSTREAM_ERROR_MAP.items():
            if key in msg:
                return status, etype, msg
        return 500, "api_error", msg
    return None


def assistant_text(env):
    if env.get("type") != "assistant":
        return ""
    parts = []
    for b in (env.get("message") or {}).get("content") or []:
        if isinstance(b, dict) and b.get("type") == "text":
            parts.append(b.get("text", ""))
    return "".join(parts)


def anthropic_error_body(err_type, message):
    return {"type": "error", "error": {"type": err_type, "message": message}}


def build_message_response(req, text, usage, sess_name, sess, result_env):
    ru = (result_env or {}).get("usage") or {}
    return {
        "id": "msg_" + uuid.uuid4().hex[:24],
        "type": "message",
        "role": "assistant",
        "model": req.get("model") or "",
        "content": [{"type": "text", "text": text}],
        "stop_reason": "end_turn",
        "stop_sequence": None,
        "usage": {
            "input_tokens": ru.get("input_tokens") or 0,
            "output_tokens": ru.get("output_tokens") or 0,
        },
        "_ccshell": {
            "session": sess_name,
            "cc_session_id": sess["cc_session_id"],
            "num_turns": (result_env or {}).get("num_turns"),
            "cost_usd": (result_env or {}).get("total_cost_usd"),
        },
    }


# --------------------------------------------------------------------------- #
# doctor
# --------------------------------------------------------------------------- #

def doctor(live=False):
    checks = []
    claude_bin = find_claude()
    checks.append({
        "name": "claude binary on PATH",
        "ok": bool(claude_bin),
        "detail": claude_bin or "not found",
    })
    if not claude_bin:
        return checks
    ver = claude_version(claude_bin)
    checks.append({"name": "claude --version", "ok": not ver.startswith("error"),
                   "detail": ver})
    try:
        hp = subprocess.run([claude_bin, "--help"], capture_output=True,
                            text=True, timeout=30).stdout or ""
    except Exception as e:
        hp = ""
        checks.append({"name": "--help readable", "ok": False, "detail": str(e)})
    if hp:
        missing = [f for f in REQUIRED_FLAGS if f not in hp]
        checks.append({"name": "required flags advertised",
                       "ok": not missing,
                       "detail": "all present" if not missing else "missing: " + ", ".join(missing)})
    # credential-free envelope probe: validates the stream-json protocol shape
    # against the installed version without needing login.
    probe_id = str(uuid.uuid4())
    argv = [claude_bin, "-p", "--verbose", "--output-format", "stream-json",
            "--session-id", probe_id, "cc-api doctor probe (no-op)"]
    seen = {"system": False, "assistant": False, "result": False}
    sid_ok = False
    auth_state = "unknown"
    try:
        p = subprocess.run(argv, stdin=subprocess.DEVNULL, capture_output=True,
                           text=True, timeout=120, cwd=tempfile.gettempdir())
        for line in (p.stdout or "").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                env = json.loads(line)
            except json.JSONDecodeError:
                continue
            t = env.get("type")
            if t in seen:
                seen[t] = True
            if env.get("session_id") == probe_id:
                sid_ok = True
            if t == "result":
                if env.get("is_error"):
                    auth_state = "not authenticated (%s)" % (
                        env.get("result") or "error")
                else:
                    auth_state = "authenticated"
    except subprocess.TimeoutExpired:
        checks.append({"name": "envelope probe", "ok": False,
                       "detail": "probe timed out"})
    except Exception as e:
        checks.append({"name": "envelope probe", "ok": False, "detail": str(e)})
    else:
        ok = all(seen.values()) and sid_ok
        detail = "envelope types system/assistant/result: %s; --session-id honored: %s" % (
            "/".join(k for k, v in seen.items() if v) or "none", sid_ok)
        checks.append({"name": "stream-json envelope probe", "ok": ok, "detail": detail})
        checks.append({"name": "claude auth state", "ok": True, "detail": auth_state})
    cfg = load_config()
    bad_mods = [d for d in cfg.get("mods_dirs") or [] if not os.path.isdir(d)]
    checks.append({"name": "mods_dirs exist",
                   "ok": not bad_mods,
                   "detail": "ok" if not bad_mods else "missing: " + ", ".join(bad_mods)})
    if live:
        checks.append({"name": "live turn", "ok": False,
                       "detail": "not implemented in this doctor pass (needs auth); "
                                 "run: printf 'reply with exactly: ok' | ..."})
    return checks


def print_doctor(checks, as_json=False):
    if as_json:
        print(json.dumps(checks, ensure_ascii=False, indent=2))
        return 0 if all(c["ok"] for c in checks) else 1
    width = max(len(c["name"]) for c in checks) + 2
    rc = 0
    for c in checks:
        mark = "PASS" if c["ok"] else "FAIL"
        if not c["ok"]:
            rc = 1
        print("%s %-*s %s" % (mark, width, c["name"], c.get("detail", "")))
    return rc


# --------------------------------------------------------------------------- #
# HTTP server (Anthropic-compatible)
# --------------------------------------------------------------------------- #

class Handler(BaseHTTPRequestHandler):
    server_version = "cc-api/" + VERSION

    def log_message(self, fmt, *args):
        sys.stderr.write("[cc-api] %s %s\n" % (self.address_string(), fmt % args))

    # -- helpers ---------------------------------------------------------- #
    def _send_json(self, code, obj):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_error(self, exc: ShellError):
        self._send_json(exc.http_status, anthropic_error_body(exc.err_type, exc.message))

    def _check_auth(self):
        cfg = self.server.cfg
        want = cfg.get("api_key") or ""
        if not want:
            return True
        got = self.headers.get("x-api-key") or ""
        auth = self.headers.get("authorization") or ""
        if auth.lower().startswith("bearer "):
            got = auth[7:]
        return got == want

    def _read_json(self):
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            length = 0
        if length <= 0:
            return {}
        raw = self.rfile.read(length)
        try:
            return json.loads(raw.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            raise ShellError(400, "invalid_request_error", "invalid JSON body")

    def _session_name(self, req):
        name = self.headers.get("x-cc-session") or ""
        if not name and isinstance(req.get("_ccshell"), dict):
            name = req["_ccshell"].get("session") or ""
        return name.strip() or "default"

    # -- routing ---------------------------------------------------------- #
    def do_GET(self):
        if not self._check_auth():
            self._send_json(401, anthropic_error_body("authentication_error",
                                                      "invalid x-api-key"))
            return
        path = urllib.parse.urlparse(self.path).path
        if path in ("/healthz", "/health"):
            self._send_json(200, {"ok": True, "version": VERSION,
                                  "claude": self.server.claude_version})
        elif path == "/v1/models":
            models = [{"id": m, "type": "model", "display_name": m,
                       "created_at": "2026-01-01T00:00:00Z", "owned_by": "ccshell"}
                      for m in self.server.cfg.get("models") or []]
            self._send_json(200, {"data": models, "has_more": False,
                                  "first_id": models[0]["id"] if models else None,
                                  "last_id": models[-1]["id"] if models else None})
        elif path == "/v1/sessions":
            sessions = load_sessions()
            self._send_json(200, {"data": [
                {"name": n, "cc_session_id": s.get("cc_session_id"),
                 "turns": s.get("turns", 0),
                 "last_active": s.get("last_active")}
                for n, s in sessions.items()]})
        else:
            self._send_json(404, anthropic_error_body("not_found_error",
                                                      "unknown path: " + path))

    def do_DELETE(self):
        if not self._check_auth():
            self._send_json(401, anthropic_error_body("authentication_error",
                                                      "invalid x-api-key"))
            return
        path = urllib.parse.urlparse(self.path).path
        m = re.fullmatch(r"/v1/sessions/([^/]+)", path)
        if not m:
            self._send_json(404, anthropic_error_body("not_found_error",
                                                      "unknown path: " + path))
            return
        name = urllib.parse.unquote(m.group(1))
        sessions = load_sessions()
        s = sessions.pop(name, None)
        save_sessions(sessions)
        self._send_json(200, {
            "deleted": bool(s), "session": name,
            "note": "shell mapping removed; the claude transcript stays on disk and "
                    "can still be resumed from the TUI: claude --resume %s"
                    % ((s or {}).get("cc_session_id") or "<unknown>")})

    def do_POST(self):
        if not self._check_auth():
            self._send_json(401, anthropic_error_body("authentication_error",
                                                      "invalid x-api-key"))
            return
        path = urllib.parse.urlparse(self.path).path
        if path != "/v1/messages":
            self._send_json(404, anthropic_error_body("not_found_error",
                                                      "unknown path: " + path))
            return
        try:
            req = self._read_json()
            check_tools_unsupported(req)
            prompt = extract_user_text(req.get("messages"))
            if not req.get("model"):
                raise ShellError(400, "invalid_request_error", "model is required")
            # max_tokens is required by the Anthropic schema; accepted but the
            # wrapped session manages its own budget (see --max-budget-usd).
            stream = bool(req.get("stream"))
            sess_name = self._session_name(req)
            if stream:
                self._handle_messages_stream(req, prompt, sess_name)
            else:
                self._handle_messages_once(req, prompt, sess_name)
        except ShellError as e:
            self._send_error(e)
        except (BrokenPipeError, ConnectionResetError):
            pass
        except Exception as e:
            self._send_json(500, anthropic_error_body("api_error",
                                                      "internal error: %s" % e))

    # -- /v1/messages ----------------------------------------------------- #
    def _prepare_turn(self, req, sess_name):
        cfg = self.server.cfg
        claude_bin = self.server.claude_bin
        if not claude_bin:
            raise ShellError(500, "api_error", "claude binary not found on PATH")
        with session_lock(sess_name):
            sess, is_new = get_or_create_session(sess_name, cfg)
            argv = build_argv(claude_bin, sess, None, req, cfg, is_new)
        return cfg, claude_bin, sess, is_new, argv

    def _run_turn_collect(self, req, prompt, sess_name):
        """Run one turn, return (result_env, assistant_texts, error_tuple|None)."""
        cfg, claude_bin, sess, is_new, argv = self._prepare_turn(req, sess_name, )
        argv = argv[:-1] + [prompt]
        texts, result_env, err = [], None, None
        try:
            for env in run_turn(claude_bin, argv, cfg["workdir"],
                                cfg.get("turn_timeout_s") or 1800):
                if not isinstance(env, dict):
                    continue
                e = envelope_error(env)
                if e:
                    err = e
                    break
                t = assistant_text(env)
                if t:
                    texts.append(t)
                if env.get("type") == "result":
                    result_env = env
                    if env.get("is_error") and not err:
                        err = envelope_error(env) or (
                            500, "api_error", env.get("result") or "turn failed")
                    break
        except ShellError as se:
            err = (se.http_status, se.err_type, se.message)
        if not err and result_env is not None:
            sessions = load_sessions()
            s = sessions.get(sess_name)
            if s:
                s["turns"] = s.get("turns", 0) + 1
                s["last_active"] = time.time()
                save_sessions(sessions)
        final_text = (result_env or {}).get("result")
        if not isinstance(final_text, str) or not final_text:
            final_text = "".join(texts)
        return result_env, final_text, err, sess

    def _handle_messages_once(self, req, prompt, sess_name):
        result_env, final_text, err, sess = self._run_turn_collect(req, prompt, sess_name)
        if err:
            status, etype, msg = err
            self._send_json(status, anthropic_error_body(etype, msg))
            return
        if result_env is None:
            self._send_json(500, anthropic_error_body(
                "api_error", "no result envelope from claude"))
            return
        self._send_json(200, build_message_response(req, final_text,
                                                    result_env.get("usage") or {},
                                                    sess_name, sess, result_env))

    def _handle_messages_stream(self, req, prompt, sess_name):
        cfg, claude_bin, sess, is_new, argv = self._prepare_turn(req, sess_name)
        argv = argv[:-1] + [prompt]
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("X-Accel-Buffering", "no")
        self.send_header("x-cc-session", sess_name)
        self.end_headers()

        def emit(event, data):
            payload = "event: %s\ndata: %s\n\n" % (
                event, json.dumps(data, ensure_ascii=False))
            self.wfile.write(payload.encode("utf-8"))
            self.wfile.flush()

        msg_id = "msg_" + uuid.uuid4().hex[:24]
        model = req.get("model") or ""
        try:
            emit("message_start", {"type": "message_start", "message": {
                "id": msg_id, "type": "message", "role": "assistant",
                "model": model, "content": [], "stop_reason": None,
                "stop_sequence": None,
                "usage": {"input_tokens": 0, "output_tokens": 0}}})
            emit("content_block_start", {"type": "content_block_start",
                                         "index": 0,
                                         "content_block": {"type": "text", "text": ""}})
            result_env, err = None, None
            try:
                for env in run_turn(claude_bin, argv, cfg["workdir"],
                                    cfg.get("turn_timeout_s") or 1800):
                    if not isinstance(env, dict):
                        continue
                    e = envelope_error(env)
                    if e:
                        err = e
                        break
                    t = assistant_text(env)
                    if t:
                        emit("content_block_delta",
                             {"type": "content_block_delta", "index": 0,
                              "delta": {"type": "text_delta", "text": t}})
                    if env.get("type") == "result":
                        result_env = env
                        if env.get("is_error") and not err:
                            err = envelope_error(env) or (
                                500, "api_error", env.get("result") or "turn failed")
                        break
            except ShellError as se:
                err = (se.http_status, se.err_type, se.message)
            if err:
                status, etype, msg = err
                emit("error", {"type": "error",
                               "error": {"type": etype, "message": msg,
                                         "http_status": status}})
                return
            if result_env is not None:
                sessions = load_sessions()
                s = sessions.get(sess_name)
                if s:
                    s["turns"] = s.get("turns", 0) + 1
                    s["last_active"] = time.time()
                    save_sessions(sessions)
            ru = (result_env or {}).get("usage") or {}
            emit("content_block_stop",
                 {"type": "content_block_stop", "index": 0})
            emit("message_delta", {"type": "message_delta",
                                  "delta": {"stop_reason": "end_turn",
                                            "stop_sequence": None},
                                  "usage": {"output_tokens": ru.get("output_tokens") or 0}})
            emit("message_stop", {"type": "message_stop"})
        except (BrokenPipeError, ConnectionResetError):
            pass


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #

def cmd_serve(args):
    cfg = load_config()
    if args.host:
        cfg["host"] = args.host
    if args.port:
        cfg["port"] = args.port
    ensure_dirs()
    claude_bin = find_claude()
    if not claude_bin:
        print("error: claude binary not found on PATH", file=sys.stderr)
        return 1
    if cfg.get("api_key"):
        print("[cc-api] API key auth enabled", file=sys.stderr)
    elif (cfg.get("host") or DEFAULT_HOST) not in ("127.0.0.1", "localhost", "::1"):
        print("[cc-api] WARNING: no api_key configured and binding to non-loopback; "
              "set api_key in %s" % CONFIG_PATH, file=sys.stderr)
    server = ThreadingHTTPServer((cfg.get("host") or DEFAULT_HOST,
                                  int(cfg.get("port") or DEFAULT_PORT)), Handler)
    server.daemon_threads = True
    server.cfg = cfg
    server.claude_bin = claude_bin
    server.claude_version = claude_version(claude_bin)
    print("[cc-api] serving Anthropic-compatible API on %s:%s (claude %s)" % (
        cfg.get("host"), cfg.get("port"), server.claude_version), file=sys.stderr)
    print("[cc-api] config: %s" % CONFIG_PATH, file=sys.stderr)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


def cmd_doctor(args):
    ensure_dirs()
    checks = doctor(live=args.live)
    return print_doctor(checks, as_json=args.json)


def cmd_sessions(args):
    sessions = load_sessions()
    if args.action == "list":
        if args.json:
            print(json.dumps(sessions, ensure_ascii=False, indent=2))
        elif not sessions:
            print("no shell sessions yet")
        else:
            for n, s in sessions.items():
                print("%-20s cc_session_id=%s turns=%s last_active=%s" % (
                    n, s.get("cc_session_id"), s.get("turns", 0),
                    time.strftime("%Y-%m-%d %H:%M:%S",
                                  time.localtime(s.get("last_active") or 0))))
    elif args.action == "rm":
        s = sessions.pop(args.name, None)
        save_sessions(sessions)
        print("removed %s" % args.name if s else "no such session: %s" % args.name)
    elif args.action == "show":
        s = sessions.get(args.name)
        if args.json or True:
            print(json.dumps(s or {}, ensure_ascii=False, indent=2))
    return 0


def cmd_config(args):
    cfg = load_config()
    if args.set:
        for kv in args.set:
            if "=" not in kv:
                print("bad --set (want key=value): %s" % kv, file=sys.stderr)
                return 1
            k, v = kv.split("=", 1)
            try:
                v = json.loads(v)
            except json.JSONDecodeError:
                pass
            cfg[k.strip()] = v
        save_config(cfg)
        print("saved %s" % CONFIG_PATH)
    else:
        print(json.dumps(cfg, ensure_ascii=False, indent=2))
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(prog="cc-api",
                                 description="Anthropic-compatible API shell "
                                             "around a persistent Claude Code session")
    ap.add_argument("--version", action="version", version="cc-api " + VERSION)
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("serve", help="run the HTTP API server")
    p.add_argument("--host", default="")
    p.add_argument("--port", type=int, default=0)
    p.set_defaults(fn=cmd_serve)

    p = sub.add_parser("doctor", help="check claude compatibility (run after upgrades)")
    p.add_argument("--json", action="store_true")
    p.add_argument("--live", action="store_true",
                   help="also run a live turn (requires claude auth)")
    p.set_defaults(fn=cmd_doctor)

    p = sub.add_parser("sessions", help="inspect shell sessions")
    p.add_argument("action", choices=["list", "rm", "show"])
    p.add_argument("name", nargs="?", default="")
    p.add_argument("--json", action="store_true")
    p.set_defaults(fn=cmd_sessions)

    p = sub.add_parser("config", help="show or set config")
    p.add_argument("--set", nargs="*", default=[],
                   help="key=value pairs (values parsed as JSON when possible)")
    p.set_defaults(fn=cmd_config)

    args = ap.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
