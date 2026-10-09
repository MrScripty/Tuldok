"""Actual exporter input from authored QA images/test review states, no human corpus."""
from pathlib import Path
import sys
sys.path[:0]=[str(Path(__file__).resolve().parents[1]),str(Path(__file__).resolve().parent/'fixtures')]
from app import Dataset, main
from image_detection_fixture import populate, OTHER_LABEL

if __name__=='__main__':
    destination=Path(sys.argv[sys.argv.index('--data')+1])
    source=Dataset(str(destination.parent/'native-source'))
    try:
        rows=populate(source)
        # Keep six retained images; a second original category makes the selected
        # foreground category2. The unrelated positive stays unselected/draft.
        other=rows[2]
        rows[2]=source.workbench.save(other['id'],dict(other,
            annotation={'boxes':[dict(other['annotation']['boxes'][0],label=OTHER_LABEL)]},review='human_reviewed'))
        r=rows[0]
        boxes=[dict(r['annotation']['boxes'][0],x=14.5,width=1.5)]
        rows[0]=source.workbench.save(r['id'],dict(revision=r['revision'],source_revision=r['source_revision'],
            task=r['task'],annotation={'boxes':boxes},groups=r['groups'],review='human_reviewed'))
        body=dict(format='canonical_v1',seed=42,ratios={'train':34,'validation':33,'test':33},
            items=[{k:r[k] for k in ('id','revision','source_revision')} for r in rows])
        preview=source.releases.preview(body);assert preview['eligible'],preview
        release=source.releases.create(dict(body,preview_token=preview['preview_token']))
        (destination.parent/'native.zip').write_bytes(source.releases.locate(release['id']).read_bytes())
    finally:source.close()
    target=Dataset(str(destination))
    try:target.workbench.import_asset(dict(kind='text',text='Preserve unrelated editor.',name='Unrelated text',groups=['unrelated-source'],rights='Authored'))
    finally:target.close()
    main()
