"""
agent.py - the agent from Day 2, made robust. Used by every day after this.

Day 3. Day 2's loop worked when things went well. This one adds the five things
that separate a demo from something you would run twice:

  1. BUDGETS      steps, wall-clock seconds, and tokens. All three, enforced.
  2. RETRIES      a model that returns unparseable JSON gets told so, once.
  3. VALIDATION   arguments are checked before the tool is called (tools.py).
  4. NO REPEATS   an identical call is refused and handed back what it returned
                  the first time, because small models loop instead of finishing.
  5. A TRACE      every event recorded, so Thursday you can debug an answer
                  and Saturday you can measure one.

The trace is the point. An agent you cannot trace is an agent you cannot fix.
"""

import json
import time

from .llm import LLMError, ask_json, tokens_used
from .tools import TOOLS, ToolError, run_tool, tool_specs

SYSTEM = """You are a tool-using agent. You answer by taking one step at a time.

Tools:

%s

Reply with ONLY a JSON object, no prose and no code fence:

  To use a tool:   {"thought": "<why>", "tool": "<name>", "args": {...}}
  To finish:       {"thought": "<why>", "answer": "<the final answer>"}

Rules:
  - One tool per reply. You will see the result and may take another step.
  - Never do arithmetic yourself; use the calculator.
  - Never guess dataset contents; call sensor_schema_info first.
  - If a tool returns ERROR, read it and correct your arguments. Do not repeat
    the same failing call.
  - Never call a tool twice with the same arguments. The result is already in
    the history above; read it from there.
  - When you have enough to answer, answer. If the history above already
    contains what the question asked for, reply with "answer" now.
"""


class Budget:
    """Three limits. Whichever is reached first stops the agent."""

    def __init__(self, steps=6, seconds=120, tokens=20000):
        self.steps = steps
        self.seconds = seconds
        self.tokens = tokens

    def __repr__(self):
        return "Budget(steps=%d, seconds=%d, tokens=%d)" % (
            self.steps, self.seconds, self.tokens)


class Trace:
    """Everything that happened, in order, with what it cost."""

    def __init__(self, question):
        self.question = question
        self.events = []
        self.started = time.time()
        self.tokens = 0
        self.model_calls = 0
        self.tool_calls = 0
        self.tool_errors = 0
        self.parse_failures = 0
        self.repeat_calls = 0
        self.answer = None
        self.stopped_because = None

    def add(self, kind, **data):
        self.events.append(dict(kind=kind, at=round(time.time() - self.started, 2),
                                **data))

    @property
    def elapsed(self):
        return round(time.time() - self.started, 2)

    def summary(self):
        return {
            "answered": self.answer is not None,
            "stopped_because": self.stopped_because,
            "steps": sum(1 for e in self.events if e["kind"] == "step"),
            "model_calls": self.model_calls,
            "tool_calls": self.tool_calls,
            "tool_errors": self.tool_errors,
            "parse_failures": self.parse_failures,
            "repeat_calls": self.repeat_calls,
            "tokens": self.tokens,
            "seconds": self.elapsed,
        }

    def show(self, width=150):
        print("question: %s" % self.question)
        for e in self.events:
            kind = e["kind"]
            stamp = "%6.2fs" % e["at"]
            if kind == "step":
                print("%s  --- step %d" % (stamp, e["n"]))
            elif kind == "thought":
                print("%s      thought : %s" % (stamp, e["text"][:width]))
            elif kind == "action":
                print("%s      action  : %s(%s)" % (stamp, e["tool"],
                                                    json.dumps(e["args"])))
            elif kind == "observation":
                print("%s      result  : %s" % (stamp, e["text"][:width]))
            elif kind == "refused":
                print("%s      REFUSED : %s" % (stamp, e["text"][:width]))
            elif kind == "parse_failure":
                print("%s      unparseable reply (%s)" % (stamp, e["text"][:80]))
            elif kind == "answer":
                print("%s      ANSWER  : %s" % (stamp, e["text"][:width]))
            elif kind == "stopped":
                print("%s      STOPPED : %s" % (stamp, e["text"]))
        print("summary : %s" % json.dumps(self.summary()))


