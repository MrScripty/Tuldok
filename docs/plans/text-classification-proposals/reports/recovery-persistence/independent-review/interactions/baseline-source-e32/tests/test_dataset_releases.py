import unittest
from dataset_releases import allocate
from workbench import WorkbenchError


def row(identifier, groups=None, split='unassigned', kind='text', content=None, pixels=None):
    return dict(id=identifier,groups=groups or [identifier],parents=[],source_split=split,kind=kind,
                content_hash=content or identifier,pixel_hash=pixels,source_available=True,book_id='',session_id=identifier)


class AllocationTests(unittest.TestCase):
    def test_existing_splits_preserved_and_zero_weight_rejected(self):
        rows=[row('a',split='test'),row('b'),row('c')]
        result, report=allocate(rows,rows,dict(train=80,validation=10,test=10),42)
        self.assertEqual(result['a'],'test'); self.assertEqual(set(result.values()),{'train','validation','test'})
        with self.assertRaises(WorkbenchError):allocate(rows,rows,dict(train=100,validation=0,test=0),42)

    def test_conflicting_selected_component_rejected_unrelated_not_blocking(self):
        a=row('a',['same'],split='train');b=row('b',['same'],split='test');c=row('c')
        with self.assertRaises(WorkbenchError):allocate([a],[a,b,c],dict(train=50,validation=0,test=50),42)
        assigned,_=allocate([c],[a,b,c],dict(train=100,validation=0,test=0),42)
        self.assertEqual(assigned,{'c':'train'})

    def test_decoded_duplicates_and_legacy_groups_connected(self):
        a=row('a',kind='image',pixels='same');b=row('b',kind='image',pixels='same')
        with self.assertRaises(WorkbenchError):allocate([a,b],[a,b],dict(train=50,validation=0,test=50),42)
        b['pixel_hash']='different'; a['book_id']=b['book_id']='book-one'
        with self.assertRaises(WorkbenchError):allocate([a,b],[a,b],dict(train=50,validation=0,test=50),42)

    def test_invalid_ratios_and_seed(self):
        rows=[row('a')]
        for ratios in ({'train':True,'validation':0,'test':99}, {'train':100}, {'train':99,'validation':0,'test':0}):
            with self.assertRaises(WorkbenchError):allocate(rows,rows,ratios,42)
        for seed in (-1,True,2**32):
            with self.assertRaises(WorkbenchError):allocate(rows,rows,dict(train=100,validation=0,test=0),seed)
