"""
tools.py - the four tools the agent can call, and the registry that describes them.

Day 2. A tool is an ordinary Python function plus a JSON schema telling the model
how to call it. Nothing more. The model never runs your code; it names a tool and
supplies arguments, and YOUR dispatcher decides whether to honour that.

Read SAFE_EVAL below before you write your own calculator. Passing model output
to eval() is the single most common way a student agent becomes a security hole.
"""

import ast
import csv
import json
import operator
import os
import urllib.error
import urllib.request

# The package lives in agent/, the data beside it in data/, so the project
# root is one level up from this file.
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA = os.path.join(ROOT, "data")
SENSORS = os.path.join(DATA, "sensors.csv")


class ToolError(Exception):
    """A tool refused the call. The agent sees this text and may try again."""


# --------------------------------------------------------------- 1. calculator

_OPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
}


def _safe_eval(node):
    """Evaluate a arithmetic-only AST. Anything else raises.

    WHY NOT eval()? The model produces this string. eval("__import__('os')
    .system('rm -rf /')") is a valid Python expression. An agent that evals
    model output has handed a stranger a shell. This walks the parse tree and
    permits numbers and seven operators - nothing else exists.
    """
    if isinstance(node, ast.Expression):
        return _safe_eval(node.body)
    if isinstance(node, ast.Constant):
        if isinstance(node.value, (int, float)) and not isinstance(node.value, bool):
            return node.value
        raise ToolError("only numbers are allowed, got %r" % (node.value,))
    if isinstance(node, ast.BinOp):
        op = _OPS.get(type(node.op))
        if op is None:
            raise ToolError("operator not allowed")
        return op(_safe_eval(node.left), _safe_eval(node.right))
    if isinstance(node, ast.UnaryOp):
        op = _OPS.get(type(node.op))
        if op is None:
            raise ToolError("operator not allowed")
        return op(_safe_eval(node.operand))
    raise ToolError("expression contains something that is not arithmetic")


def calculator(expression):
    """Evaluate an arithmetic expression and return the result as text."""
    if not isinstance(expression, str):
        raise ToolError("expression must be a string, got %s"
                        % type(expression).__name__)
    if len(expression) > 200:
        raise ToolError("expression too long")
    try:
        tree = ast.parse(expression, mode="eval")
    except SyntaxError as e:
        raise ToolError("not a valid expression: %s" % e.msg)
    try:
        value = _safe_eval(tree)
    except ZeroDivisionError:
        raise ToolError("division by zero")
    if isinstance(value, float):
        value = round(value, 6)
    return str(value)


# ------------------------------------------------------- 2. sensor data lookup

_METRICS = ("temperature_c", "humidity_pct", "soil_moisture_pct", "light_lux")
_OPERATIONS = ("mean", "min", "max", "sum", "count", "latest")


