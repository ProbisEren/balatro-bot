"""Run logger: her run için eklemeli (append-only) JSONL kaydı.

Bir run dosyası üç tür kayıt içerir, her satır bir JSON nesnesi:
  run_basi  (1 adet, ilk satır): kim, hangi kodla, hangi ayarla, hangi seed ile oynuyor
  karar     (N adet): her adımda gözlem, oyuna giden komut, ham durum, süre, serbest `ek`
  run_sonu  (en fazla 1 adet): sonuç. Yoksa run yarım kalmıştır (çökme).

Kurallar (CLAUDE.md, "Run kaydı"):
- Kayıt değişmez: var olan run dosyası yeniden açılmaz, eski satır düzenlenmez.
- Logger hata verirse run sessizce devam etmez, istisna yükselir.
- `ham_durum` botun görmediği bilgiyi (seed, deste sırası) içerir; yalnızca ölçüm içindir.
"""

from __future__ import annotations

import hashlib
import json
import platform
import subprocess
import sys
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Self

SEMA_SURUMU = "sema_v1"
SONUC_DURUMLARI = frozenset({"kazandi", "kaybetti", "iptal", "hata"})
# Eğitim/test sızıntısını önlemek için her run bir seed bölümüne ait olmalı.
BOLUMLER = frozenset({"gelistirme", "egitim", "dogrulama", "test"})
# Hile ve hata ayıklama komutları: kullanıldıysa run geçersiz sayılır (adil oyun kuralı).
HILE_KOMUTLARI = frozenset({"set", "add", "load", "save", "screenshot"})
SAYACLAR = ("zaman_asimi", "yeniden_deneme", "oyun_cokmesi", "mod_hatasi")


class LoggerHatasi(Exception):
    """Logger kural ihlali veya kayıt hatası; run'ın sessizce devam etmemesi için istisna olarak yükseltilir.
    """


def _simdi() -> str:
    """Şu anın UTC zamanını ISO biçiminde metin olarak döndürür."""
    return datetime.now(UTC).isoformat()


