"""JSONL run kayıtlarını DuckDB ile sorgulama.

`baglan(kok)` iki görünüm (view) açar; kayıtlar dosyada kalır, DuckDB yalnızca okur:
  runs       run başına bir satır (run_basi + run_sonu birleşik; sonu olmayan run `durum` NULL)
  decisions  karar başına bir satır
Gömülü alanlar (gozlem, komut, ham_durum, ajan, ek, ...) JSON türünde kalır:
  SELECT json_extract_string(ham_durum, '$.seed') FROM decisions
"""

from __future__ import annotations

from pathlib import Path

import duckdb


def baglan(kok: str | Path) -> duckdb.DuckDBPyConnection:
    kok = Path(kok)
    desen = str(kok / "*.jsonl").replace("'", "''")
    con = duckdb.connect(":memory:")
    con.execute(
        f"CREATE VIEW ham AS SELECT json, filename FROM read_ndjson_objects('{desen}', filename=true)"
    )
    j = lambda yol: f"json_extract_string(json, '{yol}')"
    con.execute(
        f"""
        CREATE VIEW decisions AS
        SELECT
          {j('$.run_id')} AS run_id,
          CAST({j('$.adim')} AS INTEGER) AS adim,
          CAST({j('$.zaman')} AS TIMESTAMPTZ) AS zaman,
          {j('$.faz')} AS faz,
          json_extract(json, '$.gozlem') AS gozlem,
          json_extract(json, '$.komut') AS komut,
          json_extract(json, '$.ham_durum') AS ham_durum,
          json_extract(json, '$.cevap') AS cevap,
          json_extract(json, '$.hata') AS hata,
          json_extract(json, '$.secenekler') AS secenekler,
          CAST({j('$.sure_ms')} AS DOUBLE) AS sure_ms,
          json_extract(json, '$.ek') AS ek,
          {j('$.sema')} AS sema
        FROM ham WHERE {j('$.tip')} = 'karar'
        """
    )
    con.execute(
        f"""
        CREATE VIEW run_basi AS
        WITH basi AS (SELECT json FROM ham WHERE {j('$.tip')} = 'run_basi'),
             sonu AS (SELECT json FROM ham WHERE {j('$.tip')} = 'run_sonu')
        SELECT
          {j('$.run_id')} AS run_id,
          CAST({j('$.baslangic')} AS TIMESTAMPTZ) AS baslangic,
          {j('$.seed')} AS seed,
          {j('$.deste')} AS deste,
          {j('$.stake')} AS stake,
          {j('$.yaklasim')} AS yaklasim,
          {j('$.rol')} AS rol,
          {j('$.kaynak')} AS kaynak,
          {j('$.gorev_id')} AS gorev_id,
          json_extract(json, '$.ajan') AS ajan,
          json_extract(json, '$.surumler') AS surumler,
          json_extract(json, '$.oyun') AS oyun,
          json_extract(json, '$.yapilandirma') AS yapilandirma,
          {j('$.yapilandirma_ozeti')} AS yapilandirma_ozeti,
          {j('$.sema')} AS sema
        FROM basi
        """
    )
    # Sonuç bilgisini runs'a ekle.
    con.execute(
        f"""
        CREATE VIEW runs AS
        SELECT r.*,
          s.durum, s.son_ante, s.son_round, s.olum_nedeni, s.hata, s.adim_sayisi, s.sure_sn
        FROM run_basi r
        LEFT JOIN (
          SELECT {j('$.run_id')} AS run_id,
                 {j('$.durum')} AS durum,
                 CAST({j('$.son_ante')} AS INTEGER) AS son_ante,
                 CAST({j('$.son_round')} AS INTEGER) AS son_round,
                 {j('$.olum_nedeni')} AS olum_nedeni,
                 {j('$.hata')} AS hata,
                 CAST({j('$.adim_sayisi')} AS INTEGER) AS adim_sayisi,
                 CAST({j('$.sure_sn')} AS DOUBLE) AS sure_sn
          FROM ham WHERE {j('$.tip')} = 'run_sonu'
        ) s USING (run_id)
        """
    )
    _turetilmis_gorunumler(con)
    return con


