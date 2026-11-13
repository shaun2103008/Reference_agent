"""
store.py - chunking, embeddings and a vector store, in the standard library.

Day 4. Three ideas, no dependencies:

  1. CHUNKING    cut documents into pieces small enough to retrieve usefully
  2. EMBEDDING   turn a piece of text into a list of numbers
  3. SEARCH      find the pieces whose numbers are closest to the question's

There are two backends, exactly as with generation:
    ollama   needs:  ollama pull nomic-embed-text
    gemini   needs:  GOOGLE_API_KEY

And a KEYWORD fallback that needs nothing at all. The fallback is not a
consolation prize - comparing it against embeddings is the most instructive
exercise of the day. Semantic search is not always better, and you should be
able to say when.
"""

import json
import math
import os
import re
import urllib.error
import urllib.request

from . import llm

OLLAMA_EMBED_MODEL = os.environ.get("OLLAMA_EMBED_MODEL", "nomic-embed-text")
GEMINI_EMBED_MODEL = os.environ.get("GEMINI_EMBED_MODEL", "text-embedding-004")


class StoreError(RuntimeError):
    pass


# ---------------------------------------------------------------- 1. chunking

def chunk_text(text, size=600, overlap=120):
    """Split on paragraph boundaries where possible, else on size.

    size and overlap are in characters, not tokens, because this has to run
    without a tokeniser. overlap exists so a sentence spanning a boundary is
    still findable from both sides - drop it to 0 in the lab and watch recall
    fall.
    """
    if size <= 0:
        raise StoreError("size must be positive")
    if overlap >= size:
        raise StoreError("overlap must be smaller than size")

    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    chunks, current = [], ""
    for p in paragraphs:
        if len(current) + len(p) + 2 <= size:
            current = (current + "\n\n" + p).strip()
        else:
            if current:
                chunks.append(current)
            while len(p) > size:
                chunks.append(p[:size])
                p = p[size - overlap:]
            current = p
    if current:
        chunks.append(current)

    if overlap and len(chunks) > 1:
        stitched = [chunks[0]]
        for prev, nxt in zip(chunks, chunks[1:]):
            stitched.append((prev[-overlap:] + " " + nxt).strip())
        return stitched
    return chunks


# --------------------------------------------------------------- 2. embedding

def _post(url, payload, headers=None, timeout=60):
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=body, method="POST")
    req.add_header("Content-Type", "application/json")
    for k, v in (headers or {}).items():
        req.add_header(k, v)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def embed_one(text, provider=None):
    """Return a list of floats for one string."""
    provider = (provider or llm.DEFAULT_PROVIDER).lower()

    if provider == "ollama":
        base = llm.OLLAMA_BASE.rstrip("/").replace("/v1", "")
        try:
            data = _post(base + "/api/embeddings",
                         {"model": OLLAMA_EMBED_MODEL, "prompt": text})
            return data["embedding"]
        except urllib.error.HTTPError as e:
            if e.code == 404:
                try:                       # newer Ollama endpoint
                    data = _post(base + "/api/embed",
                                 {"model": OLLAMA_EMBED_MODEL, "input": text})
                    return data["embeddings"][0]
                except urllib.error.HTTPError:
                    pass
            raise StoreError(
                "Ollama has no embedding model installed.\n"
                "  Run:  ollama pull %s\n"
                "  Or use the keyword index instead (see build_index)."
                % OLLAMA_EMBED_MODEL)
        except urllib.error.URLError as e:
            raise StoreError("Cannot reach Ollama for embeddings (%s)." % e.reason)

    if provider == "gemini":
        key = os.environ.get("GOOGLE_API_KEY", "").strip()
        if not key:
            raise StoreError("GOOGLE_API_KEY is not set.")
        try:
            data = _post(llm.GEMINI_BASE.rstrip("/") + "/embeddings",
                         {"model": GEMINI_EMBED_MODEL, "input": text},
                         {"Authorization": "Bearer " + key})
            return data["data"][0]["embedding"]
        except urllib.error.HTTPError as e:
            raise StoreError("Gemini embeddings returned HTTP %d: %s"
                             % (e.code, e.read().decode("utf-8", "replace")[:300]))

    raise StoreError("unknown provider %r" % provider)


