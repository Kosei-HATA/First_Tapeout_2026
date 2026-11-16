# 外付けの SSD に移した計算の出力（目録と道具）

内蔵ディスクの空きを保つため（10/30 から）、終わった計算の出力を外付けの SSD（ボリューム名 `mukiebi`）の `first_tapeout_archive/` に、リポジトリの中と同じ相対パスで移した。元の場所にはシンボリックリンクを残している。リンクはどれも、git が見ない run のフォルダの中にある。

- 移した中身（15,995 ファイル、102.9 GB）は GitHub にはない。生の波形、抽出、LibreLane、チップの組み立て、precheck の出力などで、結果は文書と図にまとめてあり、スクリプトから作り直せる。
- r12 のものでは、コアの LVS（`gf180/tapeout/layout/runs/chip_top/core_r12_20261113`）と precheck（`gf180/tapeout/layout/runs/precheck/runs/pre_20261113_r12`）のフォルダが SSD にだけある。どちらもログは内蔵側に残している。
- 11/16：SSD を入れ替えるので、目録と道具をここに写した（11/13〜14 の目録 6 つは、作業の一時フォルダにしかなかった）。mukiebi を外している間はリンクの先が見えず、つなぎ直せば戻る。

| ファイル | 中身 |
|---|---|
| `MANIFEST_20261030.tsv` | 10/30 に移した分（4,898 ファイル、63.6 GB）。SSD の上のパス、バイト数、更新時刻（ns）、sha256 |
| `MANIFEST_20261113.tsv`、`MANIFEST_20261113c.tsv`〜`MANIFEST_20261113g.tsv`、`MANIFEST_20261114a.tsv` | 11/13〜14 に移した分（7 回、11,097 ファイル、39.3 GB）。リポジトリからの相対パス、バイト数、sha256 |
| `move_runs.py` | 移す道具。ファイルごとに写し、ページキャッシュを通さずに読み直して sha256 を比べ、元がまだ同じときだけ元を消してリンクに替える。Bash から起こしたプロセスは SSD を読めない（EPERM）ので、ターミナルのタブから回す。移し先は環境変数 `EEG_ARCHIVE`（既定は `/Volumes/mukiebi/first_tapeout_archive`） |

使い方：`EEG_ARCHIVE=<移し先> python3 gf180/tools/archive/move_runs.py <目録> <リスト>`（リストはリポジトリからの相対パスを 1 行に 1 つ）。
