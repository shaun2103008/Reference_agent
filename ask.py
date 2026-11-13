"""Ask the agent one question.

    python ask.py "What was the hottest day in September?"
"""
import sys

from agent import Budget, run_agent


def main():
    question = " ".join(sys.argv[1:]) or \
        "By how many degrees did the hottest day exceed the coldest?"
    trace = run_agent(question, budget=Budget(steps=6), verbose=True)
    print()
    print("ANSWER:", trace.answer or "(no answer - %s)" % trace.stopped_because)


if __name__ == "__main__":
    main()
