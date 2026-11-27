# 外付けの SSD に移した計算の出力（目録と道具）

内蔵ディスクの空きを保つため（10/30 から）、終わった計算の出力を外付けの SSD（ボリューム名 `mukiebi`）の `first_tapeout_archive/` に、リポジトリの中と同じ相対パスで移した。元の場所にはシンボリックリンクを残している。リンクはどれも、git が見ない run のフォルダの中にある。

- 移した中身（15,995 ファイル、102.9 GB）は GitHub にはない。生の波形、抽出、LibreLane、チップの組み立て、precheck の出力などで、結果は文書と図にまとめてあり、スクリプトから作り直せる。
- r12 のものでは、コアの LVS（`gf180/tapeout/layout/runs/chip_top/core_r12_20261113`）と precheck（`gf180/tapeout/layout/runs/precheck/runs/pre_20261113_r12`）のフォルダが SSD にだけある。どちらもログは内蔵側に残している。
- 11/16：SSD を入れ替えるので、目録と道具をここに写した（11/13〜14 の目録 6 つは、作業の一時フォルダにしかなかった）。mukiebi を外している間はリンクの先が見えず、つなぎ直せば戻る。mukiebi は中身を消さずにそのまま保管する（11/16、ユーザーの判断）。これから移す分は、入れ替えた先の SSD に置く。

| ファイル | 中身 |
|---|---|
| `MANIFEST_20261030.tsv` | 10/30 に移した分（4,898 ファイル、63.6 GB）。SSD の上のパス、バイト数、更新時刻（ns）、sha256 |
| `MANIFEST_20261113.tsv`、`MANIFEST_20261113c.tsv`〜`MANIFEST_20261113g.tsv`、`MANIFEST_20261114a.tsv` | 11/13〜14 に移した分（7 回、11,097 ファイル、39.3 GB）。リポジトリからの相対パス、バイト数、sha256 |
| `MANIFEST_20261127.tsv`、`LIST_20261127.txt` | 11/27 に外付けの SSD `mukigani`（`/Volumes/mukigani/first_tapeout_archive`、ユーザーの指定）へ移した分：r14 の全変異の試験の写し 7 個（`gf180/tapeout/rtl_r14/build/fullrun_*`、44,975 ファイル、22.71 GB）。新しい precheck のイメージ（v1.8.1）の場所を空けるため。写しの中の、リポジトリのファイルを指すリンク（各 4 本）はリンクのまま写した（目録では `symlink:<先>`） |
| `MANIFEST_20261128.tsv`、`LIST_20261128.txt` | 11/28 に `mukigani` へ移した分（2,540 ファイル、4.95 GB）：15 回目のチップの 11/27 の組み立て（r15m1、`layout/runs/chip_top_r15/r15m1_20261127`）、r15m1 のマクロのランとゲートの水準（`digital/eeg_digital_top_r15/runs/r15m1_20261127`、`gl_r15m1_20261127`、`gl_r15m1_20261127_bench8cbe4bd7`）、precheck の出力 3 つ（pre_20261119_r13、pre_20261124_r14、pre_20261127_r15）。組み直した 15 回目のチップのイメージの LVS で、docker の VM のディスク（内蔵ディスクの上で伸びる）が足りなくなったため |
| `move_runs.py` | 移す道具。ファイルごとに写し、ページキャッシュを通さずに読み直して sha256 を比べ、元がまだ同じときだけ元を消してリンクに替える。Bash から起こしたプロセスは SSD を読めない（EPERM）ので、ターミナルのタブから回す。移し先は環境変数 `EEG_ARCHIVE`（既定は `/Volumes/mukiebi/first_tapeout_archive`）。`EEG_ARCHIVE_KEEP_LINKS=1` では、中のシンボリックリンクを同じ先を指すリンクとして写す（11/27。無いときはリンクを見つけて止まる） |

使い方：`EEG_ARCHIVE=<移し先> python3 gf180/tools/archive/move_runs.py <目録> <リスト>`（リストはリポジトリからの相対パスを 1 行に 1 つ）。
