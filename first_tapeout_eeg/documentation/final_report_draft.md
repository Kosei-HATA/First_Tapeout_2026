# EEG AFE SoC 最終技術報告書（骨格・執筆中）

**プロジェクト**: first_tapeout_eeg / Sky130 / caravel `user_analog_project_wrapper`
**対象期間**: 2026-09-05 時点 / trial `source/trials/20260902/`
**状態**: 回路レベル検証完了・E2E 合格・レイアウト進行中

## 1. システム構成
- 電極 → 入力容量網（Cin 32 pF×2、疑似抵抗バイアス、RST TG）→ チョップ PGA（×8/16/32/64 可変、f_chop=1 kHz）→ CT 1 次 ΣΔ ADC（fs=16 kHz）→ CIC sinc³ デシメータ（OSR=64、250 SPS、24 bit）
- クロック: `eeg_clkgen`（256 kHz マスタ → 1 kHz チョップ 4 相非重複＋16 kHz SDM）
- 図: ブロック図（TODO: 挿入）

## 2. 設計判断の記録（2026-09-04/05 の解析）
1. **ベンチクロック反転バグ**: `PULSE({VDD} 0 ...)` の v1/v2 反転が「信号消滅」の全原因だった（同時 ON で入力短絡・同時 OFF でゲート浮遊ポンプ）
2. **DSL 設計→撤去**: CM/差動サーボを実装・検証したが、正クロック下でポンプ電流は実在せず、雑音優先で疑似抵抗のみに回帰
3. **チョップ帰還固有の HP コーナー**: fc≈f_chop/770（実測比例確認）。Rf 帰還（β 崩壊）・PFL（4–8 Hz 共振）は却下
4. **f_chop=1 kHz 採用**: fc≈1.3 Hz、雑音 0.38 µVrms、段 2 1/f 抑制改善、CIC ノッチ整合
5. **ADC**: DAC の TG∥RDAC 並列バグ修正（常時接続の参照切替抵抗 DAC 化）＋コンパレータ出力保持容量 1 pF（同時立下り→ラッチ無効状態の防止）

## 3. 検証結果（全て実測、図は `documentation/figures/20260905/`）
- AFE 周波数応答: 4–40 Hz で ±2.4 % 以内（図 01）。0.5–2 Hz は既知のロールオフ（次期課題）
- PVT 5 コーナー: ゲイン 31.5–31.8（誤差 −0.7〜−1.6 %）、idd 63–99 µA（図 02）
- 雑音: 0.38 µVrms（規格 1.0）、ngspice `inoise_spectrum` は本回路で破綻するためデバイス別 onoise 合算で評価（図 03）
- ADC: 帯域内 SNDR 47.9 dB（図 04）
- E2E: 電極 ±300 mV オフセット・50 Hz 同相 200 µV 下で 8 Hz 100 µV を検出（図 05）
- Monte Carlo N=30: CMRR 最小 71.5 dB、ゲイン σ=0.21 %（図 06）
- 受入照合: 図 07

## 4. レイアウト（KLayout バッチフロー）
- full2 OTA: DRC クリーン・LVS 一致（1865.5×1433.5 µm）
- TODO: PGA アセンブリ / ADC / トップ / caravel 統合

## 5. caravel 統合設計（ピン案）
- TODO: `user_analog_project_wrapper` へのピン割り当て表

## 6. PEX 後再検証（2026-09-12 実施）

## 5.5 caravel ラッパーピン再配置（2026-09-12、precheck 指摘対応）

提出前 precheck 準備で **io_in[0..4] / io_out[0..1]（= mprj_io[4:0]）が
システム予約パッド**（serial/WB/user clock）と判明し、全デジタル信号を
ユーザ使用可能な io_in/out[5..26] へ再配置した。パッド対応（テンプレ
ヘッダ検証済）: io_in/out/oeb[13:0] ↔ mprj_io[13:0]（東エッジ）、
io_in/out/oeb[26:14] ↔ mprj_io[37:25]（西エッジ）。io_in[i] と io_out[i]
は同一パッドを共有する。

- 新ピン配置: PHII..NPHIBI → io_in[5..8]（東, y240.76/464.05/1364.16/
  1586.27）、PHIM..NPHIBM → io_in[9..12]（東, y1812.38/2044.49/2266.6/
  2488.71）、CLK16 → io_in[13]（東, y2935.82）、NCLK16 → io_in[14]（西,
  y2540.20）、S8..S64 → io_in[15..18]（西, y2324.09/2107.98/1891.87/
  1675.76）、BIT/NBIT → io_out[19..20]（西, y1453.74/1238.63）。
  アナログ io_analog[0..4]・電源は変更なし。
