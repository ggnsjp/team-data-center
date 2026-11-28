# 任意の追加機能

[English](optional-addons.md)

このページの追加機能は、このリポジトリのどこにも必要ありません。設定しなければ、アプリもスクリプトもテストも、[README](../README.ja.md) に書いたとおりに動きます。

## 言語モデルのルーター（OrcaRouter）

Warm Ishikariページの質問欄は、OpenAI互換の言語モデル1つに直接つなぎます（`LLM_API_KEY`・`LLM_BASE_URL`・`LLM_MODEL`。READMEを参照）。代わりに、[OrcaRouter](https://docs.orcarouter.ai/) 経由にして、モデルの順番（フォールバックの順番）を指定することもできます。1つのモデルの障害や429があっても、質問欄が止まりにくくなります。`ORCAROUTER_API_KEY` を設定しなければ、何も変わりません。

1. OrcaRouterのコンソールで、BYOKに、使っている言語モデルのサービスをカスタムのOpenAI互換エンドポイントとして追加し（ベースURLとキー）、モデルをインポートします。
2. 必要ならガードレールを追加します（コンソールのGuardrailsで作成し、キーに割り当てる）。例：入力に `max_chars` のルールと個人情報のマスク。ガードレールは入力を確認し、出力は質問欄の数値のチェックが確認します。
3. 次の環境変数を設定します。`LLM_MODELS` の最初は、インポート後にコンソールに表示されるモデルIDです。OrcaRouterのモデルIDならどれでも並べられます。たとえば `LLM_MODELS=orcarouter/fusion-flash` とすれば、OrcaRouter自身のルーター用モデルを使い、インポートは要りません。

| 環境変数 | 意味 |
| --- | --- |
| `ORCAROUTER_API_KEY` | OrcaRouterのキー（`sk-orca-...`）。設定するとルーター経由になります |
| `ORCAROUTER_BASE_URL` | 既定は `https://api.orcarouter.ai/v1` |
| `LLM_MODELS` | フォールバックの順番（カンマ区切り、最大5） |
| `LLM_API_KEY`、`LLM_BASE_URL`、`LLM_MODEL` | 直接つなぐサービス。ルーターに接続できないとき、または5xx/429のときに使います |

ルーターが次のモデルに切り替えるのは、5xx・429・ネットワークのエラーのときだけです。401/403やガードレールによるブロックは、再試行せずエラーとして表示します。プライバシー：このモードでは、プロンプト（質問とモデルの数値）がモデルの提供元に加えてルーターも通ります。回答の下の説明に、ルーター経由か直接接続かを表示します。

ハッカソンの期間中は、直接つなぐサービスとしてCarbonForgeを使いました（ベースURL `https://endpoint.carbonforge.ai/v1`、モデル `carbonforge-flash`）。そのときの設定も使えます。`CF_API_KEY` だけを設定すると、この接続先とモデルを使います。`CARBONFORGE_BASE_URL` と `LLM_MODEL` で変えられます。両方のキーがあるときは `LLM_API_KEY` が優先です。

## 計画のグラフをNeo4jで

`uv run python scripts/export_plan_graph.py` は、NetworkXで計画のグラフを作り、ほかに何も要りません（READMEの「計画をグラフとして見る」）。Neo4jのデータベースがあれば（`uv sync --extra graph` のあと、`NEO4J_URI`、`NEO4J_USERNAME`、`NEO4J_PASSWORD` を設定）、`--neo4j` で同じグラフを読み込み、同じ問いをCypherで尋ねて、答えが一致するかを確かめます。アプリもほかのスクリプトも、Neo4jなしで動きます。

データ台帳の来歴のグラフも、Neo4jに読み込めます：[data-accountability.md](data-accountability.md) の *Optional: the lineage graph in Neo4j*（英語）。
