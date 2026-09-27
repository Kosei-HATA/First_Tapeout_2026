# GF180MCU 移植可能性検討（wafer.space Run 3 向けフィージビリティ）

**目的**: wafer.space GF180MCU Run 3（180 nm、gf180mcuD バリアント、フルスロット
コア 12.92 mm²）への EEG AFE SoC（チョップ PGA + CT ΣΔ ADC）移植の可否を、
(1) 寄生抽出込みシミュレーション能力の実証、(2) レイアウト面積見積もり、の
2 点で評価する。sky130 版（rev1/rev2）は凍結済み・変更なし。

## 1. PDK とツール

| 項目 | 値 |
|---|---|
| PDK | gf180mcu **gf180mcuD**（5LM + 1TM 9 kA、MIM は M4/M5 間） |
| PDK コミット | `f6eeac7dad085ffcc829ccfd721f7b4ce39edcf7`（wafer.space プロジェクトテンプレートと同一、open_pdks） |
| インストール | `ciel` v3.0.0（volare 後継）、`~/.ciel`。**volare のプレビルドには gf180mcuD が無い**（A/B/C のみ・fd_pr 欠落の版あり）ため ciel を使用 |
| ngspice | 46 (`/opt/homebrew/bin/ngspice`)、モデル: `libs.tech/ngspice/sm141064.ngspice` typical コーナー + `design.ngspice` |
| KLayout | 0.30.12 python module + gdsfactory 7.27.2（GF180 pcell が gdsfactory 経由のため python3.10 venv `gf180/tools/venv310`） |
| magic | 8.3 ローカルビルド `tools/magic/bin/magic` + PDK の `gf180mcuD.tech` |

smoke test: nfet_03v3 W=10/L=2 の DC スイープ（Vth≈0.51 V、gm/id=15.4 @ Id=21.8 µA）— `gf180/sim/tb_fet_dc.spice`、正常動作。

## 2. OTA スライスの移植

`source/trials/20260902/xschem/` の rev2 構成（`rev2_afe_chopped_full2`：RLOAD=20Meg
両段、RSET=25k、CMFB ダイオード負荷、内部チョッパ）を GF180 3.3V デバイス
（nfet_03v3/pfet_03v3）へ移植: `gf180/sim/gf180_afe_cells.spice`。
VDD=3.3 V、VCM=1.65 V。長 L 方針を維持（信号経路 L=2–4 µm、段2 ペア L=20 µm、
チョッパ TG のみ最小 L=0.28 µm）。

sky130 からの変更点（最小限）:

| 項目 | sky130 rev2 | GF180 移植 | 理由 |
|---|---|---|---|
| デバイス | sky130_fd_pr__nfet/pfet_01v8, L=4 | nfet/pfet_03v3, L=4（段1）、L=2（CMFB）、L=20（段2 ペア） | 3.3 V 電源でヘッドルーム確保 |
| 段1 入力ペア | W=240 L=4 nf=24 | W=120 L=4 nf=12 | gm 同等化（電流 2 倍弱で動作） |
| 段2 NMOS | W=12 L=12 | W=4 L=20 | 段1 出力 CM≈VCM が 1.8→3.3 V 系で上がるため弱体化（段2 電流を ~21 µA に抑制） |
| RZ | 20k | **80k** | LHP ゼロを ~200 kHz へ移し PM(β=1/32) を 74°→104° に改善 |
| RSET | 25k | 40k | テール電流 ~55 µA（段1 片側 ~28 µA）に調整 |

### 測定結果（TT 27 °C、ベンチは sky130 と同構造: `gf180/sim/tb_ac_ol.spice`, `tb_noise.spice`, `tb_f1k8.spice`）

