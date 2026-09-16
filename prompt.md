# PyPSA-GUI2 への「帯域分解Sobol感度分析（MODWT × LAR-PCE）」機能の実装指示

## 1. 実装の目的と背景
`PyPSA-GUI2` に、研究プレゼンテーション『発電リソースの時間帯域別価値評価に関する研究』で提案された**「帯域分解Sobol感度分析（MODWT × LAR-PCE）」**モジュールを新たに統合します。
これにより、ユーザーがGUI上で複数不確実パラメータ（不確実な設備CAPEX、V1G普及率、地域間送電線拡張コスト等）を設定し、8,760時間のPyPSA最適化結果に対して5つの物理時間帯域ごとの感度指標（S_i, ST_i）およびリソース間の競合・相補関係（交差項の符号判断）を解析・可視化できるようにします。

---

## 2. 実装対象の5ステップ解析ワークフロー

以下の5つの技術ステップをモジュール化して実装してください：

1. **LHS（ラテン超方格）サンプリング**:
   - 入力不確実パラメータ（k個）の値域から、空間を均一カバーする $N=300 \sim 600$ 点のサンプルセットを生成。
   - V1G/V0Gなどの比較評価用として、共通乱数（CRN: Common Random Numbers）によるペア求解用サンプルの生成に対応。
2. **PyPSAバッチ求解ワーカー**:
   - `pypsa_runner.py` と連携し、LHSサンプル点ごとのPyPSAモデル求解をバッチ実行。
   - 各求解結果から、主問題側の帯域別仕事量 $W_t$ および双対問題側の影の価格 $\lambda(t)$ （または双対価格内積 $\Pi_b$）を時系列抽出（8,760時間）。
3. **MODWT（最大重複離散ウェーブレット変換）帯域分解**:
   - 抽出した時系列データ（8,760時間）に対し、MODWTを適用してParsevalの定理を満たす形で以下の5つの物理帯域に完全分解：
     - ① **サブ日内帯**: < 12時間
     - ② **日次帯（Daily）**: 12〜36時間
     - ③ **総観規模帯（Synoptic）**: 36〜192時間
     - ④ **Dunkelflaute帯**: 192〜720時間
     - ⑤ **季節帯（Seasonal）**: > 720時間
4. **LAR-PCE（スパース多項式カオス展開）代理モデル**:
   - LHSの入力 $\mathbf{X}$ と、各帯域の分解出力 $Y(b)$ （5帯域分）から、帯域ごとに独立したPCEモデル $Y(b) \approx \sum_{\boldsymbol{\alpha}} c_{\boldsymbol{\alpha}}(b) \psi_{\boldsymbol{\alpha}}(\mathbf{X})$ を学習。
   - 入力が一様分布の場合は直交ルジャンドル多項式を基底関数として使用。
   - LAR（Least Angle Regression）アルゴリズムにより、LOO（Leave-One-Out）交差検証誤差（$\epsilon_{LOO}$ または $1-Q^2$）を監視し、誤差最小化点で自動打ち切り（スパース化）。
5. **Sobol指数算出 ＆ 競合・相補の符号判定**:
   - 展開係数 $c_{\boldsymbol{\alpha}}(b)$ から代数的に $S_i(b)$（1次感度）、$ST_i(b)$（全効果感度）、$S_{ij}(b)$（2次感度）を算出。
   - 2次交差項の多項式係数 $c_{ij}(b)$ の実数符号を判定：
     - **$c_{ij}(b) < 0$**: 同一帯域での代替関係（競合 / 仕事の奪い合い）
     - **$c_{ij}(b) > 0$**: 同一帯域での相乗的補完（シナジー）
     - **主効果の帯域分離**: 異なる帯域での機能分担（補完）

---

## 3. ディレクトリ構造と新規・更新ファイル仕様

既存の `src/` 配下に `sensitivity/` パッケージを新規作成し、以下の構成でコードを追加・拡張してください：

