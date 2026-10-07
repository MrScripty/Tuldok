"""Reviewer-owned loopback app plus two separate bounded synthetic endpoints."""
import pathlib,sys
root=pathlib.Path('/workspace/Tuldok');sys.path[:0]=[str(root),str(root/'tests')]
import app
from fake_caption_model import start as captions
from fake_classification_model import start as classifications
caption,_,_=captions();classification,_,_=classifications()
print('CAPTION_MODEL_PORT='+str(caption.server_port),flush=True)
print('CLASSIFICATION_MODEL_PORT='+str(classification.server_port),flush=True)
try:app.main()
finally:
    caption.shutdown();caption.server_close();classification.shutdown();classification.server_close()
