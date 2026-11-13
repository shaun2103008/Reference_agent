"""
llm.py - a minimal LLM client that talks to BOTH Ollama (local) and Google Gemini (hosted).

Why this file exists
--------------------
Every script this week imports from here. Swapping backend is one environment
variable, so the same lab works whether the lab machines have Ollama running or
only have internet access.

It uses nothing but the Python standard library - no pip install required.
Both Ollama and Gemini expose an OpenAI-compatible /chat/completions endpoint,
so one code path serves both.

Quick use
---------
    from llm import ask, chat

    print(ask("Name three uses of an accelerometer."))

    reply = chat([{"role": "user", "content": "Hello"}], temperature=0.0)
    print(reply["text"], reply["latency_s"], reply["usage"])

Choosing a backend
------------------
    set LLM_PROVIDER=ollama      (Windows)      export LLM_PROVIDER=ollama   (mac/Linux)
    set LLM_PROVIDER=gemini

Environment variables
---------------------
    LLM_PROVIDER    "ollama" (default) or "gemini"
    OLLAMA_MODEL    default "llama3.2:3b"
    OLLAMA_BASE     default "http://localhost:11434/v1"
    GOOGLE_API_KEY  required for gemini - get one free at https://aistudio.google.com
    GEMINI_MODEL    default "gemini-2.0-flash"
"""

import json
import os
import sys
import time
import urllib.error
import urllib.request

# Some lab machines still run the console in a legacy code page (chcp 437),
# where printing a dash or a degree sign raises UnicodeEncodeError and the
# exercise stops for a reason that has nothing to do with agents.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# --------------------------------------------------------------------------- config

OLLAMA_BASE = os.environ.get("OLLAMA_BASE", "http://localhost:11434/v1")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "llama3.2:3b")

GEMINI_BASE = os.environ.get("GEMINI_BASE",
                             "https://generativelanguage.googleapis.com/v1beta/openai")
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.0-flash")

DEFAULT_PROVIDER = os.environ.get("LLM_PROVIDER", "ollama").strip().lower()

# Running total of tokens the backend has reported this process.
#
# ask() and ask_json() return only what the caller asked for - text, or a parsed
# object - so the usage figures would otherwise be thrown away, and agent.py
# could never enforce its token budget. A counter here lets any caller measure a
# call without changing a single signature: read it before, read it after, take
# the difference. See run_agent() in agent.py.
_TOKENS_USED = 0


def tokens_used():
    """Total tokens reported by the backend since this process started.

    Zero if the backend reports no usage figures, which some do not.
    """
    return _TOKENS_USED


class LLMError(RuntimeError):
    """Raised with a message a student can act on."""


# --------------------------------------------------------------------------- core

def _post_json(url, payload, headers, timeout):
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=body, method="POST")
    req.add_header("Content-Type", "application/json")
    for k, v in headers.items():
        req.add_header(k, v)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _endpoint(provider):
    """Return (url, headers, default_model) for a provider."""
    if provider == "ollama":
        return OLLAMA_BASE.rstrip("/") + "/chat/completions", {}, OLLAMA_MODEL

    if provider == "gemini":
        key = os.environ.get("GOOGLE_API_KEY", "").strip()
        if not key:
            raise LLMError(
                "GOOGLE_API_KEY is not set.\n"
                "  1. Get a free key at https://aistudio.google.com/apikey\n"
                "  2. Windows:  set GOOGLE_API_KEY=your_key_here\n"
                "     mac/Linux: export GOOGLE_API_KEY=your_key_here\n"
                "  Never paste the key into a .py file you will commit."
            )
        return (GEMINI_BASE.rstrip("/") + "/chat/completions",
                {"Authorization": "Bearer " + key},
                GEMINI_MODEL)

    raise LLMError("Unknown provider %r. Use 'ollama' or 'gemini'." % provider)


