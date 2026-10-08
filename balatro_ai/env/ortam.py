"""Gymnasium ortamı: gerçek oyunu (BalatroBot) ve ileride simülatörü aynı arayüzle sunar.

- Bot yalnızca `insan_gozlemi()` çıktısını görür (adil oyun kuralı).
- Geçerli aksiyonlar ortam tarafından hesaplanır; bota aksiyon kimlikleri ve maske gider.
- Her komut (botun seçtiği ve otomatik geçilen aşamalar dahil) `RunLogger` ile kaydedilir.
- Aksiyon kümesi "dar" (yalnızca el oynama/discard, kalan aşamalar sabit kurallarla) veya
  "tam" (blind, mağaza, paket kararları da botta). Bkz. aksiyonlar.py.
"""

from __future__ import annotations

import re
import time
from pathlib import Path
from typing import Any, ClassVar

import gymnasium as gym
import numpy as np
from gymnasium import spaces

from balatro_ai.data.logger import RunLogger
from balatro_ai.env import aksiyonlar
from balatro_ai.env.client import (
    BaglantiHatasi,
    BalatroHatasi,
    GecersizDurum,
    GecersizIstek,
    RpcHatasi,
)
from balatro_ai.env.gozlem import insan_gozlemi

GECIS_FAZLARI = frozenset({"HAND_PLAYED", "DRAW_TO_HAND", "NEW_ROUND", "PLAY_TAROT"})
# Bu komutlardan sonra oyun gecikmeli olay tetikleyebilir (tag ile açılan paket, satın alma animasyonu):
# durum değişmeyene kadar beklemeden yeni komut gönderilirse oyun kilitlenebiliyor (gerçek oyunda görüldü).
# Mod bu komutların cevabını bazen hiç göndermiyor ama komut oyunda uygulanıyor (gerçek oyunda görüldü:
# tag paketini `pack skip` ile atlamak). Cevap gelmezse durum yoklanır, değiştiyse komut başarılı sayılır.
CEVAPSIZ_OLABILEN = frozenset({"pack"})
CEVAP_ZAMAN_ASIMI_SN = 8.0
HEDEF_HATASI = re.compile(r"Card '([^']+)' requires (?:exactly )?(\d+)(?:-(\d+))? target card")
YERLESME_KOMUTLARI = frozenset({"skip", "buy", "use", "pack", "sell", "reroll"})
ODUL_BLIND = {"SMALL": 1.0, "BIG": 1.0, "BOSS": 3.0}
ODUL_KAZANMA = 20.0  # docs/PLAN.md, Bölüm 7.2. Ara ölçütlere (para, ham skor) ödül verilmez.


def _durum_imzasi(durum: dict[str, Any]) -> tuple:
    """Durumun yerleşip yerleşmediğini anlamak için kısa parmak izi."""
    kartlar = lambda a: tuple(k.get("key") for k in (durum.get(a) or {}).get("cards", []))
    return (
        durum.get("state"), durum.get("money"), kartlar("pack"), kartlar("hand"),
        kartlar("shop"), kartlar("jokers"), kartlar("consumables"),
        tuple((b.get("status")) for b in (durum.get("blinds") or {}).values()),
    )


class OrtamHatasi(Exception):
    """Ortamın kendi hatası: oyun beklenmedik bir fazda, geçerli aksiyon kalmadı gibi durumlar."""


class GecersizAksiyon(OrtamHatasi):
    """Ajan, geçerli olmayan bir aksiyon kimliği seçti (ajan hatası)."""


