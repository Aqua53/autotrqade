import MetaTrader5 as mt5

if mt5.initialize():
    symbols = mt5.symbols_get()
    print("Daftar simbol yang mengandung emas:")
    for s in symbols:
        if "XAU" in s.name or "GOLD" in s.name:
            print(f"- {s.name}")
    mt5.shutdown()
else:
    print("MT5 belum terbuka atau tidak terdeteksi")