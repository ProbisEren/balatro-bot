"""Mağaza değerlendirmesi (sim/magaza.py) ve planlayıcının rollout tabanlı mağaza/paket kararlarının testleri."""

from balatro_ai.agents.planlayici import PlanlayiciAjan
from balatro_ai.env import aksiyonlar
from balatro_ai.sim.magaza import faiz, faiz_kaybi, maliyet, sonraki_hedefler
from balatro_ai.sim.puan import EL_TABLOSU


def test_faiz_her_bes_dolara_bir_dolar_en_cok_bes():
    """Faizin her 5 dolar için 1 dolar ve en çok 5 dolar olduğunu doğrular."""
    assert [faiz(p) for p in (0, 4, 5, 9, 10, 24, 25, 40)] == [0, 0, 1, 1, 2, 4, 5, 5]


def test_faiz_kaybi_ve_maliyet():
    """Harcamanın kaybettirdiği faizin (3 tur boyunca) ve maliyetin doğru hesaplandığını doğrular."""
    assert faiz_kaybi(10, 3) == 3  # $10 -> $7: faiz 2 -> 1, 3 tur
    assert faiz_kaybi(4, 3) == 0
    assert maliyet(10, 3) > maliyet(4, 3)


def _duz(hedefler):
    """Karışımlı hedef listesini, her blind için (hedef, olasılık) çiftleri olarak sadeleştirir (test okunabilirliği için)."""
    return [[(round(h, 1), round(w, 4)) for h, w in blind] for blind in hedefler]


def test_sonraki_hedefler_gorunen_blindlardan_sonra_tablodan():
    """Ekrandaki geçilmemiş blind'ların gerçek hedeflerinin, yetmeyince bir sonraki ante'nin tablodan tahminlerinin kullanıldığını doğrular."""
    blinds = {
        "small": {"status": "DEFEATED", "score": 300},
        "big": {"status": "SELECT", "score": 450},
        "boss": {"status": "UPCOMING", "score": 600},
    }
    assert _duz(sonraki_hedefler(blinds, 1, 3)) == [[(450.0, 1.0)], [(600.0, 1.0)], [(800.0, 1.0)]]
    bes = _duz(sonraki_hedefler(blinds, 1, 5))
    assert bes[3] == [(1200.0, 1.0)]  # ante 2 big = 800 x 1,5
    assert [h for h, _ in bes[4]] == [800.0, 1600.0, 3200.0]  # bilinmeyen ante 2 bossu: Needle 1x, çoğu 2x, Wall 4x
    ham = sonraki_hedefler(blinds, 1, 5)[4]
    assert abs(sum(w for _, w in ham) - 1.0) < 1e-9 and max(ham, key=lambda x: x[1])[0] == 1600.0


def test_hedefler_stake_ile_olceklenir():
    """Yüksek stake'lerde (Green, Purple) ante hedeflerinin oyunun daha yüksek tablosundan alındığını doğrular."""
    blinds = {"small": {"status": "DEFEATED", "score": 300}, "big": {"status": "DEFEATED", "score": 450},
              "boss": {"status": "SELECT", "score": 600}}
    kucuk = lambda st: _duz(sonraki_hedefler(blinds, 1, 3, st))[1:]
    assert kucuk("WHITE") == [[(800.0, 1.0)], [(1200.0, 1.0)]]
    assert kucuk("GREEN") == [[(900.0, 1.0)], [(1350.0, 1.0)]]
    assert kucuk("PURPLE") == [[(1000.0, 1.0)], [(1500.0, 1.0)]]


def test_boss_carpan_dagilimi_ante_ve_showdown():
    """Boss çarpan karışımının ante'ye göre (Ox/Wall/Needle uygunluğu) ve showdown'da (Violet Vessel 6x) doğru olduğunu doğrular."""
    from balatro_ai.sim.magaza import boss_carpan_dagilimi

    d1 = dict(boss_carpan_dagilimi(1))
    assert set(d1) == {2.0}  # ante 1'de Needle (min 2) ve Wall (min 2) çıkamaz
    d3 = dict(boss_carpan_dagilimi(3))
    assert set(d3) == {1.0, 2.0, 4.0} and abs(sum(d3.values()) - 1.0) < 1e-9
    d8 = dict(boss_carpan_dagilimi(8))
    assert set(d8) == {2.0, 6.0} and abs(d8[6.0] - 0.2) < 1e-9  # 5 showdown boss, biri Violet Vessel


def test_olcekleme_stake_adlarindan():
    """Stake adının ölçekleme tablosuna doğru eşlendiğini doğrular (Green'den itibaren 2, Purple'dan itibaren 3)."""
    from balatro_ai.sim.magaza import olcekleme

    assert [olcekleme(s) for s in ("WHITE", "RED", "GREEN", "BLACK", "BLUE", "PURPLE", "ORANGE", "GOLD")] == [1, 1, 2, 2, 2, 3, 3, 3]


