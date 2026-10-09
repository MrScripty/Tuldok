"""Retained authored PNGs and QA boxes only; actual local app, no models."""
from pathlib import Path
import sys
sys.path[:0]=[str(Path(__file__).resolve().parents[1]),str(Path(__file__).resolve().parent/'fixtures')]
from app import Dataset,main
from general_coco_fixture import populate,freeze,BOXES
import json

if __name__=='__main__':
    destination=Path(sys.argv[sys.argv.index('--data')+1])
    empty='--empty' in sys.argv
    if empty:sys.argv.remove('--empty')
    else:
        source=Dataset(destination.parent/'native-source')
        try:(destination.parent/'native.zip').write_bytes(freeze(source,populate(source)))
        finally:source.close()
        (destination.parent/'boxes.json').write_text(json.dumps(BOXES))
        target=Dataset(destination)
        try:target.workbench.import_asset(dict(kind='text',text='Unrelated draft source',name='Unrelated text',groups=['unrelated'],rights='Authored QA fixture'))
        finally:target.close()
    main()
