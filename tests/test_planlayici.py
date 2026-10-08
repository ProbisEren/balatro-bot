"""Tur simülatörü (sim/tur.py) ve rollout ile karar veren planlayıcı ajanın (agents/planlayici.py) testleri."""

import random

from balatro_ai.agents.planlayici import PlanlayiciAjan
from balatro_ai.env import aksiyonlar
from balatro_ai.sim.kartlar import anahtardan
from balatro_ai.sim.puan import EL_TABLOSU
from balatro_ai.sim.tur import Tur, alt_kume_skoru, at, deger, en_iyi, oyna, rollout

D = {t: (float(v[0]), float(v[1])) for t, v in EL_TABLOSU.items()}


def kartlar(*anahtarlar):
    """Oyun anahtarlarından düz kart listesi."""
    return [anahtardan(a) for a in anahtarlar]


def tur(el, deste, *, el_hakki=4, discard=3, chips=0.0, hedef=300.0, **kw):
    """Verilen el ve destede (üst kart = son eleman) bir tur kurar."""
    return Tur(kartlar(*el), kartlar(*deste), el_hakki, discard, chips, hedef, D, **kw)


# --- simülatör ---------------------------------------------------------------------------------
def test_oyna_skor_ekler_hak_harcar_ve_desteden_tamamlar():
    """Oynamanın skoru eklediğini, bir el hakkı harcadığını ve eli desteden (üstten) 8'e tamamladığını doğrular."""
    el = ["S_A", "D_A", "H_9", "C_4", "S_2", "D_7", "H_K", "C_3"]
    t = tur(el, ["H_5", "H_6", "H_7"])
    skor, idx = en_iyi(t)
    assert skor == 64 and idx == (0, 1)  # As çifti: (10+22)*2
    oyna(t, idx, skor)
    assert t.chips == 64 and t.kalan_el == 3 and len(t.el) == 8
    assert [k.rutbe + k.renk for k in t.el[-2:]] == ["7H", "6H"]  # üstten çekildi
    assert t.deste[-1].rutbe == "5"


def test_at_discard_harcar_el_hakkina_dokunmaz_ve_deste_tukenince_el_kucuk_kalir():
    """Discard'ın yalnızca discard hakkını harcadığını ve deste tükenince elin küçük kaldığını doğrular."""
    t = tur(["S_A", "D_A", "H_9", "C_4", "S_2", "D_7", "H_K", "C_3"], ["H_5"])
    at(t, (0, 1, 2))
    assert t.kalan_discard == 2 and t.kalan_el == 4 and len(t.el) == 6


def test_kazanma_ve_bitis():
    """Hedefe ulaşınca turun kazanıldığını, el hakkı bitince kaybedildiğini doğrular."""
    t = tur(["S_A", "D_A"], [], chips=290.0)
    assert not t.bitti()
    oyna(t, (0, 1), 64)
    assert t.kazandi() and t.bitti()
    k = tur(["S_2"], [], el_hakki=1, hedef=1000.0)
    oyna(k, (0,), 7)
    assert k.bitti() and not k.kazandi()


def test_deger_kazanmayi_kalan_elle_oduller_kaybi_ilerlemeyle_siralar():
    """Değerin kazanınca 1'den büyük (kalan ele göre), kaybedince ilerlemeyle artan küçük bir sayı olduğunu doğrular."""
    az = tur(["S_2"], [], el_hakki=1, chips=300.0)
    cok = tur(["S_2"], [], el_hakki=3, chips=300.0)
    assert deger(cok) > deger(az) > 1.0
    assert 0 < deger(tur(["S_2"], [], chips=10.0)) < deger(tur(["S_2"], [], chips=200.0)) < 0.25


def test_psychic_bes_kartlik_oynanis_ister():
    """The Psychic'te en iyi oynanışın 5 karta tamamlandığını (skor aynı), 5'ten az kartla 0 olduğunu doğrular."""
    t = tur(["S_A", "D_A", "H_9", "C_4", "S_2", "D_7", "H_K", "C_3"], [], tam_bes=True)
    skor, idx = en_iyi(t)
    assert skor == 64 and len(idx) == 5 and {0, 1} <= set(idx)
    assert alt_kume_skoru(t, (0, 1)) == 0 and alt_kume_skoru(t, idx) == 64


