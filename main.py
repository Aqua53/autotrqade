import MetaTrader5 as mt5
from telethon import TelegramClient, events
import re
import threading
import time

# --- 1. KONFIGURASI API ---
API_ID = '36075963'
API_HASH = '8f80612a8520475f7ac55b6f9e1c4e54'
TARGET_ID = -1003308319488 

import os
signal = os.getenv('PESAN_TELEGRAM')
print(f"Sinyal diterima: {signal}")

import os

# Menangkap pesan yang dikirim dari Make.com via GitHub Actions
pesan_signal = os.getenv('PESAN_TELEGRAM')

if pesan_signal:
    print(f"Sinyal diterima: {pesan_signal}")
    # Tambahkan logika trading Anda di sini
else:
    print("Tidak ada sinyal yang diterima.")

# --- 2. KONFIGURASI TRADING ---
SYMBOL_MT5 = "XAUUSDc"
LOT_PER_LAYER = 0.02
MAGIC_NUMBER = 999111

# --- 3. PARAMETER OTOMATISASI ---
SL_PLUS_TRIGGER = 35.0  # Aktif setelah profit 35 pips
SL_PLUS_PROFIT = 1.0    # Kunci profit $1
TRAILING_START = 50.0   # Trailing aktif di 50 pips
TRAILING_DIST = 30.0    # Jarak SL membuntuti harga

client = TelegramClient('sesi_adam_bot', API_ID, API_HASH)

def check_conn():
    if not mt5.initialize(): mt5.initialize()
    return mt5.terminal_info() is not None

def get_spread():
    symbol_info = mt5.symbol_info(SYMBOL_MT5)
    return symbol_info.spread * symbol_info.point if symbol_info else 0.0

def monitor_system():
    while True:
        try:
            if not check_conn(): 
                time.sleep(1)
                continue
            
            pos = mt5.positions_get(symbol=SYMBOL_MT5, magic=MAGIC_NUMBER)
            orders = mt5.orders_get(symbol=SYMBOL_MT5, magic=MAGIC_NUMBER)
            tick = mt5.symbol_info_tick(SYMBOL_MT5)
            
            # --- FITUR AUTO CLEANUP ---
            # Menghapus sisa limit jika semua posisi aktif sudah closed
            if (not pos or len(pos) == 0) and (orders and len(orders) > 0):
                for o in orders:
                    mt5.order_send({"action": mt5.TRADE_ACTION_REMOVE, "order": o.ticket})
                print("🧹 Cleanup: Sisa pending order dihapus.")

            # --- LOGIKA TRAILING & SL+ ---
            if pos and tick:
                for p in pos:
                    cp = tick.bid if p.type == 0 else tick.ask
                    dist = abs(cp - p.price_open)
                    if SL_PLUS_TRIGGER <= dist < TRAILING_START:
                        n_sl = p.price_open + SL_PLUS_PROFIT if p.type == 0 else p.price_open - SL_PLUS_PROFIT
                        if (p.type == 0 and p.sl < n_sl) or (p.type == 1 and (p.sl > n_sl or p.sl == 0)):
                            mt5.order_send({"action": mt5.TRADE_ACTION_SLTP, "symbol": SYMBOL_MT5, "sl": round(n_sl, 3), "position": p.ticket})
                    if dist >= TRAILING_START:
                        tsl = cp - TRAILING_DIST if p.type == 0 else cp + TRAILING_DIST
                        if (p.type == 0 and tsl > p.sl) or (p.type == 1 and (tsl < p.sl or p.sl == 0)):
                            mt5.order_send({"action": mt5.TRADE_ACTION_SLTP, "symbol": SYMBOL_MT5, "sl": round(tsl, 3), "position": p.ticket})
        except: pass
        time.sleep(0.5)