class BalatroOrtami(gym.Env):
    """Gymnasium ortamı: gerçek oyunu (BalatroBot) bota insan gözlemi ve aksiyon kimlikleriyle sunar, her komutu loglar.
    """
    metadata: ClassVar[dict[str, Any]] = {"render_modes": []}

    def __init__(
        self,
        istemci: Any,
        *,
        kume: str = "dar",
        log_kok: str | Path | None = None,
        yaklasim: str | None = None,
        ajan: dict[str, Any] | None = None,
        yapilandirma: dict[str, Any] | None = None,
        bolum: str = "gelistirme",
        deste: str = "RED",
        stake: str = "WHITE",
        max_adim: int = 3000,
        oyun_bilgisi: dict[str, Any] | None = None,
        oyun_ayarlari: dict[str, Any] | None = None,
        lovely_log: str | Path | None = None,
        gecis_bekleme_sn: float = 60.0,
        uyku_sn: float = 0.05,
        yerlesme_sn: float = 0.6,
        yerlesme_en_cok_sn: float = 8.0,
    ):
        """Ortamı kurar: istemci, aksiyon kümesi (dar/tam), log klasörü, ajan bilgisi ve zamanlama ayarları.
        """
        if kume not in aksiyonlar.KUMELER:
            raise ValueError(f"Bilinmeyen aksiyon kümesi: {kume}")
        super().__init__()
        self.istemci = istemci
        self.kume = kume
        self.log_kok = Path(log_kok) if log_kok else None
        self.yaklasim = yaklasim or f"{kume}_kume"
        self.ajan = ajan or {"tur": "bilinmiyor"}
        self.yapilandirma = yapilandirma or {}
        self.bolum = bolum
        self.deste = deste
        self.stake = stake
        self.max_adim = max_adim
        self.oyun_bilgisi = oyun_bilgisi or {}
        self.oyun_ayarlari = oyun_ayarlari or {}
        self.lovely_log = lovely_log
        self.gecis_bekleme_sn = gecis_bekleme_sn
        self.uyku_sn = uyku_sn
        self.yerlesme_sn = yerlesme_sn
        self.yerlesme_en_cok_sn = yerlesme_en_cok_sn

        self.action_space = spaces.Discrete(aksiyonlar.aksiyon_sayisi(kume))
        # Gözlem, filtrelenmiş oyun durumu sözlüğüdür; sabit boyutlu bir uzay değil.
        self.observation_space = spaces.Space(dtype=object)

        self._durum: dict[str, Any] = {}
        self._log: RunLogger | None = None
        self._engelli: set[int] = set()
        self._hedef_gereksinimi: dict[str, tuple[int, int]] = {}
        self._adim = 0
        self._son_gozlem_zamani = time.monotonic()
        self.run_id: str | None = None
        self.ajan_ek: dict[str, Any] | None = None  # ajanın karar açıklaması; sonraki step'in kaydına yazılır

    # ------------------------------------------------------------------ gym API
    def reset(self, *, seed: int | None = None, options: dict[str, Any] | None = None):
        super().reset(seed=seed)
        options = options or {}
        self._run_kapat("iptal")
        self._adim = 0
        self._engelli = set()
        self._durum = self.istemci.durum()
        if self._durum.get("state") != "MENU":
            self._durum = self.istemci.komut("menu")
        oyun_seed = options.get("oyun_seed")
        deste = options.get("deste", self.deste)
        stake = options.get("stake", self.stake)

        if self.log_kok is not None:
            self._log = RunLogger(self.log_kok, run_id=options.get("run_id")).__enter__()
            self.run_id = self._log.run_id
            self._log.run_basla(
                seed=oyun_seed,
                deste=deste,
                stake=stake,
                yaklasim=self.yaklasim,
                ajan=self.ajan,
                yapilandirma=self.yapilandirma,
                oyun=self.oyun_bilgisi,
                oyun_ayarlari=self.oyun_ayarlari,
                bolum=options.get("bolum", self.bolum),
                rol=options.get("rol", "baseline"),
                gorev_id=options.get("gorev_id"),
            )
        param: dict[str, Any] = {"deck": deste, "stake": stake}
        if oyun_seed is not None:
            param["seed"] = oyun_seed
        self._gonder({"yontem": "start", "parametreler": param}, otomatik=True)
        self._otomatik_ilerle()
        self._son_gozlem_zamani = time.monotonic()
        return self._gozlem(), self._bilgi()

    def step(self, aksiyon: int):
        """Ajanın seçtiği aksiyonu oyunda uygular; ödülü hesaplar, sabit kural aşamalarını geçer, bitişte run'ı kapatır.
        """
        if self._log is None and self.log_kok is not None:
            raise OrtamHatasi("Run açık değil, önce reset() çağır")
        bot_ms = (time.monotonic() - self._son_gozlem_zamani) * 1000
        aksiyon = int(aksiyon)
        gecerli = self._gecerli()
        if aksiyon not in gecerli:
            raise GecersizAksiyon(f"Aksiyon {aksiyon} bu durumda geçerli değil (faz={self._durum.get('state')})")
        onceki = self._durum
        secenekler = [aksiyonlar.komut(i) for i in gecerli]
        cmd = aksiyonlar.komut(aksiyon)
        ok = self._gonder(
            cmd, otomatik=False, secenekler=secenekler, aksiyon_id=aksiyon, bot_ms=bot_ms
        )
        odul = 0.0
        gecersiz = False
        if not ok:
            self._engelli.add(aksiyon)  # oyun reddetti: bu durumda tekrar önerme
            gecersiz = True
        else:
            self._engelli.clear()
            odul = self._odul(onceki, self._durum)
            self._otomatik_ilerle()
            odul += ODUL_KAZANMA if self._durum.get("won") and not onceki.get("won") else 0.0
        self._adim += 1
        sonlandi = self._durum.get("state") == "GAME_OVER" or bool(self._durum.get("won"))
        kesildi = (not sonlandi) and self._adim >= self.max_adim
        if sonlandi or kesildi:
            self._run_kapat(self._sonuc_durumu(kesildi))
        self._son_gozlem_zamani = time.monotonic()
        return self._gozlem(), odul, sonlandi, kesildi, self._bilgi(gecersiz=gecersiz)

    def close(self) -> None:
        """Açık bir run varsa `iptal` olarak kapatır."""
        self._run_kapat("iptal")

    # ------------------------------------------------------------------ yardımcılar
    def _gozlem(self) -> dict[str, Any]:
        return insan_gozlemi(self._durum)

    def _gecerli(self) -> list[int]:
        """O anki durumda geçerli aksiyon kimlikleri (oyunun reddedenleri hariç, öğrenilmiş hedef sayılarıyla).
        """
        return aksiyonlar.gecerli(
            self._durum, self.kume, frozenset(self._engelli), self._hedef_gereksinimi
        )

    def _hedef_ogren(self, mesaj: str) -> None:
        """Oyunun reddettiği "Card 'c_sun' requires 1-3 target card(s)" mesajından hedef sayısını öğrenir."""
        m = HEDEF_HATASI.search(mesaj or "")
        if m:
            en_az = int(m.group(2))
            self._hedef_gereksinimi[m.group(1)] = (en_az, int(m.group(3) or en_az))

    def _bilgi(self, gecersiz: bool = False) -> dict[str, Any]:
        """Ajanın göreceği bilgi sözlüğü: geçerli aksiyonlar, maske, faz, ante, run kimliği."""
        ids = self._gecerli()
        bitti = self._durum.get("state") == "GAME_OVER" or self._durum.get("won")
        if not ids and not bitti:
            raise OrtamHatasi(
                f"Geçerli aksiyon kalmadı (faz={self._durum.get('state')}, engelli={sorted(self._engelli)})"
            )
        maske = np.zeros(self.action_space.n, dtype=bool)
        maske[ids] = True
        return {
            "gecerli_aksiyonlar": ids,
            "action_mask": maske,
            "faz": self._durum.get("state"),
            "ante": self._durum.get("ante_num"),
            "run_id": self.run_id,
            "gecersiz": gecersiz,
        }

    def _odul(self, once: dict[str, Any], sonra: dict[str, Any]) -> float:
        """Bir blind geçildiyse ödül (docs/PLAN.md): Small/Big +1, Boss +3."""
        if once.get("state") != "SELECTING_HAND" or sonra.get("state") == "SELECTING_HAND":
            return 0.0
        if sonra.get("state") == "GAME_OVER":
            return 0.0
        simdiki = next(
            (b for b in (once.get("blinds") or {}).values() if b.get("status") == "CURRENT"), None
        )
        return ODUL_BLIND.get(simdiki.get("type"), 0.0) if simdiki else 0.0

    def _gonder(
        self,
        cmd: dict[str, Any],
        *,
        otomatik: bool,
        secenekler: list[dict[str, Any]] | None = None,
        aksiyon_id: int | None = None,
        bot_ms: float | None = None,
    ) -> bool:
        """Komutu gönderir ve kaydeder. Oyun reddederse False döner (durum değişmez)."""
        once = self._durum
        t0 = time.monotonic()
        cevap = hata = None
        ek_not: dict[str, Any] = {}
        try:
            zaman_asimi = CEVAP_ZAMAN_ASIMI_SN if cmd["yontem"] in CEVAPSIZ_OLABILEN else None
            cevap = self.istemci.komut(cmd["yontem"], cmd["parametreler"], zaman_asimi)
        except (GecersizDurum, GecersizIstek) as e:
            hata = {"kod": e.kod, "mesaj": e.mesaj}
            self._hedef_ogren(e.mesaj)
        except BaglantiHatasi:
            cevap = self._cevapsizi_toparla(cmd, once)
            if cevap is None:
                if self._log:
                    self._log.sayac_artir("zaman_asimi")
                raise
            ek_not = {"cevap_zaman_asimi": True}
        except RpcHatasi as e:
            self._kaydet(once, cmd, None, {"kod": e.kod, "mesaj": e.mesaj}, otomatik, secenekler,
                         aksiyon_id, bot_ms, (time.monotonic() - t0) * 1000)
            if self._log:
                self._log.sayac_artir("mod_hatasi")
            raise
        except BalatroHatasi:
            if self._log:
                self._log.sayac_artir("oyun_cokmesi")
            raise
        api_ms = (time.monotonic() - t0) * 1000
        self._kaydet(once, cmd, cevap, hata, otomatik, secenekler, aksiyon_id, bot_ms, api_ms, ek_not)
        if cevap is not None:
            self._durum = cevap
            if cmd["yontem"] in YERLESME_KOMUTLARI:
                self._yerles()
        return hata is None

    def _cevapsizi_toparla(self, cmd: dict[str, Any], once: dict[str, Any]) -> dict[str, Any] | None:
        """Cevap gelmeyen komutun oyunda uygulanıp uygulanmadığına bakar; uygulandıysa yeni durumu döndürür."""
        if cmd["yontem"] not in CEVAPSIZ_OLABILEN:
            return None
        bitis = time.monotonic() + self.yerlesme_en_cok_sn
        baslangic = _durum_imzasi(once)
        while time.monotonic() < bitis:
            time.sleep(max(self.uyku_sn, 0.1))
            try:
                yeni = self.istemci.durum()
            except BaglantiHatasi:
                continue
            if _durum_imzasi(yeni) != baslangic:
                return yeni
        return None

    def _yerles(self) -> None:
        """Durum en az `yerlesme_sn` boyunca hiç değişmeyene kadar bekler (gecikmeli olaylar için)."""
        if self.yerlesme_sn <= 0:
            return
        simdi = time.monotonic()
        bitis = simdi + self.yerlesme_en_cok_sn
        onceki = _durum_imzasi(self._durum)
        son_degisim = simdi
        aralik = min(0.05, self.yerlesme_sn / 4)
        while time.monotonic() < bitis:
            time.sleep(aralik)
            yeni = self.istemci.durum()
            self._durum = yeni
            imza = _durum_imzasi(yeni)
            if imza != onceki:
                onceki, son_degisim = imza, time.monotonic()
            elif time.monotonic() - son_degisim >= self.yerlesme_sn:
                return
        if self._log:
            self._log.sayac_artir("zaman_asimi")

    def _kaydet(self, once, cmd, cevap, hata, otomatik, secenekler, aksiyon_id, bot_ms, api_ms, ek_not=None):
        """Bir komutu logger'a yazar: gözlem, ham durum, cevap, hata, seçenekler, süreler ve ajanın karar açıklaması.
        """
        if self._log is None:
            return
        self._log.karar(
            faz=once.get("state", "?"),
            gozlem=insan_gozlemi(once),
            komut=cmd,
            ham_durum=once,
            cevap=cevap,
            hata=hata,
            secenekler=secenekler,
            sure_ms=(bot_ms or 0.0) + api_ms,
            bot_ms=bot_ms,
            api_ms=api_ms,
            ek={
                "otomatik": otomatik,
                "aksiyon_id": aksiyon_id,
                "kume": self.kume,
                "ajan": self.ajan_ek if not otomatik else None,
                "hedef_gereksinimi": {k: list(v) for k, v in self._hedef_gereksinimi.items()},
                **(ek_not or {}),
            },
        )

    def _gecis_bekle(self) -> None:
        """Animasyon/geçiş fazlarında oyun sabit bir duruma gelene kadar bekler."""
        bitis = time.monotonic() + self.gecis_bekleme_sn
        while self._durum.get("state") in GECIS_FAZLARI:
            if time.monotonic() > bitis:
                if self._log:
                    self._log.sayac_artir("zaman_asimi")
                raise OrtamHatasi(f"Geçiş fazı bitmedi: {self._durum.get('state')}")
            time.sleep(self.uyku_sn)
            self._durum = self.istemci.durum()

    def _otomatik_ilerle(self) -> None:
        """Botun karar vermediği aşamaları sabit kurallarla geçer."""
        for _ in range(100):
            self._gecis_bekle()
            faz = self._durum.get("state")
            if self._durum.get("won") or faz in ("GAME_OVER", "MENU", "SELECTING_HAND"):
                return
            if faz == "ROUND_EVAL":
                cmd = {"yontem": "cash_out", "parametreler": None}
            elif self.kume == "dar" and faz == "BLIND_SELECT":
                cmd = {"yontem": "select", "parametreler": None}
            elif self.kume == "dar" and faz == "SHOP":
                cmd = {"yontem": "next_round", "parametreler": None}
            elif self.kume == "dar" and faz in aksiyonlar.PAKET_FAZLARI:
                cmd = {"yontem": "pack", "parametreler": {"skip": True}}
            elif self.kume == "tam" and faz in ("BLIND_SELECT", "SHOP", *aksiyonlar.PAKET_FAZLARI):
                return  # botun kararı
            else:
                raise OrtamHatasi(f"Bilinmeyen faz, otomatik ilerlenemiyor: {faz}")
            if not self._gonder(cmd, otomatik=True):
                raise OrtamHatasi(f"Otomatik komut reddedildi: {cmd} (faz={faz})")
        raise OrtamHatasi("Otomatik ilerleme sonlanmadı (100 adım)")

    def _sonuc_durumu(self, _kesildi: bool) -> str:
        """Bitmiş run'ın sonucunu belirler: kazandi, kaybetti veya iptal."""
        if self._durum.get("won"):
            return "kazandi"
        if self._durum.get("state") == "GAME_OVER":
            return "kaybetti"
        return "iptal"

    def _run_kapat(self, durum: str) -> None:
        """Run'ın sonuç kaydını (son ante, ölüm nedeni, skor) yazıp logger'ı kapatır."""
        if self._log is None:
            return
        d = self._durum
        simdiki = next(
            (b for b in (d.get("blinds") or {}).values() if b.get("status") == "CURRENT"), None
        )
        try:
            self._log.run_bitir(
                durum=durum,
                son_ante=d.get("ante_num"),
                son_round=d.get("round_num"),
                olum_nedeni=(simdiki or {}).get("name") if durum == "kaybetti" else None,
                lovely_log=self.lovely_log,
                ek={
                    "son_skor": (d.get("round") or {}).get("chips"),
                    "hedef_skor": (simdiki or {}).get("score"),
                },
            )
        finally:
            self._log.__exit__(None, None, None)
            self._log = None
