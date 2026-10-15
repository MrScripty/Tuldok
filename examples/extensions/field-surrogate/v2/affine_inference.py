"""Author-owned inference only; no training imports or host callbacks.

CLI: affine_inference.py SPECIFICATION WEIGHTS TRANSFORM INPUT OUTPUT
All state is bounded float64 NPY with allow_pickle=False. Packaging/execution
permission, immutable source capture and runtime verification belong to P5/Run.
"""
import ast
import io
import math
import struct
import json
import os
from pathlib import Path
import stat
import sys

import numpy as np

MAX_INPUT_BYTES=8*1024*1024


def read(path,maximum):
    descriptor=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    try:
        before=os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode) or before.st_nlink!=1 or not 0<before.st_size<=maximum:
            raise ValueError('Inference inputs must be bounded single-link regular files')
        chunks=[];remaining=maximum+1
        while remaining:
            chunk=os.read(descriptor,min(remaining,65536))
            if not chunk:break
            chunks.append(chunk);remaining-=len(chunk)
        raw=b''.join(chunks);after=os.fstat(descriptor)
        identity=lambda value:(value.st_dev,value.st_ino,value.st_mode,value.st_nlink,value.st_uid,
                               value.st_size,value.st_mtime_ns,value.st_ctime_ns)
        if (identity(before)!=identity(after) or identity(after)!=identity(os.stat(path,follow_symlinks=False)) or
                len(raw)!=after.st_size or len(raw)>maximum):
            raise ValueError('Inference input changed while reading')
        return raw
    finally:os.close(descriptor)


def array(path,shape):
    raw=read(path,MAX_INPUT_BYTES)
    if raw[:6]!=b'\x93NUMPY' or raw[6:8] not in (b'\x01\x00',b'\x02\x00'):
        raise ValueError('Inference requires NPY1/2 data')
    prefix=10 if raw[6:8]==b'\x01\x00' else 12
    if len(raw)<prefix:raise ValueError('Truncated NPY header')
    length=struct.unpack('<H' if prefix==10 else '<I',raw[8:prefix])[0]
    if not 1<=length<=4096 or prefix+length>len(raw):raise ValueError('Bounded NPY header required')
    try:header=ast.literal_eval(raw[prefix:prefix+length].decode('latin1').strip())
    except (ValueError,SyntaxError,RecursionError):raise ValueError('Invalid NPY literal header') from None
    if (type(header) is not dict or set(header)!={'descr','fortran_order','shape'} or
            header['descr']!='<f8' or header['fortran_order'] is not False or
            type(header['shape']) is not tuple or len(header['shape'])!=len(shape) or
            any(type(size) is not int or size!=expected for size,expected in zip(header['shape'],shape,strict=True)) or
            len(raw)!=prefix+length+math.prod(shape)*8):
        raise ValueError('Exact bounded NPY shape/payload required before allocation')
    stream=io.BytesIO(raw)
    values=np.load(stream,allow_pickle=False,max_header_size=4096)
    if (stream.tell()!=len(raw) or type(values) is not np.ndarray or values.dtype.str!='<f8' or not values.flags.c_contiguous or
            not np.isfinite(values).all() or (shape is not None and values.shape!=shape)):
        raise ValueError('Inference requires finite native C-order float64 state')
    return values


def main(specification_path,weights_path,transform_path,input_path,output_path):
    def pairs(items):
        result={}
        for key,value in items:
            if key in result:raise ValueError('Duplicate specification field')
            result[key]=value
        return result
    specification=json.loads(read(specification_path,65536),object_pairs_hook=pairs)
    expected={'format':'authored_affine_scalar_v2','input_fields':['initial'],
              'output_fields':['prediction'],'trainable_parameters':['scale','offset']}
    if specification!=expected:raise ValueError('Unsupported authored affine specification')
    weights=array(weights_path,(2,));transform=array(transform_path,(2,));initial=array(input_path,(4,4,4))
    if transform[1]<=0:
        raise ValueError('Inference field shape or fitted transform differs')
    scale,offset=weights;mean,std=transform
    prediction=scale*((initial-mean)/std)+offset
    if not np.isfinite(prediction).all():raise ValueError('Inference produced nonfinite values')
    with Path(output_path).open('xb') as handle:
        np.save(handle,np.ascontiguousarray(prediction,dtype='<f8'),allow_pickle=False)
        handle.flush();os.fsync(handle.fileno())
    print(json.dumps({'format':'authored_affine_inference_result_v1','shape_zyx':list(prediction.shape),
                      'state':'reconstructed','training_performed':False},allow_nan=False))


if __name__=='__main__':
    if len(sys.argv)!=6:raise SystemExit('Use affine_inference.py SPECIFICATION WEIGHTS TRANSFORM INPUT OUTPUT')
    main(*sys.argv[1:])
