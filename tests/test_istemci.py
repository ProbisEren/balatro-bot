"""BalatroBot istemcisinin sahte bir HTTP sunucusuna karşı testleri."""

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from balatro_ai.env.client import (
    IZINLI_AKSIYONLAR,
    BaglantiHatasi,
    BalatroIstemci,
    GecersizDurum,
    IzinVerilmedi,
    ProtokolHatasi,
    RpcHatasi,
)


class _SahteSunucu:
    """Sunucunun vereceği cevabı test başına ayarlanabilen küçük HTTP sunucusu."""

    def __init__(self):
        """Rastgele bir boş portta, cevabı test başına ayarlanabilen küçük bir HTTP sunucusu başlatır.
        """
        self.gelenler: list[dict] = []
        self.cevap = lambda istek: {"jsonrpc": "2.0", "id": istek["id"], "result": {}}
        sunucu = self

        class Isleyici(BaseHTTPRequestHandler):
            """Gelen JSON-RPC isteklerini kaydedip ayarlanan cevabı döndüren HTTP işleyicisi."""
            def do_POST(self):
                """POST isteğini okuyup kaydeder ve ayarlı cevabı gönderir."""
                istek = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                sunucu.gelenler.append(istek)
                govde = sunucu.cevap(istek)
                ham = govde if isinstance(govde, bytes) else json.dumps(govde).encode()
                self.send_response(200)
                self.send_header("Content-Length", str(len(ham)))
                self.end_headers()
                self.wfile.write(ham)

            def log_message(self, *a):
                """Sunucu günlüğünü sessizleştirir (test çıktısını kirletmesin)."""

        self.httpd = HTTPServer(("127.0.0.1", 0), Isleyici)
        self.adres = f"http://127.0.0.1:{self.httpd.server_port}"
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    def kapat(self):
        """Sunucuyu durdurup soketini kapatır."""
        self.httpd.shutdown()
        self.httpd.server_close()


@pytest.fixture
def sahte():
    """Her teste temiz bir sahte sunucu verir ve test bitince kapatır."""
    s = _SahteSunucu()
    yield s
    s.kapat()


def test_saglik_ve_istek_bicimi(sahte):
    """Sağlık kontrolünün çalıştığını ve isteğin JSON-RPC 2.0 biçiminde gittiğini doğrular."""
    sahte.cevap = lambda i: {"jsonrpc": "2.0", "id": i["id"], "result": {"status": "ok"}}
    assert BalatroIstemci(sahte.adres).saglik() is True
    assert sahte.gelenler[0]["method"] == "health"
    assert sahte.gelenler[0]["jsonrpc"] == "2.0"


def test_parametreler_gonderiliyor(sahte):
    """Komut parametrelerinin istekte doğru iletildiğini doğrular."""
    BalatroIstemci(sahte.adres).oyna([0, 2, 4])
    assert sahte.gelenler[0]["method"] == "play"
    assert sahte.gelenler[0]["params"] == {"cards": [0, 2, 4]}


def test_baslat_seed_opsiyonel(sahte):
    """`start` komutunda seed'in yalnızca verildiğinde gönderildiğini doğrular."""
    c = BalatroIstemci(sahte.adres)
    c.baslat("RED", "WHITE")
    c.baslat("RED", "WHITE", seed="ABC")
    assert "seed" not in sahte.gelenler[0]["params"]
    assert sahte.gelenler[1]["params"]["seed"] == "ABC"


def test_rpc_hatasi_ozel_siniflara_cevrilir(sahte):
    """Oyunun hata kodlarının ilgili hata sınıflarına çevrildiğini doğrular."""
    sahte.cevap = lambda i: {
        "jsonrpc": "2.0",
        "id": i["id"],
        "error": {"code": -32002, "message": "Invalid state"},
    }
    with pytest.raises(GecersizDurum) as e:
        BalatroIstemci(sahte.adres).oyna([0])
    assert e.value.kod == -32002


def test_bilinmeyen_hata_kodu_genel_hata_olur(sahte):
    """Bilinmeyen hata kodunun genel RPC hatası olarak yükseltildiğini doğrular."""
    sahte.cevap = lambda i: {
        "jsonrpc": "2.0",
        "id": i["id"],
        "error": {"code": -1, "message": "x"},
    }
    with pytest.raises(RpcHatasi):
        BalatroIstemci(sahte.adres).durum()


def test_bozuk_json_protokol_hatasi(sahte):
    """Bozuk JSON cevabının protokol hatası verdiğini doğrular."""
    sahte.cevap = lambda i: b"bu json degil"
    with pytest.raises(ProtokolHatasi):
        BalatroIstemci(sahte.adres).durum()


def test_cevap_kimligi_uyusmazsa_hata(sahte):
    """Cevaptaki kimlik istekle uyuşmazsa protokol hatası verildiğini doğrular."""
    sahte.cevap = lambda i: {"jsonrpc": "2.0", "id": 999, "result": {}}
    with pytest.raises(ProtokolHatasi):
        BalatroIstemci(sahte.adres).durum()


def test_result_ve_error_yoksa_hata(sahte):
    """Cevapta ne sonuç ne hata varsa protokol hatası verildiğini doğrular."""
    sahte.cevap = lambda i: {"jsonrpc": "2.0", "id": i["id"]}
    with pytest.raises(ProtokolHatasi):
        BalatroIstemci(sahte.adres).durum()


def test_oyun_kapaliysa_baglanti_hatasi():
    # 9 numaralı port (discard) dinleyen yok: bağlantı reddedilir.
    """Oyun kapalıyken bağlantı hatası verildiğini doğrular."""
    with pytest.raises(BaglantiHatasi):
        BalatroIstemci("http://127.0.0.1:9", zaman_asimi=2).durum()


@pytest.mark.parametrize("yontem", ["set", "add", "load", "save", "screenshot", "rpc.discover"])
def test_hile_ve_hata_ayiklama_uc_noktalari_engelli(sahte, yontem):
    """set, add, load, save gibi hile uç noktalarının sunucuya hiç gitmeden reddedildiğini doğrular.
    """
    with pytest.raises(IzinVerilmedi):
        BalatroIstemci(sahte.adres)._cagri(yontem, {})
    assert sahte.gelenler == []  # sunucuya hiç gitmemeli


def test_izinli_aksiyonlar_hile_icermez():
    """İzinli aksiyon listesinde hile komutlarının bulunmadığını doğrular."""
    assert not ({"set", "add", "load", "save", "screenshot"} & IZINLI_AKSIYONLAR)


def test_paket_secimi_parametreleri(sahte):
    """Paketten kart seçme ve atlama komutlarının doğru parametrelerle gittiğini doğrular."""
    c = BalatroIstemci(sahte.adres)
    c.paket_sec(kart=2, hedefler=[0, 1])
    c.paket_sec(atla=True)
    assert sahte.gelenler[0]["method"] == "pack"
    assert sahte.gelenler[0]["params"] == {"card": 2, "targets": [0, 1]}
    assert sahte.gelenler[1]["params"] == {"skip": True}