| 指標 | sky130 rev2 (実測値) | GF180 (本検討) | 備考 |
|---|---|---|---|
| オープンループ DC ゲイン | 65.4 dB (vr) | **68.4 dB** | タスク参照値 77.6 dB は docs 上の rev1/rev2 ベンチでは再現せず（rev1 v0=58.6 dB、rev2 vr=65.4 dB が確認できた値） |
| ループ帯域 GBW | 3.16 MHz | 8.4 MHz（OL UGF、RZ ゼロで押し上げ）/ ループ交叉 178 kHz @β=1/32 | 同ポスト処理 |
| PM @β=1/32 | 88.8° | **104.4°** | RZ=80k 効果。β=1/8 でも 87.8° |
| 閉ループゲイン (x32) | 31.9 | **31.96** | AC（frozen chopper） |
| 8 Hz 過渡ゲイン (x32, チョップ 1 kHz) | 31.7（実測 6.32 mV/200 µV） | **31.89**（6.377 mV、LS-fit skip 0.5 s） | `tb_f1k8` 1.536 s 実チョップ過渡 |
| ノイズ @1 kHz（出力） | 417.7 nV/√Hz (rev2 vr) / 2057.5 (rev1 v0) | **1295 nV/√Hz** | |
| 入力換算 @10 Hz / @1 kHz | 〜 / 13 nV/√Hz | **378 / 40.5 nV/√Hz** | ÷32 |
| 帯域内ノイズ指標（1 kHz 密度×√100 Hz、0.5–100 Hz） | 0.130 µVrms (rev2) / 0.644 (rev1) | **0.405 µVrms** | 仕様 1.0 µVrms に対し 2.5x マージン |
| idd（OP / 過渡平均、OTA のみ） | 69.3 µA @1.8 V | 165.7 / 166.8 µA @3.3 V | 電力 125 µW→550 µW || 出力 CM（閉ループ過渡） | 0.92 V（≒VCM 0.9） | 2.165 V（VCM_REF=1.65 に対し +0.5 V） | CMFB ダイオード負荷比の再調整が必要（リスク 8 参照） |

ノイズ内訳（1 kHz、デバイス別 onoise）: 段1 入力ペア XM1/2 が 64%（837 nV）、
段1 負荷 XM3/4 が 26%。**GF180 nfet_03v3 の 1/f ノイズが支配的**で、
sky130 01v8（低 1/f で有名）+ W=240·L=4（960 µm²/ペア）には面積を 480 µm² へ
増やしても届かない。改善余地: (a) 入力ペア面積のさらなる増加、
(b) PMOS 入力ペア化（gf180 の pfet は一般に KF が小さい—要検証）、
(c) fchop 引き上げ（8 kHz: 実測 8 kHz で 603.6 nV/√Hz = 1 kHz の半分）。
いずれにせよ現状で仕様（1.0 µVrms）は満たす。

## 3. 寄生抽出込みシミュレーション（PEX 能力の実証）— 達成（route a）

テストレイアウト `gf180/gds/gf180_pex_test.gds`（生成: `gf180/klayout/gen_pex_test.py`）:
- nfet_03v3 pcell（W=10 L=2 nf=1）— D/S/G ラベル付き
- cap_mim pcell（MIM-B、metal_level=M5、20×20 µm）— CT/CB ラベル
- 200 µm × 0.4 µm の metal1 長配線（意図的に大きな寄生）

フロー: KLayout pcell → GDS → magic（gf180mcuD.tech）で `extract all` +
`ext2spice lvs`（`gf180/pex/extract_pex_test.tcl`）→ **sky130 と同じ
`scripts/pex/ext2pex.py` を無改造で**寄生 CAP アノテート
（`--top GF180_PEX_TEST --pins "D S G SUB"`）→ フラット PEX ネットリスト
`gf180/pex/gf180_pex_test_pex.spice`（2 デバイス + 10 寄生 CAP:
基板 27.7 fF + 結合 1.8 fF）。

検証ベンチ `gf180/sim/tb_pex_demo.spice`: PEX 版と寄生無し参照版を同一回路
（RD=100k 負荷の共通ソース、ドレインに抽出 MIM 815 fF）で同時 AC 解析。

