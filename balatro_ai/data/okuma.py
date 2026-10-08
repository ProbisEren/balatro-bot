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
    return con