def _json_satiri(kayit: dict[str, Any]) -> str:
    """Kaydı tek satırlık, anahtarları sıralı, kompakt JSON metnine çevirir (JSONL biçimi)."""
    return json.dumps(kayit, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def yapilandirma_ozeti(yapilandirma: dict[str, Any]) -> str:
    """Yapılandırmanın sha256 özeti (anahtar sırasından bağımsız)."""
    return hashlib.sha256(_json_satiri(yapilandirma).encode("utf-8")).hexdigest()


def ozet(nesne: Any) -> str | None:
    """Bir JSON nesnesinin sha256 özeti (anahtar sırasından bağımsız)."""
    if nesne is None:
        return None
    return hashlib.sha256(_json_satiri(nesne).encode("utf-8")).hexdigest()


def gozlem_sizintisi(gozlem: Any) -> str | None:
    """Bota gösterilen gözlemde gizli bilgi varsa nedenini, yoksa None döndürür.

    Denetlenenler: herhangi bir yerde `seed` anahtarı; deste (`cards.cards`) çekiliş sırasında
    ise (kart anahtarına göre sıralı değilse) sıra bilgisi sızıyor demektir.
    """
    bulunan: list[str] = []

    def gez(o: Any, yol: str) -> None:
        """Gözlemi özyinelemeli gezip `seed` anahtarlarının yollarını toplar."""
        if isinstance(o, dict):
            for k, v in o.items():
                if str(k).lower() == "seed":
                    bulunan.append(f"{yol}/{k}")
                gez(v, f"{yol}/{k}")
        elif isinstance(o, list):
            for i, v in enumerate(o):
                gez(v, f"{yol}[{i}]")

    gez(gozlem, "")
    if bulunan:
        return f"gözlemde seed var: {bulunan[0]}"
    deste = gozlem.get("cards") if isinstance(gozlem, dict) else None
    kartlar = deste.get("cards") if isinstance(deste, dict) else None
    if isinstance(kartlar, list) and all(isinstance(k, dict) for k in kartlar):
        sirali = sorted(kartlar, key=lambda k: (k.get("key", ""), k.get("id", 0)))
        if sirali != kartlar:
            return "gözlemdeki deste sıralı değil (çekiliş sırası sızıyor olabilir)"
    return None


def _dosya_ozeti(yol: str | Path | None) -> dict[str, Any] | None:
    """Bir dosyanın yolunu, sha256 özetini, boyutunu ve içindeki hata satırı sayısını döndürür (Lovely log özeti için).
    """
    if yol is None:
        return None
    yol = Path(yol)
    try:
        ham = yol.read_bytes()
    except OSError as e:
        return {"yol": str(yol), "okunamadi": repr(e)}
    return {
        "yol": str(yol),
        "sha256": hashlib.sha256(ham).hexdigest(),
        "boyut": len(ham),
        "hata_satiri": sum(1 for s in ham.decode("utf-8", "replace").splitlines() if " ERROR " in s),
    }


def _git(*args: str) -> str | None:
    """git komutunu çalıştırıp çıktısını döndürür; git yoksa veya komut hata verirse None."""
    try:
        cikti = subprocess.run(
            ["git", *args], capture_output=True, text=True, timeout=10, check=True
        )
        return cikti.stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return None


def surum_bilgisi() -> dict[str, Any]:
    """Kod ve ortam sürümleri. Run'ı bir koda bağlar."""
    from balatro_ai import __version__

    sha = _git("rev-parse", "--short", "HEAD")
    durum = _git("status", "--porcelain")
    return {
        "kod": __version__,
        "git_sha": sha,
        # None: git yok/okunamadı. True: çalışma ağacında kaydedilmemiş değişiklik var.
        "git_kirli": None if durum is None else bool(durum),
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "makine": platform.machine(),
    }


class RunLogger:
    """Tek bir run için kayıt yazar. `with` ile kullanılır."""

    def __init__(self, kok: str | Path, run_id: str | None = None):
        """Bir run için kayıt yazıcısı hazırlar (dosyayı henüz açmaz); run_id verilmezse zaman ve rastgele ek üretilir.
        """
        self.kok = Path(kok)
        self.run_id = run_id or f"{datetime.now(UTC):%Y%m%dT%H%M%SZ}-{uuid.uuid4().hex[:8]}"
        self.yol = self.kok / f"{self.run_id}.jsonl"
        self._dosya = None
        self._adim = 0
        self._basladi = False
        self._bitti = False
        self._t0 = time.monotonic()
        self._hile_komutlari: list[str] = []
        self._sayaclar = dict.fromkeys(SAYACLAR, 0)

    def sayac_artir(self, ad: str, n: int = 1) -> None:
        """Ortam sorunlarını say: zaman_asimi, yeniden_deneme, oyun_cokmesi, mod_hatasi."""
        if ad not in self._sayaclar:
            raise LoggerHatasi(f"Bilinmeyen sayaç: {ad}")
        self._sayaclar[ad] += n

    # --- yaşam döngüsü ---
    def __enter__(self) -> Self:
        self.kok.mkdir(parents=True, exist_ok=True)
        if self.yol.exists():
            raise LoggerHatasi(f"Run kaydı zaten var, değiştirilemez: {self.yol}")
        self._dosya = open(self.yol, "x", encoding="utf-8")  # "x": varsa hata verir
        return self

    def __exit__(self, tur, deger, iz) -> None:
        """Bloktan çıkarken run bitirilmediyse sonucu `hata` (istisna varsa) veya `iptal` olarak yazar ve dosyayı kapatır.
        """
        try:
            if self._basladi and not self._bitti:
                # Run beklenmedik şekilde bitti; sonucu açıkça işaretle.
                durum = "hata" if tur is not None else "iptal"
                self.run_bitir(durum=durum, hata=repr(deger) if deger else None)
        finally:
            if self._dosya:
                self._dosya.close()
                self._dosya = None

    def _yaz(self, kayit: dict[str, Any]) -> None:
        """Tek bir kaydı dosyaya ekler ve diske yazılmasını zorlar (çökmede kayıp olmasın)."""
        if self._dosya is None:
            raise LoggerHatasi("Logger açık değil (`with RunLogger(...)` kullan)")
        self._dosya.write(_json_satiri(kayit) + "\n")
        self._dosya.flush()

    # --- kayıtlar ---
    def run_basla(
        self,
        *,
        seed: str | None,
        deste: str,
        stake: str,
        yaklasim: str,
        ajan: dict[str, Any],
        yapilandirma: dict[str, Any],
        oyun: dict[str, Any] | None = None,
        kaynak: str = "gercek_oyun",
        rol: str = "baseline",
        bolum: str = "gelistirme",
        oyun_ayarlari: dict[str, Any] | None = None,
        profil_parmak_izi: str | None = None,
        gorev_id: str | None = None,
        surumler: dict[str, Any] | None = None,
        ek: dict[str, Any] | None = None,
    ) -> None:
        """`ajan` zorunlu olarak `tur` içerir (random, greedy, ppo, ...). `oyun`: oyun/mod sürümleri."""
        if self._basladi:
            raise LoggerHatasi("run_basla iki kez çağrıldı")
        if "tur" not in ajan:
            raise LoggerHatasi("`ajan` içinde `tur` olmalı")
        if kaynak not in {"gercek_oyun", "simulator"}:
            raise LoggerHatasi(f"Bilinmeyen kaynak: {kaynak}")
        if bolum not in BOLUMLER:
            raise LoggerHatasi(f"Bilinmeyen seed bölümü: {bolum} (olası: {sorted(BOLUMLER)})")
        self._yaz(
            {
                "tip": "run_basi",
                "sema": SEMA_SURUMU,
                "run_id": self.run_id,
                "baslangic": _simdi(),
                "seed": seed,
                "deste": deste,
                "stake": stake,
                "yaklasim": yaklasim,
                "ajan": ajan,
                "yapilandirma": yapilandirma,
                "yapilandirma_ozeti": yapilandirma_ozeti(yapilandirma),
                "oyun": oyun or {},
                "kaynak": kaynak,
                "rol": rol,
                "bolum": bolum,
                "oyun_ayarlari": oyun_ayarlari or {},
                "profil_parmak_izi": profil_parmak_izi,
                "gorev_id": gorev_id,
                "surumler": surumler if surumler is not None else surum_bilgisi(),
                "ek": ek or {},
            }
        )
        self._basladi = True

    def karar(
        self,
        *,
        faz: str,
        gozlem: dict[str, Any],
        komut: dict[str, Any] | None,
        ham_durum: dict[str, Any],
        cevap: dict[str, Any] | None = None,
        hata: dict[str, Any] | None = None,
        secenekler: list[Any] | None = None,
        sure_ms: float | None = None,
        bot_ms: float | None = None,
        api_ms: float | None = None,
        ek: dict[str, Any] | None = None,
    ) -> int:
        """Bir kararı kaydeder, adım numarasını döndürür.

        `komut`: {"yontem": ..., "parametreler": ...}. `cevap`: komuttan sonra oyunun döndürdüğü
        ham durum (run'ın son hamlesinin sonucu da böylece kaydedilir). `hata`: oyun komutu
        reddettiyse {"kod": ..., "mesaj": ...}. `secenekler`: o anda geçerli olan tüm aksiyonlar
        (botun seçebildiği küme); seçilmeyen alternatifleri incelemek ve pişmanlık ölçmek için.
        """
        self._kontrol_acik()
        if komut is not None and "yontem" not in komut:
            raise LoggerHatasi("`komut` içinde `yontem` olmalı")
        neden = gozlem_sizintisi(gozlem)
        if neden:
            raise LoggerHatasi(f"Adil oyun ihlali, kayıt yazılmadı: {neden}")
        if komut is not None and komut["yontem"] in HILE_KOMUTLARI:
            self._hile_komutlari.append(komut["yontem"])
        self._adim += 1
        self._yaz(
            {
                "tip": "karar",
                "sema": SEMA_SURUMU,
                "run_id": self.run_id,
                "adim": self._adim,
                "zaman": _simdi(),
                "faz": faz,
                "gozlem": gozlem,
                "komut": komut,
                "ham_durum": ham_durum,
                "ham_durum_ozeti": ozet(ham_durum),
                "cevap": cevap,
                "cevap_ozeti": ozet(cevap),
                "hata": hata,
                "secenekler": secenekler,
                "sure_ms": sure_ms,
                "bot_ms": bot_ms,
                "api_ms": api_ms,
                "ek": ek or {},
            }
        )
        return self._adim

    def run_bitir(
        self,
        *,
        durum: str,
        son_ante: int | None = None,
        son_round: int | None = None,
        olum_nedeni: str | None = None,
        hata: str | None = None,
        lovely_log: str | Path | None = None,
        ek: dict[str, Any] | None = None,
    ) -> None:
        """`lovely_log`: bu oyun oturumunun Lovely log dosyası (yol, özet, hata satırı sayısı)."""
        self._kontrol_acik()
        if durum not in SONUC_DURUMLARI:
            raise LoggerHatasi(f"Bilinmeyen sonuç durumu: {durum}")
        self._yaz(
            {
                "tip": "run_sonu",
                "sema": SEMA_SURUMU,
                "run_id": self.run_id,
                "bitis": _simdi(),
                "durum": durum,
                "son_ante": son_ante,
                "son_round": son_round,
                "olum_nedeni": olum_nedeni,
                "hata": hata,
                "adim_sayisi": self._adim,
                "manipule": bool(self._hile_komutlari),
                "manipule_komutlari": sorted(set(self._hile_komutlari)),
                "sayaclar": dict(self._sayaclar),
                "lovely_log": _dosya_ozeti(lovely_log),
                "sure_sn": round(time.monotonic() - self._t0, 3),
                "ek": ek or {},
            }
        )
        self._bitti = True

    def _kontrol_acik(self) -> None:
        """Kayıt yazmadan önce run'ın başlamış ve bitmemiş olduğunu doğrular."""
        if not self._basladi:
            raise LoggerHatasi("Önce run_basla çağrılmalı")
        if self._bitti:
            raise LoggerHatasi("Run bitti, yeni kayıt yazılamaz")
