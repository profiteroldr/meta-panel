# Meta Rapor — v0.1

Coolify sunucusunda çalışan, tek kullanıcılı Meta reklam analiz uygulaması.
Türkçe arayüz • Flask + SQLite • CSV / XLSX • Docker

## Özellikler

- Kullanıcı adı / şifre ile giriş; hash olarak saklanan şifre, CSRF koruması, süreli oturum ve giriş deneme limiti.
- Meta CSV ve XLSX dosyalarının yüklenmesi; Türkçe / İngilizce başlık eşleştirmesi ve elle düzeltme.
- Müşteri ve rapor adıyla bağımsız arşiv. Aynı dosyanın aynı müşteriye tekrar yüklenmesi engellenir.
- Harcama, gösterim, bağlantı tıklamaları, sonuçlar, CPM, bağlantı CPC/CTR, sonuç maliyeti, dönüşüm değeri ve ROAS.
- Kampanya harcama dağılımı, günlük veri mevcutsa günlük / haftalık / aylık grafik.
- Tarih, isim, para birimi ve sonuç türü filtreleri.
- Filtrelenmiş CSV indirme; tarayıcının Yazdır > PDF olarak kaydet özelliği.
- Rapor silme, mobil ekranlara uyumlu arayüz. Harici analiz, yapay zekâ veya Meta API bağlantısı yok.

## Coolify kurulumu

1. ZIP'i açın. Bu klasörün **içeriğini** yeni bir GitHub deposunun köküne yükleyin. Dockerfile ve app.py kökte olmalı. `.env`, gerçek şifre ve veri klasörünü Git'e yüklemeyin.
2. Coolify'da projenizi açın > New Resource > Git Repository. Deponuzu bağlayın.
3. Build Pack / Build Strategy: **Dockerfile**. Base Directory: `/`. Dockerfile Location: `/Dockerfile` (arayüz göreli yol istiyorsa `Dockerfile`).
4. Ports Exposes / iç port: **8000**. Sağlık kontrolü yolu: `/healthz`. Dockerfile kendi sağlık kontrolünü içerir.
5. Alt alan adının DNS A kaydını sunucu IP adresinize yönlendirin. Coolify'da HTTPS alan adını ekleyin, iç portu 8000 seçin. Sürüme göre tek alan varsa `https://rapor.ornek.com:8000` biçimi kullanılır; ziyaretçi adresinde port görünmez.
6. Persistent Storage > **Volume Mount** ekleyin. Destination Path: **`/app/data`**. Bu adım raporları redeploy sırasında korur. Mevcut bir host dizini kullanırsanız UID 10001 için yazma izni gerekir.
7. Aşağıdaki ortam değişkenlerini **runtime** için ekleyin. Build-time secret olarak kullanmayın.
8. Deploy'a basın. Loglarda uygulama açıldıktan sonra alan adından giriş yapın.

| Değişken | Değer |
|---|---|
| ADMIN_USERNAME | İstediğiniz giriş adı; ör. yusuf |
| ADMIN_PASSWORD_HASH | Aşağıdaki araçla üretilen hash; düz şifre değil |
| SECRET_KEY | Aynı araçla üretilen rastgele anahtar |
| COOKIE_SECURE | true |
| DATA_DIR | /app/data |

