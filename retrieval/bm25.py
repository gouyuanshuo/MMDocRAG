"""Okapi BM25 over a small in-memory collection.

Written out rather than pulled in as a dependency for two reasons. The corpus
is OCR-augmented, so tokenisation has to be under this project's control and
identical to the one retrieval/corpus.py wrote the index with. And retrieval
here is within a single document -- 65 pages on average -- so the per-query cost
is trivial and the machinery a library would bring is not needed.

Standard parameterisation, k1 = 1.5 and b = 0.75. No stemming and no stopword
list: both are extra choices that would need their own ablation, and BM25's idf
already discounts terms that appear on every page of a document.

    bm25 = BM25([tokenize(t) for t in page_texts])
    order = bm25.rank(tokenize(question))
"""

import math
from collections import Counter

import numpy as np

K1 = 1.5
B = 0.75


class BM25:
    def __init__(self, corpus_tokens, k1=K1, b=B):
        self.k1, self.b = k1, b
        self.n = len(corpus_tokens)
        self.lens = np.asarray([len(d) for d in corpus_tokens], dtype=np.float64)
        self.avglen = self.lens.mean() if self.n and self.lens.sum() else 1.0
        if self.avglen == 0:
            self.avglen = 1.0

        self.tf = [Counter(d) for d in corpus_tokens]
        df = Counter()
        for counts in self.tf:
            df.update(counts.keys())
        # Robertson/Sparck-Jones idf with the +1 that keeps it non-negative;
        # without it a term present in more than half the pages scores below
        # zero and actively pushes its own pages down the ranking.
        self.idf = {t: math.log(1 + (self.n - n_t + 0.5) / (n_t + 0.5))
                    for t, n_t in df.items()}

    def scores(self, query_tokens):
        s = np.zeros(self.n, dtype=np.float64)
        norm = self.k1 * (1 - self.b + self.b * self.lens / self.avglen)
        for term in query_tokens:
            idf = self.idf.get(term)
            if idf is None:
                continue
            freqs = np.asarray([tf.get(term, 0) for tf in self.tf], dtype=np.float64)
            s += idf * (freqs * (self.k1 + 1)) / (freqs + norm)
        return s

    def rank(self, query_tokens):
        """Indices best-first. Ties break on index, so the order is stable."""
        s = self.scores(query_tokens)
        return np.lexsort((np.arange(self.n), -s)), s
