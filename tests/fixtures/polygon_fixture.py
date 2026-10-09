"""Retained authored 16x12 pixels; exact QA rings/bitmap expectations, not labels."""
import copy
from image_detection_fixture import populate as retained_images, LABEL
from general_coco_fixture import body,freeze

INSTANCES = [
    dict(label='Object',points=[[1,1],[5,1],[5,5],[1,5]]),
    dict(label='object',points=[[1.25,1.25],[6.75,1.25],[6.75,2.75],[2.75,2.75],[2.75,6.75],[1.25,6.75]]),
    dict(label=LABEL,points=[[1,1],[5,1],[1,5]]),
    dict(label='Object',points=[[15.25,11.25],[15.375,11.25],[15.375,11.375],[15.25,11.375]])]


def populate(dataset):
    rows=[]
    for index,row in enumerate(retained_images(dataset)):
        rows.append(dataset.workbench.save(row['id'],dict(row,task='image_segmentation',
            annotation={'instances':copy.deepcopy(INSTANCES) if index%2==0 else []},
            groups=row['groups']+['polygon-qa-family-'+row['source_split']],review='human_reviewed')))
    return rows


def expected_bitmap(points,width,height):
    """Hand-authored expected bits, independent of projection/mask code."""
    index=next((i for i,target in enumerate(INSTANCES) if target['points']==points),None)
    if index is None:return None
    result=[[0 for _ in range(width)] for _ in range(height)]
    pixels=({(x,y) for y in range(1,5) for x in range(1,5)},
            {(x,y) for y in range(1,7) for x in range(1,7) if x<3 or y<3},
            {(1,1),(2,1),(3,1),(1,2),(2,2),(1,3)},set())[index]
    for x,y in pixels:result[y][x]=1
    return result