- DC 動作点: 両者完全一致（V(D)=0.1673 V、Id=31.3 µA）— PEX で op が壊れない
- 抽出 MIM 容量: 815 fF（20×20 µm² → **2.04 fF/µm²**、PDK モデル通り）
- 長配線寄生: 18.18 fF（200 µm m1 → 0.227 fF/µm² 相当、fringe 込みで妥当）
- ドレイン −3 dB 帯域: PEX 22.36 MHz vs 参照 22.95 MHz（**−2.57%**、寄生 CAP
  によるシフトを定量検出）

結論: **GF180 で KLayout pcell → magic 抽出 → ngspice PEX シミュレーションの
全経路が動作する**。ext2pex.py の sky130 固有部分は MIM/抵抗の理想化
（`cap_mim_m3`→`cap_mim_2f0_m4m5` への一般化が必要）と SUBSTRATE 名のみ。

## 4. サイズ見通し

PDK 実測/公称値:
- MIM 密度: **2.04 fF/µm²**（抽出実測、M4/M5 間 MIM-B。gf180mcuD では M5=9kA 厚金属）
- ppolyf_u_high_Rs: **3 kΩ/sq**（1k/2k/3k 選択可; sky130 xhigh-po は 2 kΩ/sq）
- ppolyf_u: 350 Ω/sq、nwell 抵抗も利用可
- FET フィンガピッチ: 実測 ~2.5 µm（L=2、コンタクト間）; pcell 実測フットプリント
  は `gf180/klayout/measure_footprints.py`（例: 入力ペア 120/4 nf12 = 55.3×121.3 µm）

### コンポーネント別面積見積もり（`gf180/size_estimate.py` の出力）

| block | detail | area (mm2) |
|---|---|---|
| PGA FETs | s1 input pair nfet 120/4 nf12 x2; s1 loads pfet 48/4 nf4 x2 ... | 0.020 |
| PGA MIM caps | CIN 32p x2, CFB bank ~12p, CC 10p x2, CFILT 100p, CINT 50p | 0.138 |
| PGA poly resistors | RLOAD 20Meg x4, RCM(O) 5Meg x4, RFILT 10Meg, RZ, RSET | 0.037 |
| ADC FETs (sdm3) | 2x full2-class integrator OTA + strongarm + SR latch + DFF + DAC TGs | 0.041 |
| ADC MIM caps | sdm3: CS1/CDAC1 8p x2, CI1 4p x2, CS2 2p x2, CDAC2/CI2 4p x2, CQ 1p x2, bias filters | 0.108 |
| ADC poly resistors | RIN/RDAC 500k x4, CM loads, RFILT | 0.017 |
| clkgen analog part + level shifts | analog buffers/level shifts to pads | 0.003 |
| clkgen/misc MIM | ~60 pF | 0.034 |
| **analog subtotal** | | **0.397** |
| digital: CIC decimator (sinc3, 24b out) | 351 FF + ~1200 gates (9t5v0, 50% util) | 0.089 |
| digital: clkgen (256k->1k chop + 16k SDM) | 30 FF + ~150 gates (9t5v0, 50% util) | 0.009 |
| digital: SPI slave (regs + CIC readout, NEW) | 120 FF + ~400 gates (9t5v0, 50% util) | 0.030 |
| **digital subtotal (SPI+CIC+clkgen)** | ~501 FF + ~1750 gates | **0.129** |
| **electronics total** | | **0.526** |
| macro estimate (x2 routing/whitespace) | | 1.05 |
| macro estimate (x3 routing/whitespace) | | 1.58 |

スケーリング根拠: MIM は同密度（2 fF/µm²）で等面積。アナログ FET は
「L 大きめ」設計のため面積はプロセス最小寸法ではなく幾何で決まり、
180 nm の粗い DRC 間隔分だけ微増（pcell 実測値を直接使用）。
デジタル（SPI + CIC 24 bit sinc³ + clkgen）は gf180mcu 9t5v0（LEF 実測:
NAND2_1=14.1 µm²、DFFQ_1=79.0 µm²）で ~0.13 mm²（50% utilization）。
CIC/clkgen の RTL は `source/trials/20260902/verilog/`（`cic_decimator.sv`,
`eeg_clkgen.sv`）をプロセス非依存のまま再利用。SPI スレーブのみ新規
（§5 参照）。