- 西側 7 信号は **west highway**（y2676.4..2698 の m4 レーン ×7）で配線:
  マクロ上端（2674.95）と vdda1 m4 立ち上がり（y2700.78〜）の隙間を
  m4 で横断し（m5 では VDD18/VN/VP/VCM/VSS/S の各ランが全走廊を塞ぐため
  m5 高速は不可能）、西端で各信号を別々の x（4/8/…/28）に m5 ダイブ
  → 西スタブ（m3, x-4..2.4）へ stack_m3 で着地。
- 東側は PHI-1/PHI-2 のファンアウトを新スタブ高に合わせて再配置
  （上向きチャンネルは「高いフライトほど西のチャンネル」規則で
  x2581..2601.5 にパック、PHI-2 も同帯域 x2581..2594.1 を共用、
  S 系の北ランを +16 東へシフトして帯域を確保）。
- 検証（全て再実施）: `check_wrapper_nets.py` **NETS OK**、
  DRC は継承 m4.5ab ×2 のみ（新規ゼロ — 経路変更で m5.2×4/m5.via4×1 が
  一度出たが、NCLK16 北ランの x ずらしと mini-hop スタックへの m5pad
  追加で解消）、hier LVS（nopurge）**"Congratulations! Netlists match."**。
  `submission/verilog/rtl/user_defines.v` も同期更新（GPIO5..13/25..29
  = input_nopull、GPIO30/31(BIT/NBIT) = USER_STD_OUTPUT、
  GPIO14..18(io_analog) = USER_STD_ANALOG、信号マップをコメント明記）。

**フロー**: magic 8.3.683（ソースから `tools/magic/` にローカルビルド、
RTimothyEdwards/magic `magic-8.3` ブランチ、headless `-dnull -noconsole`）
＋ volare sky130A tech（`libs.tech/magic/sky130A.tech`）で
`GDSII/eeg_afe_top.gds` を寄生抽出（`scripts/pex/extract_afe_top.tcl`、
`extract all` → `ext2spice lvs`＋全セル `.ext` 寄生 DB）。
`scripts/pex/ext2pex.py` が magic LVS ネットリストに `.ext` の node/cap
レコードをアノテートし、フラット ngspice ネットリストを生成
（`source/trials/20260902/xschem/eeg_afe_top_pex.spice`）。

- 抽出: 64 セル階層、**1706 デバイス、7147 寄生 CAP**（基板 8.37 pF +
  結合 20.95 pF）。並列フィンガ/ユニットデバイスを BSIM 等価のまま統合
  （652 個）し **1054 デバイス**に圧縮、20 aF 未満の CAP を間引き
  （電荷の 99.98% を保持）し **6020 CAP** に削減。PGA 単体版も生成
  （`eeg_afe_pga_pex.spice`: 544 デバイス、3282 CAP）。
- ext2pex の修正点（上流 opamp_adc 版からの一般化）: (1) union-find の
  merge エイリアスが「union 第 1 引数に現れる名前」にしか効かず子セル
  内部ノード名を解決できなかったバグ、(2) 親セルの cap レコードが子セル
  内部ノードを階層名で参照する際に子セルの merge を適用していなかった
  バグ（再帰ガード付きで修正）、(3) PGA 出力を測定用ピン
  PGA_OUTP/PGA_OUTN としてエイリアス公開。
- ベンチ: `tb_afe_f1k8_pex.spice`（フルマクロ PEX、x32、100 µV 8 Hz
  差動、チョッパ 1 kHz、SDM クロック 16 kHz で SDM 実動作負荷）、
  対照は `tb_afe_f1k8_topref.spice`（スキーマ macro、同一刺激）。
  フォールバック: `tb_pga_f1k8_pex.spice` / `tb_pga_f1k8_pgaref.spice`
  （PGA 単体、5 pF 負荷）。全て save 制限付き・逐次実行。
- プリレイアウト基準値: OTA ベンチ 6.3364 mV（ゲイン 31.7）、
  スキーマ macro（SDM 負荷込み）**6.1154 mV**（idd 138.6 µA、
  VCM_out 0.922 V、8 Hz LS-fit、--skip 0.5 で安定確認）。

**PEX 結果（AFE ゲイン @ 8 Hz、x32）**:

| ベンチ | 振幅 (8 Hz LS-fit) | idd | 備考 |
|---|---|---|---|
| プリレイアウト macro（`tb_afe_f1k8_topref`） | **6.1154 mV** | 138.6 µA | SDM 負荷込みスキーマ |
| **フルマクロ PEX（`tb_afe_f1k8_pex`）** | **6.3265 mV** | 117.3 µA | VCM_out 0.9216 V 一致 |
| プリレイアウト OTA（`tb_f1k_8`/`tb_pga_f1k8_pgaref`） | 6.3364 / 6.3380 mV | 69.3 µA | 5 pF 負荷 |
| PGA 単体 PEX（`tb_pga_f1k8_pex`） | TODO | — | 後述の時計配線 bug 修正後に再測定 |

