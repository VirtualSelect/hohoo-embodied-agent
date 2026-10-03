import gzip,json,os,shutil,tempfile,unittest,hashlib
from pathlib import Path
from audit import audit
@unittest.skipUnless(os.environ.get('SERIES_EVIDENCE'),'set SERIES_EVIDENCE to a completed run')
class EvidenceMutation(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)/'evidence';shutil.copytree(os.environ['SERIES_EVIDENCE'],self.root)
    def tearDown(self):self.tmp.cleanup()
    def test_actual(self):self.assertTrue(audit(self.root)['valid'])
    def test_hash_tamper(self):
        p=self.root/'E8--clean--hold/summary.json';p.write_text('{}')
        with self.assertRaisesRegex(ValueError,'hash'):audit(self.root)
    def test_false_summary_rehashed(self):
        rows=json.loads((self.root/'summary.json').read_text());rows[0]['placement']=False
        (self.root/'summary.json').write_text(json.dumps(rows));p=self.root/'E8--clean--hold/summary.json';p.write_text(json.dumps(rows[0]))
        h=json.loads((self.root/'sha256.json').read_text());h[p.relative_to(self.root).as_posix()]=hashlib.sha256(p.read_bytes()).hexdigest();(self.root/'sha256.json').write_text(json.dumps(h))
        with self.assertRaisesRegex(ValueError,'placement'):audit(self.root)
    def test_missing_matrix_cell(self):
        rows=json.loads((self.root/'summary.json').read_text());(self.root/'summary.json').write_text(json.dumps(rows[:-1]))
        with self.assertRaisesRegex(ValueError,'matrix'):audit(self.root)
if __name__=='__main__':unittest.main()
