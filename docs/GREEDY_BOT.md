# Greedy bot (v1)

`balatro_ai/agents/greedy.py`. Plan Bölüm 6-7, basamak 2: kesin hesap + Monte Carlo discard.

## Ne yapar
- **El seçimi:** Eldeki 1-5 kartın tüm kombinasyonlarını puan motoruyla (docs/PUAN_MOTORU.md) hesaplar, en yüksek skorluyu seçer; eşit skorda daha az kart. Blind'ı bitiren bir oynanış varsa onu oynar.
- **Discard:** Blind'ı bitiren oynanış yoksa ve discard hakkı varsa, 1-5 kartlık **tüm** discard kümelerini (8 kartta 218) değerlendirir. Her küme için destenin kalanından (insanın deste ekranında gördüğü kartlar, sırasız) ortak rastgele çekilişler örnekler, çekilişten sonraki en iyi oynanışın beklenen skorunu hesaplar. Beklenen skor şu anki en iyi oynanıştan yüksekse discard eder. Son elde ölçüt "blind'ı geçme olasılığı"dır.
- **Boss debuff'lı ya da geliştirilmiş kart varsa:** ilk aşama hızlı değerlendiriciyle (`sim/hizli.py`, tam motorla testlerle aynı sonucu verir) tüm kümeleri sıralar, en iyi 12 kümeyi tam motorla yeniden değerlendirir.
- **El dışındaki aşamalar (v1):** sabit kural: blind seç, mağazadan hiçbir şey almadan çık, paketi atla.

## Gerçek oyun sonuçları (2026-10-08, "dar" küme, 20 run, rastgele ajanla aynı seed'ler)
| | Rastgele (04) | Greedy (07) |
|---|---|---|
| Ortalama son ante | 1,0 | 1,65 |
| Ante 2'ye ulaşan | 0/20 | 13/20 |
| Aynı seed'de daha iyi / eşit / kötü | | 20 / 0 / 0 |

- Blind başına geçme (düzeltilmiş sayım): Ante 1 Small 20/20, Big 17/20, Boss 13/17; Ante 2 Small 5/13, Big 0/5. Hiçbir run Ante 3'e ulaşmadı. (Önceki sürümdeki "Small Blind 8, Big Blind 8" ifadesi her ante'nin blind'ını birlikte sayıyordu ve yanıltıcıydı.)
- En yüksek tek el: 1208 (kraliyet straight flush).
- **Tahmin doğruluğu:** oynadığı 188 elin 188'inde motorun tahmin ettiği skor, oyunun gerçekte verdiği skorla aynı (jokersiz).
- Oyundaki reddedilen komut: 0. Botun karar süresi: medyan 130 ms, %95'i 859 ms.

## Sınırlar
- Yüzü kapalı kartları hesaba katamaz, oynanışlarda ve tutulacak kartlarda yok sayar (kapalı kartlarla akıl yürütme `docs/PLANLAYICI.md`).
- Mağaza kodu (gezegen alıp kullanma) yazılı ve testli ama varsayılan olarak kapalı (`magaza=True` ile açılır); gerçek oyunda henüz denenmedi.
- **Jokerleri, gezegenleri, tarotları, kuponları satın almaz.** Joker olmadan skor bir noktadan sonra yetmiyor. Ölçülen hedefler: Ante 1: 300 / 450 / 600; Ante 2: 800 / 1200 / 1600 (boss'a göre 800-3200). Ante 3 ve sonrası bu verilerde görülmedi (kullanıcı, jokersiz botun yaklaşık 1200 üzerine çıkmasının zor olacağını belirtti; bu henüz ölçülmedi). Bu bilinçli bir v1 sınırı; mağaza kararları sıradaki iş.
- Boss geçmişi gerektiren kurallar (The Eye, The Mouth) bilinmez.
- Joker taşırken puan motoru jokersiz hesaplar, yani hesap eksik kalır.
- 20 run küçük bir örnek; kesin başarı oranı için daha fazla run gerekir.

## Çalıştırma
`python -m balatro_ai.eval.calistir --kume dar --ajan greedy --run 20 --seed-oneki SOAKD --deney-adi v1`
Kayıtlar `veri/NN_greedy_dar_v1/` klasörüne yazılır, tablo `veri/INDEKS.md`.
