# JMA daily observations, Sapporo (station 47412), 1976–2025

One CSV per year with daily observations for Sapporo, fetched from the Japan Meteorological Agency's past-weather pages by `dcopt.heat.weather` and converted to tidy CSV. They are committed so that a fresh clone runs the weather study without downloading; a missing or unreadable year is downloaded again on demand.

**Source and terms.** These files are not covered by the repository's MIT license. JMA allows its website content to be used under conditions that conform to the Public Data Terms of Use, version 1.0 (公共データ利用規約（第1.0版）), which require the source to be credited and any processing to be stated: https://www.jma.go.jp/jma/kishou/info/coment.html

- 出典：気象庁ホームページ（https://www.data.jma.go.jp/obd/stats/etrn/）
- 気象庁「過去の気象データ検索　日ごとの値（札幌）」（https://www.data.jma.go.jp/obd/stats/etrn/view/daily_s1.php?prec_no=14&block_no=47412）を加工して作成（日別の表を年ごとのCSVに変換。値は変更していません。欠けた日は読み込み時に補います）。
- Source: Japan Meteorological Agency website. Processed by Team Data Center: the daily tables were converted to one CSV per year; values are unchanged, and the loader fills a missing day when it reads them.
