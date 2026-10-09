"""Separate whole-mesh consumer for source-bound binary acquisition releases."""
import copy
import io
import zipfile

import numpy as np

import binary_mesh_core as core
from binary_mesh_assets import validate_bytes
from native_mesh_dataset import NativeMeshDataset, NativeMeshError, require, sha, DTYPES


class NativeBinaryMeshDataset(NativeMeshDataset):
    BUNDLE_LIMIT=core.BUNDLE_BYTES

    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        self._limitations=[item for item in self._limitations if not item.startswith(('Derived binary PLY preserves','Standalone binary embeds'))]
        self._limitations += ['Binary native bits and original authoritative source files are retained; source claims do not authenticate generation.',
            'Importable output is the complete source-bound bundle; standalone PLY omits the authoritative source and cannot be reimported by itself.']

    def _prepare_bundle(self,raw):
        result=validate_bytes(raw)
        return {'metadata':result['metadata']},None

    def _materialize(self,raw,row):
        prepared,_=self._prepare_bundle(raw)
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:binary=archive.read('mesh.ply')
        parsed=core.parse_ply(binary)
        actual=self._plyfile.PlyData.read(io.BytesIO(binary),mmap=False)
        require(not actual.text and actual.byte_order=='<' and [x.name for x in actual.elements]==['vertex','face'],'Actual binary reader schema mismatch')
        vertices=actual['vertex'].data
        require(vertices.dtype.names==tuple(p['name'] for p in parsed['properties']) and len(vertices)==parsed['vertex_count'],'Actual property count/order mismatch')
        fields={}
        for index,prop in enumerate(parsed['properties']):
            dtype=np.dtype(DTYPES[prop['dtype']]);observed=vertices[prop['name']]
            oracle=np.asarray(parsed['columns'][index],dtype=dtype)
            require(observed.dtype==dtype and observed.tobytes()==oracle.tobytes(),'Actual binary native property bits mismatch')
            fields[prop['name']]=observed.copy()
        require(actual['face'].data.dtype.names==('vertex_indices',) and len(actual['face'].data)==parsed['triangle_count'],'Actual topology count mismatch')
        dtype=np.dtype('<i4' if parsed['face_type']=='int' else '<u4');faces=actual['face'].data['vertex_indices']
        require(all(face.shape==(3,) and face.dtype==dtype for face in faces),'Actual triangle list dtype mismatch')
        observed=np.stack(faces)
        oracle=np.asarray(parsed['faces'],dtype=dtype).reshape(-1,3)
        require(observed.dtype==dtype and observed.tobytes()==oracle.tobytes(),'Actual ordered native triangle bits mismatch')
        fields['vertex_indices']=observed.copy()
        derivation={'representation':'retained source-bound binary PLY; exact authoritative files remain in original bundle',
            'format':'binary_little_endian PLY1.0','sha256':sha(binary),'bytes':len(binary),'bundle_sha256':sha(raw),
            'source':copy.deepcopy(prepared['metadata']['manifest']['source']),
            'zero_semantics':prepared['metadata']['source_evidence']['native_zero'],
            'release_sha256':self._sha,'record_id':row['id'],'revision':row['revision'],'source_revision':row['source_revision'],'split':row['split']}
        return fields,binary,derivation

    def _sample(self,index):
        sample,binary=super()._sample(index)
        sample['metadata']['schema']='native_binary_mesh_sample_v1'
        sample['metadata']['source_evidence']=copy.deepcopy(sample['metadata']['record']['mesh']['source_evidence'])
        return sample,binary

    def write_import_bundle(self,path,index=0):
        self._output_path(path);self[index]  # Revalidate all source/actual-reader bits before exposure.
        row=self._records[self._samples[index]]
        with zipfile.ZipFile(io.BytesIO(self._raw)) as archive:raw=archive.read(row['asset'])
        require(len(raw)<=core.BUNDLE_BYTES,'Importable whole mesh bundle cap exceeded')
        self._publish(path,lambda output:output.write(raw))
