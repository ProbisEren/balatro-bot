# Balatro AI — Final Proje Planı (Sürüm 2.0, 8 Ekim 2026)

Kaynak: `~/Downloads/Balatro_AI_Final_Proje_Plani.pdf` (16 sayfa). Aşağısı PDF'in sıkıştırılmış ama içerik kaybı olmayan karşılığıdır; ayrıntı gerekirse PDF'e bak.

## Amaç
Balatro'yu mümkün olan en iyi şekilde oynayan otonom bot. Veri setleri, analizler ve panel botu güçlendirmek ve performansını kanıtlamak için var. Tek algoritmaya bağlı kalınmaz: hesaplanabilen yerde kesin hesap, belirsizlikte simülasyon, sezgi gereken yerde öğrenilmiş model, kritik anlarda derin arama. Karar her zaman **aynı seed'lerde yapılan ölçümle** verilir.

### Ana soru ve alt sorular
- Simülasyon + ML + RL + arama birlikte Balatro'yu ne kadar iyi oynar, güçlü insanları geçer mi?
- Hangi yöntem/kombinasyon en iyi? Bot insanların kullanmadığı stratejiler keşfeder mi?
- Mağaza, discard, joker, ekonomi, blind atlama kararları birlikte optimize edilebilir mi?
- Random → Heuristic → ML → RL → Arama basamaklarında artış ne kadar?
- Farklı deste/stake/seed/boss koşullarına genelleme?

### Başarı ölçüleri
Kazanma oranı (Ante 8), ortalama ante, karar pişmanlığı (regret; kart oynamada sıfır hedef), Endless performansı, genelleme (eğitilmeyen koşullar), insana karşı (aynı seed). Sabit "%90 kazanma" hedefi yok; benchmark veriyle belirlenir. Her sürüm öncekini aynı seed'lerde yenmeli.

### Adil oyun kuralı (KRİTİK)
- Bot sadece insanın gördüğünü görür: deste sırası, gelecek mağaza, seed **kullanılmaz**.
- Simülatörde ileriye bakarken gizli bilgi rastgele örneklenir (determinizasyon).
- Seed bilgisi yalnızca ölçüm içindir: her şeyi bilen "oracle" ajan ayrı modülde, pişmanlık hesabı için. Bot karar verirken asla görmez.
- Bot skorları Steam/Game Center liderlik tablolarına gönderilmez.

## Bot gücünün 3 katmanı (sırayla ilerle)
1. **Doğru hesap**: puan hesabı jokerler, sıralama, enhancement'larla birebir doğru olmalı. Kesin, test edilebilir.
2. **İyi değer tahmini**: "bu durum ne kadar iyi", "bu jokeri almak beni ne kadar ilerletir". Öğrenilmiş modeller.
3. **Derin arama**: kritik kararlarda ileri simülasyon (MCTS). Değer iyiyse arama verimli.

