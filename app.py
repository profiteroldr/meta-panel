import os, json, sqlite3, secrets, hashlib, hmac, time, io, csv
from datetime import timedelta
from pathlib import Path
from functools import wraps
from flask import Flask, request, session, redirect, url_for, render_template, abort, send_file
from werkzeug.security import check_password_hash
from analytics import FIELDS, guess, read_file, normalize, metrics, filter_rows, series

DATA=Path(os.environ.get('DATA_DIR','data')); DATA.mkdir(parents=True,exist_ok=True)
app=Flask(__name__)
secret=os.environ.get('SECRET_KEY','')
password_hash=os.environ.get('ADMIN_PASSWORD_HASH','')
if len(secret)<32 or not password_hash: raise RuntimeError('SECRET_KEY (en az 32 karakter) ve ADMIN_PASSWORD_HASH ayarlanmalı.')
app.config.update(SECRET_KEY=secret,MAX_CONTENT_LENGTH=21*1024*1024,SESSION_COOKIE_HTTPONLY=True,SESSION_COOKIE_SAMESITE='Lax',SESSION_COOKIE_SECURE=os.environ.get('COOKIE_SECURE','true').lower()=='true',PERMANENT_SESSION_LIFETIME=timedelta(hours=8))

def db():
    c=sqlite3.connect(DATA/'reports.sqlite3',timeout=20); c.row_factory=sqlite3.Row; return c
with db() as c:
    c.executescript('''CREATE TABLE IF NOT EXISTS reports(id TEXT PRIMARY KEY, customer TEXT, title TEXT, filename TEXT, level TEXT, digest TEXT, rows TEXT, created TEXT DEFAULT CURRENT_TIMESTAMP, UNIQUE(customer,digest));
CREATE TABLE IF NOT EXISTS attempts(key TEXT PRIMARY KEY, failures INTEGER, until REAL);
CREATE TABLE IF NOT EXISTS pending(id TEXT PRIMARY KEY, filename TEXT, content BLOB, created REAL);''')

def csrf():
    if 'csrf' not in session: session['csrf']=secrets.token_hex(32)
    return session['csrf']
app.jinja_env.globals['csrf']=csrf
@app.before_request
def protect():
    if request.method=='POST' and not hmac.compare_digest(session.get('csrf','!'),request.form.get('csrf','')): abort(400,'Form süresi doldu. Sayfayı yenileyin.')
@app.after_request
def headers(r):
    r.headers['X-Content-Type-Options']='nosniff'; r.headers['X-Frame-Options']='DENY'; r.headers['Referrer-Policy']='same-origin'; r.headers['Cache-Control']='no-store'
    r.headers['Content-Security-Policy']="default-src 'self'; style-src 'self' 'unsafe-inline'; script-src 'self'; form-action 'self'; frame-ancestors 'none'"
    return r

def auth(fn):
    @wraps(fn)
    def wrapper(*a,**kw):
        if not session.get('auth'): return redirect(url_for('login'))
        return fn(*a,**kw)
    return wrapper

@app.route('/healthz')
def health(): return {'status':'ok'}
@app.route('/login',methods=['GET','POST'])
def login():
    error=None
    if request.method=='POST':
        valid_user=hmac.compare_digest(request.form.get('username','').encode(),os.environ.get('ADMIN_USERNAME','admin').encode())
        valid_pass=check_password_hash(password_hash,request.form.get('password',''))
        if valid_user and valid_pass:
            session.clear(); session['auth']=True; session.permanent=True
            return redirect('/')
        error='Kullanıcı adı veya şifre hatalı.'
    return render_template('login.html',error=error)
@app.post('/logout')
@auth
def logout(): session.clear(); return redirect('/login')
@app.get('/')
@auth
def home():
    with db() as c: reports=c.execute('SELECT id,customer,title,filename,level,created FROM reports ORDER BY created DESC').fetchall()
    return render_template('home.html',reports=reports,error=request.args.get('error'))
@app.post('/upload')
@auth
def upload():
    f=request.files.get('file')
    if not f or not f.filename: return redirect(url_for('home',error='Dosya seçin.'))
    data=f.read(); filename=Path(f.filename).name
    try:
        df=read_file(data,filename)
        token=secrets.token_hex(16)
        with db() as c:
            c.execute('DELETE FROM pending WHERE created < ?',(time.time()-3600,))
            c.execute('INSERT INTO pending VALUES(?,?,?,?)',(token,filename,data,time.time()))
        session['upload']=token
        return render_template('mapping.html',fields=FIELDS,columns=list(df.columns),mapping=guess(df.columns),preview=df.head(5).fillna('').to_dict('records'),filename=filename)
    except Exception as e: return render_template('error.html',message=str(e)),400