### スロット適合（wafer.space Run 3、外部 I/F 込み）

| スロット | コア面積 | 判定 |
|---|---|---|
| フル | 12.92 mm² | **余裕で収まる**（見積もり 1.05–1.58 mm²、x3 でも ~12%） |
| ハーフ | 4.46 / 5.02 mm² | **収まる**（保守的 x3 見積もりでも 3 倍の余裕） |
| クォーター | 1.73 mm² | リーン版（MIM 最小化・デカップリング削減）なら可能性あり、通常構成では非現実。I/O 数は 48 本で十分（§5） |

参考: sky130 マクロ実績 1842.5×2575 µm = 4.75 mm² はボトムアップ電子部品
（~0.53 mm²）に対し 9 倍の余白/配線領域を含んでおり、GF180 でも
面積はボトルネックにならない。**スロット選択は面積ではなく価格で決められる**。

## 5. 外部インターフェース（SPI スレーブ）— 要件: `documentation/gf180_interface_req.md`

wafer.space スロットは全てユーザー領域で管理 SoC が無い（caravel との根本差）。
したがって通信手段を自前で搭載する。最小構成として **SPI スレーブ**を採用
（要件メモ 2026-09-17）。

### 機能仕様（新規 RTL、プロセス非依存 Verilog）

- **レジスタマップ（書き込み）**: ゲイン選択 x8/16/32/64（2 bit → S8/S16/S32/S64
  選択ライン）、AFE/ADC リセット RST、（将来）チョップ周波数・デシメーション設定
- **読み出し**: CIC デシメータ出力 24 bit（250 SPS、data_valid 付き）を SPI
  シフトアウト。デバッグ用に BIT（1 bit 生ビットストリーム）の GPIO 直出しも併用可
- CIC/clkgen は既存 RTL（`cic_decimator.sv`, `eeg_clkgen.sv`）を無改造再利用。
  SPI スレーブはレジスタ + 32 bit シフトレジスタ + 読み出し FSM のみの小規模
  RTL（見積もり ~120 FF + ~400 ゲート = 0.03 mm²、§4 表の digital 行）

### パッド/ピン予算

| 用途 | 本数 |
|---|---|
| SPI（SCLK/CSB/MOSI/MISO） | 4 |
| BIT/NBIT 生出力（デバッグ・高精度外部デシメ用） | 1–2 |
| 外部 256 kHz マスタクロック | 1 |
| アナログ: 電極入力 ELP/ELN、VCM_REF 等 | 3–4 |
| 電源（VDD33/VSS/VDDIO 複数本） | 4–6 |
| **合計** | **~13–17** |

Quarter スロットの 48 I/O に対し 3 分の 1 以下。**ピン数はどのスロットでも
非制約**。ESD/パッドリングは wafer.space ガイドラインに従う（カスタム
パッドリング可、デフォルトは core area 内にパッドリング）。

### クロック戦略

管理 SoC のクロック供給が無いため:

1. **基本案: 256 kHz マスタを外部パッド供給**（1 ピン）。CIC のノッチ周波数と
   チョップ 1 kHz の精度はこのクロックに直結するため、外部精度のある源が最安全
2. 代替: SPI SCLK からの分周（SCLK 停止中はチョップ/SDM も止まる制約あり）
3. 将来オプション: オンチップ発振器（GF180 オープン PDK にトリム済み
   オシレータ IP は無いため自前設計・温度/プロセス補正が課題。初回 tapeout では
   採用しない）

## 6. sdm3 ADC 移植（SC 2 次 1 bit 変調器、fs=256 kHz）

