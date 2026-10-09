import json
from pathlib import Path
import numpy as np


def read_jsonl(path):
    return [json.loads(line) for line in Path(path).read_text().splitlines() if line.strip()]


def retrieval_metrics(scores, corpus, queries, k=5):
    if len(queries) == 0:
        raise ValueError("No queries to evaluate")
    if scores.shape != (len(queries), len(corpus)):
        raise ValueError("Score matrix does not align with corpus and queries")
    ids = [d["doc_id"] for d in corpus]
    if len(set(ids)) != len(ids):
        raise ValueError("Duplicate corpus IDs")
    ranking = np.argsort(-scores, axis=1, kind="stable")
    recall, reciprocal, ndcg, predictions = [], [], [], []
    for q, order in zip(queries, ranking):
        relevant = set(q["relevant_doc_ids"])
        if not relevant or not relevant <= set(ids):
            raise ValueError("Missing or unknown relevance judgments")
        top = [ids[i] for i in order[:k]]
        hits = np.array([d in relevant for d in top], dtype=float)
        recall.append(float(hits.sum() / len(relevant)))
        ranks = np.flatnonzero(hits)
        reciprocal.append(float(1 / (ranks[0] + 1)) if len(ranks) else 0.)
        discounts = 1 / np.log2(np.arange(len(top)) + 2)
        ideal = discounts[:min(len(relevant), k)].sum()
        ndcg.append(float((hits * discounts).sum()/ideal))
        predictions.append({"query_id": q["query_id"], "top_doc_ids": top})
    return {f"recall@{k}": float(np.mean(recall)), f"mrr@{k}": float(np.mean(reciprocal)),
            f"ndcg@{k}": float(np.mean(ndcg)), "queries": len(queries)}, predictions
