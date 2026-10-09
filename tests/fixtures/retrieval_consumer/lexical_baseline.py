"""A TF-IDF lexical baseline. No model downloads or neural framework required."""
import argparse
import json
from pathlib import Path
from sklearn.feature_extraction.text import TfidfVectorizer
from retrieval_common import read_jsonl, retrieval_metrics
ap = argparse.ArgumentParser()
ap.add_argument("--data", default="data/retrieval")
ap.add_argument("--out", default="runs/lexical")
ap.add_argument("--split", choices=["val", "test"], default="val", help="Reserve test for final comparison after tuning")
a = ap.parse_args(); data = Path(a.data); out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
corpus, queries = [read_jsonl(data / f"{name}.jsonl") for name in ["corpus", "queries"]]
# Fitting the vocabulary of the production corpus is allowed in this fixed-corpus
# retrieval setting. No held-out query/relevance label is used to fit it.
vectorizer = TfidfVectorizer(ngram_range=(1, 2), min_df=1, norm="l2")
docs = vectorizer.fit_transform([x["text"] for x in corpus])
report = {}
for split in [a.split]:
    qs = [q for q in queries if q["split"] == split]
    scores = (vectorizer.transform([q["text"] for q in qs]) @ docs.T).toarray()
    report[split], preds = retrieval_metrics(scores, corpus, qs)
    (out / f"{split}_rankings.json").write_text(json.dumps(preds, indent=2))
(out / "metrics.json").write_text(json.dumps(report, indent=2))
print(json.dumps(report, indent=2))
