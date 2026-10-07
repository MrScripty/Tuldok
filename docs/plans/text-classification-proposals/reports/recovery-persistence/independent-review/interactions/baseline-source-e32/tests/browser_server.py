"""Browser fixture: all four providers run locally without credentials."""
import os
import sys
import tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import app
import ai
import ai_openrouter
from fake_ai import start
server, url, _ = start()
ai_openrouter.BASE_URL = url
ai.DEFAULT_MODEL = 'corners-test'
with tempfile.TemporaryDirectory() as folder:
    script = Path(__file__).with_name('fake_ai_codex.py')
    executable = Path(folder) / 'codex'
    executable.write_text('#!/usr/bin/env python3\nimport sys, runpy\nsys.path.insert(0,'+repr(str(script.parent))+')\nrunpy.run_path('+repr(str(script))+',run_name="__main__")\n')
    executable.chmod(0o755)
    os.environ['PATH'] = folder + os.pathsep + os.environ['PATH']
    print('FIXTURE_LLM_PORT=' + str(server.server_port), flush=True)
    try:
        app.main()
    finally:
        server.shutdown()
        server.server_close()