Şifre ve anahtar üretimi (Python 3.12 kurulu bilgisayarda proje klasöründe):

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python make_secrets.py
```

Şifrenizi terminalde girin; yazarken görünmez. Üretilen iki değeri Coolify ortam değişkenlerine ayrı ayrı, değerlerin tamamını koruyarak yapıştırın. Hash içindeki `$` karakterlerini değiştirmeyin. Anahtarı veya hash'i sohbet, Git deposu ya da ekran görüntüsüyle paylaşmanız gerekmez. Coolify sürümünüzde literal değer seçeneği varsa etkinleştirin; Docker Compose değişken genişletmesi kullanmayın. Bu proje doğrudan Dockerfile ile kurulur.

### Güncelleme ve yedek

Kaynak dosyaları depoda güncelledikten sonra Redeploy kullanın. `/app/data` volume'u aynı kalmalı. SQLite verisi `reports.sqlite3` içindedir. Tek uygulama instance'ı kullanın; yatay ölçekleme tasarlanmamıştır. Veritabanının düzenli yedeğini alın (uygulama duruyken volume kopyası veya SQLite backup API). Kalıcı volume yedek yerine geçmez. Şifre değişiminde yeni hash üretin ve SECRET_KEY'i de değiştirerek eski oturumları geçersiz kılın.

## İlk raporu oluşturma

1. `ornek_meta.csv` ile akışı deneyebilirsiniz; tamamen örnek veridir.
2. Meta Reklam Yöneticisi'nde kampanya, reklam seti veya reklam düzeyinde CSV / XLSX dışa aktarın.
3. Zaman grafikleri için dışa aktarımda **gün kırılımı** kullanın.
4. Dosyayı yükleyin, müşteri / rapor adını yazın ve sütun eşleştirmelerini kontrol edin.
5. CSV sayılarınız `1.234,56` ise Türkçe; `1,234.56` ise İngilizce seçin. Excel'in gerçek sayısal hücreleri bu seçimden etkilenmez.
6. Sonuç göstergesi sütunu yoksa bütün satırların aynı sonucu ölçtüğünden emin olup sonuç türünü yazın. Örn. “Mesajlaşma konuşması”.
7. Raporu oluşturun. Sütun seçiminde hata varsa raporu silip doğru eşleştirmeyle tekrar yükleyin.

## Veri kuralları ve sınırlar

- Dosyalar **birbirine eklenmez**. Kampanya, reklam seti ve reklam ihracındaki aynı harcamanın tekrar sayılması önlenir. Her rapor kendi içinde aynı düzeyde, çakışmayan satırlar içermelidir. Aynı dosya içindeki yinelenen satırların anlamı otomatik tespit edilmez.
- CPM = toplam harcama / toplam gösterim × 1000. CPC = toplam harcama / toplam bağlantı tıklamaları. CTR = bağlantı tıklamaları / gösterim × 100.
- Görüntülenme / video oynatma gösterim yerine kullanılmaz. “Tıklamalar (tümü)” bağlantı tıklamaları yerine otomatik eşleştirilmez.
- Kaynak dosyada CPM bulunsa da uygulama bunu ortalamaz; temel toplamlar üzerinden hesaplar.
- Sonuçlar yalnızca aynı ve bilinen sonuç türünde toplanır. Karışık türlerde sonuç filtresi kullanın.
- Para birimleri birleştirilmez; filtrede seçili birim gösterilir. Döviz dönüşümü yapılmaz.
- Eksik hücre sıfıra çevrilmez; ilgili toplam / oran `—` olur. Sıfır paydalı oranlar hesaplanmaz.
- Erişim benzersiz kişi sayısıdır ve kampanyalar arasında toplanmaz. Frekans bu sürümde sunulmaz.
- Tarih filtresi satırın tamamı aralık içindeyse dahil eder. Kısmen örtüşen toplamlar bölüştürülmez; dışlanan satır sayısı görünür. Tarihsiz veriler sadece tarihsiz filtrede dahil edilir.
- Günlük grafik için tüm seçili satırlarda başlangıç = bitiş gerekir. Dönem toplamlarından günlük değer uydurulmaz.
- Sadece XLSX ilk sayfası okunur. XLS desteklenmez. En fazla 20 MB / 100.000 satır. Boş ya da “Toplam”, “Total” adlı satırlar, ad sütunu seçildiyse çıkarılır.
- Orijinal dosya geçici olarak saklanır; başarılı kayıttan sonra silinir. Rapor için normalize edilmiş değerler SQLite'da tutulur. Süresi geçmiş başarısız yüklemeler sonraki yüklemede temizlenir.
- Veriler kendi sunucunuzda kalır. Disk seviyesinde şifreleme bu sürümün parçası değildir.
- PDF ayrı bir rapor motoru değildir: yazdırma stiliyle tarayıcı PDF çıktısıdır. Otomatik yorum / öneri üretilmez.

## Yerel geliştirme

Yukarıdaki sanal ortamı kurun. `make_secrets.py` çıktılarıyla ortam değişkenlerini ayarlayın; geliştirmede HTTP kullanılıyorsa `COOKIE_SECURE=false`, `DATA_DIR=./data` seçin. `.env.example` yalnızca referanstır; uygulama `.env` dosyasını otomatik okumaz.

```bash
python -m flask --app app run --port 8000
python -m unittest discover -s tests -v
```

Canlıda geliştirme sunucusunu kullanmayın; Dockerfile Gunicorn çalıştırır.

## Doğrulama durumu

Hesaplama ve Flask test istemcisiyle giriş, CSRF, yükleme, eşleştirme, rapor oluşturma, filtreleme, CSV indirme, tekrar yükleme engeli, silme ve çıkış akışı test edilmiştir. Coolify sunucusunda Docker build/deploy ve gerçek tarayıcıyla görsel kontrol bu ortamda gerçekleştirilmedi. İlk kurulumda gerçek Meta ihracınızla sütun eşleştirmesini kontrol edin.

Resmî Coolify başvuru sayfaları:
- https://coolify.io/docs/applications/builds/dockerfile
- https://coolify.io/docs/applications/configuration/persistent-storage
