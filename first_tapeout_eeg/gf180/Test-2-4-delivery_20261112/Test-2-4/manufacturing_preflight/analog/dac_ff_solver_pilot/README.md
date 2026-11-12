# FF one solver/timestep pilot
全6run正常終了。元入力53ファイルのhash照合はinput_hash_audit.json参照。GDS・既存72frame波形に書込みなし。
条件: FF -20C, 3.3V, mismatch off、元72frame刺激の先頭14frame。観測窓frame4..12、端点補間、差分toggle数4。波形15桁保存。これは短時間pilotであり72frame全窓合格へ外挿しない。
結果fC/toggle:
gear maxstep0.5ns: +0.00004228548745
gear maxstep0.25ns: +0.00002530729196
trap maxstep0.5ns: +0.00002966104483
元72frame保存波形の同一窓: -0.000001219485558
今回3設定すべて旧0.016および暫定公称換算0.008138より小さい。ただし元波形と符号も変わり、細かな値を性能主張に使用しない。元波形との差は短縮tstopに伴う適応刻み、保存精度、積分等が混在し、原因分離未完了。最大設定差は約0.0000170fCだが数値誤差の上限を意味しない。独立simulatorではなく同一ngspiceの積分法/刻み比較。
全6runは最終時刻15.671875usに到達、returncode0。ログにm=xx on .subckt line will override multiplier m hierarchy!警告あり。モデルの一般的階層multiplier警告であるが、未監査のまま無害と断定しない。timestep too small/singular/errorは検索で検出なし。
実測時間: gear323/328秒、half485/493秒、trap280/281秒。最大2並列、約18.3分。元回路モデル・刺激電圧・温度を変更せず、solver/maxstep/記録精度/試験長のみ変更。
次の全コード試験は実用的。まずtypical27の32コードを6～12frame/コード、最大2並列で約1～2時間の初回枠を推奨（今回FF14frame実測に基づく粗い外挿）。コードごとの起動/収束で変動するためpilot4コードを先行。静止コードでもDAC_CLKを用いてラッチを更新し、最終2frameの電荷/電流安定性を確認する。settling不足なら延長し、結果不十分をPASSにしない。
INL/DNLは5bit内部DACの静的性能。16.5bit ADC保証ではない。ミスマッチ・PEX・出力compliance/参照インピーダンス・system noiseは未評価。
