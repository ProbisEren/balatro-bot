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
        self.gelenler: list[dict] = []
        self.cevap = lambda istek: {"jsonrpc": "2.0", "id": istek["id"], "result": {}}
        sunucu = self

        class Isleyici(BaseHTTPRequestHandler):
            def do_POST(self):
                istek = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                sunucu.gelenler.append(istek)
                govde = sunucu.cevap(istek)
                ham = govde if isinstance(govde, bytes) else json.dumps(govde).encode()
                self.send_response(200)
                self.send_header("Content-Length", str(len(ham)))
                self.end_headers()
                self.wfile.write(ham)

            def log_message(self, *a):
                pass

        self.httpd = HTTPServer(("127.0.0.1", 0), Isleyici)
        self.adres = f"http://127.0.0.1:{self.httpd.server_port}"
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    def kapat(self):
        self.httpd.shutdown()
        self.httpd.server_close()


@pytest.fixture
def sahte():
    s = _SahteSunucu()
    yield s
    s.kapat()


def test_saglik_ve_istek_bicimi(sahte):
    sahte.cevap = lambda i: {"jsonrpc": "2.0", "id": i["id"], "result": {"status": "ok"}}
    assert BalatroIstemci(sahte.adres).saglik() is True
    assert sahte.gelenler[0]["method"] == "health"
    assert sahte.gelenler[0]["jsonrpc"] == "2.0"


def test_parametreler_gonderiliyor(sahte):
    BalatroIstemci(sahte.adres).oyna([0, 2, 4])
    assert sahte.gelenler[0]["method"] == "play"
    assert sahte.gelenler[0]["params"] == {"cards": [0, 2, 4]}


def test_baslat_seed_opsiyonel(sahte):
    c = BalatroIstemci(sahte.adres)
    c.baslat("RED", "WHITE")
    c.baslat("RED", "WHITE", seed="ABC")
    assert "seed" not in sahte.gelenler[0]["params"]
    assert sahte.gelenler[1]["params"]["seed"] == "ABC"


def test_rpc_hatasi_ozel_siniflara_cevrilir(sahte):
    sahte.cevap = lambda i: {
        "jsonrpc": "2.0",
        "id": i["id"],
        "error": {"code": -32002, "message": "Invalid state"},
    }
    with pytest.raises(GecersizDurum) as e:
        BalatroIstemci(sahte.adres).oyna([0])
    assert e.value.kod == -32002


def test_bilinmeyen_hata_kodu_genel_hata_olur(sahte):
    sahte.cevap = lambda i: {
        "jsonrpc": "2.0",
        "id": i["id"],
        "error": {"code": -1, "message": "x"},
    }
    with pytest.raises(RpcHatasi):
        BalatroIstemci(sahte.adres).durum()


def test_bozuk_json_protokol_hatasi(sahte):
    sahte.cevap = lambda i: b"bu json degil"
    with pytest.raises(ProtokolHatasi):
        BalatroIstemci(sahte.adres).durum()


def test_cevap_kimligi_uyusmazsa_hata(sahte):
    sahte.cevap = lambda i: {"jsonrpc": "2.0", "id": 999, "result": {}}
    with pytest.raises(ProtokolHatasi):
        BalatroIstemci(sahte.adres).durum()


def test_result_ve_error_yoksa_hata(sahte):
    sahte.cevap = lambda i: {"jsonrpc": "2.0", "id": i["id"]}
    with pytest.raises(ProtokolHatasi):
        BalatroIstemci(sahte.adres).durum()


def test_oyun_kapaliysa_baglanti_hatasi():
    # 9 numaralı port (discard) dinleyen yok: bağlantı reddedilir.
    with pytest.raises(BaglantiHatasi):
        BalatroIstemci("http://127.0.0.1:9", zaman_asimi=2).durum()


@pytest.mark.parametrize("yontem", ["set", "add", "load", "save", "screenshot", "rpc.discover"])
def test_hile_ve_hata_ayiklama_uc_noktalari_engelli(sahte, yontem):
    with pytest.raises(IzinVerilmedi):
        BalatroIstemci(sahte.adres)._cagri(yontem, {})
    assert sahte.gelenler == []  # sunucuya hiç gitmemeli


def test_izinli_aksiyonlar_hile_icermez():
    assert not ({"set", "add", "load", "save", "screenshot"} & IZINLI_AKSIYONLAR)