ENOB18 スタディの sdm3（`sdm3_mod.spice`：交互フェーズ古典 2 次ループ、
NTF=(1-z^-1)^2、係数 a1=d1=2, a2=0.5, d2=1）を GF180 へ移植:
`gf180/sim/gf180_sdm3.spice`（新規、sky130 ソースは無変更）。
積分器 OTA は AFE 移植と同一デバイス構成の非チョップ版
`gf180_fd_ota_full2_nc`（段1 120/4 nf12、段2 4/20 + 12/4、RSET=40k、
RZ=80k、CC=10p）。strong-arm・TG マスタスレーブ DFF・nand2・inv は
03v3 最小 L=0.28 µm で等比移植。容量値・係数は sky130 と同一
（CS1=CDAC1=8p, CI1=4p, CS2=2p, CDAC2=CI2=4p — 係数は容量比なので
プロセス非依存）。VDD=3.3 V、VCM=1.65 V、VP/VN=VCM±25 mV、
クロックは sky130 ベンチと同一タイミング（PH1/PH2 非重複 + CMPCK=late PH1）。

### ボトムアップ立ち上げ結果（TT 27 °C）

1. **積分器単体（step A、`tb_gf180_sdm3_intsettle.spice`）**: DC 入力 + BIT 固定で
   1 サイクルあたり −79.0〜−80.7 mV の一定増分（sky130 同一刺激リファレンス:
   −78.2〜−78.3 mV、**2% 以内で一致** — 係数実現は正しい）。
   サイクル末のセトリング残留は PH2 プラトー終端 270 ns で 0.53 mV
   （差動 80 mV ステップに対し 0.7%、次サイクルへのキャリーオーバー無し）。
2. **フルループ 6 ms ブリングアップ（step B、`tb_gf180_sdm3_bringup.spice`）**:
   ループ即ロック。32 Hz 準静的スイープの duty 追従誤差 max 0.0104
   （200 サイクル平滑、sky130 実測 0.010 と同等 → DC 伝達 OK、
   duty=0.5−u/100mV、デッドゾーン無し）。積分器スイング:
   O1D −0.53..+0.58 V、O2D −0.48..+0.65 V（sky130: O1D ±0.33、O2D
   −0.29/+0.63 — やや大きいが 3.3 V レールでヘッドルーム十分。
   出力 CM は CMFB オフセットにより 2.19 V）。**idd = 346.6 µA @3.3 V**
   （変調器全体: 2 積分器 OTA + コンパレータ + デジタル）。
3. **フル SNDR ラン（step C、`tb_gf180_sdm3_256k.spice`）**: 322.5 ms
   （10 ms スキップ + 32 Hz 10 サイクルコヒーレント）、save は
   `time v(BIT)` のみ、50 ns max step、読み出しは PH2 プラトー多数決
   （`scripts/sdm3_bitstream.py`、単点サンプリングは床を偽るため必須）。

### TT 測定結果（32 Hz 0.6 FS、0.5–100 Hz 帯域）

全ラン共通: 32 Hz 0.6 FS、fs=256 kHz、PH2 プラトー多数決読み出し
（`scripts/sdm3_bitstream.py` 相当の `gf180/results/analyze_sndr_fast.py`）。
ショートランは 103.75 ms（10 ms スキップ + 3 コヒーレントサイクル）、
フルランは 322.5 ms（同 10 サイクル）。

| ラン | 構成 | SNDR |
|---|---|---|
| フル 10 サイクル（baseline） | 初回ポート（W91=4u/W92=0.5u → 出力 CM 2.19 V） | **61.75 dB** |
| **フル 10 サイクル（確定）** | **CMFB 修正（W91=11u/W92=6u → CM 1.65 V）** | **69.65 dB** |
| ショート 3 サイクル | 同上（CMFB 修正）のショート推定 | 77.29 dB（実現ばらつきで楽観側） |
| ショート 3 サイクル | CMFB 修正 + CC=6p（高速化狙い） | 63.30 dB（悪化: リンギング） |
| ショート 3 サイクル | CMFB 修正 + 理想コンパレータ（動作モデル置換） | 61.23 dB（床は潰れず） |
| ショート 3 サイクル | CMFB 修正 + CMPCK 1.30→1.55 µs | 79.18 dB（ばらつき内の微増） |
| （参考）sky130 フル 10 サイクル | final ループタイミング版 | **91.68 dB** |