def chat(messages, provider=None, model=None, temperature=0.0,
         max_tokens=None, json_mode=False, timeout=120):
    """Send a chat request and return a dict.

    messages     list of {"role": "system"|"user"|"assistant", "content": str}
    provider     "ollama" | "gemini"   (defaults to $LLM_PROVIDER)
    temperature  0.0 is as close to repeatable as these models get
    json_mode    ask the server to guarantee syntactically valid JSON
                 (silently ignored by servers that do not support it)

    Returns {"text", "provider", "model", "latency_s", "usage", "raw"}
    """
    provider = (provider or DEFAULT_PROVIDER).strip().lower()
    url, headers, default_model = _endpoint(provider)
    model = model or default_model

    payload = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
    }
    if max_tokens is not None:
        payload["max_tokens"] = max_tokens
    if json_mode:
        payload["response_format"] = {"type": "json_object"}

    started = time.time()
    try:
        data = _post_json(url, payload, headers, timeout)
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace")[:600]
        if json_mode and ("response_format" in detail or e.code == 400):
            # Some servers reject response_format. Retry without it; the prompt
            # still asks for JSON, so this usually succeeds.
            payload.pop("response_format", None)
            started = time.time()
            data = _post_json(url, payload, headers, timeout)
        elif e.code in (401, 403):
            raise LLMError("%s rejected the API key (HTTP %d). Check GOOGLE_API_KEY.\n%s"
                           % (provider, e.code, detail))
        elif e.code == 404:
            raise LLMError(
                "%s has no model called %r (HTTP 404).\n"
                "  Ollama: run  ollama list   to see what is installed,\n"
                "          then ollama pull %s\n"
                "  Gemini: check the model list at https://aistudio.google.com\n%s"
                % (provider, model, OLLAMA_MODEL, detail))
        elif e.code == 429:
            raise LLMError("%s rate limit reached (HTTP 429). Wait a minute, or switch "
                           "provider with LLM_PROVIDER.\n%s" % (provider, detail))
        else:
            raise LLMError("%s returned HTTP %d.\n%s" % (provider, e.code, detail))
    except urllib.error.URLError as e:
        if provider == "ollama":
            raise LLMError(
                "Cannot reach Ollama at %s (%s).\n"
                "  1. Is it running?  Open a terminal and run:  ollama serve\n"
                "  2. Is a model installed?                     ollama pull %s\n"
                "  3. Still stuck? switch to the hosted model:  set LLM_PROVIDER=gemini"
                % (OLLAMA_BASE, e.reason, OLLAMA_MODEL))
        raise LLMError("Cannot reach %s (%s). Check the network and the firewall."
                       % (provider, e.reason))

    latency = time.time() - started

    try:
        text = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError):
        raise LLMError("Unexpected response shape from %s:\n%s"
                       % (provider, json.dumps(data)[:600]))

    usage = data.get("usage") or {}

    global _TOKENS_USED
    _TOKENS_USED += usage.get("total_tokens") or 0

    return {
        "text": (text or "").strip(),
        "provider": provider,
        "model": data.get("model", model),
        "latency_s": round(latency, 2),
        "usage": {
            "prompt_tokens": usage.get("prompt_tokens"),
            "completion_tokens": usage.get("completion_tokens"),
            "total_tokens": usage.get("total_tokens"),
        },
        "raw": data,
    }


def ask(prompt, system=None, **kwargs):
    """One-shot convenience wrapper. Returns the reply text only."""
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})
    return chat(messages, **kwargs)["text"]


def ask_json(prompt, system=None, attempts=3, **kwargs):
    """Ask for JSON and return the parsed object.

    Models return prose around JSON more often than you would like, so this
    strips code fences, retries, and finally raises with what it actually got.
    Day 1, Lab B explains why this matters for agents.
    """
    kwargs.setdefault("json_mode", True)
    kwargs.setdefault("temperature", 0.0)
    last = ""
    for attempt in range(1, attempts + 1):
        last = ask(prompt, system=system, **kwargs)
        cleaned = last.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.split("```")[1] if "```" in cleaned[3:] else cleaned[3:]
            if cleaned.lstrip().lower().startswith("json"):
                cleaned = cleaned.lstrip()[4:]
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start != -1 and end > start:
            cleaned = cleaned[start:end + 1]
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            if attempt == attempts:
                break
    raise LLMError("Model did not return valid JSON after %d attempts.\n"
                   "Last reply was:\n%s" % (attempts, last[:600]))


def run(main_fn):
    """Run a lab script, turning setup errors into advice instead of a traceback.

    Every lab script ends with  run(main)  so that a student whose Ollama is
    not running sees three numbered steps, not forty lines of stack trace.
    """
    import sys
    try:
        main_fn()
    except LLMError as e:
        print()
        print("-" * 64)
        print("SETUP PROBLEM - the code is fine, the backend is not reachable")
        print("-" * 64)
        print(str(e))
        print("-" * 64)
        print("For a full diagnosis run:  python check_setup.py")
        sys.exit(1)
    except KeyboardInterrupt:
        print("\nStopped.")
        sys.exit(130)


def which():
    """Human-readable description of the active backend."""
    p = DEFAULT_PROVIDER
    if p == "ollama":
        return "ollama  model=%s  base=%s" % (OLLAMA_MODEL, OLLAMA_BASE)
    return "gemini  model=%s  key=%s" % (
        GEMINI_MODEL,
        "set" if os.environ.get("GOOGLE_API_KEY") else "MISSING")


if __name__ == "__main__":
    print("Active backend:", which())
    print("Reply:", ask("Reply with exactly the word: ready"))
