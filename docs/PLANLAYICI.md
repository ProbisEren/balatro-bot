# Planlayıcı ajan (rollout ile karar)

`balatro_ai/agents/planlayici.py`, `balatro_ai/sim/tur.py`. Plan Bölüm 6-7: simülasyon + arama.

## Fikir
Greedy v1'in sınırı: el kararını "şimdi en iyi eli oynayayım ya da discard edeyim" ikilisine bölüp yalnızca o anki skora bakması. Planlayıcı bunun yerine **turu simüle eder**: her aday eylemden sonra turun sonuna kadar yüzlerce hızlı deneme (rollout) oynatır ve blind'ı geçme sıklığına bakar. "Zayıf eli oynayıp kart döndürmek" gibi eylemler için elle bir kural yazılmadı, deneme sonuçları gösterir.

## Nasıl çalışır
1. **Dünyalar:** Gözlemden, kalan destenin rastgele çekiliş sıraları ve (varsa) yüzü kapalı kartların görülenle tutarlı rastgele kimlikleri örneklenir (determinizasyon). Bot yalnızca insanın görebileceği bilgiyi kullanır; kapalı kartın olabileceği kimlikler = standart deste - destede kalanlar - eldeki açık kartlar - bu turda oynanan/atılan kartlar.
2. **Aday önerisi:** Tüm 1-5 kartlık oynama ve atma eylemleri üç ucuz ölçütle sıralanır (anlık skor; oynadıktan sonra elin potansiyeli; atınca elin potansiyeli) ve her ölçütün en iyilerinden bir aday kümesi çıkar. Ölçütler yalnızca öneri üretir.
3. **Rollout ve eleme:** Adaylar aynı dünyalarda turun sonuna kadar oynatılır (`sim/tur.py`), art arda yarılanarak elenir; kazanan, son turu oynayan adaylar arasından en yüksek değerlidir. Değer: blind geçilirse 1 + kalan el payı (0,03 x el), geçilmezse 0,25 x (ilerleme)³ (dışbükey, şansı olanı ödüllendirir).
4. **Son el kuralı (kullanıcı geri bildirimi):** Son elde ve discard hakkı varken, eldeki en iyi oynanış blind'ı bitirmiyorsa, her discard kümesi için 64 dünyada "sonrasında blind'ı bitirme olasılığı" hesaplanır; sıfırdan büyük bir şans varsa discard edilir. Bu hesap her son-el kararında loga yazılır (`ek.ajan.son_el_arama`).

## Elle yazılmış parçalar (geçici, planlanan değişim: öğrenilmiş politika/değer ağı)
- Rollout'taki temel politika (`sim/tur.py`, `politika`): blind'ı bitiren eli oyna, değilse en iyi discard önerisi beklenen skoru artırıyorsa discard et. Discard önerileri kısa bir listeden gelir.
- Aday önerme ölçütleri.
- Değer fonksiyonundaki sayılar (0,25, üs 3, 0,03) tahmindir, ayarlanmadı.

## Gerçek oyun sonuçları (2026-10-08, "dar" küme, 20 run, greedy v1 ile aynı seed'ler)
| | Greedy v1 | Planlayıcı |
|---|---|---|
| Ortalama son ante | 1,65 | 1,85 |
| Ante 1 Small (300) | 20/20 | 20/20 |
| Ante 1 Big (450) | 17/20 | 20/20 |
| Ante 1 Boss (600) | 13/17 | 17/20 |
| Ante 2 Small (800) | 5/13 | 11/17 |
| Ante 2 Big (1200) | 0/5 | 3/11 |
| Aynı seed'de daha iyi / eşit / kötü | | 12 / 6 / 2 |

Hiçbiri Ante 3'e ulaşmadı (jokerler ve gezegenler yok). Son-el denetimi (`python -m balatro_ai.eval.denetim`): discard daha iyiyken oynama: **0** (23 son-el discard kararı). Karar süresi: medyan 236 ms, %95'i 524 ms. Run başına yaklaşık 48 sn.

Simülatör doğrulaması: temel politika, jokersiz ve gezegensiz 4 el / 4 discard ile hedef 300'ü %98, 450'yi %88, 600'ü %69, 800'ü %41, 1200'ü %11, 1600'ü %3 oranında geçiyor (4000 simüle tur). Gerçek greedy v1'in ilk tur sonuçlarıyla (300: 20/20) tutarlı.

## Sınırlar
- Jokerler, gezegenler, tarotlar, kuponlar yok: mağaza, paket ve blind kararları şimdilik sabit kural.
- Simülatör geliştirilmiş kartları, eldeki kart efektlerini ve jokerleri simüle etmez (kartlar düz varsayılır).
- Boss etkilerinden yalnızca debuff'lar, The Psychic, The Flint ve The Arm simüle edilir; The Hook, The Wheel, The Eye, The Mouth gibi geçmiş veya rastgelelik gerektirenler yok. Kapalı kart çıkaran bir boss'la (The House, The Wheel, The Fish, The Mark) gerçek oyunda henüz karşılaşılmadı; bu yol yalnızca birim testleriyle sınandı.
- Örnek sayısı küçük (20 run); 12/6/2 bir eğilimdir, kesin üstünlük kanıtı değildir.