## Oyuna bağlanmak
- BalatroBot modu (HTTP/JSON API; Lovely Injector + Steamodded üstünde): github.com/coder/balatrobot, pypi.org/project/balatrobot, orijinal github.com/besteon/balatrobot.
- **Steam sürümü gerekli** (Mac'te çalışır, mod kurulur, JSON durum, hızlı). Balatro+ (Apple Arcade) imzalı/sandbox'lı, mod kurulamaz → bot için uygun değil.
- Katalog ve puan motoru oyuna bağlanmadan geliştirilebilir.

## Mimari
Dört kaynak, tek arayüz, tek karar motoru: Oyun kataloğu, Gerçek oyun (Steam+BalatroBot), Simülatör (gerçek oyunla doğrulanmış), Görev tanımları → **ortak ortam arayüzü + durum kodlayıcı (Gymnasium)**: sadece insanın gördüğü bilgiyi verir, geçersiz aksiyonları maskeler. Simülatörde eğitilen bot değişmeden gerçek oyunda oynar.
Karar motoru: aday hamle üretici → değer+politika ağı / kesin hesap katmanı / MCTS. Her karar loglanır → Veri katmanı (Parquet + DuckDB: katalog, runs, decisions, hands, shop_events) → eğitim (imitation, PPO, Expert Iteration), ölçüm+panel (benchmark, replay, SHAP), analiz.

## Simülatör (botun kalbi)
Oyunun Python'da birebir kopyası; eğitimin ve aramanın motoru. Aşamalı güvenilirlik — **doğrulanmayan parça eğitimde kullanılmaz**:
| Adım | Kapsam | Doğrulama |
|---|---|---|
| 1 | Puan motoru: el türleri, chips, mult, enhancement, edition, seal | Gerçek oyundan binlerce elin puanıyla birebir |
| 2 | Jokerler: en sık 40, sonra tamamı | Her joker birim testi; sıralamayla birlikte |
| 3 | Deste, çekiliş, discard, blind, boss | Gerçek run'ların adım adım yeniden oynatılması |
| 4 | Mağaza, paketler, tarot, planet, spektral, voucher, tag | Olasılık dağılımları vs gerçek istatistik |
| 5 | Tüm desteler ve stake'ler | Otomatik regresyon testleri |

- Oyunun kendi Lua kodu ve yerelleştirme dosyaları asıl referans; wiki yardımcı (çelişkide oyun kazanır).
- Gerçek oyun ↔ simülatör sürekli karşılaştırılır; uyuşmayan kayıt "uyumsuz" işaretlenir.
- Hız gerekirse sıcak noktalar Numba/Rust. Arama derinliği simülatör hızına bağlı.

## Karar problemleri (ilk sürüm → mükemmele giden)
- **Kart oynama**: tüm 1–5 kart kombinasyonları (8 kartta 218) puan motoruyla → kalan el/sonraki eller için kısa arama.
- **Discard**: Monte Carlo (çekilişleri örnekle, blind geçme olasılığı) → değer ağı + arama.
- **Mağaza**: utility + rollout (mevcut botla N simülasyon) → değer ağı + MCTS; P(kazanma) veya beklenen kalan ante.
- **Reroll/para**: basit ekonomi kuralı → RL politikası.
- **Planet/tarot/spektral**: küçük aday listesi + değer skoru → arama içinde.
- **Blind atlama (tag)**: tag değer tablosu → politika+değer ağı.
- **Joker sıralama/satma**: tüm sıralamalar puan motoruyla → + değer ağıyla satma.
- Joker/voucher/planet için **sabit tier-list yazılmaz**; değerler bağlama göre hesaplanır/öğrenilir.
- Utility baseline: `Utility(a) = E[puan] + α·E[para] + β·P(hayatta kalma) + γ·GelecekDeğeri`; α,β,γ aynı seed'lerde arama ile ayarlanır.
- Aday hamle üretici binlerce aksiyonu birkaç mantıklı seçeneğe indirir.
- Mağaza değeri: P(kazanma | al X) karşılaştırılır (örn. Blueprint 0.72 vs hiçbir şey 0.43). Önce rollout, sonra rollout sonuçlarıyla eğitilen hızlı değer ağı.

## Öğrenme ve arama döngüsü
Basamaklar (her biri öncekini aynı seed'lerde yenmeli): 1 Random → 2 Greedy/Heuristic → 3 Gözetimli değer modelleri (lojistik → XGBoost/LightGBM → sinir ağı) → 4 Imitation (en iyi ajan + kendi kararların) → 5 PPO (simülatörde milyonlarca run) → 6 **Arama + Expert Iteration**.
Expert Iteration döngüsü: MCTS+mevcut ağ ile self-play → kararları kaydet (arama sonucu = hedef) → ağı eğit (politika←arama, değer←run sonucu) → şampiyon testi (aynı 1.000 seed, anlamlı fark şart). Kazanırsa yeni ağ aramaya girer, kaybederse eski şampiyon kalır.

- Model yapısı: ilk modeller tablo verisi ve açıklanabilir; karmaşık mimari ancak veri/ölçüm gerekçelendirirse. İleri: her joker/voucher/tarot/planet/kart için embedding, joker seti için attention/Transformer; çıktı politika+değer; geçersiz aksiyonlar maskelenir.
- **Ödül**: Small/Big blind geçmek +1, Boss geçmek (ante atlamak) +3, Ante 8 kazanmak +20, kaybetmek 0 veya küçük ceza (deneyle). **Para/faiz/ham puan gibi ara ölçütlere doğrudan ödül verilmez** (ödül hilesi); davranış replay/panelden izlenir.
- **Curriculum**: Beyaz stake + tek deste + sınırlı joker havuzu → Red → Green → … → Gold, deste ve öğe havuzu genişler.

## Veri
- **Katalog**: joker, voucher, blind, deste, poker eli, tarot, planet, spektral, enhancement (wiki + oyun dosyaları). Joker özellikleri: rarity, cost, chips, flat_mult, xmult, scaling, economy, retriggers, hand_synergy, deck_manipulation, trigger_condition.
- **Tablolar**: `runs` (run_id, seed, deste, stake, bot_sürümü, görev_id, son_ante, kazandı_mı, süre); `decisions` (faz, ham_durum, seçenekler, seçilen_aksiyon, model_skorları, arama_istatistikleri, karar_süresi); `hands` (kartlar, el_türü, chips, mult, puan, hedef, kalan_el, kalan_discard); `shop_events` (öğe_türü, öğe_adı, fiyat, alındı_mı, para_öncesi, para_sonrası).
- Ham durum JSON korunur. **Alınmayan teklifler de kaydedilir** (seçilim yanlılığı düzeltmesi için).
- Her kayıtta oyun, bot, veri sürümü; Parquet + DuckDB/Polars; veri seti v1, v2… sürümlenir.
- Kaynaklar: gerçek oyun (az ama güvenilir, simülatör referansı), kendi oyunların (insan baseline + imitation), doğrulanmış simülatör (yüksek hacim).

## Değerlendirme protokolü
- Ölçüler: kazanma oranı, ortalama ante, skor/Endless ante, karar pişmanlığı (oracle'a göre), simülatör uyumu, karar süresi.
- Ajan karşılaştırma tablosu: Random, Greedy/Heuristic, Değer modelli heuristic, Imitation+PPO, Arama+Expert Iteration, İnsan.
- **Şampiyonluk**: yeni sürüm şampiyonla aynı seed setinde (≈1.000 seed) oynar; eşleştirilmiş test + bootstrap güven aralığıyla daha iyi çıkarsa şampiyon olur. Tek yüksek skora göre terfi yok.
- **Train/test seed'leri ayrı**; aynı run'ın kararları iki tarafa düşmez (sızıntı önlemi).
- Kazanma oranı yetmez: pişmanlık, hayatta kalma eğrileri, karşı-olgusal testler ("iyi skor ama kötü karar").

## Görevler ve izleme
- Görevler YAML, sonuçlar `görev_id` ile veri setine bağlı: Beyaz stake ustalığı, Gold stake meydan okuma, Endless rekoru, Jokersiz run, Tek el türü, Ekonomi testi (Ante 1–3 tasarruf), Bulmaca durumu (oracle kararını bulma oranı), Veri üret.
- Panel: canlı run, eğitim eğrileri, ölüm analizi, replay, SHAP/özellik önemi (ileri modellerde attention), karşı-olgusal simülasyon.

## Veri bilimi çıktıları
Run kazanılacak mı (lojistik → RF → XGBoost/LightGBM; ROC-AUC, F1, kalibrasyon), joker etkisi (kontrollü regresyon, propensity score), joker sinerjisi (`Sinerji(A,B) = gözlenen ortak başarı − bağımsız beklenen`), boss ölüm riski (Kaplan-Meier), seed zorluğu, ekonomi A/B, insan-bot karar uyumu, botun keşifleri (joker embedding UMAP).

## Yol haritası (haftada 10–15 saate göre tahmini; her aşama bir kapıyla biter)
| Aşama | Hafta | İçerik | Kapı |
|---|---|---|---|
| 0 Katalog + puan motoru | 1–3 | katalog, EDA, puan motoru v1 | şema stabil; puan motoru test ellerinde birebir |
| 1 Bağlantı + logger | 4 | Steam+BalatroBot, random ajan, loglama | 100+ hatasız loglu run |
| 2 Greedy bot | 5–7 | kesin el seçimi, MC discard, utility mağaza; veri seti v1 | greedy random'u açıkça yener; el seçiminde pişmanlık sıfır |
| 3 Simülatör | 8–13 | deste, blind, mağaza, paketler, ilk 40 joker; veri seti v2 | kritik hesaplarda gerçek oyunla birebir |
| 4 Değer modelleri | 14–16 | rollout mağaza, kazanma tahmini, P(kazanma\|al) | değer modelli bot greedy'yi anlamlı yener |
| 5 Imitation + PPO | 17–22 | taklit, PPO, curriculum, görev sistemi | öğrenen bot önceki şampiyonu anlamlı yener |
| 6 Arama + Expert Iteration | 23–30 | MCTS, self-play, tüm jokerler/stake'ler | tekrarlanabilir final benchmark; insan baseline aşılır |
| 7 Yayın | 31+ | repo, veri seti, rapor, panel, Endless rekor videosu | sonuçlar ve sınırlılıklar belgeli |

## İlk hedef ve ilk adımlar
İlk gerçek hedef: **Data Collector + Puan Motoru + Logger + Random/Greedy Bot**.
Bu hafta:
- [ ] Python ortamı ve `balatro-ai` reposu
- [ ] Joker ve diğer öğelerin kataloğu; oyunun kendi dosyalarıyla doğrula
- [ ] Puan motoru v1: el türleri, chips × mult, birkaç basit joker
- [ ] Puan motoru birim testleri

Sonraki:
- [ ] Steam'den Balatro'yu al; Lovely + Steamodded + BalatroBot kur
- [ ] API ile durumu oku; gerçek el puanlarını puan motoruyla karşılaştır
- [ ] Rastgele ajan, ilk 100 run loglanır
- [ ] Greedy bot: en iyi eli oyna, Monte Carlo ile discard

## Teknoloji
Oyun bağlantısı: Steam + Lovely + Steamodded + BalatroBot. Katalog: Python, Requests, BeautifulSoup/Scrapy + oyun dosyası ayrıştırma. Simülatör: Python (+Numba/Rust). Veri: Parquet, DuckDB, Polars/Pandas. EDA: Jupyter, Matplotlib/Plotly, statsmodels, scikit-learn, SHAP. ML: scikit-learn, XGBoost/LightGBM, PyTorch (Apple Silicon MPS). RL/arama: Gymnasium; PPO için Stable-Baselines3/CleanRL veya özel PyTorch; MCTS özel kod. Takip/panel: MLflow veya W&B; Streamlit.

Repo yapısı:
```
balatro-ai/
  catalog/    # oyun kataloğu: scraper + oyun dosyası ayrıştırıcı
  sim/        # puan motoru, deste, mağaza, joker mekanikleri
  env/        # gerçek oyun ve simülatör için ortak arayüz
  agents/     # random, greedy, value, imitation, ppo, search
  search/     # MCTS, determinizasyon, rollout
  data/       # şema, logger, Parquet yazıcı
  ml/         # özellikler, kazanma tahmini, değer ve politika ağları
  tasks/      # görev tanımları (YAML)
  eval/       # benchmark, şampiyonluk testi, oracle ve pişmanlık
  dashboard/  # Streamlit + replay
  analysis/   # EDA, sinerji, hayatta kalma, deneyler
  tests/      # puan motoru ve simülatör doğrulama
```

## Riskler ve önlemler
- Simülatör gerçek oyundan sapar → birim+entegrasyon testi, sürekli karşılaştırma.
- Tüm jokerleri erken kodlamak uzun sürer → sınırlı havuzla başla, oyun kodunu referans al.
- RL kararsız/yavaş → imitation başlangıcı, aday hamle üretici, curriculum, küçük deneyler.
- Arama yavaş → sadece kritik kararlarda, sıcak noktaları hızlandır, değer ağıyla derinliği kısalt.
- Ödül hilesi → ana hedefe yakın ödül, replay/panel incelemesi.
- İstemeden seed sızması → ortam arayüzü sadece insanın gördüğünü verir; oracle ayrı modülde, sadece ölçümde.
- Veri yanlılığı/sızıntı → seed, bot, oyun sürümü ayrımı; train/test run ve seed bazında.
- İyi skor ama kötü karar → pişmanlık, hayatta kalma, karşı-olgusal testler.
- Mod oyun güncellemesiyle bozulur → oyun ve mod sürümünü sabitle.
- Mac'te işlem gücü sınırlı → PyTorch MPS; büyük eğitimler için Colab/Kaggle GPU; simülasyon çok çekirdekli.

## Final çıktılar ve ekstralar
Çıktılar: mükemmele yaklaşan bot + Random→Greedy→Değer→PPO→Arama karşılaştırması; gerçek oyunla doğrulanmış hızlı simülatör; sürümlenmiş katalog ve run/karar veri seti; joker etkisi/sinerji/seed zorluğu/boss riski/ekonomi analizleri; canlı panel, replay, tekrarlanabilir deney protokolü, rapor; GitHub reposu (uygunsa Kaggle/Hugging Face veri seti).
Ekstralar: bot-LLM-insan turnuvası, koç modu, bulmaca üretici, modlu oyun desteği (transfer learning testi), Endless rekor videosu.
