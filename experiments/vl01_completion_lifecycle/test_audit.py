import csv,gzip,hashlib,json,os,shutil,tempfile,unittest
from pathlib import Path
from audit import audit
@unittest.skipUnless(os.environ.get('E11_EVIDENCE'),'set E11_EVIDENCE to test archived evidence')
class AuditTests(unittest.TestCase):
    def test_actual(self):self.assertTrue(audit(Path(os.environ['E11_EVIDENCE']))['valid'])
    def test_rehashed_false_state_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp)/'copy';shutil.copytree(os.environ['E11_EVIDENCE'],out)
            p=out/'clean/control.csv.gz'
            with gzip.open(p,'rt',encoding='utf8') as f:rows=list(csv.DictReader(f))
            rows[-1]['state']='INVALID'
            with gzip.open(p,'wt',encoding='utf8',newline='') as f:
                w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
            h=json.loads((out/'sha256.json').read_text('utf8'));h['clean/control.csv.gz']=hashlib.sha256(p.read_bytes()).hexdigest();(out/'sha256.json').write_text(json.dumps(h),encoding='utf8')
            with self.assertRaises(AssertionError):audit(out)
    def test_missing_condition_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp)/'copy';shutil.copytree(os.environ['E11_EVIDENCE'],out)
            p=out/'summary.json';v=json.loads(p.read_text('utf8'));p.write_text(json.dumps(v[:-1]),encoding='utf8')
            with self.assertRaises(AssertionError):audit(out)
if __name__=='__main__':unittest.main()
