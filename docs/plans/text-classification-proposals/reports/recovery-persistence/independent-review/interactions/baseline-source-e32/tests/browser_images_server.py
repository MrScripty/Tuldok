"""Real Tuldok server with controlled local image and existing VLM providers."""
import runpy
from pathlib import Path
from fake_images import start
server, url, _ = start()
print('FIXTURE_IMAGE_URL=' + url, flush=True)
try:
    runpy.run_path(str(Path(__file__).with_name('browser_server.py')), run_name='__main__')
finally:
    server.shutdown()
    server.server_close()
