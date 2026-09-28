import asyncio
import logging
import time
import math
from datetime import datetime
import ccxt.async_support as ccxt
import torch

from risk import KamatosKamatEngine
from memory import ThoughtRepository
from strategies import StrategyManager
import credentials

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("CryptoQuantArchitect")

def calc_zscore(val, lst):
    if len(lst) < 2: return 0.0
    mean = sum(lst) / len(lst)
    variance = sum((x - mean) ** 2 for x in lst) / len(lst)
    std = math.sqrt(variance)
    if std == 0: return 0.0
    return (val - mean) / std

class BinanceHFTBot:
    def __init__(self):
        self.risk_engine = KamatosKamatEngine()
        self.memory = ThoughtRepository(input_features=10)
        self.strategy_manager = StrategyManager()
        self.memory.load_brain()
        self.last_hf_upload = time.time()
        self.active_trades = 0
        self.last_trade_times = {}
        
        self.exchange = ccxt.binanceusdm({
            'apiKey': credentials.BINANCE_API_KEY,
            'secret': credentials.BINANCE_SECRET_KEY,
            'enableRateLimit': True,
            'options': {
                'defaultType': 'future',
            }
        })
        
        if getattr(credentials, 'USE_TESTNET', True):
            self.exchange.set_sandbox_mode(True)
            logger.info("Binance Connected in TESTNET (Safe) Mode.")
        else:
            logger.warning("Binance Connected in LIVE REAL-MONEY Mode.")

    async def get_crypto_features(self, symbol):
        try:
            rates = await self.exchange.fetch_ohlcv(symbol, timeframe='1m', limit=50)
            if not rates or len(rates) < 50: return None
            
            orderbook = await self.exchange.fetch_order_book(symbol, limit=5)
            if not orderbook['bids'] or not orderbook['asks']: return None
            
            bid = orderbook['bids'][0][0]
            ask = orderbook['asks'][0][0]
            
            closes = [r[4] for r in rates]
            highs = [r[2] for r in rates]
            lows = [r[3] for r in rates]
            
            # Kinetic Velocity Math
            z_close = calc_zscore(closes[-1], closes[-20:])
            mom3 = (closes[-1] - closes[-3])
            moments3 = [(closes[i] - closes[i-3]) for i in range(3, len(closes))]
            z_mom3 = calc_zscore(mom3, moments3)
            mom5 = (closes[-1] - closes[-5])
            moments5 = [(closes[i] - closes[i-5]) for i in range(5, len(closes))]
            z_mom5 = calc_zscore(mom5, moments5)
            
            current_vol = highs[-1] - lows[-1]
            vols = [(highs[i] - lows[i]) for i in range(len(closes))]
            z_vol = calc_zscore(current_vol, vols)
            
            ma10 = sum(closes[-10:]) / 10
            ma20 = sum(closes[-20:]) / 20
            z_ma10_gap = calc_zscore(closes[-1] - ma10, [(closes[i] - (sum(closes[i-10:i])/10)) for i in range(10, len(closes))])
            z_ma20_gap = calc_zscore(closes[-1] - ma20, [(closes[i] - (sum(closes[i-20:i])/20)) for i in range(20, len(closes))])
            
            current_spread = ask - bid
            z_spread = current_spread / closes[-1] * 1000
            tick_gap = (ask - closes[-1]) / closes[-1] * 1000
            hour = datetime.now().hour / 24.0
            
            features = [z_close, z_mom3, z_mom5, z_vol, z_ma10_gap, z_ma20_gap, z_spread, tick_gap, hour, 0.5]
            return features, ask, bid
            
        except Exception as e:
            # logger.error(f"Error fetching data for {symbol}: {e}")
            return None

    async def _execute_crypto_lifecycle(self, symbol, current_risk_multiplier, ask, bid, direction, prob, features):
        self.active_trades += 1
        try:
            # Calculate dynamic lot size (In Crypto amounts, e.g. 0.001 BTC)
            # Leverage is assumed to be set manually on the account.
            price = ask if direction == 1 else bid
            trade_value_usd = current_risk_multiplier * 10 # Assuming 10x leverage for position sizing
            amount = trade_value_usd / price
            
            # Fetch market step size to round amount correctly
            markets = await self.exchange.load_markets()
            market = markets.get(symbol)
            if market:
                amount = self.exchange.amount_to_precision(symbol, amount)
            
            side = 'buy' if direction == 1 else 'sell'
            
            logger.info(f"CRYPTO ORDER: {symbol} {side.upper()} Amount: {amount} (Prob: {prob:.2f})")
            
            try:
                order = await self.exchange.create_order(symbol, 'market', side, amount)
            except Exception as e:
                logger.error(f"Order failed: {e}")
                self.risk_engine.position_closed(0)
                return
                
            # MICRO-SCALPING TARGETS
            max_loss = - (current_risk_multiplier * 0.80) 
            target_profit = current_risk_multiplier * 0.20 
            
            logger.info(f"--- [BINANCE KAMATOS KAMAT] Széria: {self.risk_engine.current_streak} | Tét: ${current_risk_multiplier:.2f} | Célár: +${target_profit:.2f} ---")
            
            self.last_trade_times[symbol] = time.time() 
            
            hold_time = 0
            realized_pnl = 0.0
            highest_profit = 0.0
            
            while hold_time < 300: 
                await asyncio.sleep(1) 
                hold_time += 1
                
                try:
                    # Fetch open positions to check PnL
                    positions = await self.exchange.fetch_positions(symbols=[symbol])
                    pos = [p for p in positions if float(p['contracts']) > 0]
                    
                    if pos:
                        pnl = float(pos[0]['unrealizedPnl'])
                        if pnl > highest_profit:
                            highest_profit = pnl
                            
                        # Break-Even
                        if highest_profit > current_risk_multiplier * 0.10: 
                            max_loss = current_risk_multiplier * 0.05       
                            
                        if pnl >= target_profit:
                            logger.info(f"Target hit on {symbol}: +${pnl:.2f}")
                            break 
                        if pnl <= max_loss:
                            logger.info(f"Stop hit on {symbol}: ${pnl:.2f}")
                            break 
                    else:
                        break
                except Exception as e:
                    pass
                    
            # Close Position
            close_side = 'sell' if direction == 1 else 'buy'
            try:
                # Close entirely
                await self.exchange.create_order(symbol, 'market', close_side, amount, params={"reduceOnly": True})
            except Exception as e:
                logger.error(f"Close failed: {e}")
                
            # Finalize PnL for Kamatos Kamat
            final_pnl = highest_profit if highest_profit >= target_profit else max_loss
            
            logger.info(f"Crypto Trade Closed on {symbol}. Est PnL: ${final_pnl:.2f}")
            
            trade_success = 1 if final_pnl > 0 else 0
            r_multiple = final_pnl / current_risk_multiplier if current_risk_multiplier > 0 else 0
            
            self.memory.train_on_outcome(features, trade_success, r_multiple)
            self.risk_engine.position_closed(final_pnl)
            
            # Update Dashboard JSON for Hugging Face Space
            try:
                import json
                with open("dashboard_data.json", "w") as f:
                    json.dump({
                        "total_pnl": self.risk_engine.get_current_risk() - 25.0, # Approximate profit
                        "streak": self.risk_engine.current_streak,
                        "risk": self.risk_engine.get_current_risk()
                    }, f)
            except Exception: pass
            
        finally:
            self.active_trades -= 1

    async def continuous_execution_loop(self, symbols: list):
        logger.info("=== STARTING BINANCE CRYPTO KINETIC VELOCITY BOT ===")
        
        # Init dashboard
        try:
            import json
            with open("dashboard_data.json", "w") as f:
                json.dump({"total_pnl": 0.0, "streak": 0, "risk": 25.0}, f)
        except Exception: pass
        
        while True:
            try:
                active_strat = self.strategy_manager.evaluate_tournament()
                
                leaderboard = []
                for symbol in symbols:
                    data = await self.get_crypto_features(symbol)
                    if not data: continue
                    features, ask, bid = data
                    
                    kinetic_velocity = features[1] 
                    leaderboard.append((symbol, kinetic_velocity, features, ask, bid))
                
                if not leaderboard:
                    await asyncio.sleep(2)
                    continue
                    
                leaderboard.sort(key=lambda x: x[1])
                weakest = leaderboard[0]
                strongest = leaderboard[-1]
                
                candidates = []
                # Crypto sensitivity
                if strongest[1] > 0.5: 
                    candidates.append((strongest, 1))  
                if weakest[1] < -0.5: 
                    candidates.append((weakest, -1)) 
                    
                for (sym, vel, feat, ask, bid), direction in candidates:
                    if sym in self.last_trade_times and time.time() - self.last_trade_times[sym] < 5:
                        continue
                        
                    prob = self.memory.predict(feat) 
                    
                    if self.risk_engine.can_open_position() and self.active_trades < 10: # Max 10 crypto grids
                        current_risk = self.risk_engine.get_current_risk()
                        self.risk_engine.position_opened()
                        asyncio.create_task(self._execute_crypto_lifecycle(sym, current_risk, ask, bid, direction, prob, feat))
                        
                await asyncio.sleep(2) 
                    
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Loop error: {e}")
                await asyncio.sleep(2)
                
    async def cleanup(self):
        await self.exchange.close()

async def run_bot_async():
    bot = BinanceHFTBot()
    # Binance USD-M Futures format
    symbols = ["BTC/USDT", "ETH/USDT", "SOL/USDT", "DOGE/USDT", "BNB/USDT"]
    try:
        await bot.continuous_execution_loop(symbols)
    finally:
        await bot.cleanup()

def start_bot_sync():
    asyncio.run(run_bot_async())

if __name__ == "__main__":
    start_bot_sync()

