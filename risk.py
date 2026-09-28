import logging

logger = logging.getLogger(__name__)

class KamatosKamatEngine:
    """
    Win-Streak Compounding State Machine (Kamatos Kamat Engine)
    Scales risk exponentially on win streaks, and hard resets on any loss.
    """
    def __init__(self, base_risk: float = 25.0, max_positions: int = 30):
        self.base_risk = base_risk
        self.max_positions = max_positions
        self.current_streak = 0
        self.open_positions = 0

    def record_trade_result(self, pnl: float):
        """
        The Hard Reset Trigger: Instantly wipe streak on net loss.
        """
        if pnl > 0:
            self.current_streak += 1
            logger.info(f"Trade WON. Kamatos Kamat streak increased to {self.current_streak}.")
        else:
            self.current_streak = 0
            logger.info("Trade LOST. Kamatos Kamat hard reset triggered. Streak = 0.")

    def get_current_risk(self) -> float:
        """
        The Progression Array implementation.
        """
        if self.current_streak == 0:
            return self.base_risk
        elif self.current_streak == 1:
            return self.base_risk * 1.25
        elif self.current_streak == 2:
            return self.base_risk * 1.50
        elif self.current_streak == 3:
            return self.base_risk * 2.00
        else:
            # Accelerate stepwise for 4+ wins
            return self.base_risk * (2.0 + 0.5 * (self.current_streak - 3))

    def can_open_position(self) -> bool:
        """
        Strict risk throttle capping max simultaneous open trades.
        """
        return self.open_positions < self.max_positions

    def position_opened(self):
        self.open_positions += 1

    def position_closed(self, pnl: float):
        self.open_positions = max(0, self.open_positions - 1)
        self.record_trade_result(pnl)