def _load_sensors():
    if not os.path.exists(SENSORS):
        raise ToolError("sensor data file is missing at %s" % SENSORS)
    with open(SENSORS, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def sensor_query(metric, operation, start_date=None, end_date=None):
    """Aggregate one column of the sensor log over an optional date range."""
    if metric not in _METRICS:
        raise ToolError("unknown metric %r. Available: %s"
                        % (metric, ", ".join(_METRICS)))
    if operation not in _OPERATIONS:
        raise ToolError("unknown operation %r. Available: %s"
                        % (operation, ", ".join(_OPERATIONS)))

    rows = _load_sensors()
    if start_date:
        rows = [r for r in rows if r["date"] >= start_date]
    if end_date:
        rows = [r for r in rows if r["date"] <= end_date]
    if not rows:
        # Name the remedy, not just the problem. A model asked about
        # "September" tends to supply the year it saw most in training, get
        # refused, and - having been told only what is wrong - send the exact
        # same call again until the budget runs out. "Omit the dates" is a
        # one-step correction it can actually follow.
        every = _load_sensors()
        raise ToolError("no rows in that date range. The log covers %s to %s. "
                        "Omit start_date and end_date to search the whole log."
                        % (every[0]["date"], every[-1]["date"]))

    values = [float(r[metric]) for r in rows]

    if operation == "count":
        return str(len(values))
    if operation == "latest":
        return "%s on %s" % (rows[-1][metric], rows[-1]["date"])
    if operation == "mean":
        return str(round(sum(values) / len(values), 2))
    if operation == "sum":
        return str(round(sum(values), 2))
    if operation == "min":
        row = min(rows, key=lambda r: float(r[metric]))
        return "%s on %s" % (row[metric], row["date"])
    row = max(rows, key=lambda r: float(r[metric]))
    return "%s on %s" % (row[metric], row["date"])


def sensor_schema_info():
    """Tell the model what is in the dataset. Agents guess badly without this."""
    rows = _load_sensors()
    return json.dumps({
        "rows": len(rows),
        "date_range": [rows[0]["date"], rows[-1]["date"]],
        "metrics": list(_METRICS),
        "operations": list(_OPERATIONS),
    })


# ------------------------------------------------------------- 3. http fetch

def http_get(url, max_chars=1200):
    """Fetch a URL and return the first max_chars of the body as text.

    Deliberately restricted: https only, no redirects to other schemes, a short
    timeout and a hard truncation. An unrestricted fetch tool is how an agent
    gets talked into reading an attacker's instructions - see Day 6.
    """
    if not isinstance(url, str) or not url.startswith("https://"):
        raise ToolError("url must be a string beginning with https://")
    req = urllib.request.Request(url, headers={"User-Agent": "kaushalya-agent/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            raw = resp.read(max_chars * 4)
    except urllib.error.HTTPError as e:
        raise ToolError("the server returned HTTP %d" % e.code)
    except urllib.error.URLError as e:
        raise ToolError("could not reach that URL (%s). The lab network may "
                        "block it - try a different tool." % e.reason)
    text = raw.decode("utf-8", "replace")
    # crude tag strip: enough for a lab, not a parser
    out, depth = [], 0
    for ch in text:
        if ch == "<":
            depth += 1
        elif ch == ">":
            depth = max(0, depth - 1)
        elif depth == 0:
            out.append(ch)
    cleaned = " ".join("".join(out).split())
    return cleaned[:max_chars] if cleaned else "(the page had no readable text)"


# ----------------------------------------------------------------- registry

TOOLS = {
    "calculator": {
        "fn": calculator,
        "description": "Evaluate an arithmetic expression. Use this for any "
                       "calculation - never do arithmetic yourself.",
        "parameters": {
            "expression": {
                "type": "string",
                "required": True,
                "description": "An arithmetic expression, e.g. '(24.5 + 26.1) / 2'",
            },
        },
    },
    "sensor_query": {
        "fn": sensor_query,
        "description": "Aggregate one metric from the sensor log over an "
                       "optional date range. Call sensor_schema_info first if "
                       "you do not know the metric names or the dates covered.",
        "parameters": {
            "metric": {"type": "string", "required": True,
                       "description": "One of: " + ", ".join(_METRICS)},
            "operation": {"type": "string", "required": True,
                          "description": "One of: " + ", ".join(_OPERATIONS)},
            "start_date": {"type": "string", "required": False,
                           "description": "Inclusive, YYYY-MM-DD"},
            "end_date": {"type": "string", "required": False,
                         "description": "Inclusive, YYYY-MM-DD"},
        },
    },
    "sensor_schema_info": {
        "fn": sensor_schema_info,
        "description": "Describe the sensor dataset: how many rows, which dates "
                       "it covers, and which metrics and operations exist.",
        "parameters": {},
    },
    "http_get": {
        "fn": http_get,
        "description": "Fetch an https page and return its readable text, "
                       "truncated. Use only when the answer cannot come from "
                       "the other tools.",
        "parameters": {
            "url": {"type": "string", "required": True,
                    "description": "Must begin with https://"},
        },
    },
}


def tool_specs(names=None):
    """Render the tools as text for the prompt.

    This is the whole 'function calling' idea: the schema is just words in the
    prompt. Frameworks hide this behind an API; here you can read it.
    """
    chosen = names or list(TOOLS)
    lines = []
    for name in chosen:
        spec = TOOLS[name]
        params = spec["parameters"]
        if params:
            arglist = ", ".join(
                "%s%s" % (p, "" if meta.get("required") else "?")
                for p, meta in params.items())
        else:
            arglist = ""
        lines.append("- %s(%s)\n    %s" % (name, arglist, spec["description"]))
        for p, meta in params.items():
            lines.append("    %s (%s%s): %s"
                         % (p, meta["type"],
                            "" if meta.get("required") else ", optional",
                            meta["description"]))
    return "\n".join(lines)


def validate_args(name, args):
    """Check the model's arguments BEFORE calling the function.

    Day 1 taught that valid JSON is not a valid answer. This is where that
    lesson is enforced: a missing required argument, an unknown argument or a
    wrong type is refused here, with a message the model can act on.
    """
    if name not in TOOLS:
        raise ToolError("no tool called %r. Available: %s"
                        % (name, ", ".join(TOOLS)))
    if not isinstance(args, dict):
        raise ToolError("arguments must be an object, got %s"
                        % type(args).__name__)
    spec = TOOLS[name]["parameters"]

    for p, meta in spec.items():
        if meta.get("required") and p not in args:
            raise ToolError("tool %s requires the argument %r" % (name, p))
    for p in args:
        if p not in spec:
            raise ToolError("tool %s has no argument %r. It takes: %s"
                            % (name, p, ", ".join(spec) or "no arguments"))
    for p, value in args.items():
        if spec[p]["type"] == "string" and not isinstance(value, str):
            raise ToolError("argument %r of %s must be a string, got %s"
                            % (p, name, type(value).__name__))
    return True


def run_tool(name, args):
    """Validate then call. Returns the observation text the agent will see."""
    validate_args(name, args)
    fn = TOOLS[name]["fn"]
    try:
        return str(fn(**args))
    except ToolError:
        raise
    except Exception as e:                      # a tool's own bug
        raise ToolError("%s failed: %s: %s" % (name, type(e).__name__, e))


if __name__ == "__main__":
    print("Tools available:\n")
    print(tool_specs())
    print("\nSmoke test:")
    print("  calculator('(24.5 + 26.1) / 2') ->", run_tool(
        "calculator", {"expression": "(24.5 + 26.1) / 2"}))
    print("  sensor_schema_info()            ->", run_tool("sensor_schema_info", {}))
    print("  sensor_query mean temperature   ->", run_tool(
        "sensor_query", {"metric": "temperature_c", "operation": "mean"}))
    print("\nNow the refusals you want to see:")
    for name, args in [("calculator", {"expression": "__import__('os')"}),
                       ("sensor_query", {"metric": "rainfall", "operation": "mean"}),
                       ("calculator", {"expr": "1+1"}),
                       ("nonexistent", {})]:
        try:
            run_tool(name, args)
            print("  %s%r -> NO ERROR (this is a bug)" % (name, args))
        except ToolError as e:
            print("  %s -> refused: %s" % (name, e))
