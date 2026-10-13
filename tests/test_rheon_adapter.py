"""Optional adapter contract tests; authored wire is not native qualification."""
import io
import json
import os
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from adapters.rheon import generate, project

NATIVE = Path(os.environ['TULDOK_RHEON_BINARY']) if os.environ.get('TULDOK_RHEON_BINARY') else None
BUILD = Path(os.environ['TULDOK_RHEON_BUILD_RECEIPT']) if os.environ.get('TULDOK_RHEON_BUILD_RECEIPT') else None
NATIVE_AVAILABLE = NATIVE is not None and BUILD is not None and NATIVE.is_file() and BUILD.is_file()


def wire(frames=2, seed=100):
    def message(value):
        raw=generate.encode(value);return struct.pack('<I',len(raw))+raw
    ready={'schema':'rheon-trajectory-v1','n':8,'method':'jacobi','seed':seed,'dt':1/60,'density':1.25,
           'spacing':[1/8]*3,'face_lengths':[9*8*8]*3}
    raw=message(ready)
    for index in range(1,frames+1):
        raw+=message({'frame':index,'time':index/60,'actual_divergence_max':0,'courant':0})
        for dtype,count in [('d',512),('d',512),('f',576),('f',576),('f',576),('f',512)]:
            raw+=struct.pack('<'+dtype*count,*([-0.0]+[.25]*(count-1)))
    return raw