```text
src/
├── sensitivity/                  # 【新規作成】感度解析パッケージ
│   ├── __init__.py
│   ├── lhs_sampler.py           # LHSサンプリング & CRN生成
│   ├── modwt_decomposer.py      # MODWT帯域分解（5物理帯域への全分散保存分解）
│   ├── lar_pce_engine.py        # LAR-PCEスパース多項式フィッティング & LOO評価
│   ├── sobol_analyzer.py        # Sobol指数(S_i, ST_i, S_ij)導出 & c_ij 符号判定
│   └── sensitivity_runner.py    # 全体パイプラインのオーケストレーター
├── models.py                    # 【更新】SensitivityConfig / SensitivityResult データモデル定義の追加
├── pypsa_runner.py               # 【更新】LHSバッチ並列実行機能・影の価格/仕事量抽出フックの追加
├── results_panel.py             # 【更新】「帯域別Sobol感度」タブの追加（行列ヒートマップ・競合判定マトリクス表示）
└── main_window.py               # 【更新】メニュー/タブ切り替えの配線
```

### 各モジュールの実装詳細要件

#### 1. `src/sensitivity/modwt_decomposer.py`
- Pythonの `PyWavelets` (`pywt`) または `scipy.signal` を用いてMODWTを実装（ダウンサンプリングを行わず、長さを8,760時間に維持）。
- Parsevalの定理が成り立つことを単位テストで検証（`np.isclose(np.var(x), np.sum(band_variances))`）。

#### 2. `src/sensitivity/lar_pce_engine.py`
- `scikit-learn` の `LassoLarsCV` または `LARS` をベースにスパース回帰を構成。
- ルジャンドル多項式（`numpy.polynomial.legendre`）で基底関数行列 $\Psi(\mathbf{X})$ を生成（デフォルトは3次多項式まで）。
- LOO交差検証誤差 $\epsilon_{LOO}$ を計算し、10%（$Q^2 \ge 0.90$）を超える場合は警告ダイアログを出すフックを用意。

#### 3. `src/sensitivity/sobol_analyzer.py`
- 係数 $c_{\boldsymbol{\alpha}}(b)$ から解析的閉形式で $S_i(b), ST_i(b)$ を計算：
  $$S_i = \frac{\sum_{\boldsymbol{\alpha} \in \mathcal{A}_i} c_{\boldsymbol{\alpha}}^2}{\sum_{\boldsymbol{\alpha} \neq \mathbf{0}} c_{\boldsymbol{\alpha}}^2}$$
- パラメータペア $(i, j)$ について、$c_{ij}$ の正負判定メソッド `diagnose_interaction(i, j, band)` を実装。

#### 4. UI実装（`src/results_panel.py` / PyQt6）
- **感度指標行列ヒートマップ**: `matplotlib` / `seaborn` を用いて「縦軸：入力パラメータ」×「横軸：5時間帯域」のSobol感度 $S_i(b)$ ヒートマップを描画。
- **競合・相補診断テーブル**: パラメータペアごとの主干渉帯域、交差項符号（正/負）、および診断判定（代替 / シナジー / 機能分担）を色分け表示するQTableWidgetを追加。

---

## 4. 依存ライブラリの確認と更新
`environment.yml` に必要に応じて以下のライブラリを追加・更新してください：
- `PyWavelets`（MODWT計算用）
- `scikit-learn`（LARSアルゴリズム・クロスバリデーション用）

---

## 5. 開発手順と検証テスト

1. **Step 1**: `src/sensitivity/` 内の非GUIコアロジック（LHS, MODWT, LAR-PCE, Sobol）を実装し、合成データを用いた単体テスト（`tests/test_sensitivity.py`）を作成して通過させること。
2. **Step 2**: PyPSA求解エンジン（`pypsa_runner.py`）とのバッチ接続を実装し、サンプル数 $N=10$ のテストランで時系列（8760h）から影の価格 $\lambda(t)$ が正常抽出・分解されるか確認。
3. **Step 3**: `results_panel.py` にGUIコンポーネントを追加し、サンプルデータでヒートマップおよび競合・相補テーブルが正常表示されることを確認。

以上の手順に従い、リファクタリングを保ちつつ、段階的に実装コードとユニットテストを作成してください。
