"""Dependency-light target/metric helpers for a one-object image detector."""
import math
import numpy as np


def box_from_mask(mask):
    a=np.asarray(mask)>0
    if a.ndim!=2:raise ValueError('mask must be two-dimensional')
    h,w=a.shape;ys,xs=np.nonzero(a)
    if not len(xs):return 0.0,[0.0]*4
    return 1.0,[float(xs.min()/w),float(ys.min()/h),float((xs.max()+1)/w),float((ys.max()+1)/h)]


def iou(a,b):
    ix=max(0.0,min(a[2],b[2])-max(a[0],b[0]));iy=max(0.0,min(a[3],b[3])-max(a[1],b[1]))
    area=lambda x:max(0.0,x[2]-x[0])*max(0.0,x[3]-x[1])
    union=area(a)+area(b)-ix*iy
    return ix*iy/union if union else 0.0


def detection_metrics(rows,threshold=0.5):
    tp=fp=fn=neg=fa=0;values=[]
    for r in rows:
        present=bool(r['present']);pred=r['probability']>=threshold
        overlap=iou(r['box'],r['target_box']) if present else 0.0
        if present:values.append(overlap)
        matched=present and pred and overlap>=0.5
        tp+=int(matched);fp+=int(pred and not matched);fn+=int(present and not matched)
        neg+=int(not present);fa+=int(not present and pred)
    return {'threshold':threshold,'true_positive_detections_iou_0_5':tp,'false_positive_detections':fp,
        'missed_objects':fn,'precision_iou_0_5':tp/(tp+fp) if tp+fp else 0.0,
        'recall_iou_0_5':tp/(tp+fn) if tp+fn else 0.0,
        'mean_iou_all_positive_images':sum(values)/len(values) if values else None,
        'empty_image_false_alarm_rate':fa/neg if neg else None,'images':len(rows)}


def self_test():
    m=np.zeros((10,20),dtype=np.uint8);m[2:6,4:14]=255
    p,b=box_from_mask(m);assert p==1 and b==[.2,.2,.7,.6]
    assert box_from_mask(np.zeros((5,5)))[0]==0
    assert abs(iou(b,b)-1)<1e-12
    assert iou([0,0,.1,.1],[.2,.2,.4,.4])==0
    r=detection_metrics([{'present':1,'probability':.9,'box':b,'target_box':b},{'present':0,'probability':.1,'box':b,'target_box':[0]*4}])
    assert r['precision_iou_0_5']==r['recall_iou_0_5']==1
    assert r['empty_image_false_alarm_rate']==0
    print('PASS normalized targets, empty masks, IoU and one-object detection metrics')
if __name__=='__main__':self_test()