※ 等条件（10 サイクル）の確定改善量は **61.75 → 69.65 dB（+7.9 dB）**。
3 サイクルのショート推定は帯域内 ~9 bin の粗い測定でトーン実現依存の
ばらつきが大きく（sky130 でも変種間 92–101 dB の実績）、CMFB 修正版は
ショート 77.29 dB に対しフルでは 69.65 dB と 7.6 dB 低く出た。
診断用の A/B（コンパレータ理想化・CMPCK 遅延・CC 変更の有意性判定）
には有効だが、絶対値はフルランで確認すること。
※ 帯域内コムの高さは改善: 最強ライン −71.5 dBc（HD2 支配）→
−82.8 dBc（一様コム、HD2/HD3 非支配化）。
※ 過渡解析にはデバイスノイズが含まれないため、これらの床は全て
**決定論的**（limit-cycle トーン/非線形性）である。かつて帯域内床を
1/f ノイズ天井と結論付けた記述は、数値の一致（78 vs 79.9 dB）が
たまたまだったもので誤り — 床が CMFB 修正で +7.9 dB 動くこと自体が
ノイズ天井説の反証（ノイズ天井は回路定数の修正では動かない）。

### 根本原因解析（30 dB ギャップ）

**原因 1（確定・修正済み、等条件 +7.9 dB）: CMFB の出力 CM オフセット（リスク 8）。**
ダイオード負荷 CMFB（`gf180_cmfb_amp_dl2`）の W9 比が sky130 1.8 V 前提で、
3.3 V では平衡時 VBP が段2 PMOS 負荷の必要バイアスを大きく下回り、
ループが差動対フルスイッチ点で平衡 → 出力 CM が 2.19 V
（VCM_REF=1.65 に対し +0.54 V）に張り付いていた。スイング上端で段2
PMOS のヘッドルームが非対称に食い込み、偶数次非線形性（baseline で
HD2=64 Hz が最強 −71.5 dBc）と帯域内コム床の隆起を発生。
修正は W91 4u→11u・W92 0.5u→6u（ダイオード負荷 Vsg を必要 VBP に整合、
`tb_gf180_ota_cm.spice` のスイープで決定）: 出力 CM 1.635 V、
段1 CM 1.667 V。bring-up 再測定: duty 追従 max 0.0094（修正前
コントロール 0.0102）、O1D/O2D スイング ±0.6 V 台で bounded、
idd 346.6→304.2 µA、積分器係数 −79.45〜−79.52 mV/cycle で不変。

**残余 ~22 dB（機序同定済み・未修正）: 積分器の状態依存セトリングに
起因する limit-cycle コム。** 証拠チェーン:
- 帯域内は全バリアントで一様な k·3.2 Hz コム（単一支配スパー無し）。
  sky130 は −97 dBc 以下で急減衰するスカートだが、GF180 は −71〜−77 dBc
  （CMFB 修正後のフルランでは −83〜−85 dBc の一様コム、最強 −82.8 dBc）。
- **理想コンパレータ化でも床は潰れない（61.23 dB）**:
  `gf180_sdm3_mod_icmp`（積分器・DAC・DFF はトランジスタのまま、
  strong-arm+SR ラッチのみ動作モデル）→ strong-arm ポートは犯人ではない。
  静的特性もクリーン（±20 mV ランプ 2048 サイクルでヒステリシス
  <10–40 µV、オフセット ~0、メタステーブル無し、
  `tb_gf180_strongarm_hyst2.spice`）。
- in-loop 診断（`tb_gf180_sdm3_cmpdbg.spice`）: CMPCK エッジ時点で x2 は
  まだ ±35 mV 動いており、|x2|<1 mV の曖昧サイクルでは判定が直前状態依存
  （298 サイクル中 2 回 settled 符号と逆）。判定自体は 99.3% 正しく
  メタステーブル無しだが、「未セトリングの x2 を見て決める」ことが
  リミットサイクルを攪乱する。
