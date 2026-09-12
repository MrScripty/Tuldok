import base64
import io
import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from PIL import Image

from app import Dataset, Conflict, validate_annotation


def image(color='beige', exif=None):
    buffer=io.BytesIO()
    options={'exif':exif} if exif else {}
    Image.new('RGB',(80,60),color).save(buffer,'JPEG',**options)
    return buffer.getvalue()


def label():
    names=['top_left','top_right','bottom_right','bottom_left']
    points=[(.1,.1),(.9,.1),(.9,.9),(.1,.9)]
    return dict(book_present=True,crop_suitable=True,corner_reference='book',corners=[
        dict(name=name,visibility='visible',x=p[0],y=p[1]) for name,p in zip(names,points)])


class DatasetTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.data=Dataset(self.tmp.name)
        self.addCleanup(self.data.close)

    def add(self,color='beige',book='book-a',session='desk',split='unassigned'):
        return self.data.add(dict(image=base64.b64encode(image(color)).decode(),filename='frame.jpg',
                                  book_id=book,session_id=session,split=split))

    def save(self,sample,annotation=None,**meta):
        return self.data.save(sample['id'],dict(book_id=sample['book_id'],session_id=sample['session_id'],
             split=meta.get('split',sample['split']),revision=sample['revision'],annotation=annotation or label()))

    def test_preserve_orient_and_export(self):
        exif=Image.Exif();exif[274]=6
        source=image(exif=exif)
        row=self.data.add(dict(image=base64.b64encode(source).decode(),filename='portrait.jpg',book_id='a',session_id='s'))
        self.assertEqual((row['width'],row['height']),(60,80))
        self.assertEqual((Path(self.tmp.name)/'images'/row['id']/'source').read_bytes(),source)
        self.save(row)
        self.add('blue')
        with self.data.export() as target, zipfile.ZipFile(target) as archive:
            exported=json.loads(archive.read('labels.jsonl'))
            self.assertEqual(exported['annotation']['corners'][0]['x'],.1)
            self.assertIn(exported['image'],archive.namelist())
            schema=json.loads(archive.read('schema.json'))
            self.assertEqual(schema['samples'],1)
            self.assertEqual(schema['unlabeled_excluded'],1)

    def test_split_groups_and_stale_saves(self):
        a=self.add()
        b=self.add('blue')
        saved=self.save(a,split='train')
        self.assertEqual(self.data.sample(b['id'])['split'],'train')
        with self.assertRaises(Conflict):
            self.save(b)
        with self.assertRaises(Conflict):
            self.save(saved,split='test')
        with self.assertRaises(Conflict):
            self.save(a)
        other=self.add('green',book='different',split='test')
        self.assertEqual(other['split'],'test')

    def test_negative_and_hidden_annotations(self):
        sample=self.add(book='')
        result=self.save(sample,dict(book_present=False,crop_suitable=False,corners=[]))
        self.assertEqual(result['annotation']['corners'],[])
        hidden=label();hidden['crop_suitable']=False
        hidden['corners'][0].update(visibility='occluded',x=None,y=None)
        self.assertEqual(validate_annotation(hidden),hidden)
        hidden['crop_suitable']=True
        with self.assertRaises(ValueError):validate_annotation(hidden)
        hidden['crop_suitable']=False;hidden['corners'][0]['x']=.2
        with self.assertRaises(ValueError):validate_annotation(hidden)

    def test_missing_crossed_and_nonfinite_coordinates(self):
        for bad in (None,float('nan'),2,True):
            annotation=label();annotation['corners'][0]['x']=bad
            with self.assertRaises(ValueError):validate_annotation(annotation)
        annotation=label();annotation['corners'][0].update(x=.95,y=.95)
        with self.assertRaises(ValueError):validate_annotation(annotation)

    def test_book_relative_corners_allow_all_rotations(self):
        for points in [((.9,.9),(.1,.9),(.1,.1),(.9,.1)),
                       ((.9,.1),(.9,.9),(.1,.9),(.1,.1)),
                       ((.1,.9),(.1,.1),(.9,.1),(.9,.9))]:
            annotation=label()
            annotation['corner_reference']='book'
            for corner,(x,y) in zip(annotation['corners'],points):
                corner.update(x=x,y=y)
            self.assertEqual(validate_annotation(annotation),annotation)
        crossed=label();crossed['corners'][0].update(x=.95,y=.95)
        with self.assertRaises(ValueError):validate_annotation(crossed)

    def test_legacy_corner_reference_is_preserved(self):
        row=self.add()
        old=label();old.pop('corner_reference')
        with self.data.db:
            self.data.db.execute('UPDATE samples SET annotation=? WHERE id=?',(json.dumps(old),row['id']))
        self.assertEqual(self.data.sample(row['id'])['annotation']['corner_reference'],'image')
        with self.data.export() as target, zipfile.ZipFile(target) as archive:
            self.assertEqual(json.loads(archive.read('labels.jsonl'))['annotation']['corner_reference'],'image')
            self.assertEqual(json.loads(archive.read('schema.json'))['version'],2)

    def test_duplicate_and_invalid_image(self):
        self.add()
        with self.assertRaises(Conflict):self.add()
        with self.assertRaises(ValueError):self.data.add(dict(image='bad',session_id='s'))
        self.assertEqual(len(self.data.rows()),1)

    def test_negative_sessions_group_and_persistence(self):
        a=self.add(book='')
        b=self.add('red',book='')
        self.save(a,dict(book_present=False,crop_suitable=False,corners=[]),split='validation')
        self.assertEqual(self.data.sample(b['id'])['split'],'validation')
        reopened=Dataset(self.tmp.name)
        try:self.assertEqual(len(reopened.rows()),2)
        finally:reopened.close()


if __name__=='__main__':
    unittest.main()
