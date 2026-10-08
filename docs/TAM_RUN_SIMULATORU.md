# Tam run simülatörü: tasarım taslağı

Amaç: gerçek oyunu açmadan, çok hızlı (tek çekirdekte saniyede onlarca run) tam bir Balatro run'ı oynatıp
`Q(durum, eylem)` / `V(durum)` modellerini eğitmek için veri üretmek. Şu an elimizde yalnızca **tek turu (blind)**
simüle eden kod var (`sim/tur.py`); mağaza, paketler, tüketilebilirler, kuponlar, etiketler (tag) ve ante akışı yok.

## Kural: doğrulanmamış parça eğitime girmez
Her simülatör parçası, gerçek oyun loglarıyla karşılaştırılıp doğrulanmadan eğitim verisi üretmekte kullanılmaz
(proje kuralı). Bu yüzden sıra: parçayı oyunun Lua kodundan yaz → gerçek loglarla "beklenen vs gerçek" farkını ölç →
fark yoksa eğitimde aç.

## Parçalar (bağımlılık sırasıyla)
1. **Run akışı:** ante/blind sırası, hedef tablosu (stake'e göre, `sim/magaza.py`'de var), boss seçimi, ödüller
   (blind ödülü, kalan el, faiz), blind atlama ve etiketler.
2. **Mağaza üretimi:** hangi kartların hangi olasılıkla çıktığı (joker nadirliği, planet/tarot/spectral, paket türleri,
   kupon). Gerçek mağaza örneklerinden (`shop_teklifleri` görünümü) ve oyun kodundan doğrulanmalı.
3. **Tüketilebilir etkileri:** planet (var), tarot ve spectral. Bunlar desteyi değiştirir (geliştirme, renk, silme,
   kopyalama); hızlı puanlayıcı şu an düz kart varsayar, tam motor (`sim/puan.py`) geliştirmeyi biliyor.
4. **Paketler:** açılış, seçim sayısı, atlama.
5. **Joker kataloğu:** `sim/jokerler.py` (şu an ~37). Kalanlar toplu eklenir; her biri gerçek skorla doğrulanır.
6. **Kuponlar:** şu an 6'sının etkisi biliniyor (`planlayici.KUPON_ETKILERI`); diğerleri (Overstock, Clearance Sale,
   Reroll, Telescope/Observatory, Hone/Glow Up, Crystal Ball, Antimatter, Seed Money...) mağaza ve ekonomi modeli ister.
7. **Gizli bilgi:** simülatör deste sırasını ve gelecek mağazaları rastgele üretir; **ajan bunlara bakamaz** (adil oyun).
   Ajan gözlemi gerçek oyundakiyle aynı alanlardan (`env/gozlem.py`) beslenmelidir.

## Hız
Python'da bir tur rollout'u ms düzeyinde; bir run yüzlerce tur içerir. Hedef: tek çekirdekte saniyeler/run. Gerekirse
sıcak döngüler (hızlı puanlayıcı, rollout) numba/C ile hızlandırılır; çok çekirdek için run'lar ayrı süreçlerde koşar.
GPU, simülatör için değil model eğitimi için kullanılır.

## Doğrulama ölçüsü
- Skor: gerçek oynanmış ellerde motor skoru = oyun skoru (şu an düz kart ve 11 jokerli el için var).
- Mağaza: simüle edilen teklif dağılımı ≈ gerçek teklif dağılımı (ki-kare / örnek karşılaştırması).
- Akış: aynı seed ve aynı komutlarla gerçek oyunun durumları simülatörünkilerle eşleşiyor (seed sırası bilgisi yalnızca
  doğrulamada, ajanda değil).

## Çıktı veri şeması
Gerçek oyun logları ile **aynı** alanlar (karar, geçerli aksiyonlar, reddedilen alternatifler, ham durum), `kaynak =
simulator` ve simülatör sürümü yazılır. Böylece gerçek ve simüle veri aynı şemada birleştirilir.
