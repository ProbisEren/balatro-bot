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


class LoggerHatasi(Exception):
    pass


def _simdi() -> str:
    return datetime.now(UTC).isoformat()


def _json_satiri(kayit: dict[str, Any]) -> str:
    return json.dumps(kayit, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def yapilandirma_ozeti(yapilandirma: dict[str, Any]) -> str:
    """Yapılandırmanın sha256 özeti (anahtar sırasından bağımsız)."""
    return hashlib.sha256(_json_satiri(yapilandirma).encode("utf-8")).hexdigest()


def _git(*args: str) -> str | None:
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
        self.kok = Path(kok)
        self.run_id = run_id or f"{datetime.now(UTC):%Y%m%dT%H%M%SZ}-{uuid.uuid4().hex[:8]}"
        self.yol = self.kok / f"{self.run_id}.jsonl"
        self._dosya = None
        self._adim = 0
        self._basladi = False
        self._bitti = False
        self._t0 = time.monotonic()

    # --- yaşam döngüsü ---
    def __enter__(self) -> Self:
        self.kok.mkdir(parents=True, exist_ok=True)
        if self.yol.exists():
            raise LoggerHatasi(f"Run kaydı zaten var, değiştirilemez: {self.yol}")
        self._dosya = open(self.yol, "x", encoding="utf-8")  # "x": varsa hata verir
        return self

    def __exit__(self, tur, deger, iz) -> None:
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
                "cevap": cevap,
                "hata": hata,
                "secenekler": secenekler,
                "sure_ms": sure_ms,
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
        ek: dict[str, Any] | None = None,
    ) -> None:
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
                "sure_sn": round(time.monotonic() - self._t0, 3),
                "ek": ek or {},
            }
        )
        self._bitti = True

    def _kontrol_acik(self) -> None:
        if not self._basladi:
            raise LoggerHatasi("Önce run_basla çağrılmalı")
        if self._bitti:
            raise LoggerHatasi("Run bitti, yeni kayıt yazılamaz")
