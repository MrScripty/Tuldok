"""Real application composition with a bounded synthetic classification endpoint."""
import sys
import copy
import threading
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import app
from fake_classification_model import start

# Test-only admission instrumentation. The first named request receives a real
# HTTP 409 without reaching the model; the identical later request uses the
# unchanged application's admission path. Browser barriers control delivery.
admissions = []
refused = set()
admission_lock = threading.Lock()
original_start = app.text_classification_proposals.TextClassificationProposals.start


def instrumented_start(self, body):
    with admission_lock:
        observation = {'body': copy.deepcopy(body), 'status': None}
        admissions.append(observation)
        reject = body.get('instruction', '').startswith('dispatch-refusal-') and body.get('request_id') not in refused
        if reject:
            refused.add(body['request_id'])
            observation['status'] = 409
    if reject:
        raise app.workbench.WorkbenchError('Synthetic first admission refusal.', 'conflict', 409)
    try:
        result = original_start(self, body)
    except app.workbench.WorkbenchError as error:
        with admission_lock:
            observation['status'] = error.status
        raise
    with admission_lock:
        observation['status'] = 202
    return result


app.text_classification_proposals.TextClassificationProposals.start = instrumented_start
original_handler = app.make_handler


def instrumented_handler(dataset):
    class Handler(original_handler(dataset)):
        def do_GET(self):
            if self.path == '/test/classification-dispatch':
                with admission_lock:
                    result = copy.deepcopy(admissions)
                return self.reply({'admissions': result})
            return super().do_GET()
    return Handler


app.make_handler = instrumented_handler

server, url, _ = start()
print('CLASSIFICATION_MODEL_PORT=' + str(server.server_port), flush=True)
try:
    app.main()
finally:
    server.shutdown()
    server.server_close()