- int1 の PH2 プラトーで −13 mV クリープ（80 mV ステップの 16%）と
  +26 mV の CM 回復ドリフト、サイクル末インクリメントの振幅依存
  （−79.45→−79.52 mV）を計測。ただし CC=6p の単純高速化は PM 低下の
  リンギングで 63.30 dB に悪化 → 速度とリンギングのトレードオフは
  既に際どい。CMPCK 1.55 µs 化は +1.9 dB（ばらつき内）で決定打に非ず。
- タイムステップ否定: maxstep 10 ns vs 50 ns の bring-up で duty 追従
  0.0084 vs 0.0102、50 ns 結果は統計的に信頼できる
  （ビット列差分はカオティックループの軌道分岐であり正常）。

メカニズムは sky130 自身のリミッタ（アナログ状態依存性がリミット
サイクルをトーン化）と同種だが、GF180 OTA のセトリングが弱い分だけ
強く現れている（等条件で sky130 91.68 dB vs GF180 69.65 dB、残余 22 dB。
なお残余の見え方はトーン実現で数 dB 動く）。

**残余ギャップの改善候補（優先度順、次イテレーション）:**
1. RSET 40k→25k（バイアス +16%、プラトークリープ −13→−5.3 mV、
   CC 変更と違い PM を痛めない）— 最有力。
2. CI1 増量（ENOB18 スタディの提言と同じ、int1 の per-cycle 擾乱を相対的に
   縮小）。
3. ディザ（量子化器/入力）で limit-cycle のロックを崩す。
4. アンチヒステリシス比較器は優先度低（理想比較器実験で効果無しと判明）。
5. ※ 実シリコンの熱/1/f ノイズ天井は別途存在する（ENOB18 §5–6、
   kT/C ~81 dB）が、本節の過渡解析床とは無関係。積分器 OTA チョッピングは
   実ノイズ対策としては有効だが、決定論的コムの改善策ではない。

sky130 参考値（同条件・同解析）: SNDR 91.68 dB（final ループタイミング版）、
挙動モデル天井 123 dB、帯域内は limit-cycle スカート（k*3.2 Hz、最強
−97 dBc）+ HD3 −98.9 dBc 支配。

**SS/FF コーナー**: 未実施。ENOB18 スタディのストップルールと同じ判断
（sky130 側も PVT 未実施）。上記残余改善策適用後の TT 再測定が先。

## 7. リスクリスト

1. **1/f ノイズ**: GF180 03v3 は sky130 01v8 より KF が大きい。現構成で
   0.405 µVrms（仕様 1.0、社内目標 0.15 に対し 2.7 倍超過）。チョップ周波数
   引き上げ or PMOS 入力化で対処可能だが要再検証。
2. **電力**: 166 µA @3.3 V（550 µW）は sky130 版（125 µW）の 4.4 倍。
   電流削減余地あり（ゲイン/ノイズとトレードオフ）。
3. **PEX スループット**: sky130 で必要だった高速化置換（xhigh-po→理想 R 等）
   の GF180 版チューニング（`cap_mim_2f0_m4m5` の理想化、ppolyf_u_high_Rs
   サブ circuit の式評価コスト）は未検証。フルマクロ PEX の実行時間は未知数。
4. **MIM 配置制約**: gf180mcuD では MIM は M4/M5 間のみ（M2/M3 の MIM-A は
   D バリアントの magic tech では抽出されない）。下層にデバイスを置く
   フロアプランは可能だが検証が必要。
5. **5V/6V デバイス未使用**: 電極直結部の ESD/オフセット耐性（±300 mV 電極
   オフセット）は 3.3 V 系で設計可能だが、電極保護ダイオード等の I/O 設計は
   未着手（wafer.space パッドリング `gf180mcu_fd_io` との整合が必要）。
6. **デジタルフロー未検証**: CIC/clkgen の既存 RTL はプロセス非依存で再利用可。
   SPI スレーブは新規 RTL（本検討では面積見積もりのみ、未記述）。
   合成は LibreLane + gf180mcuD（wafer.space テンプレート）で実績あり。
7. **ciel/volare 差分**: volare プレビルドに gf180mcuD 無し。ciel 運用への
   切り替え（PDK ルート `~/.ciel`）が必要。
