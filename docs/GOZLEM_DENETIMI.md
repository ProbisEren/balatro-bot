# Gözlem denetimi: bot ne görüyor?

Amaç: botun gördüğü her bilginin, oyunu normal oynayan bir insanın da gördüğü bilgi olduğunu kanıtlamak (docs/PLAN.md, adil oyun kuralı). Denetim 2026-10-08'de gerçek oyunda (Balatro + BalatroBot v1.5.2) yapıldı: her fazda API cevabı ile oyun ekranının görüntüsü yan yana kıyaslandı. Düzeltme `balatro_ai/env/gozlem.py` içindeki `insan_gozlemi()` fonksiyonundadır; bot yalnızca bu fonksiyonun çıktısını görür.

## Bulunan sızıntılar ve çözümü
| Alan | Sorun | Çözüm | Doğrulama |
|---|---|---|---|
| `seed` | Run tohumu cevapta açık. | Silinir. | Birim testi |
| `cards` (deste) | Round içinde çekiliş sırasında listeleniyor; sonraki çekilişler listenin sonundan ters sırayla geliyor. Gerçek oyunda doğrulandı (discard sonrası gelen `S_A`, `C_4` = listenin son iki kartı, ters). | Kart anahtarına göre sıralanır; içerik (hangi kartların kaldığı) korunur, sıra silinir. Oyundaki deste ekranı da kalan kartları sıralı gösterir. | Birim testi: 5 farklı rastgele sırada aynı gözlem |
| `state.hidden` (yüzü kapalı kart) | Kart kapalı olsa da `key`, `value`, `label` cevapta duruyor. | El, joker, tüketilebilir, mağaza, kupon, paket alanlarında kapalı kartın kimliği silinir, yalnızca "kapalı" bilgisi kalır. | Birim testi (sentetik kart). Gerçek bir boss ile test edilmedi. |

## Fazlar ve kıyas sonucu
| Faz | API ↔ ekran | Not |
|---|---|---|
| SELECTING_HAND | Uyuşuyor | El kartları ve sırası, kalan el/discard, para, ante/round, hedef skor, deste sayacı (42/52). |
| ROUND_EVAL | Yalnızca durum kontrol edildi | Ekran görüntüsü alınmadı. |
| SHOP | Uyuşuyor | Mağaza kartları, kupon, paketler, reroll ücreti, para, deste sayacı (52/52). |
| SMODS_BOOSTER_OPENED | İçerik uyuşuyor, zamanlama farklı | Paketin 5 kartı API'de animasyon bitmeden görünüyor, insan 1-2 saniye sonra görüyor. Sızıntı sayılmadı. |

## Doğrulanmadı (açık işler)
- BLIND_SELECT: tag ve boss bilgisi (insan seçim ekranında bunları görür, API ile kıyaslanmadı).
- GAME_OVER ve ante geçişi.
- Yüzü kapalı kart: gerçek boss (The House, The Wheel, The Mark gibi) ile.
- Joker ve tüketilebilirlerin özel durumları (ör. gizli sayaçlar).
- Kartların `id` alanı: oyunun iç kimliği, insan görmez. Karar için kullanılmaz, sızıntı olduğuna dair kanıt yok, gerekirse kaldırılır.

## Kurallar
- Bot yalnızca `insan_gozlemi()` çıktısını görür; ham `gamestate` ajana verilmez.
- `set`, `add`, `load`, `save`, `screenshot` uç noktaları `balatro_ai/env/client.py` içinde yoktur. Denetim için bu uç noktalar bota ait olmayan terminal komutlarıyla kullanıldı.