def test_rollout_kesin_kazanilacak_ve_imkansiz_turlarda():
    """Rollout'un kolay bir turu kazandığını, imkansız hedefte kaybedip küçük ilerleme payı verdiğini doğrular."""
    standart = [f"{s}_{r}" for s in "SHCD" for r in "23456789TJQKA"]
    rng = random.Random(1)
    d = standart[:]
    rng.shuffle(d)
    kolay = tur(d[:8], d[8:], hedef=20.0)
    assert rollout(kolay, rng) > 1.0
    d2 = standart[:]
    rng.shuffle(d2)
    zor = tur(d2[:8], d2[8:], hedef=10**9)
    assert rollout(zor, rng) < 0.25 and zor.kalan_el == 0


# --- planlayıcı --------------------------------------------------------------------------------
def _kart(key):
    """Ajanın okuduğu biçimde kart sözlüğü."""
    return {"key": key, "state": [], "modifier": []}


def gozlem(el, deste=(), *, hedef=300, skor=0, hands_left=4, discards_left=3, boss=None, round_num=1):
    """Ajanın göreceği gözlem sözlüğü."""
    return {
        "state": "SELECTING_HAND", "ante_num": 1, "round_num": round_num,
        "hand": {"cards": [_kart(k) if k else {"state": {"hidden": True}} for k in el], "limit": 8},
        "cards": {"cards": sorted((_kart(k) for k in deste), key=lambda c: c["key"])},
        "hands": {t: {"chips": v[0], "mult": v[1], "level": 1} for t, v in EL_TABLOSU.items()},
        "blinds": {"s": {"status": "CURRENT", "type": "BOSS" if boss else "SMALL", "name": boss or "Small Blind", "score": hedef}},
        "round": {"chips": skor, "hands_left": hands_left, "discards_left": discards_left},
        "jokers": {"cards": []},
    }


def karar(g, **ayar):
    """Planlayıcının bu gözlemde seçtiği (komut adı, kart indeksleri) ve açıklama."""
    ajan = PlanlayiciAjan(1, **ayar)
    ids = aksiyonlar.gecerli({**g, "money": 4}, "dar")
    a = ajan.sec(g, {"gecerli_aksiyonlar": ids})
    assert a in ids
    k = aksiyonlar.komut(a)
    return k["yontem"], tuple(k["parametreler"]["cards"]), ajan.son_aciklama


def test_blind_biten_oynanisi_dogrudan_oynar():
    """Her dünyada blind'ı bitiren bir oynanış varsa (flush 284 >= 250) rollout'suz onu oynadığını doğrular."""
    el = ["H_2", "H_5", "H_9", "H_J", "H_K", "D_3", "C_4", "S_7"]
    yontem, kartlar_, _ = karar(gozlem(el, ["S_A"], hedef=250))
    assert (yontem, kartlar_) == ("play", (0, 1, 2, 3, 4))


def test_flush_cizimini_koruyup_gerisini_atar():
    """Dört maça ve destede çok maça varken planlayıcının maçaları tutup diğerlerini attığını doğrular."""
    el = ["S_A", "S_K", "S_Q", "S_J", "H_2", "D_3", "C_4", "D_5"]
    deste = [f"S_{r}" for r in "3456789T"] + ["H_6", "D_7", "C_8", "H_9"]
    yontem, kartlar_, a = karar(gozlem(el, deste, hedef=2000), dunya=24)
    assert yontem == "discard" and {0, 1, 2, 3}.isdisjoint(kartlar_)
    assert a["rollout_sayisi"] > 0


def test_deste_tek_renkse_discard_kesinlikle_flush_yapar():
    """Deste yalnızca maça iken kötü bir elden discard ile flush kurulduğunu simülasyonun bildiğini doğrular (p_kazanma yüksek)."""
    el = ["S_A", "S_K", "H_2", "D_3", "C_4", "D_5", "C_6", "H_8"]
    deste = [f"S_{r}" for r in "23456789TJQ"]
    yontem, _, a = karar(gozlem(el, deste, hedef=250, discards_left=1, hands_left=1), dunya=16)
    assert yontem == "discard" and a.get("p_kazanma", a.get("son_el_arama", {}).get("discard_ile_kazanma", 0)) > 0.9


def test_yuzu_kapali_kartlarla_cokmez_gecerli_aksiyon_secer_ve_tekrarlanir():
    """Elde yüzü kapalı kartlar varken ajanın çökmediğini, geçerli aksiyon seçtiğini ve aynı tohumla aynı kararı verdiğini doğrular."""
    el = ["S_A", None, "H_9", "C_4", None, "D_7", "H_K", "C_3"]
    g = gozlem(el, ["S_5", "H_5", "D_5"] + [f"C_{r}" for r in "56789"], hedef=400)
    s1 = karar(g, dunya=16)
    s2 = karar(g, dunya=16)
    assert s1[:2] == s2[:2] and s1[2]["gizli_kart"] == 2


