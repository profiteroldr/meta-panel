import io, os, sys, tempfile, unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from analytics import *
from werkzeug.security import generate_password_hash
_temp=tempfile.TemporaryDirectory()
os.environ.update(DATA_DIR=_temp.name,SECRET_KEY='test-only-'*8,ADMIN_PASSWORD_HASH=generate_password_hash('test-password-123'),COOKIE_SECURE='false')
from app import app
ROOT=Path(__file__).resolve().parents[1]
class AnalyticsTests(unittest.TestCase):
    def rows(self):
        df=read_file((ROOT/'ornek_meta.csv').read_bytes(),'test.csv')
        return normalize(df,guess(df.columns),'tr','TRY','')[0]
    def test_weighted_cpm(self):
        rows=self.rows(); m=metrics(rows)
        self.assertAlmostEqual(m['cpm'],1663/153721*1000)
        self.assertAlmostEqual(metrics(rows[:1])['cpm'],513/51721*1000)
    def test_locale(self):
        self.assertEqual(number('1.234,56','tr'),1234.56)
        self.assertEqual(number('1,234.56','en'),1234.56)
        self.assertEqual(number(1234.56,'tr'),1234.56)
        self.assertIsNone(number('-','tr'))
        with self.assertRaises(ValueError): number('nan','en')
    def test_missing_and_zero(self):
        r=self.rows(); r[0]['clicks']=None
        self.assertIsNone(metrics(r)['cpc'])
        r=self.rows(); r[0]['impressions']=0
        self.assertIsNone(metrics(r[:1])['cpm'])
    def test_mixed(self):
        r=self.rows(); r[0]['result_type']='Purchase'
        self.assertIsNone(metrics(r)['results'])
        r[0]['currency']='USD'
        with self.assertRaises(ValueError): metrics(r)
    def test_dates(self):
        r=self.rows(); self.assertEqual(len(series(r,'daily')),2)
        self.assertEqual(len(series(r,'monthly')),1)
        r[0]['end']='2026-10-31'; self.assertEqual(series(r,'daily'),[])
        selected,excluded=filter_rows(r,'2026-10-01','2026-10-02')
        self.assertEqual(excluded,1); self.assertEqual(len(selected),2)
    def test_summary(self):
        df=pd.DataFrame({'Campaign name':['A','Total'],'Amount spent':[10,10],'Impressions':[100,100]})
        r,n=normalize(df,guess(df.columns),'en','TRY','Messages')
        self.assertEqual(n,1); self.assertEqual(metrics(r)['spend'],10)
class FlowTests(unittest.TestCase):
    def test_no_lockout(self):
        from app import db
        import time
        with db() as conn:
            conn.execute('INSERT OR REPLACE INTO attempts VALUES(?,?,?)',('admin',5,time.time()+900))
        c=app.test_client(); c.get('/login')
        with c.session_transaction() as sess: token=sess['csrf']
        for _ in range(8):
            r=c.post('/login',data={'csrf':token,'username':'admin','password':'wrong'})
            self.assertEqual(r.status_code,200)
            self.assertIn('Kullanıcı adı veya şifre hatalı.'.encode(),r.data)
        self.assertEqual(c.get('/').status_code,302)
        r=c.post('/login',data={'csrf':token,'username':'admin','password':'test-password-123'})
        self.assertEqual(r.status_code,302)
        self.assertEqual(c.get('/').status_code,200)

    def test_full_flow(self):
        app.config['TESTING']=True; c=app.test_client()
        self.assertEqual(c.get('/').status_code,302); c.get('/login')
        with c.session_transaction() as s: token=s['csrf']
        self.assertEqual(c.post('/login',data={'username':'admin','password':'test-password-123'}).status_code,400)
        self.assertEqual(c.post('/login',data={'csrf':token,'username':'admin','password':'test-password-123'}).status_code,302)
        self.assertEqual(c.get('/').status_code,200)
        with c.session_transaction() as s: token=s['csrf']
        payload=(ROOT/'ornek_meta.csv').read_bytes()
        self.assertEqual(c.post('/upload',data={'csrf':token,'file':(io.BytesIO(payload),'test.csv')}).status_code,200)
        df=read_file(payload,'test.csv'); data=guess(df.columns)
        data.update(csrf=token,customer='Test',title='Test Rapor',locale='tr',default_currency='TRY',level='Kampanya')
        response=c.post('/import',data=data); self.assertEqual(response.status_code,302)
        location=response.headers['Location']; rid=location.split('/')[-1].split('?')[0]
        response=c.get(location); self.assertEqual(response.status_code,200)
        self.assertIn('1.663,00'.encode(),response.data)
        self.assertEqual(c.get('/report/'+rid+'?start=2030-01-01').status_code,200)
        self.assertEqual(c.get('/export/'+rid).status_code,200)
        c.post('/upload',data={'csrf':token,'file':(io.BytesIO(payload),'test.csv')})
        self.assertEqual(c.post('/import',data=data).status_code,409)
        self.assertEqual(c.post('/delete/'+rid,data={'csrf':token,'confirm':'yes'}).status_code,302)
        self.assertEqual(c.get('/report/'+rid).status_code,404)
        self.assertEqual(c.post('/logout',data={'csrf':token}).status_code,302)
        self.assertEqual(c.get('/export/'+rid).status_code,302)
if __name__=='__main__': unittest.main()