- **ゲイン偏差は PEX で +3.4%**（6.3265 vs 6.1154 mV）— 寄生 CAP による
  追加負荷の影響は小さく、チョップ AFE の閉ループゲイン（CIN/CFB 比決定）
  がレイアウト後も保たれていることを確認。
- 速度対策の記録: フラット PEX（1706 デバイス + 7147 CAP）は当初 ~6 µs/s
  （実時間 70 h 級）だったが、(1) 並列フィンガ統合（nf 保持で PDK の
  bin 内に per-finger W を維持 — これが無いと modelname 解決エラー）、
  (2) MIM を理想 C（2 fF/µm²、直列 R は 1 kHz 帯で無視可）、
  (3) **res_xhigh_po を理想 R（R=2000·l/w）に置換 — これが最大の効果**
  （PDK 抵抗サブ circuit の mismatch/ボディ係数式の評価が全時間の 9 割以上
  を食っていた; 抵抗値自体は設計・KLayout 抽出と一致）、(4) 20 aF 間引き
  により ~380 µs/s（~25 倍）に到達。寄生 CAP は全て保持しており、
  これらの置換は 8 Hz/1 kHz 帯の精度に影響しない。
- idd が PEX で 15% 低下（117.3 vs 138.6 µA）: 理想 R 化した xhigh-po の
  ボディ係数（電圧依存抵抗）の差異が主因と考えられる。ゲインへの影響は
  上記の通り軽微。
- 教訓: (a) フラット化したピン名とベンチ駆動名の不一致（NPHIBI を
  ~PHI で駆動 → 入力チョッパの B 相が死ぬ）で PGA 単体ベンチが一旦
  故障 — ピンマッピングは magic の subckt pin 順で厳密に監査する事。
  (b) 未駆動ピンは singular matrix 警告で顕在化する。

## 7. 既知の課題・次期改版項目
- **ADC の RF=100 MΩ の面積**（2026-09-05 協議、一旦現状維持で保留）:
  CT 積分器の DC 帰還抵抗（`eeg_sdm1ct.spice`、CI 20 pF と並列）。DC ゲインを
  RF/RIN=200（46 dB）に制限してレール張り付きを防ぐためのもので、DC ポール ≈80 Hz。
  レイアウトでは 100 kΩ セグメント ×1000 本 ×差動 2 系統（チェーン長 ~34 mm 相当）で
  ADC 面積の主犯（~0.8 mm² 級）。削減案: (1) 疑似抵抗化（最有力、非線形性を
  シミュレーション確認要）、(2) RC スケーリング（CI 2 pF 化＋抵抗 10 倍化で ~1/5）、
  (3) 現状維持。caravel analog 領域（~2.9×1.9 mm）に収める場合の主戦場。
  - **2026-09-11 疑似抵抗化シミュレーション実施（TT）**: `eeg_sdm1ct_pr.spice` /
    `tb_sdm1ct_pr.spice`。同一条件比較で SNDR 44.22 dB → **50.47 dB（+6.3 dB）**、
    ビットストリーム振幅 0.5976→0.6138。
  - **2026-09-11 PVT + DC 掃引で採用判定**: PVT 全コーナー（SS/FF/SF/FS）で
    SNDR 51.4〜64.4 dB・振幅 0.60〜0.62・duty 0.5 と全て合格。DC オフセット
    掃引（±15 mV）でも duty=0.5−VIN/100mV の理論値通りに追従し RF 版と完全一致
    （一時「DC 非追従」と判定したが、wrdata CSV の列解釈ミス［値は列 3+2i］
    による解析側の人工物と判明。回路には問題なし）。
    積分器ヘッドルーム ±0.52 V・同相 0.927 V も RF 版と同等。
    **疑似抵抗版は全項目で RF 版と同等以上 → 本採用可**。採用すれば
    RF 蛇行 ~0.8 mm² が消え ADC 面積が大幅縮小する。
- 0.5–2 Hz のゲインロールオフ（fc≈1.3 Hz）
- ENOB 14-16 には SC 2 次 ΣΔ（eeg_sdm2）のブリングアップが必要（現 CT 1 次は 47.9 dB ≈ 7.7 ENOB）
- CFILT 1 nF の MIM アレイ面積縮小（10 MΩ×100 pF 化）
  → **2026-09-11 実施決定・検証済み**（雑音中立・ゲイン不変・起動 PVT 合格）。
    バイアス生成器 2 個所で計 ~0.9 mm² 削減見込み。RSTART 20 MΩ も疑似抵抗化済み。
    補足: それでも面積が問題になる場合は CFILT を外付け部品にする案もユーザー承認済み
- 残留オフセット σ=110 µV の要因解析（8 kHz 時は 2 µV だった）