@app.post('/import')
@auth
def import_report():
    token=session.get('upload')
    with db() as c: pending=c.execute('SELECT * FROM pending WHERE id=? AND created>?',(token,time.time()-3600)).fetchone()
    if not pending: return render_template('error.html',message='Yükleme süresi doldu; dosyayı yeniden seçin.'),400
    try:
        mapping={k:request.form.get(k,'') for k in FIELDS}
        rows,skipped=normalize(read_file(pending['content'],pending['filename']),mapping,request.form.get('locale','tr'),request.form.get('default_currency','TRY').upper().strip(),request.form.get('result_label','').strip())
        customer=request.form.get('customer','').strip()[:150]; title=request.form.get('title','').strip()[:150]
        if not customer or not title: raise ValueError('Müşteri ve rapor adı gerekli.')
        digest=hashlib.sha256(pending['content']).hexdigest(); rid=secrets.token_hex(16)
        with db() as c:
            c.execute('INSERT INTO reports(id,customer,title,filename,level,digest,rows) VALUES(?,?,?,?,?,?,?)',(rid,customer,title,pending['filename'],request.form.get('level','Kampanya'),digest,json.dumps(rows,ensure_ascii=False)))
            c.execute('DELETE FROM pending WHERE id=?',(token,))
        session.pop('upload',None)
        return redirect(url_for('report',rid=rid,skipped=skipped))
    except sqlite3.IntegrityError: return render_template('error.html',message='Bu dosya aynı müşteri için zaten arşivde. Mevcut raporu açın.'),409
    except Exception as e: return render_template('error.html',message=str(e)),400

def get_report(rid):
    with db() as c: r=c.execute('SELECT * FROM reports WHERE id=?',(rid,)).fetchone()
    if r is None: abort(404)
    rows=json.loads(r['rows']); currencies=sorted({x['currency'] for x in rows}); types=sorted({x['result_type'] for x in rows})
    currency=request.args.get('currency') or currencies[0]
    filtered,excluded=filter_rows(rows,request.args.get('start',''),request.args.get('end',''),request.args.get('q',''),currency,request.args.get('result_type',''))
    return r,filtered,excluded,currencies,types,currency

LABELS={'spend':'Harcama','impressions':'Gösterim','clicks':'Bağlantı tıklamaları','results':'Sonuçlar','cpm':'CPM','cpc':'CPC · bağlantı','ctr':'CTR · bağlantı','cpr':'Sonuç başına maliyet','revenue':'Dönüşüm değeri','roas':'ROAS'}
@app.template_filter('num')
def fmt(v): return '—' if v is None else f'{v:,.2f}'.replace(',','X').replace('.',',').replace('X','.')
@app.get('/report/<rid>')
@auth
def report(rid):
    r,rows,excluded,currencies,types,currency=get_report(rid)
    m=metrics(rows); trend=series(rows,request.args.get('period','daily'))
    groups={}
    for row in rows: groups.setdefault(row['name'],[]).append(row)
    grouped=[{'name':name,**metrics(group)} for name,group in groups.items()]
    ranked=sorted([g for g in grouped if g['spend'] is not None],key=lambda g:g['spend'],reverse=True)[:10]
    maximum=max([g['spend'] for g in ranked] or [1]) or 1
    metric=request.args.get('metric','spend'); metric=metric if metric in LABELS else 'spend'
    maxtrend=max([t[metric] or 0 for t in trend] or [1]) or 1
    return render_template('report.html',report=r,rows=rows,m=m,labels=LABELS,excluded=excluded,currencies=currencies,types=types,currency=currency,ranked=ranked,maximum=maximum,trend=trend,maxtrend=maxtrend,metric=metric,grouped=grouped)
@app.get('/export/<rid>')
@auth
def export(rid):
    _,rows,*_=get_report(rid); out=io.StringIO(); w=csv.writer(out,delimiter=';'); w.writerow(list(FIELDS))
    for r in rows:
        values=[]
        for k in FIELDS:
            v=r.get(k); s='' if v is None else str(v)
            if isinstance(v,str) and s.lstrip().startswith(('=','+','-','@')): s="'"+s
            values.append(s)
        w.writerow(values)
    return send_file(io.BytesIO(out.getvalue().encode('utf-8-sig')),mimetype='text/csv',as_attachment=True,download_name='filtrelenmis_veriler.csv')
@app.post('/delete/<rid>')
@auth
def delete(rid):
    if request.form.get('confirm')!='yes': abort(400)
    with db() as c: c.execute('DELETE FROM reports WHERE id=?',(rid,))
    return redirect('/')
@app.errorhandler(413)
def too_big(e): return render_template('error.html',message='Dosya 20 MB sınırını aşıyor.'),413
