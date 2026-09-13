# Interpreting daily changes in recorded Facebook SMS-verification prices

[**View the full research report (PDF)**](report/report.pdf) · [HTML version](report/report.html) · [View the figures](output/figures/) · [Validation and reproducibility](docs/VALIDATION_AND_REPRODUCIBILITY.md)

**Research question.** For Facebook SMS verifications using UK, US and Indonesian phone numbers from 1 August 2024 to 27 July 2025, how much of the daily change in COTSI's recorded stock-weighted price reflects within-vendor recorded-price changes versus advertised-stock-share reweighting on consecutive days with the same positive-stock vendors?

SMS verification is one input to account creation in the online manipulation economy. A stock-weighted recorded price can move because vendor quotes change, advertised-stock shares change, or both. **Python** prepares and validates the vendor-day data; **R** decomposes eligible daily changes and produces descriptive tables and figures. Across **1,001 eligible pairs**, the absolute price component was larger on more pairs than the weight component in all three selected markets, although the two often moved in opposite directions. This is a **descriptive, non-causal** analysis of recorded offers, not a measure of sales or manipulation demand.

## Data

The source is a local copy of the COTSI replication archive `verifications data_final.zip` from [Dek, Kyrychenko, van der Linden and Roozenbeek (2025), *Mapping the online manipulation economy*](https://doi.org/10.1126/science.adw8154). The analysis uses the archive's 12 monthly CSVs from August 2024 through July 2025, restricted to Facebook (`fb`), UK (`GB`), US and Indonesian (`ID`) **phone-number markets**, and four recorded vendors: SMSPVA, SMSHub, SMS-Activate and 5SIM. The selected period is **2024-08-01 to 2025-07-27**. Prices are recorded quotes and stock is advertised stock, not verified transactions or availability.

The 12 intended source members contained **9,960,721 rows** before filtering. The fixed scope retained **1,080 observed country-days**, reshaped to **4,320 observed vendor-day records** and **4,332 calendar-complete vendor-day rows**. **30 December 2024** is missing in every market and is kept as a gap. Of **1,074** valid adjacent-day pairs, **1,001** had an unchanged set of at least two positive-stock vendors and entered the decomposition; **73** changing-set pairs entered only the selection check.

## Method

Python reads every intended archive member in chunks, filters and reshapes the data, converts RUB quotes using the archive's recorded exchange rate, reconstructs the source's combined stock and weighted price, and creates explicit calendar-day lags and vendor-set eligibility. R applies a symmetric accounting decomposition on eligible stable-set pairs: the **price component** uses changes in vendors' recorded USD prices weighted by average stock shares; the **weight component** uses changes in advertised-stock shares weighted by average recorded prices. Their sum is checked against each observed weighted-price change. R then reports country-specific absolute-magnitude summaries, compares stable and changing sets on observed combined-price movement, and makes two figures. No changing-set pair is decomposed by inventing a missing vendor quote.

## Main findings

| Market | Eligible stable-set pairs | Pairs with larger absolute price component | Pairs with opposite-signed components |
| --- | ---: | ---: | ---: |
| UK (GB) | 325 | 202 | 160 |
| US | 326 | 258 | 153 |
| Indonesia (ID) | 350 | 196 | 210 |

The price-component pattern was clearest in the US and less pronounced in Indonesia. Three **8–10 July 2025** movements in recorded SMSHub USD quotes strongly influence mean price-component magnitudes in the UK and Indonesia, so medians give important context for a typical eligible pair. The large observations passed the implemented arithmetic checks but may still reflect upstream reporting issues. Changing-set pairs' share of total absolute combined-price movement was smaller than their share of valid pairs in all three markets; their median absolute movements were nevertheless higher, particularly in the UK. These exclusions are not inconsequential, and the decomposition describes only eligible stable-set pairs. The [report](report/report.pdf) gives the numerical results and interpretation.

## Repository structure

```text
python/prepare_data.py                Data preparation and validation
R/analyze_prices.R                    Decomposition, summaries and figures
report/report.qmd                     Quarto source
report/report.pdf                     PDF report
report/report.html                    Rendered report with embedded figures
output/tables/                        Two concise validated result tables
output/figures/                       Two validated figures
docs/VALIDATION_AND_REPRODUCIBILITY.md  Checks, provenance and limitations
```

## Reproduction

Run from the repository root, in this order:

1. Obtain the authors' [OSF replication materials](https://osf.io/t3xzg/) and place the original `verifications data_final.zip` at `data/raw/verifications data_final.zip` (create `data/raw/` locally). The local archive used for validation had SHA-256 `0acd5daf991033022c19f6276e4e4d5ea05a61bd564a903cf7fef4bbdd1f3b2d`. Check the download's version and checksum before running; a different archive is **not** interchangeable without investigation.
2. With Python 3.13 and `pandas`/`numpy`, run `python python/prepare_data.py`. It writes `data/processed/facebook_vendor_day_analytical.csv` and `output/tables/data_preparation_audit.csv`.
3. With R 4.6 and `tidyverse`/`digest`, run `Rscript R/analyze_prices.R`. It verifies the prepared CSV's validated fingerprint and audit, then regenerates three result tables and two figures. The detailed 1,001-pair table is generated locally but not committed to this public copy.
4. Check the numerical text in `report/report.qmd` against the regenerated tables, then run `quarto render report/report.qmd --to html`. Quarto embeds the regenerated figures in `report/report.html`; it does **not** automatically refresh the report's manually maintained numerical prose or tables.

The final reviewed run used Python 3.13.15, R 4.6.1 and Quarto 1.10.18. Exact third-party package versions were not pinned. If a checksum or validation count differs, investigate the source and environment rather than changing an expected value to force a pass.

## Validation

The preparation audit had **53 PASS, 6 INFO and 0 FAIL** checks, including unique keys, valid positive-stock prices, exact stock reconstruction and weighted-price reconstruction within the documented tolerance. The R decomposition identity passed on **all 1,001 eligible pairs**, with zero failures and a maximum numerical residual of about **3.89 × 10⁻¹⁶ recorded USD**. A fresh Python → R → Quarto run regenerated the analytical input, tables, figures and report. Details and published-output fingerprints are in [Validation and reproducibility](docs/VALIDATION_AND_REPRODUCIBILITY.md).

## Limitations

Advertised stock is not sales, unique SIM cards or verified availability; a recorded quote need not be a realised successful-verification cost. Source/reporting problems cannot be ruled out, including for the July SMSHub spikes. Vendors may differ in quality or product mix. The three purposively selected phone-number markets are not representative, adjacent pairs are temporally dependent, and changing-set pairs are not decomposed. The accounting split does not identify why prices or stocks changed and supports no causal claim.

## Data availability

The raw COTSI archive, detailed prepared and pair-level data, reference code and literature are **not redistributed** here. The [source paper](https://doi.org/10.1126/science.adw8154) identifies the [OSF data-and-code project](https://osf.io/t3xzg/); the exact remote archive version and download path were not independently verified for this release. This repository contains the analysis scripts and concise derived result tables/figures, not source data collected by this project's author. The archive filename and validated local checksum above identify the version needed to reproduce these results.
