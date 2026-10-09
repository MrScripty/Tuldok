"""Actual app with authored QA source data; no model calls or human-label claim."""
from pathlib import Path
import sys
sys.path[:0]=[str(Path(__file__).resolve().parents[1]),str(Path(__file__).resolve().parent/'fixtures')]
from app import Dataset,main
from polygon_fixture import populate,freeze

if __name__=='__main__':
    destination=Path(sys.argv[sys.argv.index('--data')+1])
    if '--empty' in sys.argv:sys.argv.remove('--empty')
    else:
        source=Dataset(destination.parent/'native-source')
        try:(destination.parent/'native.zip').write_bytes(freeze(source,populate(source)))
        finally:source.close()
        target=Dataset(destination)
        try:target.workbench.import_asset(dict(kind='text',text='Unrelated retained draft source',name='Unrelated draft',groups=['unrelated'],rights='Authored QA fixture'))
        finally:target.close()
    main()
