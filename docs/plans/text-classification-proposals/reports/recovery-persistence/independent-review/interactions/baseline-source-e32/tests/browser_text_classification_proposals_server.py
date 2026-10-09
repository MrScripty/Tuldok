"""Real application composition with a bounded synthetic classification endpoint."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import app
from fake_classification_model import start

server, url, _ = start()
print('CLASSIFICATION_MODEL_PORT=' + str(server.server_port), flush=True)
try:
    app.main()
finally:
    server.shutdown()
    server.server_close()
