# Kaynaklar

Projede kullanılan araç, yazılım ve dokümanların listesi. Yeni bir şey eklenince bu dosya güncellenir. Erişim tarihi: 2026-10-08.

## Proje planı
- `docs/PLAN.md`: Balatro AI Final Proje Planı, sürüm 2.0 (8 Ekim 2026).

## Oyun ve mod zinciri (gerçek oyuna bağlanmak için)
Zincir: Balatro (Steam) → Lovely Injector → Steamodded → BalatroBot. Hepsi macOS'te, Steam üzerinden değil `run_lovely_macos.sh` ile açılan oyunda çalışır (Steam istemcisindeki bilinen hata nedeniyle).

| Parça | Sürüm (kurulan) | Gereken | Kaynak | Lisans |
|---|---|---|---|---|
| Balatro | Steam sürümü (kayıtlı sürüm numarası ayrıca loglanacak) | 1.0.1 veya üstü | https://store.steampowered.com/app/2379780/Balatro/ | Ticari, satın alındı |
| Lovely Injector | 0.10.0 | 0.8.0 veya üstü | https://github.com/ethangreen-dev/lovely-injector | MIT |
| Steamodded | 26.1002.0 (manifest iç sürümü 26.829.0) | 1.0.0-beta-1221a veya üstü | https://github.com/Steamodded/smods · indirme: https://release.smods.dev | GPL-3.0 |
| BalatroBot | v1.5.2 etiketi, commit `9052d76f14723293f6c6b2cecaa791a5c4ae68f3` (mod kendini 1.5.1 olarak bildiriyor) | Steamodded (>=1.~) | https://github.com/coder/balatrobot | MIT |

Lisanslar GitHub lisans bilgisi ve indirilen LICENSE dosyalarıyla doğrulandı.

Kurulum dokümanları:
- BalatroBot dokümanı: https://coder.github.io/balatrobot/latest/ (installation, cli, api sayfaları)
- BalatroBot API: JSON-RPC 2.0 over HTTP, varsayılan adres `127.0.0.1:12346`
- Steamodded macOS kurulumu: https://docs.smods.dev/Installation/Installing%20Steamodded%20mac
- Lovely macOS kurulumu: Lovely README (yukarıdaki repo)

Not: BalatroBot modunda `start.lua` içinde bizim bir satırlık yamamız var (`docs/yamalar/`, ayrıntı `docs/OYUN_BASLATMA.md`).

Oyunu başlatan komut satırı: `balatrobot` 1.5.2 (PyPI, https://pypi.org/project/balatrobot/), MIT. Ayrıntı: `docs/OYUN_BASLATMA.md`.

Doğrulama: Lovely log'u `~/Library/Application Support/Balatro/Mods/lovely/log/` altında. Kurulum sonrası `health` isteği `{"status":"ok"}` döndürdü.

## Yazılım bağımlılıkları (şu an)
| Paket | Sürüm | Kullanım | Kaynak |
|---|---|---|---|
| Python | 3.13.9 | dil | https://www.python.org |
| pytest | 9.1.1 | test | https://docs.pytest.org |
| ruff | 0.16.10 | lint | https://docs.astral.sh/ruff |
| duckdb | 1.5.6 | run kayıtlarını sorgulama | https://duckdb.org (MIT) |
| gymnasium | 1.4.0 | ortam arayüzü | https://gymnasium.farama.org (MIT) |
| numpy | (gymnasium ile gelen) | aksiyon maskesi | https://numpy.org (BSD-3) |

Planda ileride kullanılacaklar (henüz kurulmadı): Gymnasium, PyTorch, scikit-learn, XGBoost/LightGBM, Parquet, DuckDB, Polars, MLflow veya Weights & Biases, Streamlit, SHAP.

## Karşılaştırma ve yöntem kaynakları (planda geçenler)
- Expert Iteration (arama + öğrenme döngüsü), MCTS, PPO, determinizasyon: planın 2. ve 7. bölümlerinde anlatıldığı şekliyle. Orijinal makale bağlantıları eklenecek.
- Kaplan-Meier, propensity score, bootstrap güven aralığı: planın 9. ve 11. bölümleri.