def run_agent(question, tools=None, budget=None, approve=None, verbose=False,
              provider=None):
    """Run the agent and return a Trace.

    tools    list of tool names to expose (default: all of them)
    budget   a Budget, or None for the default
    approve  callable(tool_name, args) -> bool. Return False to block a call.
             Day 5 uses this for human-in-the-loop.
    """
    budget = budget or Budget()
    names = tools or list(TOOLS)
    system = SYSTEM % tool_specs(names)
    trace = Trace(question)
    history = []
    already_run = {}          # (tool, args) -> the observation it produced

    for n in range(1, budget.steps + 1):
        # ---- budget checks, before spending anything
        if trace.elapsed > budget.seconds:
            trace.stopped_because = "time"
            trace.add("stopped", text="time budget (%ds) exhausted" % budget.seconds)
            break
        if trace.tokens > budget.tokens:
            trace.stopped_because = "tokens"
            trace.add("stopped", text="token budget (%d) exhausted" % budget.tokens)
            break

        trace.add("step", n=n)

        prompt = "QUESTION: %s\n\n%s" % (question, "\n\n".join(history))

        # ---- REASON
        # ask_json returns the parsed object only, so the token figures come
        # from the counter in llm.py. Read it either side of the call, including
        # on the failure path: a reply that could not be parsed still cost
        # tokens, and a budget that ignored those would never stop a model
        # looping on unparseable output.
        spent_before = tokens_used()
        try:
            decision = ask_json(prompt, system=system, temperature=0.0,
                                attempts=2, provider=provider)
            trace.model_calls += 1
            trace.tokens += tokens_used() - spent_before
        except LLMError as e:
            trace.parse_failures += 1
            trace.model_calls += 1
            trace.tokens += tokens_used() - spent_before
            trace.add("parse_failure", text=str(e).splitlines()[0])
            history.append("OBSERVATION: your previous reply was not valid JSON. "
                           "Reply with a JSON object only.")
            continue

        thought = str(decision.get("thought", ""))
        if thought:
            trace.add("thought", text=thought)

        # ---- finished?
        if "answer" in decision:
            trace.answer = str(decision["answer"])
            trace.stopped_because = "answered"
            trace.add("answer", text=trace.answer)
            break

        name = decision.get("tool")
        if not name:
            trace.add("refused", text="reply had neither 'tool' nor 'answer'")
            history.append("OBSERVATION: your reply had neither 'tool' nor "
                           "'answer'. Supply exactly one.")
            continue

        args = decision.get("args") or {}
        trace.add("action", tool=name, args=args)

        # ---- least privilege, enforced by the dispatcher
        # Listing tools in the prompt only ASKS the model to stay inside them.
        # The gate that matters is this one: a name we did not grant never
        # reaches run_tool, however convincingly the model asks for it. Day 6
        # calls an agent that trusts the prompt here a confused deputy.
        if name not in names:
            observation = ("ERROR: there is no tool called %r available to you. "
                           "You may use only: %s" % (name, ", ".join(names)))
            trace.tool_errors += 1
            trace.add("refused", text="%r is not in the granted tool list" % name)
            history.append("ACTION: %s(%s)\nOBSERVATION: %s"
                           % (name, json.dumps(args), observation))
            continue

        # ---- have we already done exactly this?
        # Small models loop in two ways: repeating a call that failed, and
        # repeating one that succeeded instead of answering with the result.
        # Both burn the whole budget and end with answered=false. Telling the
        # model what it already got, and refusing to run it again, converts a
        # wasted step into a usable one - and costs nothing when the model
        # behaves.
        signature = (name, json.dumps(args, sort_keys=True))
        if signature in already_run:
            # Say what to do next, not only what not to do. Told merely that a
            # call was a duplicate, a small model proposes it a sixth time and
            # dies on the step budget with the answer sitting in its own
            # reasoning. Restating the required JSON shape is what actually
            # gets it to stop.
            observation = ("ERROR: you have already called %s with exactly "
                           "these arguments.\nIt returned: %s\n\n"
                           "STOP CALLING TOOLS. You already have what you need. "
                           "Reply now with exactly this shape and nothing else:\n"
                           '{"thought": "<why>", "answer": "<your answer, '
                           'using the result above>"}'
                           % (name, already_run[signature]))
            trace.repeat_calls += 1
            trace.add("refused", text="identical call already made this run")
            history.append("ACTION: %s(%s)\nOBSERVATION: %s"
                           % (name, json.dumps(args), observation))
            continue

        # ---- human-in-the-loop gate
        if approve is not None and not approve(name, args):
            observation = "ERROR: a human declined this action."
            trace.add("refused", text="blocked by approval gate")
            history.append("ACTION: %s(%s)\nOBSERVATION: %s"
                           % (name, json.dumps(args), observation))
            continue

        # ---- ACT
        try:
            observation = run_tool(name, args)
            trace.tool_calls += 1
            trace.add("observation", text=observation)
        except ToolError as e:
            observation = "ERROR: %s" % e
            trace.tool_calls += 1
            trace.tool_errors += 1
            trace.add("refused", text=str(e))

        already_run[signature] = observation
        history.append("ACTION: %s(%s)\nOBSERVATION: %s"
                       % (name, json.dumps(args), observation))
    else:
        trace.stopped_because = "steps"
        trace.add("stopped", text="step budget (%d) exhausted" % budget.steps)

    if verbose:
        trace.show()
    return trace


def ask_agent(question, **kwargs):
    """Convenience: return just the answer text, or None."""
    return run_agent(question, **kwargs).answer


if __name__ == "__main__":
    import sys
    q = sys.argv[1] if len(sys.argv) > 1 else (
        "By how many degrees did the hottest day in September exceed the coldest?")
    run_agent(q, verbose=True)
