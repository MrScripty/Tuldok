"""Browser fixture for the real proposal API against a controlled Pumas chat server."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import app
from fake_grounded import start
server,url,_=start()
print('GROUNDED_MODEL_PORT='+str(server.server_port),flush=True)
try:app.main()
finally:server.shutdown();server.server_close()