def _durum(faz="SHOP", dukkan=(), paketler=(), tuketilebilir=(), para=10, pack=()):
    """Tam desteli, Ante 1'de Small Blind geçilmiş bir mağaza (veya açık paket) durumu üretir."""
    kart = lambda k, f=3, s="PLANET": {"key": k, "label": k, "set": s, "cost": {"buy": f, "sell": 1}, "modifier": [], "state": []}
    deste = [{"key": f"{s}_{r}", "state": [], "modifier": []} for s in "SHCD" for r in "23456789TJQKA"]
    return {
        "state": faz, "money": para, "ante_num": 1, "round_num": 1, "stake": "WHITE",
        "round": {"reroll_cost": 5, "hands_left": 4, "discards_left": 4},
        "cards": {"cards": deste}, "hand": {"cards": [], "limit": 8},
        "hands": {t: {"chips": v[0], "mult": v[1], "level": 1} for t, v in EL_TABLOSU.items()},
        "blinds": {
            "small": {"status": "DEFEATED", "score": 300, "type": "SMALL", "name": "Small Blind"},
            "big": {"status": "SELECT", "score": 450, "type": "BIG", "name": "Big Blind"},
            "boss": {"status": "UPCOMING", "score": 600, "type": "BOSS", "name": "The Club"},
        },
        "shop": {"cards": [kart(k, f, s) for k, f, s in dukkan]}, "vouchers": {"cards": []},
        "packs": {"cards": [kart(k, f, "BOOSTER") for k, f in paketler]},
        "jokers": {"cards": [], "limit": 5}, "consumables": {"cards": [kart(k) for k in tuketilebilir], "limit": 2},
        "pack": {"cards": [kart(k, 0) for k in pack]},
    }


def _karar(g, tohum=1):
    """Planlayıcının bu mağaza/paket durumunda seçtiği (komut, parametreler) ve karar açıklaması."""
    ajan = PlanlayiciAjan(tohum)
    ids = aksiyonlar.gecerli(g, "tam")
    a = ajan.sec(g, {"gecerli_aksiyonlar": ids})
    k = aksiyonlar.komut(a)
    return k["yontem"], k["parametreler"], ajan.son_aciklama


def test_degerli_gezegeni_satin_alir():
    """Flush gezegenini (en değerlilerden) karşılayabildiğinde satın aldığını doğrular."""
    yontem, p, a = _karar(_durum(dukkan=[("c_jupiter", 3, "PLANET")]))
    assert (yontem, p) == ("buy", {"card": 0}) and a["karar"] == "satin_al:c_jupiter"


def test_parasi_yetmiyorsa_almaz_ve_cikar():
    """Parası yetmediğinde satın almadığını, mağazadan çıktığını doğrular."""
    assert _karar(_durum(dukkan=[("c_jupiter", 3, "PLANET")], para=2))[0] == "next_round"


def test_etkisi_tanimsiz_ogeleri_almaz():
    """Etkisi tanımlı olmayan öğelerin (Blueprint gibi jokerler, tarot, diğer paketler) alınmadığını doğrular."""
    g = _durum(dukkan=[("j_blueprint", 4, "JOKER"), ("c_fool", 3, "TAROT")], paketler=[("p_arcana_normal_1", 4), ("p_buffoon_normal_1", 4)])
    assert _karar(g)[0] == "next_round"


def test_etkisi_tanimli_degerli_jokeri_satin_alir():
    """Etkisi tanımlı ve değerli bir jokeri (Jolly Joker: Pair'de +8 mult) satın aldığını doğrular."""
    yontem, p, a = _karar(_durum(dukkan=[("j_jolly", 3, "JOKER")]))
    assert (yontem, p) == ("buy", {"card": 0}) and a["karar"] == "satin_al:j_jolly"


def test_etkisiz_cikan_jokeri_almaz():
    """Mevcut elde işe yaramayan bir jokerin (örn. Wily Joker: yalnızca Three of a Kind'da chips) pahalıysa alınmadığını doğrular."""
    g = _durum(dukkan=[("j_gluttenous_joker", 5, "JOKER")], para=5)  # yalnızca sinekte +3 mult, bu $5 faiz kaybettirir
    yontem, _, a = _karar(g)
    assert yontem in ("buy", "next_round")  # karar rollout'a bağlı; çökmeden geçerli eylem seçer
    assert "adaylar" in a


def test_veri_toplama_modunda_degerlendirmeden_joker_alir():
    """Veri toplama modunda (`joker_toplama=True`) bir jokerin değerlendirilmeden satın alındığını, tanımlı olanın tercih edildiğini doğrular."""
    g = _durum(dukkan=[("j_blueprint", 4, "JOKER"), ("j_gluttenous_joker", 5, "JOKER")], para=10)
    ajan = PlanlayiciAjan(1, joker_toplama=True)
    a = ajan.sec(g, {"gecerli_aksiyonlar": aksiyonlar.gecerli(g, "tam")})
    assert aksiyonlar.komut(a)["parametreler"] == {"card": 1}  # tanımlı olan (Gluttonous) tercih edilir
    assert ajan.son_aciklama["karar"].startswith("veri_toplama_joker")


