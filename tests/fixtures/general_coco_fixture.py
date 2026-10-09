"""Same six retained 16x12 authored PNGs; test-only boxes/review, no human corpus."""
from image_detection_fixture import populate as retained_images, LABEL

BOXES = [dict(label='Object',x=0.5,y=1.25,width=4.5,height=3.75),
         dict(label='Object',x=15.25,y=11.25,width=0.5,height=0.25),
         dict(label='object',x=3,y=3,width=7,height=5),
         dict(label=LABEL,x=15,y=11,width=1,height=1)]


def populate(dataset):
    rows=[]
    for ordinal,row in enumerate(retained_images(dataset)):
        boxes=[dict(box) for box in BOXES] if ordinal % 2 == 0 else []
        rows.append(dataset.workbench.save(row['id'],dict(row,annotation={'boxes':boxes},
            groups=row['groups']+['coco-qa-family-'+row['source_split']],review='human_reviewed')))
    return rows


def body(rows):
    return dict(format='canonical_v1',seed=42,ratios=dict(train=34,validation=33,test=33),
        items=[{k:row[k] for k in ('id','revision','source_revision')} for row in rows])


def freeze(dataset,rows):
    request=body(rows);preview=dataset.releases.preview(request)
    assert preview['eligible'],preview
    release=dataset.releases.create(dict(request,preview_token=preview['preview_token']))
    return dataset.releases.locate(release['id']).read_bytes()