8. **CMFB の CM オフセット**: **解決済み（2026-09-27）**。3.3 V では
   ダイオード負荷 CMFB の W9 比が sky130 1.8 V 前提で出力 CM が 2.19 V
   まで上昇していたが、W91 4u→11u・W92 0.5u→6u で出力 CM 1.635 V、
   段1 CM 1.667 V に修正（§6、sdm3 改善 +7.9 dB の主因）。
   AFE チョップ OTA（`gf180_fd_ota_chopped_full2`）側も同じ W91/W92 を
   デフォルトに持つため、次の AFE イテレーションで同様の再調整を適用すること。
9. **sdm3 ADC の SNDR**: TT 61.75 dB（初回ポート）→ CMFB 修正で 69.65 dB
   （フル 322.5 ms ランで確定）。残余 22 dB（vs sky130 91.68 dB）
   は積分器の状態依存セトリングに起因する limit-cycle コム（決定論的、
   §6）。改善候補: RSET 25k 化、CI1 増量、ディザ。
10. **外部クロック依存**: 256 kHz マスタを外部供給する構成では、ホスト側の
   クロック精度が CIC ノッチ/チョップ周波数精度を決める。オンチップ化は
   将来課題（§5 クロック戦略）。

## 8. 再現手順

```
# PDK (ciel)
gf180/tools/venv/bin/ciel enable --pdk-family gf180mcu --pdk-root ~/.ciel \
    f6eeac7dad085ffcc829ccfd721f7b4ce39edcf7
# AC/noise/op
cd gf180/sim && /opt/homebrew/bin/ngspice tb_ac_ol.spice
/opt/homebrew/bin/ngspice tb_noise.spice
/opt/homebrew/bin/ngspice tb_f1k8.spice   # 過渡（長時間）
python3 ../../scripts/lsfit_gain.py ../results/tb_afe_f1k8.csv 8 --skip 0.5
# PEX デモ
gf180/tools/venv310/bin/python gf180/klayout/gen_pex_test.py
cd gf180/pex && ../../tools/magic/bin/magic -dnull -noconsole extract_pex_test.tcl
python3 ../../scripts/pex/ext2pex.py --ext-dir . --lvs gf180_pex_test.extracted.spice \
    --out gf180_pex_test_pex.spice --top GF180_PEX_TEST --pins "D S G SUB" --min-cap 0
# (CTB ピン追加・CT->D 短絡の sed 後処理: gf180_pex_test_pex_w.spice 参照)
cd ../sim && /opt/homebrew/bin/ngspice tb_pex_demo.spice
# 面積見積もり
gf180/tools/venv310/bin/python gf180/klayout/measure_footprints.py
python3 gf180/size_estimate.py
# sdm3 ADC (TT)
cd gf180/sim && /opt/homebrew/bin/ngspice tb_gf180_sdm3_intsettle.spice   # step A (~1 min)
/opt/homebrew/bin/ngspice tb_gf180_sdm3_bringup.spice                    # step B (~12 min)
/opt/homebrew/bin/ngspice tb_gf180_sdm3_256k.spice                       # step C (~10 h)
python3 ../../scripts/sdm3_bitstream.py ../results/sdm3_256k_gf180.csv
# sdm3 根本原因解析ベンチ (2026-09-27)
/opt/homebrew/bin/ngspice tb_gf180_ota_cm.spice                          # CMFB W91/W92 スイープ (~1 min)
/opt/homebrew/bin/ngspice tb_gf180_strongarm_hyst2.spice                 # strongarm 静的ヒステリシス
/opt/homebrew/bin/ngspice tb_gf180_sdm3_cmpdbg.spice                     # in-loop 判定診断 (~5 min)
/opt/homebrew/bin/ngspice tb_gf180_sdm3_256k_cmfix_short.spice           # ショート SNDR (~2.5 h)
python3 ../results/analyze_sndr_fast.py ../results/sdm3_256k_gf180_cmfix_short.csv.gz 10
```
