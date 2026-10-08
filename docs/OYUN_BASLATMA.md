# Oyunu botla başlatma

Kurulum: Balatro (Steam) + Lovely + Steamodded + BalatroBot modu. Sürümler için `docs/KAYNAKLAR.md`.

## Doğru yöntem: `balatrobot serve`
Oyunu `balatrobot` komut satırıyla başlat. `run_lovely_macos.sh` ile açılan oyunda BalatroBot'un `start` komutu hata verdi:
`attempt to index field 'viewed_back' (a nil value)` (`start.lua`, 116. satır). Aynı oyun `balatrobot serve` ile açılınca `start` her denemede çalıştı. Farkın nedenini araştırmadım, yalnızca sonucu doğruladım.

Proje bağımlılıklarından ayrı bir sanal ortama kur (paket yalnızca oyunu başlatmak içindir, botun kendisi kullanmaz):

```
python3 -m venv ~/.balatrobot-venv
~/.balatrobot-venv/bin/pip install balatrobot==1.5.2
~/.balatrobot-venv/bin/balatrobot serve --fast
```

- Paketin 1.5.2 sürümünün içeriği GitHub'daki `v1.5.2` kaynağıyla karşılaştırıldı, `src/balatrobot` birebir aynı.
- macOS'te oyun Steam üzerinden değil, bu komutla (veya `run_lovely_macos.sh` ile) açılmalıdır; Steam istemcisinde bilinen bir hata var.
- Varsayılan adres `127.0.0.1:12346`. `--fast` oyunu 10 kat hızlandırır. Durdurmak için Ctrl+C.

## Doğrulanan davranış (2026-10-08)
- `start(deste, stake, seed)` menüden çağrılınca `BLIND_SELECT` durumuna geçer.
- Aynı seed ve aynı deste aynı ilk eli verir. Örnek: `TEST0001`, RED/WHITE → `D_A D_Q S_T C_T D_T H_9 D_4 S_2`. Bu, ajanları aynı seed'lerde karşılaştırmayı (docs/PLAN.md, Bölüm 9) mümkün kılar.
- Seed verilmezse oyun rastgele bir seed seçer ve cevapta döndürür. Bot bu alanı görmez (`docs/GOZLEM_DENETIMI.md`).

## Gerçek oyunda bulunan sorunlar ve çözümleri (2026-10-08)

### 1. `start` bir `GAME_OVER`'dan sonra hata veriyor (yama gerekli)
Biten bir run'dan sonra `menu` + `start` her seferinde `attempt to index field 'viewed_back' (a nil value)` hatası veriyor. `viewed_back` yalnızca arayüzdeki deste önizlemesi için kullanılıyor, seçili deste `selected_back` ile ayrıca ayarlanıyor. Çözüm, BalatroBot modunda tek bir satırı "nesne yoksa atla" şeklinde korumak: `docs/yamalar/balatrobot-start-viewed-back.patch`. Yama `~/Library/Application Support/Balatro/Mods/balatrobot/src/lua/endpoints/start.lua` dosyasına uygulanır, orijinali `start.lua.orig` olarak saklanır; oyunu yeniden başlatmak gerekir. Bu, üçüncü taraf modda bizim yamamızdır; upstream'de bildirilmedi.
Doğrulama: yamadan sonra biten run'ların ardından üst üste 4 yeni run başladı.

### 2. `pack` komutunun cevabı bazen hiç gelmiyor
Tag ile açılan paketi `pack {skip: true}` ile atlayınca komut oyunda uygulanıyor (durum `BLIND_SELECT`'e dönüyor) ama API cevabı hiç gönderilmiyor (15 sn+ zaman aşımı). Ortam (`BalatroOrtami`) `pack` için 8 sn bekler, durumu yoklar; durum değiştiyse komutu başarılı sayar ve kayda `cevap_zaman_asimi: true` yazar.

### 3. Gecikmeli olaylar: bekleme şart
Bir blind'ı atlayınca ödül tag'i (ör. Charm Tag → bedava Mega Arcana Pack) paketi gecikmeyle açıyor. API bu sırada `BLIND_SELECT` döndürüyor. Ajan beklemeden bir sonraki blind'ı da atlarsa iki tag etkisi iç içe girip oyunu kilitliyor (ekranda "Choose your next Blind" yazısı ve ortada boş bir paket kalıyor). Ortam, `skip`, `buy`, `use`, `pack`, `sell`, `reroll` komutlarından sonra durum 0,6 sn boyunca değişmeyene kadar bekler.

### 4. Tarot paketleri ve hedef kartlar
Bazı tarotlar (`c_sun`, `c_world`, `c_empress` ...) eldeki 1-3 kartı hedef olarak istiyor; hedefsiz seçim `-32001` hatasıyla reddediliyor ("requires 1-3 target card(s)"). Ortam bu mesajdan her kartın hedef sayısını öğrenir ve sonraki seçeneklerde yalnızca geçerli hedef kombinasyonlarını sunar.

### 5. Oyunu yeniden başlatırken
`balatrobot serve` ile açılan oyun kapatıldıktan sonra hemen yeniden açılırsa 30 sn içinde sağlık kontrolü başarısız olabiliyor; eski `love` sürecinin tamamen bitmesi için birkaç saniye beklenmeli.

### Ölçülen hız (2026-10-08, `--fast`, rastgele ajan, 6 run)
Ortalama run süresi yaklaşık 10 sn (hepsi ilk blind'da bitti). API cevap süresi: medyan 483 ms, %95'i 1394 ms. Uzun run'ların süresi henüz ölçülmedi.