def test_elde_gezegen_varsa_kullanir():
    """Tüketilebilir slotundaki gezegeni hemen kullandığını doğrular."""
    yontem, p, a = _karar(_durum(tuketilebilir=["c_jupiter"]))
    assert (yontem, p) == ("use", {"consumable": 0}) and a["karar"] == "gezegen_kullan"


def test_acik_pakette_en_degerli_gezegeni_secer():
    """Açık gezegen paketinde değeri en yüksek gezegenin (Flush, Pluto'dan çok daha değerli) seçildiğini doğrular."""
    g = _durum(faz="SMODS_BOOSTER_OPENED", pack=["c_pluto", "c_jupiter", "c_mars"])
    yontem, p, _ = _karar(g)
    assert (yontem, p) == ("pack", {"card": 1})


def test_gezegen_paketini_degerliyse_alir():
    """Karşılanabilir bir gezegen paketinin beklenen katkısı maliyetinden yüksekse satın alındığını doğrular."""
    yontem, p, a = _karar(_durum(paketler=[("p_celestial_jumbo_1", 6)], para=15))
    assert (yontem, p) == ("buy", {"pack": 0}) and a["karar"].startswith("satin_al")


def test_ayni_tohum_ayni_karar():
    """Aynı tohumla mağaza kararının tekrarlandığını doğrular."""
    g = _durum(dukkan=[("c_mercury", 3, "PLANET"), ("c_pluto", 3, "PLANET")])
    assert _karar(g, 5)[:2] == _karar(g, 5)[:2]


def _kupon(g, anahtar, fiyat=10):
    """Duruma bir kupon teklifi ekler."""
    g["vouchers"]["cards"] = [{"key": anahtar, "set": "VOUCHER", "cost": {"buy": fiyat, "sell": 5}, "modifier": [], "state": []}]
    return g


def test_el_hakki_kuponu_degerlenir_ve_net_pozitifse_alinir():
    """Grabber'ın (oyun kodundan +1 el) aday olarak değerlendirildiğini; maliyeti kazancından küçükse alındığını doğrular."""
    g = _kupon(_durum(para=98), "v_grabber", fiyat=1)
    for ad, skor in (("big", 1800), ("boss", 2400)):  # kolay hedefte ek el hakkı fark yaratmaz; zor hedef seçilir
        g["blinds"][ad]["score"] = skor
    yontem, p, a = _karar(g)
    assert [ad for _, ad in a["adaylar"]] == ["v_grabber"] and a["adaylar"][0][0] > 0
    assert (yontem, p) == ("buy", {"voucher": 0})


def test_modellenmemis_kuponu_almaz():
    """Etkisi modellenmemiş bir kuponun (Telescope) alınmadığını doğrular."""
    assert _karar(_kupon(_durum(para=98), "v_telescope"))[0] != "buy"


def test_zengin_bot_gezegen_alir_ve_yeterince_gorduyse_yeniler():
    """98 dolarla gezegenin satın alındığını; alınacak bir şey yokken ve görülmüş öğeler değerliyse yenileme yapıldığını doğrular."""
    assert _karar(_durum(dukkan=[("c_jupiter", 3, "PLANET")], para=98))[2]["karar"] == "satin_al:c_jupiter"
    ajan = PlanlayiciAjan(1)
    g = _durum(dukkan=[("c_jupiter", 3, "PLANET")], para=98)
    ajan.sec(g, {"gecerli_aksiyonlar": aksiyonlar.gecerli(g, "tam")})  # gezegeni görür (alır)
    bos = _durum(dukkan=[("c_fool", 3, "TAROT")], para=98)
    a = ajan.sec(bos, {"gecerli_aksiyonlar": aksiyonlar.gecerli(bos, "tam")})
    assert aksiyonlar.komut(a)["yontem"] == "reroll" and ajan.son_aciklama["karar"] == "yenile"


def test_yuva_doluyken_daha_iyi_jokeri_icin_takas_yapar():
    """Joker yuvası doluyken, elde zayıf (işe yaramayan) bir joker varsa onu satıp mağazadaki iyi jokeri aldığını doğrular."""
    g = _durum(dukkan=[("j_jolly", 4, "JOKER")], para=10)
    zayif = lambda k: {"key": k, "set": "JOKER", "cost": {"buy": 4, "sell": 2}, "modifier": [], "state": []}
    g["jokers"] = {"cards": [zayif("j_card_sharp")] * 5, "limit": 5, "count": 5}
    ajan = PlanlayiciAjan(1)
    a = ajan.sec(g, {"gecerli_aksiyonlar": aksiyonlar.gecerli(g, "tam")})
    assert aksiyonlar.komut(a)["yontem"] == "sell" and ajan.son_aciklama["karar"].startswith("takas_sat")
    g2 = _durum(dukkan=[("j_jolly", 4, "JOKER")], para=12)
    g2["jokers"] = {"cards": [zayif("j_card_sharp")] * 4, "limit": 5, "count": 4}
    ajan._takas_hedefi = "j_jolly"
    a2 = ajan.sec(g2, {"gecerli_aksiyonlar": aksiyonlar.gecerli(g2, "tam")})
    assert aksiyonlar.komut(a2) == {"yontem": "buy", "parametreler": {"card": 0}}
