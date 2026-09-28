import asyncio
import logging
import time
import math
from datetime import datetime
import MetaTrader5 as mt5
import torch

from risk import KamatosKamatEngine
from memory import ThoughtRepository
from strategies import StrategyManager

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("QuantitativeSystemsArchitect")

MT5_AVAILABLE = True

def calc_zscore(val, lst):
    if len(lst) < 2: return 0.0
    mean = sum(lst) / len(lst)
    variance = sum((x - mean) ** 2 for x in lst) / len(lst)
    std = math.sqrt(variance)
    if std == 0: return 0.0
    return (val - mean) / std

class HFTScalperBot:
    def __init__(self):
        self.risk_engine = KamatosKamatEngine()
        self.memory = ThoughtRepository(input_features=10)
        self.strategy_manager = StrategyManager()
        self.memory.load_brain()
        self.last_hf_upload = time.time()
        self.active_trades = 0
        self.last_trade_times = {}

        if not mt5.initialize():
            logger.error("MT5 init failed")
            global MT5_AVAILABLE
            MT5_AVAILABLE = False
        else:
            logger.info("MT5 connected for VETERAN QUANTITATIVE HFT SCALPING.")

    def get_hft_market_features(self, symbol):
        rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M1, 0, 50)
        if rates is None or len(rates) < 50:
            return None
        
        tick = mt5.symbol_info_tick(symbol)
        s_info = mt5.symbol_info(symbol)
        if not tick or not s_info: return None
        
        # Loose Spread Filter
        spread_points = (tick.ask - tick.bid) / s_info.point
        if spread_points > 50: 
            return None
            
        closes = [r['close'] for r in rates]
        highs = [r['high'] for r in rates]
        lows = [r['low'] for r in rates]
        
        # --- 35-YEAR VETERAN MATHEMATICAL FEATURES (STATISTICAL Z-SCORES) ---
        try:
            # How unusual is the current price compared to the last 20 minutes?
            z_close = calc_zscore(closes[-1], closes[-20:])
            
            # How unusual is the momentum?
            mom3 = (closes[-1] - closes[-3])
            moments3 = [(closes[i] - closes[i-3]) for i in range(3, len(closes))]
            z_mom3 = calc_zscore(mom3, moments3)
            
            mom5 = (closes[-1] - closes[-5])
            moments5 = [(closes[i] - closes[i-5]) for i in range(5, len(closes))]
            z_mom5 = calc_zscore(mom5, moments5)
            
            # How unusual is the current volatility?
            current_vol = highs[-1] - lows[-1]
            vols = [(highs[i] - lows[i]) for i in range(len(closes))]
            z_vol = calc_zscore(current_vol, vols)
            
            # Distance from moving averages (Normalized)
            ma10 = sum(closes[-10:]) / 10
            ma20 = sum(closes[-20:]) / 20
            z_ma10_gap = calc_zscore(closes[-1] - ma10, [(closes[i] - (sum(closes[i-10:i])/10)) for i in range(10, len(closes))])
            z_ma20_gap = calc_zscore(closes[-1] - ma20, [(closes[i] - (sum(closes[i-20:i])/20)) for i in range(20, len(closes))])
            
            # Tick and Spread math
            current_spread = tick.ask - tick.bid
            z_spread = current_spread / closes[-1] * 1000 # Normalized scale
            
            last_price = tick.last if tick.last > 0 else tick.ask
            tick_gap = (last_price - closes[-1]) / closes[-1] * 1000
            
            hour = datetime.now().hour / 24.0
            
        except Exception:
            return None
            
        # These features are mathematically sound Z-Scores (usually between -3.0 and +3.0)
        # This is exactly what Institutional Quants feed into Neural Networks.
        features = [z_close, z_mom3, z_mom5, z_vol, z_ma10_gap, z_ma20_gap, z_spread, tick_gap, hour, 0.5]
        return features, tick

    async def _execute_hft_lifecycle(self, symbol, current_risk_multiplier, tick, direction, prob, features):
        self.active_trades += 1
        try:
            lot_size = max(0.01, round(0.01 * current_risk_multiplier, 2))
            order_type = mt5.ORDER_TYPE_BUY if direction == 1 else mt5.ORDER_TYPE_SELL
            price = tick.ask if direction == 1 else tick.bid
            
            request = {
                "action": mt5.TRADE_ACTION_DEAL,
                "symbol": symbol,
                "volume": lot_size,
                "type": order_type,
                "price": price,
                "deviation": 20,
                "magic": 999999,
                "comment": "Veteran Quant",
                "type_time": mt5.ORDER_TIME_GTC,
            }
            
            result = None
            for fill_mode in [mt5.ORDER_FILLING_IOC, mt5.ORDER_FILLING_FOK, mt5.ORDER_FILLING_RETURN]:
                request["type_filling"] = fill_mode
                result = mt5.order_send(request)
                if result and result.retcode == mt5.TRADE_RETCODE_DONE:
                    break
                    
            if result and result.retcode == mt5.TRADE_RETCODE_DONE:
                ticket = result.order
                
                # MICRO-SCALPING TARGETS (Given breathing room against XAUUSD spread)
                max_loss = - (current_risk_multiplier * 0.80)  # -$20.00 base stop (allows price to move beyond the spread)
                target_profit = current_risk_multiplier * 0.20 # +$5.00 base target
                
                logger.info(f"--- [KAMATOS KAMAT] Széria: {self.risk_engine.current_streak} | Tét: ${current_risk_multiplier:.2f} | Lot: {lot_size} | Célár: +${target_profit:.2f} ---")
                logger.info(f"QUANT ORDER: {symbol} {'BUY' if direction==1 else 'SELL'} (Prob: {prob:.2f})")
                
                self.last_trade_times[symbol] = time.time() # Start cooldown
                
                hold_time = 0
                realized_pnl = 0.0
                highest_profit = 0.0
                
                while hold_time < 300: 
                    await asyncio.sleep(0.5) 
                    hold_time += 0.5
                    
                    pos = mt5.positions_get(ticket=ticket)
                    if pos and len(pos) > 0:
                        realized_pnl = pos[0].profit
                        
                        if realized_pnl > highest_profit:
                            highest_profit = realized_pnl
                            
                        # Extremely aggressive Break-Even
                        if highest_profit > current_risk_multiplier * 0.10: # +$2.50
                            max_loss = current_risk_multiplier * 0.05       # +$1.25
                            
                        if realized_pnl >= target_profit:
                            break 
                        if realized_pnl <= max_loss:
                            break 
                    else:
                        break
                        
                close_tick = mt5.symbol_info_tick(symbol)
                if close_tick:
                    close_req = {
                        "action": mt5.TRADE_ACTION_DEAL,
                        "symbol": symbol,
                        "volume": lot_size,
                        "type": mt5.ORDER_TYPE_SELL if direction == 1 else mt5.ORDER_TYPE_BUY,
                        "position": ticket,
                        "price": close_tick.bid if direction == 1 else close_tick.ask,
                        "deviation": 20,
                        "magic": 999999,
                        "comment": "Quant Close",
                        "type_time": mt5.ORDER_TIME_GTC,
                    }
                    for fill_mode in [mt5.ORDER_FILLING_IOC, mt5.ORDER_FILLING_FOK, mt5.ORDER_FILLING_RETURN]:
                        close_req["type_filling"] = fill_mode
                        c_res = mt5.order_send(close_req)
                        if c_res and c_res.retcode == mt5.TRADE_RETCODE_DONE:
                            break
                
                await asyncio.sleep(0.5)
                history = mt5.history_deals_get(position=ticket)
                if history:
                    realized_pnl = sum([h.profit for h in history])
                    
                logger.info(f"Quant Trade Closed on {symbol}. PnL: ${realized_pnl:.2f}")
                
                trade_success = 1 if realized_pnl > 0 else 0
                r_multiple = realized_pnl / current_risk_multiplier if current_risk_multiplier > 0 else 0
                
                self.memory.train_on_outcome(features, trade_success, r_multiple)
                self.risk_engine.position_closed(realized_pnl)
            else:
                logger.error(f"MT5 Order Failed: {result.comment if result else 'Unknown'}")
                self.risk_engine.position_closed(0) 
        finally:
            self.active_trades -= 1

    async def continuous_execution_loop(self, symbols: list):
        logger.info("=== STARTING CROSS-ASSET KINETIC VELOCITY BOT ===")
        
        while True:
            try:
                active_strat = self.strategy_manager.evaluate_tournament()
                
                # 1. BATCH ANALYZE ALL SYMBOLS (The "Other Perspective")
                leaderboard = []
                for symbol in symbols:
                    if not MT5_AVAILABLE: continue
                    data = self.get_hft_market_features(symbol)
                    if not data: continue
                    features, tick = data
                    
                    # features[1] is the mathematically pure Z-Score of short-term momentum
                    kinetic_velocity = features[1] 
                    leaderboard.append((symbol, kinetic_velocity, features, tick))
                
                if not leaderboard:
                    await asyncio.sleep(1)
                    continue
                    
                # 2. RANK THEM (Find the absolute strongest and weakest right now)
                leaderboard.sort(key=lambda x: x[1])
                weakest = leaderboard[0]
                strongest = leaderboard[-1]
                
                candidates = []
                # Extreme high-frequency sensitivity (Fire on the slightest momentum)
                if strongest[1] > 0.2: 
                    candidates.append((strongest, 1))  # BUY the strongest
                if weakest[1] < -0.2: 
                    candidates.append((weakest, -1)) # SELL the weakest
                    
                for (sym, vel, feat, tick), direction in candidates:
                    # Only a 2 second cooldown! Gépágyú mód.
                    if sym in self.last_trade_times and time.time() - self.last_trade_times[sym] < 2:
                        continue
                        
                    prob = self.memory.predict(feat) # We still use AI to log and learn!
                    
                    t_info = mt5.terminal_info()
                    if t_info:
                        import os
                        hud_dir = os.path.join(t_info.data_path, "MQL5", "Files")
                        os.makedirs(hud_dir, exist_ok=True)
                        hud_path = os.path.join(hud_dir, "kamatos_hud.txt")
                        try:
                            vang_p = tick.ask + ((vel) * (tick.ask * 0.005))
                            with open(hud_path, "w") as f:
                                f.write(f"KINETIC_VELOCITY\n{self.risk_engine.current_streak}\n{self.risk_engine.get_current_risk():.2f}\n{self.active_trades}/30\n{vel:.2f}\n{vang_p:.5f}\n")
                        except Exception: pass
                    
                    if self.risk_engine.can_open_position() and self.active_trades < 30:
                        current_risk = self.risk_engine.get_current_risk()
                        self.risk_engine.position_opened()
                        asyncio.create_task(self._execute_hft_lifecycle(sym, current_risk, tick, direction, prob, feat))
                        
                await asyncio.sleep(1) 
                
                if time.time() - self.last_hf_upload > 300:
                    self.memory.save_brain()
                    self.last_hf_upload = time.time()
                    
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Loop error: {e}")
                await asyncio.sleep(1)

async def run():
    bot = HFTScalperBot()
    symbols = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "XAUUSD", "NAS100", "US30", "EURUSD", "GBPJPY"]
    await bot.continuous_execution_loop(symbols)

if __name__ == "__main__":
    asyncio.run(run())
