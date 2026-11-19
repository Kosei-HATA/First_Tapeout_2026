# マクロの回し直し（11/19、遅延込みのゲートレベルのための SDF）

2 つのデジタルのマクロ（eeg_digital_top、eeg_adc_dig）を、10/23 のラン f2／f3 と同じ形で LibreLane に回し直した。

## なぜ回し直したか

- 遅延込み（SDF）のゲートレベルのシミュレーションに、マクロの SDF が要る。
- f2／f3 のランのフォルダ（SDF、SPEF、DEF、ODB を含む）は、外付けの SSD（mukiebi）に移してあり、手元にない（目録は `gf180/tools/archive/MANIFEST_20261113e.tsv` など）。
- 11/19 にユーザーから、回し直して作るよう言われた（返事「回し直して作ってください」）。

## 回し方

- 設定は f2／f3 と同じ `eeg_digital_top/config.yaml`、`eeg_adc_dig/config.yaml`。
- PDK は ciel の 792ef670（10/22 から同じ）、nix shell は `ws_gf180/eeg_padring`（flake.lock は 10/22 のまま）。
- `runs/` は、外付けの SSD を指す切れたリンクだった。リンクは消さずに `runs/archived_link_mukiebi` に移し、`runs/` を手元のフォルダにした（git の対象外）。
- スクリプト：`eeg_digital_top/runs/run_rerun_20261119.sh`（ターミナルのタブから回す。効率コアで回す `taskpolicy -b`）。
  - ランのタグは `f3_rerun_20261119`（eeg_adc_dig、16:07〜16:15）と `f2_rerun_20261119`（eeg_digital_top、16:15〜16:41）。どちらも exit 0。

## 元のランと同じか

目録の sha256（元のファイル）と比べた。

| ファイル | eeg_adc_dig（f3_rerun） | eeg_digital_top（f2_rerun） |
|---|---|---|
| `final/nl/*.nl.v`、`final/pnl/*.pnl.v` | 同じ（バイト単位） | 同じ（バイト単位） |
| `final/def/*.def` | 同じ | 同じ |
| `final/lib/max_ss_125C_3v00/*.lib`（STA のタイミングモデル） | 同じ | 同じ |
| `final/sdf/`（nom_tt、max_ss、min_ff） | 頭の `(DATE ...)` の行だけが違う。その行を元の時刻「Fri Oct 23 11:16:30 2026」にすると、3 つとも sha256 が目録と一致 | 同じく、元の時刻「Fri Oct 23 11:08:50 2026」で 3 つとも一致 |
| `final/spef/nom/*.spef` | 頭の `*DATE` の行だけが違う（元は「11:16:28 Friday October 23, 2026」で一致） | 同じく（元は「11:08:45 Friday October 23, 2026」） |
| `final/gds/*.gds` | sha256 は違う（GDS の頭の日時）。チップの `layout/gds/` の写しと XOR すると、24 層とも形もラベルも同じ | 同じく、24 層とも同じ |

- チップに入っているネットリストと GDS（`gf180/tapeout/layout/gds/`）は f2／f3 の最終出力と sha256 で同じ（11/19 に確かめた）。回し直しの SDF は、チップのマクロの SDF そのもの。

## 使い道

- `gf180/tapeout/rtl/run_tests.sh --gl-only` と `run_e2e.sh --gl` に `GL_SDF_CORNER` を与えると、この SDF でゲートレベルを遅延込みで回す（`gf180/tapeout/rtl/gl_sdf_prep.sh`、`tb/gl_shadow.sv`）。