@client.on(events.NewMessage(chats=TARGET_ID))
@client.on(events.MessageEdited(chats=TARGET_ID))
async def handler(event):
    msg = event.raw_text.upper()
    try:
        # Regex Fleksibel untuk menangkap data sinyal
        z = re.search(r"@\s*(\d+\.?\d*)\s*-\s*(\d+\.?\d*)", msg)
        sl_m = re.search(r"SL\D*(\d+\.?\d*)", msg)
        tp1_m = re.search(r"TP\s*1\D*(\d+\.?\d*)", msg)
        tp2_m = re.search(r"(?:TP\s*2|TP\s*MAX)\D*(\d+\.?\d*)", msg)
        
        if not z or not sl_m or not tp1_m: return
        
        p1, p2 = float(z.group(1)), float(z.group(2))
        n_sl, n_tp1 = float(sl_m.group(1)), float(tp1_m.group(1))
        n_tp2 = float(tp2_m.group(1)) if tp2_m else n_tp1
        
        # Proteksi Typo Zona
        if abs(p1 - p2) > 20: return
        if not check_conn(): return
        
        tick = mt5.symbol_info_tick(SYMBOL_MT5)
        spread = get_spread()
        step = (p1 - p2) / 3
        prices = [p1, p1-step, p1-(2*step), p2]
        side = mt5.ORDER_TYPE_BUY if "BUY" in msg else mt5.ORDER_TYPE_SELL

        # --- EKSEKUSI AWAL 4 LAYER (Default TP 1) ---
        for i, ep in enumerate(prices):
            # Akurasi TP & SL dikompensasi dengan spread broker
            adj_tp = n_tp1 - spread if side == 0 else n_tp1 + spread
            adj_sl = n_sl + spread if side == 0 else n_sl - spread

            if side == mt5.ORDER_TYPE_BUY:
                t = mt5.ORDER_TYPE_BUY if tick.ask <= ep else mt5.ORDER_TYPE_BUY_LIMIT
                p_exec = tick.ask if t == 0 else ep
            else:
                t = mt5.ORDER_TYPE_SELL if tick.bid >= ep else mt5.ORDER_TYPE_SELL_LIMIT
                p_exec = tick.bid if t == 1 else ep

            mt5.order_send({
                "action": mt5.TRADE_ACTION_DEAL if t < 2 else mt5.TRADE_ACTION_PENDING,
                "symbol": SYMBOL_MT5, "volume": LOT_PER_LAYER, "type": t, 
                "price": round(p_exec, 3), "sl": round(adj_sl, 3), "tp": round(adj_tp, 3),
                "magic": MAGIC_NUMBER, "comment": f"L{i+1}", "type_filling": mt5.ORDER_FILLING_IOC
            })
        
        # --- LOGIKA DYNAMIC TP2 (BUY & SELL) ---
        # Jeda 1.5 detik untuk stabilitas koneksi hotspot
        time.sleep(1.5) 
        active_pos = mt5.positions_get(symbol=SYMBOL_MT5, magic=MAGIC_NUMBER)
        
        if active_pos and len(active_pos) > 0:
            is_buy = (side == mt5.ORDER_TYPE_BUY)
            # Mengurutkan posisi untuk mencari layer paling ujung (paling jauh harganya)
            sorted_pos = sorted(active_pos, key=lambda x: x.price_open, reverse=not is_buy)
            last_p = sorted_pos[0] 
            
            # Hitung TP2 presisi (dikurangi spread)
            final_tp2 = n_tp2 - spread if is_buy else n_tp2 + spread
            
            # Update posisi paling ujung tersebut ke target TP 2
            mt5.order_send({
                "action": mt5.TRADE_ACTION_SLTP, "position": last_p.ticket,
                "sl": last_p.sl, "tp": round(final_tp2, 3)
            })
            print(f"🎯 Adam Bot: Layer Ujung ({'BUY' if is_buy else 'SELL'}) Ticket: {last_p.ticket} disetel ke TP 2.")

    except Exception as e: print(f"Error: {e}")

# Jalankan monitoring di thread terpisah
threading.Thread(target=monitor_system, daemon=True).start()

print("Adam Bot MT5 Ready (Versi Terbaru - Silent & Dynamic TP2)...")
client.start()
client.run_until_disconnected()