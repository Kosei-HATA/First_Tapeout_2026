# Test-2-4 パッド容量抽出と次段階

## 実行結果

変更前 Test2-3 と変更後 Test-2-4 の Bondpad_5LM を実GDSから取り出し、同一条件でMagic容量抽出を実行しました。元データは変更していません。

- Magic: 8.3.664
- 技術ファイル: /foss/pdks/gf180mcuD/libs.tech/magic/gf180mcuD.tech
- 容量出力しきい値: 0.001 fF
- Test2-3 PAD–VSUBS: 111.68 fF
- Test-2-4 PAD–VSUBS: 100.70 fF
- 差: −10.98 fF、約−9.83%

スロットの充填では金属面積だけでなく周長・遮蔽も変わり、このモデルでは容量が減る推定となりました。これは単体パッドのモデル推定で、実測やファウンドリ認定精度ではありません。

## 限界

この抽出は容量のみです。周辺IO素子・配線、パッケージ、抵抗、EM/IR、ESD、機械強度、全チップ精度は評価していません。Magicログは非電気的fill層が抽出対象外であることも示しています。

元プロジェクトのpex.pyは容量抽出とLVSネット名マッピングを行いますが、Mac/nix固定パス、現在存在しないブロック別LVS DB、固定のMIM遮蔽係数・層名に依存しています。そのままの再実行を有効な全チップPEXとは扱えません。

全pad-ringデバイスLVSについてはIOプリミティブCDLはありますが、独立した全チップ/パッド接続の基準CDLが見つかっていません。抽出結果から基準を生成して自己一致させる方法は、独立LVS検証にならないため採用しません。

## 次段階

1. 設計意図に基づくpad-ring/top接続表から独立した基準CDLを構成・確認する。
2. 現在PASSしているコアLVS DBを用いて、対象窓またはコアの容量抽出とネット名対応を検証する。
3. 現PDKに対するMIMモデル/遮蔽補正と素子同値性を確認し、寄生込み機能・精度試験へ進む。
4. 抵抗/電源降下の抽出・評価フローは別に構築する。

## 再現

既存コンテナ内で:

python3 /work/Test-2-4/manufacturing_preflight/extraction/prepare_pad.py

各 test23、test24 ディレクトリーで:

/foss/tools/magic/bin/magic -dnull -noconsole -rcfile /foss/pdks/gf180mcuD/libs.tech/magic/gf180mcuD.magicrc extract.tcl > magic.log 2>&1

最後に:

python3 /work/Test-2-4/manufacturing_preflight/extraction/summarize.py

結果・入力ハッシュ・技術ファイルハッシュは extraction_summary.json に保存しています。各ディレクトリーにはパッドGDS、抽出Tcl、Magicログ、.ext、SPICEがあります。再実行前に今回結果を別フォルダーへ保全してください。

## 単体アナログIOの追加LVS調査

actual GDS内の gf180mcu_fd_io__asig_5p0 とPDKの標準GDSセルをそれぞれ同一KLayoutデッキで独立CDLと比較しました。両方とも不一致でしたが、抽出デバイスネットリストは一致し、形状差は今回のBondpad金属追加だけでした。KLayout抽出側にはPダイオードとMOSCAPのみが出力され、CDLにあるNダイオード2群がありません。

別系統Magic/NetgenではNダイオードも抽出され、3ネット・並列統合後4素子・5端子のトポロジーが一致しました。しかしMOSCAPはplaceholder/black box扱いで、ダイオードPJの単位差も未解決です。したがって「単体IOのデバイス寸法を含むLVS合格」ではありません。VDD/VSSの未接続は両基準とも同じで、任意の接続を足して合わせる操作はしていません。

詳細は io_lvs_assessment.json、io_asig_lvs、io_asig_control、io_asig_magic を参照してください。最初のMagic出力はtopサブ回路ラッパーがないため照合不能でしたが、抽出済み.extを再利用し、netlist.tclでtopラッパーを明示した結果を最終比較に用いています。初回ログも保全しました。

### 面積・周長項の整合

area_perimeter_diagnostic.jsonに、使用したnominal ngspice()スタイルの主要金属面積・周長係数と形状値を記録しました。M2～M4の周長が約3,850～3,890µmから約388～389µmへ減り、容量の周長項が減る方向と整合します。ただし遮蔽・重なり補正を省いた単純積を総容量として足し合わせることはできません。extresistによる抵抗ネットワーク抽出は未実施です。

## 追補: 単体IOの寸法検証を解決

上記のPJ単位差とMOSCAP比較範囲を追加調査しました。最新判定は io_strict_validation.json です。

- .ext のscale値0.5は1座標単位=0.005µmです。ダイオードp=21200は106µm、a=6000000は150µm²になります。面積が一致する生.ext記録を照合した上で、出力SPICEのPJだけを物理長さへ正規化した別ファイル actual_normalized.spice を作りました。GDS・PDK原本・生抽出結果は不変です。
- 公式Netgen設定はPJを比較から削除していたため、別コピー strict_setup.tcl ではPJを保持し、2%許容と並列周長加算を明示しました。パラメータ無視や強制一致は追加していません。
- 厳格設定でトポロジー一致、property errorなし。
- MOSCAP幅を10%変えた負対照は1%の比較許容で不一致を検出。PJを10%変えた負対照も2%の比較許容で不一致を検出しました。
- 独立した数値集計でも、ダイオード面積・周長・多重度とMOSCAP長さ・幅・多重度が基準に一致しました。

公式Magic定義はMOSCAPを c_length/c_width を持つプリミティブsubcircuitとして抽出し、公式ngspiceモデルもこれらの積を用いる電圧依存容量モデルです。Netgenのplaceholder警告だけを合格としたのではなく、実際の寸法不一致を検出する負対照と独立数値比較を行いました。この単体IOについては、指定したプリミティブモデルのトポロジー・幾何パラメータ比較をPASSと判定できます。

これは全pad-ring LVS、ESD電流・破壊耐量、機械的接合、全RC/性能保証ではありません。KLayout側のIO抽出問題は残りますが、限定範囲ではMagic/Netgen経路を検証できました。全体に拡張するには独立した意図接続トップCDLと他IO種の同様の検証が必要です。
