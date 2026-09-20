"""
ai/embeddings.py — Semantic search over tasks/projects (PRD Milestone 4, §63
"Semantic Memory").

This was a docstring-only stub; ai_coach_service._find_referenced_task
matched tasks by literal word overlap instead ("real semantic match is AI
Memory territory (ai/embeddings.py, not yet built)" — noted directly in
that module's comments). This fills that gap in.

Two backends, tried in order:

1. sentence-transformers (already in requirements.txt) + cosine similarity,
   when a local embedding model is available. This is the "real" semantic
   backend -- it matches "the CV assignment" to a task titled "Finish
   resume for internship" on meaning, not shared words.
2. TF-IDF + cosine similarity (scikit-learn), used whenever the
   sentence-transformers model hasn't been downloaded yet or the package
   isn't importable for any reason.

BrainDUMP is local-first: the embedding model is downloaded once (like an
Ollama model pull) and then works offline. Until that download has
happened -- or on a machine where it's skipped entirely -- semantic
matching should still work, just with a cheaper backend, rather than
crashing or silently reverting to the old word-overlap heuristic. This
mirrors the graceful-degradation pattern ai/ollama_client.py already uses
for the LLM itself (OllamaError -> a clear message, never a crash).

FAISS (also in requirements.txt) is intentionally not used here: it's
built for indexing thousands-to-millions of vectors with fast approximate
search. BrainDUMP is single-user with, realistically, dozens to a few
hundred active tasks -- re-embedding and brute-force cosine-comparing the
full candidate set on every query is single-digit milliseconds and needs
no persisted index, no incremental-update logic, and no staleness risk
from a cached index missing a task that was just edited.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Optional, Sequence

logger = logging.getLogger(__name__)

_MODEL_NAME = "all-MiniLM-L6-v2"

_sentence_model = None
_sentence_model_load_attempted = False


def _get_sentence_model():
    """Lazily load the sentence-transformers model, at most once per
    process. Returns None (and logs at info level, not warning -- this is
    an expected, handled case, not an error) if the package or model
    weights aren't available."""
    global _sentence_model, _sentence_model_load_attempted
    if _sentence_model_load_attempted:
        return _sentence_model
    _sentence_model_load_attempted = True
    try:
        from sentence_transformers import SentenceTransformer

        _sentence_model = SentenceTransformer(_MODEL_NAME)
        logger.info("embeddings: loaded sentence-transformers model %s", _MODEL_NAME)
    except Exception as exc:  # noqa: BLE001 - any load failure -> fall back
        logger.info(
            "embeddings: sentence-transformers model unavailable (%s); "
            "falling back to TF-IDF for semantic matching",
            exc,
        )
        _sentence_model = None
    return _sentence_model


@dataclass
class ScoredMatch:
    index: int
    score: float


def _word_overlap_fallback(query: str, corpus: Sequence[str]) -> Optional[int]:
    """Last-resort match if even scikit-learn's TF-IDF path fails (should
    only happen if scikit-learn itself isn't importable, which
    requirements.txt guards against). Same heuristic the coach used before
    this module existed -- kept only as a floor, not a target."""
    query_words = {w.lower() for w in re.findall(r"[a-zA-Z]{4,}", query)}
    best_idx, best_overlap = None, 0
    for i, text in enumerate(corpus):
        text_words = {w.lower() for w in re.findall(r"[a-zA-Z]{4,}", text)}
        overlap = len(query_words & text_words)
        if overlap > best_overlap:
            best_idx, best_overlap = i, overlap
    return best_idx if best_overlap > 0 else None


class SemanticIndex:
    """
    Semantic search over a small, changing corpus. Rebuilt fresh on every
    query rather than persisted/incrementally maintained -- see module
    docstring for why that's the right tradeoff at this scale.
    """

    def __init__(self, corpus: Sequence[str]):
        self._corpus = list(corpus)
        self.backend = "none"
        self._vectors = None
        self._vectorizer = None

        if not self._corpus:
            return

        model = _get_sentence_model()
        if model is not None:
            try:
                self._vectors = model.encode(self._corpus, normalize_embeddings=True)
                self.backend = "sentence-transformers"
                return
            except Exception as exc:  # noqa: BLE001
                logger.warning("embeddings: encode() failed, falling back to TF-IDF (%s)", exc)

        try:
            from sklearn.feature_extraction.text import TfidfVectorizer

            self._vectorizer = TfidfVectorizer(stop_words="english", min_df=1)
            self._vectors = self._vectorizer.fit_transform(self._corpus)
            self.backend = "tfidf"
        except Exception as exc:  # noqa: BLE001
            logger.warning("embeddings: TF-IDF fallback also failed (%s)", exc)
            self.backend = "none"

    def query(self, text: str, top_k: int = 1, min_score: float = 0.15) -> list[ScoredMatch]:
        if self.backend == "none":
            idx = _word_overlap_fallback(text, self._corpus)
            return [ScoredMatch(index=idx, score=1.0)] if idx is not None else []

        import numpy as np

        if self.backend == "sentence-transformers":
            model = _get_sentence_model()
            q_vec = model.encode([text], normalize_embeddings=True)[0]
            sims = self._vectors @ q_vec
        else:  # tfidf
            q_vec = self._vectorizer.transform([text])
            sims = (self._vectors @ q_vec.T).toarray().ravel()

        order = np.argsort(-sims)[:top_k]
        return [ScoredMatch(index=int(i), score=float(sims[i])) for i in order if sims[i] >= min_score]


def find_best_task_match(query: str, tasks: Sequence, min_score: float = 0.15):
    """
    Semantic replacement for the coach's old word-overlap task matcher.
    Embeds each candidate task as "title. description" and returns the
    closest match to a free-text query (e.g. "the CV assignment", "my
    internship report"), or None if nothing clears min_score.
    """
    if not tasks:
        return None

    corpus = [f"{t.title}. {t.description or ''}".strip() for t in tasks]
    index = SemanticIndex(corpus)
    matches = index.query(query, top_k=1, min_score=min_score)
    if not matches:
        return None
    return tasks[matches[0].index]
