# PyPSA-GUI2

[日本語](#日本語) | [English](#english)

<a id="日本語"></a>
## 日本語

PyPSA（Python for Power System Analysis）による電力・エネルギーシステムのモデル構築と最適化を、GUI 上で行うためのデスクトップアプリケーション（PyQt6 製）。

複数エリア（地域）にまたがるエネルギーシステムを、TIMES 由来の Reference Energy System（RES）記法で自由に構築し、PyPSA で容量拡張・運用最適化を実行、複数シナリオの結果を比較できることを目指す。詳細な機能仕様は [`PyPSA-GUI_仕様書.md`](PyPSA-GUI_仕様書.md) を参照。

### 主な機能

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

### 動作環境

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

### 実行方法

```bash
python main.py
```

起動時に `project.xlsx`（存在すれば）を自動で読み込む。新規プロジェクトの作成・保存・読込はメニューから行う。

### プロジェクト構成

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

### 開発状況

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

---

<a id="english"></a>
## English

A PyQt6 desktop application for building and optimizing power/energy system models with PyPSA (Python for Power System Analysis), entirely through a GUI.

The goal is to let you freely build multi-area energy systems using a TIMES-style Reference Energy System (RES) notation, run capacity-expansion / operational optimization with PyPSA, and compare results across multiple scenarios. For detailed functional specifications, see [`PyPSA-GUI_仕様書.md`](PyPSA-GUI_仕様書.md) (Japanese only).

### Key Features

- **Area overview (map view)**: place areas and interconnections on OpenStreetMap tiles (`map_bridge.py` / Leaflet)
- **RES configuration editor**: edit each area's energy system (generators, demand, storage, pumped hydro, converters) as a diagram
  - Add components from the left side panel across 5 categories: Primary Resource / Conversion Process / Demand / Energy Storage / Carrier Management
  - Right-click a node on the diagram to edit or delete it; double-click for detailed editing
  - A warning banner flags components connected to a carrier with no supply source
  - From the Generator and Load edit dialogs, click "Edit Time Series…" to edit 8760-hour data directly per component (data is scoped independently per area even for identically-named components)
  - Capacity/energy-capacity input fields for generators, loads, storage, pumped hydro, converters, and interconnections have a unit-switching combo box (power: W/kW/MW/GW; energy: Wh/kWh/MWh/GWh/PJ/toe). Internal data is always kept in MW/MWh (`unit_widgets.py`)
- **Component templates**: define reusable compound components — batteries, hydrogen tanks, pumped hydro, etc. — as combinations of `Bus`/`Store`/`Link`/`Generator` (`node_graph.py` + `component_template_editor.py`)
- **Scenario management**: define CO2 caps, carbon prices, per-carrier costs, etc. as profiles and apply them across multiple scenarios and planning years
- **Time series data**: holds 8760-hour capacity-factor data for solar/wind/hydro/biomass and demand (load); editable from the RES configuration editor, with bulk Excel import/export also supported
- **Run optimization**: batch-run with solvers such as HiGHS / Gurobi / CPLEX, with progress logging
  - When HiGHS is selected, choose the algorithm (Automatic / Simplex / Interior Point (IPM))
- **Results dashboard**: view installed capacity, generation, cost breakdown, dispatch time series, and year-over-year comparison charts
- **Excel import/export / netCDF save**: save/load an entire project as a single Excel file; optimization results are saved as netCDF
- **Multi-language support**: Japanese/English switching based on Qt Linguist (`i18n.py` / `translations/`)

### Requirements

- Python 3.11
- PyQt6 / PyQt6-WebEngine
- PyPSA ≥ 1.2.0 (HiGHS bundled; Gurobi / CPLEX can be used with a separate license.
  On pandas ≥ 3.0, PyPSA 1.2.0 or later is required to avoid an xarray alignment
  error during multi-period optimization)
- pandas, numpy, openpyxl, netCDF4, xarray, matplotlib

Create the conda environment from the included [`environment.yml`](environment.yml):

```bash
conda env create -f environment.yml
conda activate pypsa-gui2
```

### Running

```bash
python main.py
```

On startup, `project.xlsx` is loaded automatically if present. Creating, saving, and loading projects is done from the menu.

### Project Structure

```
main.py                        Application entry point
src/
  main_window.py               Main window / screen navigation
  network_editor.py            Area/RES editing screen (map, RES diagram, component tables)
  unit_widgets.py               Unit-switching widgets for capacity/energy input fields (MW/MWh base, W-GW / Wh-PJ/toe)
  node_graph.py                Node-graph editor for component templates
  component_template_editor.py Editor for compound component (Bus/Store/Link/Generator) definitions
  map_bridge.py                Signal bridge to the map (Leaflet)
  models.py                    Data models (Area / Generator / Load / Store / Scenario, etc.)
  network_manager.py           Network data management
  config_generator.py          GUI data -> pypsa.Network conversion
  pypsa_runner.py               Optimization worker and result extraction
  run_panel.py                  Run-queue UI
  results_panel.py              Results comparison dashboard
  scenario_editor.py            Scenario / profile editing
  timeseries_editor.py          Internal store for time series data (CF, demand) + bulk Excel I/O (used from the RES editing screen in the UI)
  excel_handler.py              Excel import/export
  i18n.py                        Multi-language support
translations/                  Qt Linguist translation files (.ts/.qm)
```

### Development Status

Being extended incrementally, following the priority order in section 7 of `PyPSA-GUI_仕様書.md`.

- [x] Interactive RES configuration editor (add from left palette, right-click edit/delete, unconnected-component warnings)
- [x] Demand (Load) time series editing in the RES editing screen (scoped by area + load name, symmetric with generators)
- [ ] Explicit resource Bus+Store for primary resources — on hold: confirmed that PyPSA/linopy's internal constraint
      generation changes optimization results for networks with multiple extendable, unconnected areas
      (the conversion formula itself has been validated). The existing `Generator`-based PyPSA output is unchanged.
- [ ] Parallelizing the run queue / IIS diagnostics
- [ ] Generic scatter plots / delta display for the results comparison dashboard
- [x] Unit conversion tool (applies to capacity/energy input fields in the RES editing screen; does not cover
      capital/marginal cost unit switching or component templates / scenario overrides)
- [ ] Power-flow visualization for the area overview
