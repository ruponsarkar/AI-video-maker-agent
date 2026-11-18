"""
The serial's long-term memory: everything that has happened, so episode 80 still knows what happened in episode 3.

Three parts, all in series/<slug>/memory/:
    facts.jsonl   one fact per line: {"ep": 12, "kind": "event", "text": "...", "chars": ["ram", "sita"]}
    vectors.npy   an embedding per fact (Ollama's nomic-embed-text), for "find what matters to this episode"
    state.json    the story so far, each character's current status, threads still open, how the last episode ended

Search falls back to word matching when the embedding model isn't installed (ollama pull nomic-embed-text).
"""
import json
import math
import os
import re
from collections import Counter

import numpy as np

EMBED_MODEL = "nomic-embed-text"
KINDS = ("event", "state", "relation", "place", "object", "promise", "secret", "rule")


class Memory:
    def __init__(self, series_dir):
        self.dir = os.path.join(series_dir, "memory")
        os.makedirs(self.dir, exist_ok=True)
        self.facts_path = os.path.join(self.dir, "facts.jsonl")
        self.vec_path = os.path.join(self.dir, "vectors.npy")
        self.state_path = os.path.join(self.dir, "state.json")
        self.facts = []
        if os.path.exists(self.facts_path):
            self.facts = [json.loads(x) for x in open(self.facts_path, encoding="utf-8") if x.strip()]
        self.vectors = np.load(self.vec_path) if os.path.exists(self.vec_path) else None
        if self.vectors is not None and len(self.vectors) != len(self.facts):
            self.vectors = None   # out of step: rebuilt on the next add
        self.state = json.load(open(self.state_path, encoding="utf-8")) if os.path.exists(self.state_path) else {
            "story_so_far": "", "characters": {}, "open_threads": [], "last_episode": None, "episodes": {}}

    # ---------------------------------------------------------------- embeddings
    @staticmethod
    def embed(texts):
        try:
            import ollama
            out = ollama.embed(model=EMBED_MODEL, input=[f"search_document: {t}" for t in texts])
            v = np.array(out["embeddings"], np.float32)
            return v / (np.linalg.norm(v, axis=1, keepdims=True) + 1e-9)
        except Exception:
            return None

    def _sync_vectors(self):
        if self.vectors is not None and len(self.vectors) == len(self.facts):
            return True
        v = self.embed([f["text"] for f in self.facts]) if self.facts else None
        if v is None:
            return False
        self.vectors = v
        np.save(self.vec_path, v)
        return True

    # ---------------------------------------------------------------- writing
    def forget_episode(self, ep):
        """Before an episode's memories are written again (it was edited), drop the old ones."""
        keep = [k for k, f in enumerate(self.facts) if f.get("ep") != ep]
        if len(keep) == len(self.facts):
            return
        self.facts = [self.facts[k] for k in keep]
        if self.vectors is not None:
            self.vectors = self.vectors[keep] if len(keep) else None
        self._save_facts()

    def add(self, ep, facts):
        clean = []
        for f in facts:
            text = " ".join(str(f.get("text") or "").split())
            if len(text) < 8:
                continue
            clean.append({"ep": ep, "kind": f.get("kind") if f.get("kind") in KINDS else "event", "text": text,
                          "chars": [str(c) for c in (f.get("chars") or [])][:8]})
        if not clean:
            return
        self.facts += clean
        new = self.embed([f["text"] for f in clean])
        if new is not None and (self.vectors is not None or len(self.facts) == len(clean)):
            self.vectors = new if self.vectors is None else np.vstack([self.vectors, new])
            np.save(self.vec_path, self.vectors)
        else:
            self.vectors = None
            if os.path.exists(self.vec_path):
                os.remove(self.vec_path)
        self._save_facts()

    def _save_facts(self):
        with open(self.facts_path, "w", encoding="utf-8") as f:
            for x in self.facts:
                f.write(json.dumps(x, ensure_ascii=False) + "\n")
        if self.vectors is not None:
            np.save(self.vec_path, self.vectors)

    def save_state(self):
        json.dump(self.state, open(self.state_path, "w", encoding="utf-8"), ensure_ascii=False, indent=2)

    # ---------------------------------------------------------------- reading
    def search(self, query, k=14, chars=(), before=None):
        """The facts that matter most for this query; facts about these characters count extra; recent ones too."""
        pool = [i for i, f in enumerate(self.facts) if before is None or f["ep"] < before]
        if not pool:
            return []
        latest = max(self.facts[i]["ep"] for i in pool)
        scores = None
        if self._sync_vectors():
            q = self.embed([f"search_query: {query}"])
            if q is not None:
                scores = (self.vectors[pool] @ q[0]).astype(float)
        if scores is None:   # word overlap, weighted by how rare the word is
            words = lambda s: re.findall(r"[a-zA-Zऀ-ॿ]{3,}", s.lower())
            df = Counter(w for i in pool for w in set(words(self.facts[i]["text"])))
            qw = set(words(query))
            scores = np.array([sum(math.log(1 + len(pool) / df[w]) for w in qw & set(words(self.facts[i]["text"])))
                               for i in pool], float)
            scores = scores / (scores.max() + 1e-9)
        bonus = np.array([0.08 * len(set(self.facts[i]["chars"]) & set(chars)) + 0.05 * (self.facts[i]["kind"] in ("promise", "secret", "state"))
                          + 0.06 * math.exp(-(latest - self.facts[i]["ep"]) / 4) for i in pool])
        order = np.argsort(-(scores + bonus))[:k]
        picked = sorted((pool[j] for j in order), key=lambda i: (self.facts[i]["ep"], i))
        return [self.facts[i] for i in picked]

    def context(self, query, chars=(), before=None, k=14):
        """Everything the writer needs to remember, as text."""
        st = self.state
        parts = []
        if st.get("story_so_far"):
            parts.append("STORY SO FAR:\n" + st["story_so_far"])
        last = st.get("last_episode")
        if last:
            parts.append(f"LAST EPISODE (ep {last.get('n')}): {last.get('summary', '')}\nIT ENDED WITH: {last.get('ending', '')}")
        cs = st.get("characters") or {}
        if cs:
            parts.append("WHERE EVERYONE IS NOW:\n" + "\n".join(
                f"- {cid}: {c.get('status', 'alive')}, at {c.get('where', '?')}. {c.get('notes', '')}" for cid, c in cs.items()))
        if st.get("open_threads"):
            parts.append("STORY THREADS STILL OPEN:\n" + "\n".join(f"- {x}" for x in st["open_threads"][-12:]))
        hits = self.search(query, k=k, chars=chars, before=before)
        if hits:
            parts.append("RELEVANT THINGS FROM EARLIER EPISODES:\n" + "\n".join(f"- (ep {f['ep']}) {f['text']}" for f in hits))
        return "\n\n".join(parts)
