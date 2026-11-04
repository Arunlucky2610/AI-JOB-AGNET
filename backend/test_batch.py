import unittest
from .worker import validate_batch

class BatchTests(unittest.TestCase):
    def setUp(self):
        self.snapshot={'elements':[{'id':0,'tag':'INPUT','type':'text','label':'Full name'},{'id':1,'tag':'INPUT','type':'email','label':'Email'},{'id':2,'tag':'INPUT','type':'file','label':'Resume'},{'id':3,'tag':'BUTTON','type':'submit','text':'Submit application'}]}
        self.fields={'name':'Fictional Candidate','email':'test@example.invalid'}
    def test_whole_form_batch(self):
        actions=[{'action':'fill','element_id':0,'field_key':'name'},{'action':'fill','element_id':1,'field_key':'email'},{'action':'upload_resume','element_id':2},{'action':'submit','element_id':3}]
        self.assertEqual(validate_batch({'actions':actions},self.snapshot,self.fields),actions)
    def test_unapproved_answer_rejects_whole_batch(self):
        with self.assertRaises(ValueError):validate_batch({'actions':[{'action':'fill','element_id':0,'field_key':'invented'}]},self.snapshot,self.fields)
    def test_submit_must_be_last(self):
        with self.assertRaises(ValueError):validate_batch({'actions':[{'action':'submit','element_id':3},{'action':'fill','element_id':0,'field_key':'name'}]},self.snapshot,self.fields)
    def test_fill_cannot_click_submit(self):
        with self.assertRaises(ValueError):validate_batch({'actions':[{'action':'fill','element_id':3,'field_key':'name'}]},self.snapshot,self.fields)
    def test_duplicate_target_rejected(self):
        with self.assertRaises(ValueError):validate_batch({'actions':[{'action':'fill','element_id':0,'field_key':'name'},{'action':'fill','element_id':0,'field_key':'email'}]},self.snapshot,self.fields)

if __name__=='__main__':unittest.main()
