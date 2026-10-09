"""Run the exact pinned Chapter 9 reader only, never its model/trainer/predictor.

Inputs are explicitly authored compatibility fixtures with simulated review
states, or a locally exported fixture ZIP. They are not a human-labelled corpus.
"""
import argparse
from contextlib import ExitStack
import hashlib
import io
import json
from pathlib import Path
import re
import stat
import sys
import tempfile
from unittest.mock import patch
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT/'tests/fixtures')]
from app import Dataset
from image_detection_fixture import populate
import image_detection_export as projection


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--archive', type=Path)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    source = ROOT/'tests/fixtures/train_detector.py'
    helper = source.with_name('detector_common.py')
    assert hashlib.sha256(source.read_bytes()).hexdigest() == projection.CONSUMER['sha256']
    assert hashlib.sha256(helper.read_bytes()).hexdigest() == projection.CONSUMER['helper_sha256']
    import numpy as np
    import torch
    from PIL import Image
    import train_detector as reader
    from detector_common import box_from_mask
    torch.set_num_threads(1)
    with tempfile.TemporaryDirectory(prefix='reader-only-', dir=args.output) as temporary:
        folder = Path(temporary)
        archive_path = args.archive
        if archive_path is None:
            dataset = Dataset(str(folder/'source'))
            try:
                rows = populate(dataset)
                body = dict(format=projection.FORMAT, seed=42,
                    ratios={'train':34, 'validation':33, 'test':33},
                    items=[{k:row[k] for k in ('id','revision','source_revision')} for row in rows])
                preview = dataset.releases.preview(body)
                assert preview['eligible'], preview
                release = dataset.releases.create(dict(body, preview_token=preview['preview_token']))
                archive_path = args.output/'reader-fixture.zip'
                archive_path.write_bytes(dataset.releases.locate(release['id']).read_bytes())
            finally:
                dataset.close()
        assert archive_path.stat().st_size <= projection.MAX_BYTES + 512*1024
        raw = archive_path.read_bytes()
        with zipfile.ZipFile(io.BytesIO(raw)) as packet:
            infos = packet.infolist()
            names = [info.filename for info in infos]
            assert len(names) == len(set(names)) <= 2*projection.MAX_RECORDS+2
            assert sum(info.file_size for info in infos) <= projection.MAX_BYTES
            assert all(info.compress_type == zipfile.ZIP_STORED and not info.flag_bits & 1
                       and stat.S_IFMT(info.external_attr >> 16) in (0,stat.S_IFREG) for info in infos)
            manifest = json.loads(packet.read('manifest.json'))
            assert manifest['format'] == projection.FORMAT and manifest['max_objects'] == 1
            assert manifest['consumer'] == projection.CONSUMER
            assert manifest['label_mapping'] == dict(annotation_label=manifest['foreground_label'],
                consumer_label='foreground object', consumer_class_index=0,
                positive_presence=1, negative_presence=0)
            rows = manifest['records']
            assert 1 <= len(rows) <= projection.MAX_RECORDS
            expected = {'manifest.json','README.txt'}
            for row in rows:
                assert re.fullmatch(r'[a-f0-9]{32}', row['id'])
                split = projection.SPLIT_MAPPING[row['split']]
                assert row['export_split'] == split
                assert row['asset'] == f"{split}/images/{row['id']}.png"
                assert row['mask_asset'] == f"{split}/masks/{row['id']}.png"
                assert row['native_category_id_status'] == projection.category_id_status(row)
                expected.update((row['asset'],row['mask_asset']))
                for key, digest in (('asset','asset_sha256'),('mask_asset','mask_sha256')):
                    assert hashlib.sha256(packet.read(row[key])).hexdigest() == row[digest]
            assert set(names) == expected
            data = folder/'data';data.mkdir()
            for name in names:
                target = data/name;target.parent.mkdir(parents=True,exist_ok=True)
                target.write_bytes(packet.read(name))
        records = {row['asset']:row for row in rows}
        checked = 0
        with ExitStack() as guards:
            for name in ('Detector','objective','evaluate','main'):
                guards.enter_context(patch.object(reader,name,side_effect=AssertionError('Training/model entry point is forbidden.')))
            guards.enter_context(patch.object(torch.optim,'AdamW',side_effect=AssertionError('Optimizer is forbidden.')))
            for split in ('train','val','test'):
                corpus = reader.Images(data,split)
                for index,path in enumerate(corpus.images):
                    row = records[str(path.relative_to(data))]
                    image, present, box = corpus[index]
                    assert list(image.shape) == [3,96,96] and image.dtype == torch.float32
                    assert torch.isfinite(image).all() and image.min() >= 0 and image.max() <= 1
                    assert row['review'] == 'human_reviewed' and row['task'] == 'image_detection'
                    assert row['source_available'] is True
                    assert row['content_hash'] == row['asset_sha256'] == hashlib.sha256((data/row['asset']).read_bytes()).hexdigest()
                    with Image.open(data/row['asset']) as original:
                        assert original.format == 'PNG' and original.size == (row['width'],row['height'])
                        assert hashlib.sha256(str(original.size).encode()+original.convert('RGB').tobytes()).hexdigest() == row['pixel_hash'] == row['exported_pixel_sha256']
                        expected_image = np.asarray(original.convert('RGB').resize((96,96),Image.Resampling.BILINEAR),dtype=np.float32)/255
                    assert torch.equal(image,torch.from_numpy(expected_image.copy()).permute(2,0,1))
                    # Independent canonical annotation oracle; no projection/mask_target helper.
                    boxes = row['annotation']['boxes']
                    assert len(boxes) in (0,1)
                    edges = [0,0,0,0]
                    expected_mask = np.zeros((row['height'],row['width']),dtype=np.uint8)
                    if boxes:
                        target = boxes[0]
                        assert target['label'] == manifest['foreground_label']
                        values = [target[k] for k in ('x','y','width','height')]
                        assert all(type(v) in (int,float) and np.isfinite(v) and float(v).is_integer() for v in values)
                        x,y,width,height = map(int,values)
                        assert x >= 0 and y >= 0 and width > 0 and height > 0
                        assert x+width <= row['width'] and y+height <= row['height']
                        edges = [x,y,x+width,y+height]
                        expected_mask[y:y+height,x:x+width] = 255
                    expected_presence = int(bool(boxes))
                    normalized = [edges[0]/row['width'],edges[1]/row['height'],edges[2]/row['width'],edges[3]/row['height']]
                    assert present.dtype == torch.float32 and present.item() == expected_presence
                    assert box.dtype == torch.float32 and torch.equal(box,torch.tensor(normalized,dtype=torch.float32))
                    assert row['derived_target'] == dict(present=expected_presence,pixel_xyxy=edges,normalized_xyxy=normalized)
                    with Image.open(data/row['mask_asset']) as mask:
                        assert mask.mode == 'L' and mask.size == (row['width'],row['height'])
                        assert set(mask.tobytes()) <= {0,255}
                        assert np.array_equal(np.asarray(mask),expected_mask)
                        presence, bounds = box_from_mask(mask)
                        assert presence == present.item() and torch.equal(torch.tensor(bounds,dtype=torch.float32),box)
                        assert mask.getbbox() == (tuple(row['derived_target']['pixel_xyxy']) if presence else None)
                    checked += 1
            # Actual unchanged reader rejection behavior, using a disposable copy.
            first = reader.Images(data,'train').images[0]
            with Image.open(first) as first_image: first_size = first_image.size
            mask = data/'train/masks'/first.name;original = mask.read_bytes()
            mask.unlink()
            try: reader.Images(data,'train')
            except FileNotFoundError: pass
            else: raise AssertionError('Missing mask accepted.')
            for size,value,message in [((1,1),255,'dimensions differ'),(first_size,127,'0 and 255')]:
                Image.new('L',size,value).save(mask,'PNG')
                corpus = reader.Images(data,'train')
                try: corpus[0]
                except ValueError as error: assert message in str(error), error
                else: raise AssertionError('Malformed mask accepted.')
            mask.write_bytes(original)
            for image in (data/'test/images').glob('*.png'): image.unlink()
            try: reader.Images(data,'test')
            except ValueError as error: assert 'no images' in str(error), error
            else: raise AssertionError('Empty split accepted.')
    report = dict(result='PASS',scope='Exact published reader only; authored QA annotations and automated review actions are not a human-labelled corpus.',
        consumer=projection.CONSUMER, numpy_version=np.__version__,torch_version=torch.__version__,
        release_sha256=hashlib.sha256(raw).hexdigest(),reader_records=checked,
        exact_image_and_float32_box_presence_transport=True,canonical_annotation_independent_oracle=True,source_asset_pixel_hash_dimensions_review_verified=True,actual_reader_malformed_mask_rejections=True,
        label_mapping=manifest['label_mapping'],native_category_evidence=manifest['native_category_evidence'],
        model_instantiated=False,training_executed=False,predictor_executed=False,downloads=False)
    (args.output/'reader-report.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report))


if __name__ == '__main__': main()