def _turetilmis_gorunumler(con: duckdb.DuckDBPyConnection) -> None:
    """Ham durumdan türetilen görünümler: ne gördü, ne seçti, neyi reddetti."""
    # Mağazada her adımda görülen her teklif ve alınıp alınmadığı.
    parcalar = []
    for tur, alan, param in (("kart", "shop", "card"), ("kupon", "vouchers", "voucher"), ("paket", "packs", "pack")):
        parcalar.append(
            f"""
            SELECT d.run_id, d.adim, '{tur}' AS tur, i AS indeks,
              json_extract_string(d.ham_durum, '$.{alan}.cards[' || i || '].key') AS anahtar,
              json_extract_string(d.ham_durum, '$.{alan}.cards[' || i || '].label') AS ad,
              CAST(json_extract_string(d.ham_durum, '$.{alan}.cards[' || i || '].cost.buy') AS INTEGER) AS fiyat,
              CAST(json_extract_string(d.ham_durum, '$.money') AS INTEGER) AS para,
              (json_extract_string(d.komut, '$.yontem') = 'buy'
                AND CAST(json_extract_string(d.komut, '$.parametreler.{param}') AS INTEGER) = i) AS alindi
            FROM decisions d,
                 range(CAST(COALESCE(json_array_length(json_extract(d.ham_durum, '$.{alan}.cards')), 0) AS BIGINT)) AS t(i)
            """
        )
    con.execute("CREATE VIEW shop_teklifleri AS " + " UNION ALL ".join(parcalar))
    # Açılan pakette görülen kartlar ve seçilip seçilmediği.
    con.execute(
        """
        CREATE VIEW paket_icerikleri AS
        SELECT d.run_id, d.adim, i AS indeks,
          json_extract_string(d.ham_durum, '$.pack.cards[' || i || '].key') AS anahtar,
          json_extract_string(d.ham_durum, '$.pack.cards[' || i || '].label') AS ad,
          json_extract_string(d.ham_durum, '$.pack.cards[' || i || '].value.effect') AS etki,
          (json_extract_string(d.komut, '$.yontem') = 'pack'
            AND CAST(json_extract_string(d.komut, '$.parametreler.card') AS INTEGER) = i) AS secildi
        FROM decisions d,
             range(CAST(COALESCE(json_array_length(json_extract(d.ham_durum, '$.pack.cards')), 0) AS BIGINT)) AS t(i)
        """
    )
    # Oynanan ve atılan eller: hangi kartlar, hangi el türü, ne çekildi, skor değişimi.
    onceki = "from_json(json_extract(d.ham_durum, '$.hand.cards'), '[{\"id\":\"BIGINT\",\"key\":\"VARCHAR\"}]')"
    sonraki = "from_json(json_extract(d.cevap, '$.hand.cards'), '[{\"id\":\"BIGINT\",\"key\":\"VARCHAR\"}]')"
    con.execute(
        f"""
        CREATE VIEW eller AS
        SELECT d.run_id, d.adim, json_extract_string(d.komut, '$.yontem') AS islem,
          list_transform(
            from_json(json_extract(d.komut, '$.parametreler.cards'), '["INTEGER"]'),
            x -> json_extract_string(d.ham_durum, '$.hand.cards[' || x || '].key')
          ) AS kartlar,
          -- Oynanan el türü: `played` sayacı artan tek tür (yalnızca play için).
          CASE WHEN json_extract_string(d.komut, '$.yontem') = 'play' THEN
            list_filter(
              json_keys(json_extract(d.ham_durum, '$.hands')),
              k -> CAST(json_extract_string(d.cevap, '$.hands."' || k || '".played') AS INTEGER)
                 > CAST(json_extract_string(d.ham_durum, '$.hands."' || k || '".played') AS INTEGER)
            )[1]
          END AS el_turu,
          -- Elde olup seçilmeyen (tutulan) kartlar.
          list_filter(
            list_transform(
              range(CAST(json_array_length(json_extract(d.ham_durum, '$.hand.cards')) AS BIGINT)),
              i -> json_extract_string(d.ham_durum, '$.hand.cards[' || i || '].key')
            ),
            k -> NOT list_contains(
              list_transform(
                from_json(json_extract(d.komut, '$.parametreler.cards'), '["INTEGER"]'),
                x -> json_extract_string(d.ham_durum, '$.hand.cards[' || x || '].key')),
              k)
          ) AS tutulan,
          -- Komuttan sonra ele yeni gelen kartlar (id farkı).
          list_transform(
            list_filter({sonraki}, c -> NOT list_contains(list_transform({onceki}, b -> b.id), c.id)),
            c -> c.key
          ) AS cekilen,
          CAST(json_extract_string(d.ham_durum, '$.round.hands_left') AS INTEGER) AS kalan_el,
          CAST(json_extract_string(d.ham_durum, '$.round.discards_left') AS INTEGER) AS kalan_discard,
          CAST(json_extract_string(d.ham_durum, '$.round.chips') AS BIGINT) AS skor_once,
          CAST(json_extract_string(d.cevap, '$.round.chips') AS BIGINT) AS skor_sonra,
          CAST(json_extract_string(d.ham_durum, '$.round_num') AS INTEGER) AS tur_no,
          CAST(json_extract_string(d.ham_durum, '$.ante_num') AS INTEGER) AS ante
        FROM decisions d
        WHERE json_extract_string(d.komut, '$.yontem') IN ('play', 'discard')
        """
    )
    # Tüketilebilir (tarot/gezegen/spektral) kullanımı: eldeki veya açık paketten, hedef kartlarıyla.
    hedefler = (
        "list_transform(from_json(json_extract(d.komut, '$.parametreler.{alan}'), '[\"INTEGER\"]'),"
        " x -> json_extract_string(d.ham_durum, '$.hand.cards[' || x || '].key'))"
    )
    con.execute(
        f"""
        CREATE VIEW tuketilebilir_kullanimi AS
        SELECT d.run_id, d.adim, 'eldeki' AS kaynak,
          json_extract_string(d.ham_durum,
            '$.consumables.cards[' || json_extract_string(d.komut, '$.parametreler.consumable') || '].key') AS anahtar,
          {hedefler.format(alan='cards')} AS hedef_kartlar
        FROM decisions d WHERE json_extract_string(d.komut, '$.yontem') = 'use'
        UNION ALL
        SELECT d.run_id, d.adim, 'paket' AS kaynak,
          json_extract_string(d.ham_durum,
            '$.pack.cards[' || json_extract_string(d.komut, '$.parametreler.card') || '].key') AS anahtar,
          {hedefler.format(alan='targets')} AS hedef_kartlar
        FROM decisions d
        WHERE json_extract_string(d.komut, '$.yontem') = 'pack'
          AND json_extract(d.komut, '$.parametreler.card') IS NOT NULL
        """
    )
    # Elimizde duran tüketilebilirler: her adımda, kullanıldı/satıldı mı yoksa tutuldu mu.
    con.execute(
        """
        CREATE VIEW eldeki_tuketilebilirler AS
        SELECT d.run_id, d.adim, i AS indeks,
          json_extract_string(d.ham_durum, '$.consumables.cards[' || i || '].key') AS anahtar,
          json_extract_string(d.ham_durum, '$.consumables.cards[' || i || '].label') AS ad,
          CAST(json_extract_string(d.komut, '$.parametreler.consumable') AS INTEGER) = i
            AND json_extract_string(d.komut, '$.yontem') = 'use' AS kullanildi,
          CAST(json_extract_string(d.komut, '$.parametreler.consumable') AS INTEGER) = i
            AND json_extract_string(d.komut, '$.yontem') = 'sell' AS satildi
        FROM decisions d,
             range(CAST(COALESCE(json_array_length(json_extract(d.ham_durum, '$.consumables.cards')), 0) AS BIGINT)) AS t(i)
        """
    )
    # Satışlar: ne satıldı, kaça.
    con.execute(
        """
        CREATE VIEW satislar AS
        SELECT d.run_id, d.adim,
          CASE WHEN json_extract(d.komut, '$.parametreler.joker') IS NOT NULL THEN 'joker' ELSE 'tuketilebilir' END AS tur,
          json_extract_string(d.ham_durum,
            CASE WHEN json_extract(d.komut, '$.parametreler.joker') IS NOT NULL
                 THEN '$.jokers.cards[' || json_extract_string(d.komut, '$.parametreler.joker') || '].key'
                 ELSE '$.consumables.cards[' || json_extract_string(d.komut, '$.parametreler.consumable') || '].key' END) AS anahtar,
          CAST(json_extract_string(d.ham_durum,
            CASE WHEN json_extract(d.komut, '$.parametreler.joker') IS NOT NULL
                 THEN '$.jokers.cards[' || json_extract_string(d.komut, '$.parametreler.joker') || '].cost.sell'
                 ELSE '$.consumables.cards[' || json_extract_string(d.komut, '$.parametreler.consumable') || '].cost.sell' END) AS INTEGER) AS satis_fiyati
        FROM decisions d WHERE json_extract_string(d.komut, '$.yontem') = 'sell'
        """
    )
