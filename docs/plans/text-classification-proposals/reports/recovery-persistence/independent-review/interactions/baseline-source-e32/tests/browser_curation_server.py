"""Authored local fixtures for exact current metadata diagnostics; no model calls."""
import argparse
import base64
import io
import sys
from pathlib import Path
from PIL import Image, PngImagePlugin

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import app
parser=argparse.ArgumentParser(add_help=False);parser.add_argument('--data',required=True)
args,_=parser.parse_known_args();dataset=app.Dataset(args.data);w=dataset.workbench
try:
    for i in range(41):
        w.import_asset(dict(kind='text',name=f'Fictional {i:02}',text=f'Authored fictional source {i}',groups=['fictional'],rights='unknown'))
    negative=w.import_asset(dict(kind='text',name='Reviewed negative',text='Fictional negative statement',groups=['negative'],rights='Authored fixture'))
    w.save(negative['id'],dict(negative,task='text_entities',annotation={'spans':[]},review='human_reviewed'))
    for name in ['Duplicate A','Duplicate B','Deleted source']:
        out=io.BytesIO();info=PngImagePlugin.PngInfo();info.add_text('fixture',name)
        Image.new('RGB',(16,16),'red' if name.startswith('Duplicate') else 'blue').save(out,'PNG',pnginfo=info)
        row=w.import_asset(dict(kind='image',name=name,image=base64.b64encode(out.getvalue()).decode(),groups=['images'],rights='unknown'))
        if name=='Deleted source': dataset.delete(row['id'],{'revision':row['source_revision']})
finally:dataset.close()
app.main()
