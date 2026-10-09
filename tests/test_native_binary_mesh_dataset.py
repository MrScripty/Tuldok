"""New-profile consumer ownership/refusal/atomic output regression controls."""
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

import numpy as np
from app import Dataset
from native_mesh_dataset import NativeMeshDataset, NativeMeshError
from native_binary_mesh_dataset import NativeBinaryMeshDataset
from tests.fixtures.binary_mesh_fixture import packets
from tests.test_binary_mesh_acquisition import upload
from tests.fixtures.native_mesh_fixture import freeze
from workbench import encode
import binary_mesh_core as core


class NativeBinaryConsumer(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.path=Path(self.tmp.name)
        self.owner=Dataset(self.path/'data');self.addCleanup(self.owner.close)
        self.raw=packets()[0][1];w=self.owner.workbench;row=upload(w,self.raw)
        row=w.save(row['id'],dict(revision=1,source_revision=1,task='mesh_geometry',groups=row['groups'],
            annotation={'note':'Source and exact midpoint native geometry inspected.'},review='human_reviewed'))
        release,_=freeze(self.owner,[row],{'train':100,'validation':0,'test':0})
        self.release=self.path/'release.zip';self.release.write_bytes(release);self.hash=core.sha(release)

    def dataset(self,path=None,digest=None):
        return NativeBinaryMeshDataset(path or self.release,sha256=digest or self.hash,split='train')

    def test_new_native_fields_source_schema_fresh_values_and_importable_bundle(self):
        d=self.dataset();self.assertEqual(len(d),1);first=d[0];second=d[0]
        self.assertEqual(first['metadata']['schema'],'native_binary_mesh_sample_v1')
        self.assertEqual(first['fields']['x'].view('<u4')[0],0x3f800001)
        self.assertEqual(first['fields']['ny'].view('<u4')[0],0x3f800001)
        self.assertEqual(first['fields']['vertex_indices'].dtype,np.dtype('<i4'))
        self.assertEqual(first['fields']['y'].dtype,np.dtype('<f8'))
        first['fields']['x'][0]=9.;first['metadata']['record']['name']='changed'
        self.assertEqual(second['fields']['x'].view('<u4')[0],0x3f800001)
        self.assertNotEqual(second['metadata']['record']['name'],'changed')
        output=self.path/'reimport.zip';d.write_import_bundle(output);self.assertEqual(output.read_bytes(),self.raw)
        npz=self.path/'sample.npz';d.write_npz(npz)
        with np.load(npz,allow_pickle=False) as archive:
            self.assertEqual(archive['x'].view('<u4')[0],0x3f800001)
            self.assertIn('authoritative_source',json.loads(bytes(archive['metadata_utf8']))['record']['provenance'])

    def test_old_consumer_still_refuses_additive_profile_and_new_hash_required(self):
        with self.assertRaises(NativeMeshError):NativeMeshDataset(self.release,sha256=self.hash,split='train')
        with self.assertRaisesRegex(NativeMeshError,'SHA256 mismatch'):self.dataset(digest='0'*64)
        with self.assertRaises(NativeMeshError):NativeBinaryMeshDataset(self.release,sha256=self.hash,split='unassigned')

    def test_truncated_source_missing_family_or_source_metadata_are_refused(self):
        truncated=self.path/'bad.zip';truncated.write_bytes(self.release.read_bytes()[:-1])
        with self.assertRaises(NativeMeshError):self.dataset(truncated,core.sha(truncated.read_bytes()))
        with zipfile.ZipFile(self.release) as archive:files={n:archive.read(n) for n in archive.namelist()}
        manifest=json.loads(files['manifest.json']);del manifest['protected_components'];files['manifest.json']=encode(manifest).encode()
        stream=io.BytesIO()
        with zipfile.ZipFile(stream,'w',zipfile.ZIP_STORED) as archive:
            for name,raw in files.items():archive.writestr(zipfile.ZipInfo(name),raw)
        truncated.write_bytes(stream.getvalue())
        with self.assertRaisesRegex(NativeMeshError,'complete family proof'):self.dataset(truncated,core.sha(stream.getvalue()))

    def test_atomic_import_output_failure_and_source_aliases(self):
        d=self.dataset();destination=self.path/'output.zip';destination.write_bytes(b'previous')
        with patch('native_mesh_dataset.os.replace',side_effect=OSError('controlled replacement failure')):
            with self.assertRaises(OSError):d.write_import_bundle(destination)
        self.assertEqual(destination.read_bytes(),b'previous');self.assertFalse(list(self.path.glob('.native-mesh-*')))
        link=self.path/'alias.zip';link.symlink_to(self.release)
        with self.assertRaises(NativeMeshError):d.write_import_bundle(link)
        with self.assertRaises(NativeMeshError):d.write_import_bundle(self.release)
        self.assertEqual(core.sha(self.release.read_bytes()),self.hash)


if __name__=='__main__':unittest.main()
