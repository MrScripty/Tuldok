"""Original one-class, at-most-one-object detector. torch2.8 API, neural runtime untested."""
import argparse, json, hashlib
from pathlib import Path
import numpy as np
from PIL import Image
import torch
from torch import nn
from torch.nn import functional as F
from torch.utils.data import Dataset,DataLoader
from detector_common import box_from_mask,detection_metrics


class Detector(nn.Module):
    def __init__(self):
        super().__init__()
        self.features=nn.Sequential(nn.Conv2d(3,16,3,padding=1),nn.ReLU(),nn.MaxPool2d(2),
            nn.Conv2d(16,32,3,padding=1),nn.ReLU(),nn.MaxPool2d(2),
            nn.Conv2d(32,64,3,padding=1),nn.ReLU(),nn.MaxPool2d(2),nn.AdaptiveAvgPool2d((4,4)))
        self.head=nn.Linear(64*4*4,5)
    def forward(self,x):
        raw=self.head(self.features(x).flatten(1));z=raw[:,1:].sigmoid()
        low=torch.minimum(z[:,:2],z[:,2:]);high=torch.maximum(z[:,:2],z[:,2:])
        return raw[:,0],torch.cat([low,high],dim=1)


def image_tensor(image):
    arr=np.asarray(image.convert('RGB').resize((96,96),Image.Resampling.BILINEAR),dtype=np.float32)/255.0
    return torch.from_numpy(arr.copy()).permute(2,0,1)


class Images(Dataset):
    def __init__(self,root,split):
        self.images=sorted((root/split/'images').glob('*.png'));self.mask_root=root/split/'masks'
        if not self.images:raise ValueError(f'no images for {split}')
        self.hashes={}
        for p in self.images:
            m=self.mask_root/p.name
            if not m.exists():raise FileNotFoundError(m)
            for f in [p,m]:self.hashes[str(f.relative_to(root))]=hashlib.sha256(f.read_bytes()).hexdigest()
    def __len__(self):return len(self.images)
    def __getitem__(self,i):
        p=self.images[i]
        with Image.open(p) as im:
            original_size=im.size;x=image_tensor(im)
        with Image.open(self.mask_root/p.name) as mask:
            if mask.size!=original_size:raise ValueError('image and mask dimensions differ')
            mask=mask.convert('L')
            if not set(np.unique(np.asarray(mask))).issubset({0,255}):raise ValueError('mask must use 0 and 255')
            present,box=box_from_mask(mask)
        return x,torch.tensor(present,dtype=torch.float32),torch.tensor(box,dtype=torch.float32)


def objective(logits,boxes,present,target):
    classification=F.binary_cross_entropy_with_logits(logits,present)
    localization=(F.smooth_l1_loss(boxes,target,reduction='none').mean(1)*present).sum()/present.sum().clamp_min(1)
    return classification+5.0*localization


@torch.no_grad()
def evaluate(model,loader,device):
    model.eval();rows=[];objectness_sum=0;box_sum=0;n=0;positives=0
    for x,y,b in loader:
        x,y,b=x.to(device),y.to(device),b.to(device);logits,boxes=model(x)
        objectness_sum+=F.binary_cross_entropy_with_logits(logits,y,reduction='sum').item()
        box_sum+=(F.smooth_l1_loss(boxes,b,reduction='none').mean(1)*y).sum().item()
        positives+=int(y.sum().item());n+=len(x)
        for yy,pp,bb,tt in zip(y.cpu().tolist(),logits.sigmoid().cpu().tolist(),boxes.cpu().tolist(),b.cpu().tolist()):
            rows.append({'present':yy,'probability':pp,'box':bb,'target_box':tt})
    return {'loss':objectness_sum/n+5.0*box_sum/max(positives,1),**detection_metrics(rows)}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--data',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    p.add_argument('--epochs',type=int,default=15);p.add_argument('--batch-size',type=int,default=16)
    p.add_argument('--lr',type=float,default=.001);p.add_argument('--device',choices=['cpu','cuda'],default='cpu')
    a=p.parse_args()
    if min(a.epochs,a.batch_size)<1 or a.lr<=0:p.error('positive epochs, batch size and learning rate required')
    if a.device=='cuda' and not torch.cuda.is_available():p.error('CUDA requested but unavailable')
    if a.out.exists() and any(a.out.iterdir()):p.error('use a new empty output directory')
    manifest=json.loads((a.data/'manifest.json').read_text())
    if manifest.get('max_objects')!=1:raise ValueError('this detector requires data generated with --max-objects 1')
    torch.manual_seed(42);datasets={s:Images(a.data,s) for s in ['train','val','test']}
    loaders={s:DataLoader(ds,batch_size=a.batch_size,shuffle=s=='train',num_workers=0,
              generator=torch.Generator().manual_seed(42)) for s,ds in datasets.items()}
    m=Detector().to(a.device);opt=torch.optim.AdamW(m.parameters(),lr=a.lr,weight_decay=.0001,foreach=False)
    a.out.mkdir(parents=True,exist_ok=True)
    meta={'parameters':sum(p.numel() for p in m.parameters()),'architecture':'original_single_object_cnn_v1','class_names':['foreground object'],
          'input_size':[96,96],'channels':'RGB','scale':'divide by 255','box_format':'normalized xyxy; exclusive maximum edge',
          'threshold':.5,'max_objects':1,'dtype':'float32','torch':str(torch.__version__),
          'epochs':a.epochs,'batch_size':a.batch_size,'lr':a.lr,'box_loss_weight':5.0,'seed':42,
          'data_hashes':{s:ds.hashes for s,ds in datasets.items()}}
    (a.out/'config.json').write_text(json.dumps(meta,indent=2));best=float('inf');history=[]
    for epoch in range(a.epochs):
        m.train()
        for x,y,b in loaders['train']:
            x,y,b=x.to(a.device),y.to(a.device),b.to(a.device);opt.zero_grad(set_to_none=True)
            logits,boxes=m(x);loss=objective(logits,boxes,y,b)
            if not torch.isfinite(loss):raise FloatingPointError('nonfinite loss')
            loss.backward();torch.nn.utils.clip_grad_norm_(m.parameters(),1.0,error_if_nonfinite=True);opt.step()
        val=evaluate(m,loaders['val'],a.device);row={'epoch':epoch+1,'validation':val};history.append(row);print(json.dumps(row))
        if val['loss']<best:
            best=val['loss'];torch.save(m.state_dict(),a.out/'best.pt')
    m.load_state_dict(torch.load(a.out/'best.pt',map_location=a.device,weights_only=True))
    result={'history':history,'test':evaluate(m,loaders['test'],a.device)}
    (a.out/'metrics.json').write_text(json.dumps(result,indent=2));print(json.dumps(result['test'],indent=2))
if __name__=='__main__':main()
