"""
Match a question to a curated answer in faq.md.

Answers are returned verbatim, never generated. Matching embeds the heading
and every `asks` phrasing with all-MiniLM-L6-v2 and takes the best cosine
per entry. If the model can't load, it falls back to word overlap.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)

FAQ_PATH = Path(__file__).parent / "faq.md"
EMBED_MODEL = "all-MiniLM-L6-v2"
PRAYERS = ("fajr", "dhuhr", "asr", "maghrib", "isha")

# Scores at or above ACCEPT answer directly; between SUGGEST and ACCEPT
# offer "did you mean" choices; below SUGGEST say what the bot can answer.
ACCEPT = 0.55
SUGGEST = 0.40
# A question naming a prayer prefers entries tagged with it.
TAG_BONUS = 0.08
TAG_PENALTY = 0.12


@dataclass
class Entry:
    id: str
    title: str
    answer: str
    sources: str = ""
    prayers: set[str] = field(default_factory=set)
    asks: list[str] = field(default_factory=list)


def parse_faq(text: str) -> list[Entry]:
    entries = []
    for block in re.split(r"^## ", text, flags=re.MULTILINE)[1:]:
        title, _, rest = block.partition("\n")
        meta, body = {}, []
        lines = rest.split("\n")
        i = 0
        while i < len(lines) and re.match(r"^(id|prayers|asks|sources):", lines[i]):
            k, _, v = lines[i].partition(":")
            meta[k] = v.strip()
            i += 1
        body = "\n".join(lines[i:]).strip()
        entries.append(Entry(
            id=meta["id"],
            title=title.strip(),
            answer=body,
            sources=meta.get("sources", ""),
            prayers={p.strip() for p in meta.get("prayers", "").split(",") if p.strip()},
            asks=[a.strip() for a in meta.get("asks", "").split("|") if a.strip()],
        ))
    return entries


def _words(s: str) -> set[str]:
    stop = {"the", "a", "an", "is", "are", "of", "in", "to", "do", "does", "i", "can",
            "how", "what", "when", "it", "for", "and", "or", "be", "my", "me", "there"}
    return {w for w in re.findall(r"[a-z']+", s.lower()) if w not in stop}


class FAQ:
    def __init__(self, path: Path = FAQ_PATH, use_model: bool = True) -> None:
        self.entries = parse_faq(path.read_text(encoding="utf-8"))
        self.by_id = {e.id: e for e in self.entries}
        self._owner: list[int] = []
        phrasings: list[str] = []
        for idx, e in enumerate(self.entries):
            for p in [e.title, *e.asks]:
                phrasings.append(p)
                self._owner.append(idx)
        self._phrasings = phrasings
        self._model = None
        self._matrix = None
        if use_model:
            try:
                from sentence_transformers import SentenceTransformer
                self._model = SentenceTransformer(EMBED_MODEL)
                self._matrix = self._model.encode(phrasings, normalize_embeddings=True)
            except Exception as e:
                logger.warning("embedding model unavailable, using word overlap: %s", e)
                self._model = None

    @property
    def mode(self) -> str:
        return "embeddings" if self._model is not None else "keywords"

    def _raw_scores(self, question: str) -> list[float]:
        best = [0.0] * len(self.entries)
        if self._model is not None:
            q = self._model.encode([question], normalize_embeddings=True)[0]
            sims = self._matrix @ q
            for owner, s in zip(self._owner, sims):
                best[owner] = max(best[owner], float(s))
        else:
            qw = _words(question)
            for owner, p in zip(self._owner, self._phrasings):
                pw = _words(p)
                if qw and pw:
                    best[owner] = max(best[owner], len(qw & pw) / len(qw | pw))
        return best

    def rank(self, question: str, prayers: set[str] | None = None) -> list[tuple[float, Entry]]:
        prayers = prayers or set()
        scored = []
        for s, e in zip(self._raw_scores(question), self.entries):
            if prayers and e.prayers:
                s += TAG_BONUS if prayers & e.prayers else -TAG_PENALTY
            scored.append((s, e))
        scored.sort(key=lambda t: -t[0])
        return scored

    def suggestions(self, n: int = 4) -> list[str]:
        picks = ["five-daily", "asr-time", "witr", "forbidden-times"]
        return [self.by_id[i].title for i in picks if i in self.by_id][:n]
