# PyPSA-GUI2

PyPSA（Python for Power System Analysis）による電力・エネルギーシステムのモデル構築と最適化を、GUI 上で行うためのデスクトップアプリケーション（PyQt6 製）。

複数エリア（地域）にまたがるエネルギーシステムを、TIMES 由来の Reference Energy System（RES）記法で自由に構築し、PyPSA で容量拡張・運用最適化を実行、複数シナリオの結果を比較できることを目指す。詳細な機能仕様は [`PyPSA-GUI_仕様書.md`](PyPSA-GUI_仕様書.md) を参照。

## 主な機能

- **エリア間概観（地図表示）**: OpenStreetMap タイル上にエリアと連系線を配置（`map_bridge.py` / Leaflet）
- **RES構成エディタ**: エリアごとのエネルギーシステム（発電機・需要・貯蔵・揚水発電・変換器）を構成図として編集
  - 左サイドパネルから「1次資源／変換プロセス／需要／エネルギー貯蔵／キャリア管理」の5カテゴリでコンポーネントを追加
  - 図上のノードを右クリックで編集・削除、ダブルクリックで詳細編集
  - 供給元のないキャリアに接続されたコンポーネントを警告バナーで通知
  - 発電機・需要（Load）それぞれの編集ダイアログから「時系列を編集…」で8760時間データをコンポーネント単位に直接編集（同名でもエリアが異なれば独立したデータとして扱われる）
  - 発電機・負荷・貯蔵・揚水発電所・変換器・連系線の容量/エネルギー容量入力欄は単位切替コンボ付き（電力: W/kW/MW/GW、エネルギー: Wh/kWh/MWh/GWh/PJ/toe）。内部データは常にMW/MWhで保持（`unit_widgets.py`）
- **コンポーネントテンプレート**: 蓄電池・水素タンク・揚水発電などの複合コンポーネントを `Bus`/`Store`/`Link`/`Generator` の組み合わせで定義し再利用（`node_graph.py` + `component_template_editor.py`）
- **シナリオ管理**: CO2上限・炭素価格・キャリア別コストなどをプロファイルとして定義し、複数シナリオ・複数計画年に適用
- **時系列データ**: 太陽光/風力/水力/バイオマスの容量係数、需要（負荷）の8760時間データを保持。RES構成エディタから編集するほか、Excelでの一括インポート/エクスポートにも対応
- **最適化実行**: HiGHS / Gurobi / CPLEX などのソルバーでバッチ実行し、進捗ログを表示
  - HiGHS選択時はアルゴリズム（自動 / 単体法 Simplex / 内点法 IPM）を切り替え可能
- **結果ダッシュボード**: 設備容量・発電量・コスト内訳・稼働時系列・年次比較グラフを表示
- **Excel入出力 / netCDF保存**: プロジェクト全体を Excel 1ファイルで保存・読込、最適化結果は netCDF で保存
- **多言語対応**: Qt Linguist ベースの日英切り替え（`i18n.py` / `translations/`）

## 動作環境

- Python 3.11
- PyQt6 / PyQt6-WebEngine
- PyPSA ≥ 1.2.0（HiGHS 同梱、Gurobi / CPLEX は別途ライセンスがあれば利用可。
  pandas ≥ 3.0 環境では、multi-period最適化でのxarrayアライメントエラーを回避するため
  PyPSA 1.2.0 以降が必須）
- pandas, numpy, openpyxl, netCDF4, xarray, matplotlib

付属の [`environment.yml`](environment.yml) から conda 環境を作成:

```bash
conda env create -f environment.yml
conda activate pypsa-gui2
```

## 実行方法

```bash
python main.py
```

起動時に `project.xlsx`（存在すれば）を自動で読み込む。新規プロジェクトの作成・保存・読込はメニューから行う。

## プロジェクト構成

```
main.py                        アプリケーションエントリポイント
src/
  main_window.py               メインウィンドウ・画面遷移
  network_editor.py            エリア/RES編集画面（地図・RES構成図・コンポーネントテーブル）
  unit_widgets.py               容量/エネルギー入力欄の単位切替ウィジェット（MW/MWh基準、W〜GW・Wh〜PJ/toe対応）
  node_graph.py                コンポーネントテンプレート用のノードグラフエディタ
  component_template_editor.py 複合コンポーネント（Bus/Store/Link/Generator）の定義エディタ
  map_bridge.py                地図(Leaflet)とのシグナル連携
  models.py                    データモデル（Area / Generator / Load / Store / Scenario 等）
  network_manager.py           ネットワークデータの管理
  config_generator.py          GUIデータ → pypsa.Network への変換
  pypsa_runner.py               最適化実行ワーカーと結果抽出
  run_panel.py                  実行キューUI
  results_panel.py              結果比較ダッシュボード
  scenario_editor.py            シナリオ・プロファイル編集
  timeseries_editor.py          時系列データ（CF・需要）の内部ストア＋Excel一括入出力（画面上はRES編集画面から利用）
  excel_handler.py              Excel入出力
  i18n.py                        多言語対応
translations/                  Qt Linguist 翻訳ファイル (.ts/.qm)
```

## 開発状況

`PyPSA-GUI_仕様書.md` の優先順位（7章）に沿って段階的に拡張中。

- [x] RES構成エディタのインタラクティブ化（左パレットからの追加・右クリック編集/削除・未接続警告）
- [x] RES編集画面での需要（Load）時系列編集（エリア＋負荷名でスコープ、発電機と対称の設計）
- [ ] 一次資源の資源Bus+Store明示化 — PyPSA/linopy側の内部制約生成が、拡張可能かつ非連系の複数エリアを含むネットワークで
      最適化結果を変化させてしまう事象を確認したため保留中（変換式自体は検証済み）。既存の `Generator` ベースの
      PyPSA出力は変更していない
- [ ] 実行キューの並列化・IIS診断
- [ ] 結果比較ダッシュボードの汎用散布図・Δ表示
- [x] 単位変換ツール（RES編集画面の容量/エネルギー入力欄が対象。建設費/変動費や
      コンポーネントテンプレート・シナリオオーバーライドの単位切替は対象外）
- [ ] エリア間概観の潮流フロー可視化