def test_psychic_bossunda_bes_kart_oynar():
    """The Psychic boss'unda planlayıcının 5 kart oynadığını (azı sıfır puan) doğrular."""
    el = ["S_A", "D_A", "H_9", "C_4", "S_2", "D_7", "H_K", "C_3"]
    yontem, kartlar_, _ = karar(gozlem(el, [], hedef=10_000, discards_left=0, boss="The Psychic"), dunya=8)
    assert yontem == "play" and len(kartlar_) == 5


def test_el_disindaki_asamalar_sabit_kurala_duser():
    """El seçimi dışındaki aşamalarda (blind seçimi) sabit kuralın (blind'ı seç) uygulandığını doğrular."""
    g = {"state": "BLIND_SELECT", "money": 4, "blinds": {"a": {"status": "SELECT", "type": "SMALL"}}, "jokers": {"cards": []}}
    ajan = PlanlayiciAjan(1)
    ids = aksiyonlar.gecerli(g, "tam")
    assert aksiyonlar.komut(ajan.sec(g, {"gecerli_aksiyonlar": ids}))["yontem"] == "select"


def test_son_elde_kesin_kayipken_discard_eder():
    """Son el ve discard hakkı varken eldeki en iyi oynanış blind'ı bitirmiyorsa ve discard'la şans varsa discard ettiğini doğrular (kullanıcı hatası: oynayıp elendi)."""
    el = ["S_A", "S_K", "S_Q", "H_2", "D_3", "C_4", "D_5", "C_6"]  # en iyi oynanış yüksek kart: 16 puan
    deste = [f"S_{r}" for r in "3456789TJ"]  # destede 9 maça: discard ile flush/straight flush mümkün
    yontem, kartlar_, a = karar(gozlem(el, deste, hedef=250, hands_left=1, discards_left=1))
    assert yontem == "discard" and a["karar"] == "son_el_discard" and a["son_el_arama"]["discard_ile_kazanma"] > 0
    assert {0, 1, 2}.isdisjoint(kartlar_)  # maçaları tutar


def test_son_elde_kazanabiliyorsa_oynar_hic_sansi_yoksa_da_oynar():
    """Son elde elindeki oynanış blind'ı bitiriyorsa oynadığını; hiçbir şans yoksa da çökmeden geçerli bir eylem seçtiğini doğrular."""
    flush = ["H_2", "H_5", "H_9", "H_J", "H_K", "D_3", "C_4", "S_7"]  # flush 284
    yontem, _, _ = karar(gozlem(flush, ["S_A"], hedef=250, hands_left=1, discards_left=2))
    assert yontem == "play"
    zayif = ["S_2", "H_3", "D_4", "C_6", "S_8", "H_9", "D_J", "C_K"]
    yontem, kartlar_, _ = karar(gozlem(zayif, ["S_5"], hedef=10_000, hands_left=1, discards_left=1))
    assert yontem in ("play", "discard") and kartlar_  # hiçbir şansı olmayan durumda çökmez, geçerli eylem seçer


def test_kayip_degeri_dis_bukey_yuksek_varyansi_oduller():
    """Kaybedilen turlarda ilerleme değerinin dışbükey olduğunu (yarıya yaklaşmak, yarısından çok daha az değerli) doğrular."""
    yarim = tur(["S_2"], [], chips=150.0, hedef=300.0, el_hakki=0)
    yakin = tur(["S_2"], [], chips=290.0, hedef=300.0, el_hakki=0)
    assert deger(yakin) > 6 * deger(yarim)


def test_rollout_politikasi_straight_cizimi_de_onerir():
    """Rollout politikasının discard önerilerinde, 5 ardışık rütbenin 3+'ı varken straight çizimini (diğerlerini atmayı) da bulunduğunu doğrular."""
    from balatro_ai.sim.tur import discard_adaylari

    t = tur(["S_5", "H_6", "D_7", "C_8", "S_K", "H_2", "D_Q", "C_A"], ["H_9"] * 3)
    oneriler = discard_adaylari(t, (0,))
    # 5-6-7-8 straight çizimi: K, 2, Q, A atılır (5,6,7,8 tutulur)
    assert (4, 5, 6, 7) in oneriler
