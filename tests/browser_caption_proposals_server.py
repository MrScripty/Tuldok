"""Real application composition with a controlled image-caption endpoint."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import app
from fake_caption_model import start

server, url, _ = start()
print('CAPTION_MODEL_PORT=' + str(server.server_port), flush=True)
try:
    app.main()
finally:
    server.shutdown()
    server.server_close()