def cosine(a, b):
    """Similarity of two vectors: 1.0 identical direction, 0.0 unrelated."""
    if len(a) != len(b):
        raise StoreError("vectors of different length: %d vs %d" % (len(a), len(b)))
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


# ------------------------------------------------------------------ 3. stores

class VectorIndex:
    """Embeddings plus cosine similarity. Fine for a few hundred chunks."""

    kind = "vector"

    def __init__(self, provider=None):
        self.provider = provider or llm.DEFAULT_PROVIDER
        self.chunks = []        # [{"source","text","vector"}]

    def add(self, source, text):
        self.chunks.append({"source": source, "text": text,
                            "vector": embed_one(text, self.provider)})

    def search(self, query, k=4):
        qv = embed_one(query, self.provider)
        scored = [(cosine(qv, c["vector"]), c) for c in self.chunks]
        scored.sort(key=lambda pair: pair[0], reverse=True)
        return [(round(s, 4), c["source"], c["text"]) for s, c in scored[:k]]

    def save(self, path):
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"kind": "vector", "provider": self.provider,
                       "chunks": self.chunks}, f)

    @classmethod
    def load(cls, path):
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        idx = cls(provider=data.get("provider"))
        idx.chunks = data["chunks"]
        return idx


class KeywordIndex:
    """Lexical scoring, no model required. Rare words count for more."""

    kind = "keyword"

    def __init__(self, provider=None):
        self.chunks = []        # [{"source","text","tokens"}]

    @staticmethod
    def _tokens(text):
        return re.findall(r"[a-z0-9]+", text.lower())

    def add(self, source, text):
        self.chunks.append({"source": source, "text": text,
                            "tokens": self._tokens(text)})

    def _idf(self, term):
        n = sum(1 for c in self.chunks if term in c["tokens"])
        return math.log((len(self.chunks) + 1) / (n + 0.5))

    def search(self, query, k=4):
        terms = self._tokens(query)
        scored = []
        for c in self.chunks:
            score = 0.0
            for t in set(terms):
                tf = c["tokens"].count(t)
                if tf:
                    score += self._idf(t) * (tf / (tf + 1.5))
            scored.append((score, c))
        scored.sort(key=lambda pair: pair[0], reverse=True)
        return [(round(s, 4), c["source"], c["text"]) for s, c in scored[:k]]

    def save(self, path):
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"kind": "keyword",
                       "chunks": [{"source": c["source"], "text": c["text"]}
                                  for c in self.chunks]}, f)

    @classmethod
    def load(cls, path):
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        idx = cls()
        for c in data["chunks"]:
            idx.add(c["source"], c["text"])
        return idx


def load_index(path):
    """Load whichever kind of index was saved."""
    with open(path, encoding="utf-8") as f:
        kind = json.load(f).get("kind")
    return (VectorIndex if kind == "vector" else KeywordIndex).load(path)


def read_docs(folder):
    """Read every .txt and .md in a folder. Returns [(filename, text)]."""
    if not os.path.isdir(folder):
        raise StoreError("no such folder: %s" % folder)
    out = []
    for name in sorted(os.listdir(folder)):
        if name.lower().endswith((".txt", ".md")):
            with open(os.path.join(folder, name), encoding="utf-8") as f:
                out.append((name, f.read()))
    if not out:
        raise StoreError("no .txt or .md files in %s" % folder)
    return out


if __name__ == "__main__":
    sample = ("The soil moisture probe is capacitive.\n\n"
              "It must be calibrated in dry air and then in water.\n\n"
              "Readings drift if the probe is left in saline soil.")
    for size, overlap in ((60, 0), (60, 20), (600, 120)):
        pieces = chunk_text(sample, size=size, overlap=overlap)
        print("size=%d overlap=%d -> %d chunks" % (size, overlap, len(pieces)))
        for p in pieces:
            print("    %r" % p[:70])
    print("\ncosine([1,0],[1,0]) =", cosine([1, 0], [1, 0]))
    print("cosine([1,0],[0,1]) =", cosine([1, 0], [0, 1]))
