"""
graph.py - a state graph in seventy lines, so frameworks stop being magic.

Day 3. LangGraph, and every orchestration framework like it, is this idea:
  * state is a dict that flows through the system
  * a node is a function: state -> state
  * an edge says which node runs next, and may look at the state to decide
  * you run until a node routes to END

That is all. The real frameworks add persistence, streaming, concurrency and a
large API surface - worth having in production, and worth understanding first.

    g = Graph({"n": 0})
    g.node("count", lambda s: {**s, "n": s["n"] + 1})
    g.edge("count", lambda s: END if s["n"] >= 3 else "count")
    g.entry("count")
    final = g.run()
"""

END = "__end__"


class GraphError(RuntimeError):
    pass


class Graph:
    def __init__(self, state=None, max_hops=50):
        self.state = dict(state or {})
        self.nodes = {}
        self.edges = {}
        self.start = None
        self.max_hops = max_hops
        self.path = []

    # ---------------------------------------------------------------- build

    def node(self, name, fn):
        """Register a node. fn takes the state dict and returns a new one."""
        if name == END:
            raise GraphError("'%s' is reserved" % END)
        self.nodes[name] = fn
        return self

    def edge(self, name, target):
        """Where to go after `name`.

        target is either a node name (an unconditional edge) or a callable
        state -> node name, which is how a framework does branching.
        """
        self.edges[name] = target
        return self

    def entry(self, name):
        self.start = name
        return self

    # ------------------------------------------------------------------ run

    def run(self, verbose=False):
        if self.start is None:
            raise GraphError("no entry node set - call entry()")
        current = self.start
        self.path = []

        for hop in range(self.max_hops):
            if current == END:
                return self.state
            if current not in self.nodes:
                raise GraphError("no node called %r" % current)

            self.path.append(current)
            if verbose:
                print("  -> %s" % current)

            result = self.nodes[current](self.state)
            if result is not None:
                if not isinstance(result, dict):
                    raise GraphError("node %r returned %s, expected a dict"
                                     % (current, type(result).__name__))
                self.state = result

            target = self.edges.get(current, END)
            current = target(self.state) if callable(target) else target

        raise GraphError(
            "graph ran %d hops without reaching END. Path: %s\n"
            "This is the same failure as an agent with no step budget - a loop "
            "with no exit." % (self.max_hops, " -> ".join(self.path[-8:])))


if __name__ == "__main__":
    print("Demo 1 - a counter that loops back to itself")
    g = Graph({"n": 0})
    g.node("count", lambda s: {**s, "n": s["n"] + 1})
    g.edge("count", lambda s: END if s["n"] >= 3 else "count")
    g.entry("count")
    print("  final state:", g.run(verbose=True))
    print("  path:", " -> ".join(g.path))

    print("\nDemo 2 - branching on the state")
    g2 = Graph({"value": 7})
    g2.node("classify", lambda s: {**s, "big": s["value"] > 5})
    g2.node("report_big", lambda s: {**s, "msg": "that is a big number"})
    g2.node("report_small", lambda s: {**s, "msg": "that is a small number"})
    g2.edge("classify", lambda s: "report_big" if s["big"] else "report_small")
    g2.edge("report_big", END)
    g2.edge("report_small", END)
    g2.entry("classify")
    print("  final state:", g2.run(verbose=True))

    print("\nDemo 3 - the runaway loop, caught")
    g3 = Graph({}, max_hops=5)
    g3.node("spin", lambda s: s)
    g3.edge("spin", "spin")
    g3.entry("spin")
    try:
        g3.run()
    except GraphError as e:
        print("  caught:", str(e).splitlines()[0])
