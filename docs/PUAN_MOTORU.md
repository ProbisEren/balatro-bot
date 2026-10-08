# Puan motoru (`balatro_ai/sim/`)

Bir elin skorunu, oyunun kendi kurallarına göre hesaplar. Referans oyunun Lua kodudur (`Balatro.love`: `game.lua`, `card.lua`, `blind.lua`, `functions/misc_functions.lua`, `functions/state_events.lua`); wiki kullanılmadı.

## Parçalar
- `kartlar.py`: kart modeli (rütbe, renk, geliştirme, baskı, mühür, debuff) ve BalatroBot kartından çevirici (`apiden`).
- `el_turu.py`: `evaluate_poker_hand` karşılığı. Tam N kartlı gruplar, flush (Wild her rengi sayar), straight (As düşük/yüksek, köşe sarma yok), puanlayan kartlar, Stone kartların her zaman puanlaması, Four Fingers/Shortcut/Splash seçenekleri.
- `puan.py`: `evaluate_play` karşılığı. Taban değer (seviyeye göre) → puanlayan kartlar soldan sağa (chip, mult kartı, glass x2, baskı; kırmızı mühür iki kez) → elde kalan Steel kartlar → `floor(chips × mult)`.
- `boss.py`: boss blind etkileri: renk bosları (Club, Goad, Window, Head), The Plant, Verdant Leaf, The Psychic, The Eye, The Mouth, The Flint, The Arm.

## Doğrulama (gerçek oyun, 2026-10-08)
524 jokersiz el, gerçek run kayıtlarından (`tests/veri/gercek_eller.json`; 535 el, 11'i jokerli ve çıkarıldı):

| Blind | El | El türü | Skor |
|---|---|---|---|
| Small | 372 | 372 doğru | 372 doğru |
| Big | 76 | 76 doğru | 76 doğru |
| Boss | 76 | 76 doğru | 76 doğru |

Boss'lar: The Psychic, The Window, The Goad, The Club, The Hook ve diğerleri (kayıtlarda geçenler). İki yöntemle sınandı: (1) oyunun karta verdiği `state.debuff` bayraklarıyla, (2) yalnızca `boss.py` kurallarıyla; ikisi de %100 uyuşuyor. Doğrulama `tests/test_puan_motoru.py` içindedir; fixture `python -m balatro_ai.eval.el_ornekleri` ile üretilir.

Doğrulamada bulunan ve düzeltilen iki şey: Stone kart "en yüksek kart" seçiminde hiç seçilmez (oyunda çarpan -1000); testte jokerli bir run (Abstract Joker, +3 mult) motorun tam 2,5 katı skor verince jokerler doğrulamadan çıkarıldı.

## Bilinen sınırlar (henüz yok / doğrulanmadı)
- **Jokerler yok.** `puan_hesapla(jokerler=...)` boş olmayan değerde `NotImplementedError` verir. Plan: en sık görülen jokerler, her biri gerçek oyun kayıtlarıyla doğrulanarak.
- **Geliştirilmiş kartlar gerçek oyunda neredeyse hiç doğrulanmadı.** Fixture'da yalnızca 1 Bonus kart var. Mult, Glass, Steel, Stone, Lucky, Wild, baskılar (Foil/Holo/Polychrome) ve mühürler oyunun Lua kodundan okunan sayılarla yazıldı ve birim testleriyle sınandı, ama gerçek skorlarla karşılaştırılmadı. `apiden` yalnızca `{'enhancement': 'BONUS'}` biçimini gerçek oyunda gördü; diğer değerler tahmin (bilinmeyen değer hata verir).
- **Lucky kart** rastgele; varsa `belirsiz=True` döner, etkisi sayılmaz.
- **Seviyesi yükselmiş eller** gerçek veride görülmedi (fixture'da hepsi seviye 1). Seviye artışları oyunun tablosundan alındı.
- **Boss'lar**: The Pillar, The Hook, The House, The Wheel, The Fish, The Mark, The Serpent, The Manacle, The Needle, The Water, The Wall, Violet Vessel, Amber Acorn, Crimson Heart, Cerulean Bell, The Ox, The Tooth uygulanmadı (puanlamayı değiştirmezler ya da geçmiş/rastgelelik gerektirir). Kart debuff'ını oyun `state.debuff` ile bildirir.
- Hand'in "contains" listesi (`iceren`) jokerler için hazır ama kullanılmadı.
