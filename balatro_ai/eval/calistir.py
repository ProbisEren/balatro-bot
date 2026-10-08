"""Ajanı gerçek oyunda oynatır ve her run'ı loglar.

Örnek (oyun `balatrobot serve` ile açıkken):
    python -m balatro_ai.eval.calistir --kume dar --run 3 --log-dizini veri/denemeler
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from balatro_ai.agents.greedy import GreedyAjan
from balatro_ai.agents.planlayici import PlanlayiciAjan
from balatro_ai.agents.rastgele import RastgeleAjan
from balatro_ai.agents.rutbe_grubu import RutbeGrubuAjan
from balatro_ai.env.client import BalatroIstemci
from balatro_ai.env.ortam import BalatroOrtami
from balatro_ai.eval.indeks import sonraki_deney_dizini, yaz

OYUN_BILGISI = {
    "balatrobot": "1.5.2",
    "steamodded": "26.1002.0",
    "lovely": "0.10.0",
    "baslatma": "balatrobot serve",
}
LOVELY_LOG_DIZINI = Path.home() / "Library/Application Support/Balatro/Mods/lovely/log"


def son_lovely_log() -> Path | None:
    """En son yazılan Lovely log dosyasını bulur (run kaydına bağlanır)."""
    kayitlar = sorted(LOVELY_LOG_DIZINI.glob("lovely-*.log"), key=lambda p: p.stat().st_mtime)
    return kayitlar[-1] if kayitlar else None


def run_oyna(env: BalatroOrtami, ajan: RastgeleAjan | RutbeGrubuAjan | GreedyAjan | PlanlayiciAjan, oyun_seed: str, **secenekler) -> dict:
    """Tek run oynatır; özet döndürür."""
    gozlem, bilgi = env.reset(options={"oyun_seed": oyun_seed, **secenekler})
    toplam_odul, adim = 0.0, 0
    sonlandi = kesildi = False
    while not (sonlandi or kesildi):
        aksiyon = ajan.sec(gozlem, bilgi)
        env.ajan_ek = getattr(ajan, "son_aciklama", None) or None
        gozlem, odul, sonlandi, kesildi, bilgi = env.step(aksiyon)
        toplam_odul += odul
        adim += 1
    return {
        "run_id": env.run_id,
        "seed": oyun_seed,
        "adim": adim,
        "odul": toplam_odul,
        "ante": gozlem.get("ante_num"),
        "kazandi": bool(gozlem.get("won")),
        "son_faz": gozlem.get("state"),
    }


def main(argv: list[str] | None = None) -> int:
    """Komut satırı girişi: seçilen ajanı seçilen kümede N run oynatır, kayıtları yazar ve indeks tablosunu günceller.
    """
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--kume", choices=["dar", "tam"], default="dar")
    ap.add_argument("--ajan", choices=["rastgele", "rutbe_grubu", "greedy", "planlayici"], default="rastgele")
    ap.add_argument("--run", type=int, default=1, help="oynatılacak run sayısı")
    ap.add_argument("--seed-oneki", default="BOT", help="oyun seed'leri: <önek><5 haneli sıra>")
    ap.add_argument("--ajan-tohumu", type=int, default=0)
    ap.add_argument("--bolum", default="gelistirme", choices=["gelistirme", "egitim", "dogrulama", "test"])
    ap.add_argument("--log-dizini", default=None, help="verilmezse veri/NN_ajan_küme_<deney-adi> otomatik")
    ap.add_argument("--deney-adi", default="deney", help="otomatik klasör adının son parçası")
    ap.add_argument("--kesif", type=float, default=0.0, help="planlayıcı: el dışı aşamalarda rastgele geçerli eylem olasılığı (ε); 0 = kapalı")
    ap.add_argument("--joker-toplama", action="store_true", help="planlayıcı: doğrulama verisi için tanımlı jokerleri değerlendirmeden satın alır")
    ap.add_argument("--max-adim", type=int, default=3000)
    args = ap.parse_args(argv)

    log_dizini = args.log_dizini or str(sonraki_deney_dizini("veri", args.ajan, args.kume, args.deney_adi))
    print(f"Kayıt klasörü: {log_dizini}")
    istemci = BalatroIstemci(zaman_asimi=60)
    if not istemci.saglik():
        print("Oyun/BalatroBot cevap vermiyor.", file=sys.stderr)
        return 2
    ajan = {"rutbe_grubu": RutbeGrubuAjan, "greedy": GreedyAjan, "planlayici": PlanlayiciAjan}.get(args.ajan, RastgeleAjan)(args.ajan_tohumu, **({"joker_toplama": True} if args.joker_toplama else {}), **({"kesif": args.kesif} if args.kesif else {}))
    env = BalatroOrtami(
        istemci,
        kume=args.kume,
        log_kok=log_dizini,
        yaklasim="A_tam" if args.kume == "tam" else "B_dar",
        ajan=ajan.bilgi(),
        yapilandirma={"ajan": args.ajan, "kume": args.kume, "max_adim": args.max_adim, "seed_oneki": args.seed_oneki},
        bolum=args.bolum,
        max_adim=args.max_adim,
        oyun_bilgisi=OYUN_BILGISI,
        oyun_ayarlari={"fast": True},
        lovely_log=son_lovely_log(),
    )
    try:
        for i in range(1, args.run + 1):
            ozet = run_oyna(env, ajan, f"{args.seed_oneki}{i:05d}")
            print(ozet)
    finally:
        env.close()
        yaz("veri")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
