"""Independent test-only data-JSON inference; imports no Tuldok source."""
import json
from pathlib import Path
import sys

import numpy as np
from scipy.special import expit, logsumexp

model = json.loads(Path(sys.argv[1]).read_bytes())
inputs = json.loads(Path(sys.argv[2]).read_bytes())['inputs']
if 'vocabulary' in model:
    from sklearn.feature_extraction.text import TfidfVectorizer
    transform = model['transform']
    vectorizer = TfidfVectorizer(vocabulary=model['vocabulary'], max_features=model['parameters']['max_features'],
        lowercase=transform['lowercase'], token_pattern=transform['token_pattern'], ngram_range=tuple(transform['ngram_range']),
        norm=transform['norm'], use_idf=transform['use_idf'], smooth_idf=transform['smooth_idf'], sublinear_tf=transform['sublinear_tf'])
    vectorizer.idf_ = np.array(model['idf'])
    scores = vectorizer.transform(inputs) @ np.array(model['feature_log_prob']).T + np.array(model['class_log_prior'])
    probabilities = np.exp(scores - logsumexp(scores, axis=1)[:, None])
else:
    features = (np.array(inputs) - np.array(model['mean'])) / np.array(model['scale'])
    scores = features @ np.array(model['coefficients']).T + np.array(model['intercepts'])
    if scores.shape[1] == 1:
        positive = expit(scores[:, 0])
        probabilities = np.column_stack((1 - positive, positive))
    else:
        probabilities = np.exp(scores - logsumexp(scores, axis=1)[:, None])
assert 'text_training' not in sys.modules and 'audio_training' not in sys.modules
print(json.dumps(probabilities.tolist(), allow_nan=False))
