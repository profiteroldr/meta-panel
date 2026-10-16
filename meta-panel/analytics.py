import csv, io, math, re, unicodedata, zipfile
from datetime import date
import pandas as pd

FIELDS = {'name':'Kampanya / reklam adı','spend':'Harcanan tutar','impressions':'Gösterim','clicks':'Bağlantı tıklamaları','results':'Sonuçlar','result_type':'Sonuç türü','revenue':'Satın alma dönüşüm değeri','start':'Rapor başlangıcı / gün','end':'Rapor bitişi','currency':'Para birimi'}
ALIASES = {
'name':['kampanya adı','campaign name','reklam seti adı','ad set name','reklam adı','ad name'],
'spend':['harcanan tutar','amount spent','spend'], 'impressions':['gösterim','gösterimler','impressions'],
'clicks':['bağlantı tıklamaları','link clicks'], 'results':['sonuçlar','results'],
'result_type':['sonuç göstergesi','result indicator','result type','sonuç türü'],
'revenue':['satın alma dönüşüm değeri','purchases conversion value','purchase conversion value'],
'start':['rapor başlangıcı','reporting starts','day','gün','date','tarih'],
'end':['rapor bitişi','reporting ends'], 'currency':['para birimi','currency','account currency','hesap para birimi']}

def norm(s):
    return ''.join(c for c in unicodedata.normalize('NFKD',str(s).lower().replace('ı','i')) if not unicodedata.combining(c)).strip()

def guess(columns):
    out={}
    for key,aliases in ALIASES.items():
        out[key]=next((str(c) for a in aliases for c in columns if norm(c)==norm(a) or norm(c).startswith(norm(a)+' (')),'')
    return out

def read_file(data, filename, sheet=0):
    if len(data)>20*1024*1024: raise ValueError('Dosya en fazla 20 MB olabilir.')
    if filename.lower().endswith('.xlsx'):
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            if sum(x.file_size for x in z.infolist())>100*1024*1024: raise ValueError('Excel açılmış boyutu çok büyük.')
        df=pd.read_excel(io.BytesIO(data),sheet_name=sheet,engine='openpyxl')
    elif filename.lower().endswith('.csv'):
        text=None
        for enc in ['utf-8-sig','utf-16','cp1254']:
            try:
                text=data.decode(enc); break
            except UnicodeError: pass
        if text is None: raise ValueError('CSV karakter kodlaması okunamadı.')
        try: sep=csv.Sniffer().sniff(text[:20000],delimiters=',;\t').delimiter
        except csv.Error: sep=';'
        df=pd.read_csv(io.StringIO(text),sep=sep,dtype=str,keep_default_na=False)
    else: raise ValueError('CSV veya XLSX dosyası seçin.')
    if len(df)>100000: raise ValueError('En fazla 100.000 satır yükleyebilirsiniz.')
    df=df.dropna(how='all'); df.columns=[str(c).strip() for c in df.columns]
    if len(set(df.columns))!=len(df.columns): raise ValueError('Sütun adları benzersiz olmalıdır.')
    if df.empty: raise ValueError('Dosyada veri satırı yok.')
    return df

def number(v,locale):
    if v is None or pd.isna(v) or str(v).strip() in ('','—','-'): return None
    if isinstance(v,(int,float)): n=float(v)
    else:
        s=str(v).strip().replace('\u00a0','').replace(' ','')
        s=re.sub(r'(TRY|TL|USD|EUR|₺|\$|€)','',s,flags=re.I)
        if locale=='tr': s=s.replace('.','').replace(',','.')
        else: s=s.replace(',','')
        try: n=float(s)
        except ValueError: raise ValueError(f'Sayısal değer okunamadı: {str(v)[:50]}')
    if not math.isfinite(n) or n<0: raise ValueError('Negatif veya geçersiz sayısal değer bulundu.')
    return n

def day(v):
    if v is None or pd.isna(v) or not str(v).strip(): return None
    if isinstance(v,(int,float)): raise ValueError('Tarih sütununda biçimlendirilmemiş sayı var.')
    try:
        s=str(v).strip()
        return pd.to_datetime(s,dayfirst=not bool(re.match(r'^\d{4}-',s))).date().isoformat()
    except Exception: raise ValueError(f'Tarih okunamadı: {str(v)[:50]}')

def normalize(df,mapping,locale,currency,result_label):
    if not mapping.get('spend') or not mapping.get('impressions'): raise ValueError('Harcama ve gösterim sütunlarını eşleştirin.')
    chosen=[v for v in mapping.values() if v]
    if len(chosen)!=len(set(chosen)): raise ValueError('Aynı sütunu iki alana eşleştirmeyin.')
    rows=[]; skipped=0
    for i,src in df.iterrows():
        def val(k): return src[mapping[k]] if mapping.get(k) else None
        name=val('name')
        if mapping.get('name') and (pd.isna(name) or not str(name).strip() or norm(name) in ['total','totals','toplam','genel toplam','results from all campaigns']):
            skipped+=1; continue
        row={'name':str(name) if name is not None else f'Satır {i+1}'}
        for k in ['spend','impressions','clicks','results','revenue']: row[k]=number(val(k),locale)
        row['start']=day(val('start')); row['end']=day(val('end')) or row['start']
        if row['start'] and row['end']<row['start']: raise ValueError('Bitiş tarihi başlangıçtan önce olamaz.')
        c=val('currency'); row['currency']=str(c).strip().upper() if c is not None and not pd.isna(c) and str(c).strip() else currency
        t=val('result_type'); row['result_type']=str(t).strip() if t is not None and not pd.isna(t) and str(t).strip() else result_label or 'Belirtilmemiş'
        rows.append(row)
    if not rows: raise ValueError('Eşleştirmeden sonra veri satırı kalmadı.')
    return rows,skipped

def metrics(rows):
    def total(k):
        vals=[r[k] for r in rows]
        return sum(vals) if vals and all(v is not None for v in vals) else None
    def ratio(a,b,m=1): return a/b*m if a is not None and b is not None and b>0 else None
    m={k:total(k) for k in ['spend','impressions','clicks','results','revenue']}
    if len({r['currency'] for r in rows})>1: raise ValueError('Farklı para birimleri birleştirilemez.')
    if len({r['result_type'] for r in rows})!=1 or any(r['result_type']=='Belirtilmemiş' for r in rows): m['results']=None
    m.update(cpm=ratio(m['spend'],m['impressions'],1000),cpc=ratio(m['spend'],m['clicks']),ctr=ratio(m['clicks'],m['impressions'],100),cpr=ratio(m['spend'],m['results']),roas=ratio(m['revenue'],m['spend']))
    return m

def filter_rows(rows,start='',end='',query='',currency='',result_type=''):
    selected=[]; excluded=0
    for r in rows:
        if currency and r['currency']!=currency: continue
        if result_type and r['result_type']!=result_type: continue
        if query and query.casefold() not in r['name'].casefold(): continue
        if (start or end) and (not r['start'] or (start and r['start']<start) or (end and r['end']>end)):
            excluded+=1; continue
        selected.append(r)
    return selected,excluded

def series(rows,period):
    groups={}
    # Aggregate dates must never be expanded into invented daily values.
    if not rows or any(not r['start'] or r['start']!=r['end'] for r in rows): return []
    for r in rows:
        d=date.fromisoformat(r['start'])
        key=d.isoformat() if period=='daily' else d.strftime('%Y-%m') if period=='monthly' else f'{d.isocalendar().year}-H{d.isocalendar().week:02}'
        groups.setdefault(key,[]).append(r)
    return [{'label':key,**metrics(group)} for key,group in sorted(groups.items())]