class AdapterTests(unittest.TestCase):
    def test_controls_closed_bounds_no_process(self):
        with patch.object(generate.subprocess,'Popen',side_effect=AssertionError('Unexpected process')):
            for values in ((True,2,100),(7,2,100),(33,2,100),(8,3,100),(8,1,-1),(8,1,2147483648)):
                with self.subTest(values=values), self.assertRaises(ValueError): generate.controls(*values)
            self.assertEqual(generate.controls(32,2,100)['method'],'jacobi')

    def test_original_payloads_and_staggered_shapes_survive_bundle(self):
        raw=wire();request=generate.controls(8,2,100)
        ready,frames=generate.decode_wire(raw,request)
        bundle=generate.scientific_bundle(raw,request,b'original build',b'original producer')
        with zipfile.ZipFile(io.BytesIO(bundle)) as archive:
            manifest=json.loads(archive.read('manifest.json'))
            self.assertEqual(archive.read('sources/wire.bin'),raw)
            self.assertEqual(archive.read('sources/build-receipt.json'),b'original build')
            self.assertEqual(len(manifest['fields']),6)
            for fi,frame in enumerate(manifest['frames']):
                for ai,array in enumerate(frame['arrays']):
                    data=archive.read(array['path']);length=struct.unpack('<H',data[8:10])[0]
                    self.assertEqual(data[10+length:],frames[fi]['arrays'][ai]['raw'])
                    self.assertIn(repr(tuple(frames[fi]['arrays'][ai]['shape_zyx'])).encode(),data[:10+length])
                    self.assertEqual(generate.sha(data),array['sha256'])
            self.assertEqual(manifest['time_units'],'native time units (unspecified)')
            self.assertEqual(manifest['fields'][0]['stage'],'preprojection RHS')

    def test_family_excludes_requested_frame_count_but_binds_seed(self):
        def family(count,seed):
            raw=generate.scientific_bundle(wire(count,seed),generate.controls(8,count,seed),b'b',b'p')
            with zipfile.ZipFile(io.BytesIO(raw)) as archive:return json.loads(archive.read('manifest.json'))['family']
        self.assertEqual(family(1,100),family(2,100));self.assertNotEqual(family(2,100),family(2,101))

    def test_native_wire_truncation_extra_bytes_bad_controls_nonfinite(self):
        original=wire();request=generate.controls(8,2,100)
        for raw in (original[:-1],original+b'x',b'\xff'*4,original.replace(b'"seed":100',b'"seed":101',1)):
            with self.assertRaises(ValueError):generate.decode_wire(raw,request)
        _ready,frames=generate.decode_wire(original,request)
        needle=frames[0]['arrays'][0]['raw'];position=original.index(needle)
        bad=original[:position]+struct.pack('<d',float('nan'))+original[position+8:]
        with self.assertRaises(ValueError):generate.decode_wire(bad,request)

    def test_special_input_refusal_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as root:
            path=Path(root)/'fifo';os.mkfifo(path)
            with self.assertRaises(ValueError):generate.capture(path,100)
            path.unlink();path.symlink_to('/etc/passwd')
            with self.assertRaises(OSError):generate.capture(path,100)
        with self.assertRaises(ValueError):generate.build_receipt(b'{}',b'not qualified')

    def test_policy_fails_before_execution_on_unsupported_loader(self):
        with patch.object(generate.subprocess,'Popen',side_effect=AssertionError('Unexpected process')):
            with self.assertRaises(ValueError):generate.native_policy(b'{}',b'wrong')
            with self.assertRaises(ValueError):generate.decode(b'{"a":1,"a":2}')

    def test_recipe_is_generic_with_native_source_and_scientific_role(self):
        definition=project.definition(b'wrapper',b'native')
        self.assertEqual(definition['native_sources'],['rheon-trajectory-probe'])
        self.assertEqual(definition['outputs'][0]['role'],'scientific_fields')
        self.assertEqual(definition['inputs'],{'build_receipt':{'max_bytes':65536}})
        self.assertEqual(definition['resources']['max_output_bytes'],16*1024*1024)

    @unittest.skipUnless(NATIVE_AVAILABLE,'Set TULDOK_RHEON_BINARY and TULDOK_RHEON_BUILD_RECEIPT to actual pinned files; no mocked acceptance')
    def test_actual_project_assembly_retains_inputs_without_execution(self):
        with tempfile.TemporaryDirectory() as root, patch.object(generate.subprocess,'Popen',side_effect=AssertionError('Assembly executed code')):
            destination=Path(root)/'project';manifest=project.assemble(NATIVE,BUILD,destination)
            self.assertEqual((destination/'rheon-trajectory-probe').read_bytes(),NATIVE.read_bytes())
            self.assertEqual((destination/'build-receipt.json').read_bytes(),BUILD.read_bytes())
            self.assertEqual((destination/'rheon-trajectory-probe').stat().st_mode&0o777,0o400)
            self.assertEqual(manifest['data'][0]['sha256'],generate.sha(BUILD.read_bytes()))
            with self.assertRaises(FileExistsError):project.assemble(NATIVE,BUILD,destination)

    @unittest.skipUnless(NATIVE_AVAILABLE,'Set TULDOK_RHEON_BINARY and TULDOK_RHEON_BUILD_RECEIPT to actual pinned files; no mocked acceptance')
    def test_actual_sealed_loader_two_frames_and_second_seed(self):
        import recipe_contract
        import scientific_fields
        native=NATIVE.read_bytes();definition=project.definition(Path(generate.__file__).read_bytes(),native)
        runtime=recipe_contract.runtime_identity()
        policy=recipe_contract.native_policies(definition,{'rheon-trajectory-probe':native},runtime)['rheon-trajectory-probe']
        with tempfile.TemporaryDirectory() as root:
            root=Path(root);policy_path=root/'policy.json';policy_path.write_bytes(generate.encode(policy))
            for seed in (100,101):
                output=root/str(seed);output.mkdir()
                receipt=generate.generate(NATIVE,BUILD,policy_path,32,2,seed,output)
                summary=scientific_fields.parse_bundle((output/'fields.zip').read_bytes())
                self.assertEqual((summary['frame_count'],summary['field_count']),(2,6))
                self.assertEqual(receipt['controls']['seed'],seed)
                self.assertIn('sealed-native',receipt['loaded_mappings']);self.assertIn('sealed-loader',receipt['loaded_mappings'])
                self.assertEqual(generate.sha((output/'wire.bin').read_bytes()),receipt['wire_sha256'])
                with zipfile.ZipFile(output/'fields.zip') as archive:
                    self.assertEqual(archive.read('sources/build-receipt.json'),BUILD.read_bytes())
