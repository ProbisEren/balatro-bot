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
