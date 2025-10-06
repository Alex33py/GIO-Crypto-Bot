#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Cumulative Volume Delta (CVD) Calculator
Накопительная дельта объёмов для определения давления покупателей/продавцов
"""

import time
from typing import List, Dict, Optional
from collections import deque
from config.settings import logger
from utils.validators import DataValidator
from utils.error_logger import ErrorLogger


class CumulativeVolumeDelta:
    """
    Расчёт CVD для определения накопительного давления

    CVD растёт = преобладают покупки (BUY pressure)
    CVD падает = преобладают продажи (SELL pressure)
    """

    def __init__(self, max_history: int = 10000):
        """
        Инициализация CVD Calculator

        Args:
            max_history: Максимальное количество точек в истории
        """
        self.cvd = 0.0
        self.history = deque(maxlen=max_history)
        self.total_buy_volume = 0.0
        self.total_sell_volume = 0.0
        self.last_update = time.time()

        logger.info(f"✅ CVD Calculator инициализирован (max_history={max_history})")

    def update(self, trades: List[Dict]) -> float:
        """
        Обновить CVD на основе aggTrades

        Args:
            trades: Список сделок с полями [price, size, side, timestamp]

        Returns:
            Текущее значение CVD
        """
        try:
            # Валидация входных данных
            if not trades or not isinstance(trades, list):
                logger.warning("⚠️ Невалидные trades для CVD")
                return self.cvd

            # Обрабатываем каждую сделку
            for trade in trades:
                try:
                    side = trade.get("side", "").upper()
                    size = float(trade.get("size", 0))

                    if side == "BUY":
                        self.cvd += size
                        self.total_buy_volume += size
                    elif side == "SELL":
                        self.cvd -= size
                        self.total_sell_volume += size
                    else:
                        logger.warning(f"⚠️ Неизвестная сторона сделки: {side}")

                except (ValueError, TypeError) as e:
                    logger.warning(f"⚠️ Ошибка обработки trade: {e}")
                    continue

            # Сохраняем в историю
            self.history.append({
                "timestamp": time.time(),
                "cvd": self.cvd,
                "buy_volume": self.total_buy_volume,
                "sell_volume": self.total_sell_volume
            })

            self.last_update = time.time()

            logger.debug(
                f"📊 CVD обновлён: {self.cvd:,.2f} "
                f"(+{self.total_buy_volume:,.2f} / -{self.total_sell_volume:,.2f})"
            )

            return self.cvd

        except Exception as e:
            ErrorLogger.log_calculation_error(
                calculation_name="CVD Update",
                input_data={"trades_count": len(trades) if trades else 0},
                error=e
            )
            return self.cvd

    def get_trend(self, lookback_periods: int = 10) -> str:
        """
        Определить тренд CVD

        Args:
            lookback_periods: Количество последних периодов для анализа

        Returns:
            "BULLISH", "BEARISH" или "NEUTRAL"
        """
        try:
            if len(self.history) < lookback_periods:
                return "NEUTRAL"

            recent = list(self.history)[-lookback_periods:]

            # Проверка на последовательный рост
            if all(recent[i]["cvd"] > recent[i-1]["cvd"] for i in range(1, len(recent))):
                return "BULLISH"

            # Проверка на последовательное падение
            elif all(recent[i]["cvd"] < recent[i-1]["cvd"] for i in range(1, len(recent))):
                return "BEARISH"

            # Проверка средней дельты
            else:
                cvd_values = [p["cvd"] for p in recent]
                avg_delta = (cvd_values[-1] - cvd_values[0]) / len(cvd_values)

                if avg_delta > 0:
                    return "BULLISH"
                elif avg_delta < 0:
                    return "BEARISH"
                else:
                    return "NEUTRAL"

        except Exception as e:
            logger.error(f"❌ Ошибка определения CVD тренда: {e}")
            return "NEUTRAL"

    def get_divergence(self, price_history: List[float]) -> Optional[str]:
        """
        Определить дивергенцию между CVD и ценой

        Бычья дивергенция: цена падает, CVD растёт → разворот вверх
        Медвежья дивергенция: цена растёт, CVD падает → разворот вниз

        Args:
            price_history: История цен (соответствует истории CVD)

        Returns:
            "BULLISH_DIV", "BEARISH_DIV" или None
        """
        try:
            if len(self.history) < 20 or len(price_history) < 20:
                return None

            # Последние 20 значений
            recent_cvd = [p["cvd"] for p in list(self.history)[-20:]]
            recent_prices = price_history[-20:]

            # Тренды
            cvd_trend = recent_cvd[-1] - recent_cvd[0]
            price_trend = recent_prices[-1] - recent_prices[0]

            # Бычья дивергенция
            if price_trend < 0 and cvd_trend > 0:
                logger.info("📈 БЫЧЬЯ ДИВЕРГЕНЦИЯ: цена↓, CVD↑")
                return "BULLISH_DIV"

            # Медвежья дивергенция
            elif price_trend > 0 and cvd_trend < 0:
                logger.info("📉 МЕДВЕЖЬЯ ДИВЕРГЕНЦИЯ: цена↑, CVD↓")
                return "BEARISH_DIV"

            return None

        except Exception as e:
            logger.error(f"❌ Ошибка определения дивергенции: {e}")
            return None

    def get_statistics(self, last_n_seconds: int = 300) -> Dict:
        """
        Получить статистику CVD за последние N секунд

        Args:
            last_n_seconds: Временной интервал (секунды)

        Returns:
            Словарь со статистикой
        """
        try:
            now = time.time()
            cutoff = now - last_n_seconds

            recent = [p for p in self.history if p["timestamp"] >= cutoff]

            if not recent:
                return {
                    "cvd": self.cvd,
                    "trend": "NEUTRAL",
                    "buy_volume": 0,
                    "sell_volume": 0,
                    "buy_sell_ratio": 0,
                    "delta": 0
                }

            cvd_values = [p["cvd"] for p in recent]
            buy_volumes = [p["buy_volume"] for p in recent]
            sell_volumes = [p["sell_volume"] for p in recent]

            buy_vol = buy_volumes[-1] - buy_volumes[0]
            sell_vol = sell_volumes[-1] - sell_volumes[0]

            buy_sell_ratio = buy_vol / sell_vol if sell_vol > 0 else 0

            delta = cvd_values[-1] - cvd_values[0]

            trend = "BULLISH" if delta > 0 else "BEARISH" if delta < 0 else "NEUTRAL"

            return {
                "cvd": self.cvd,
                "trend": trend,
                "buy_volume": buy_vol,
                "sell_volume": sell_vol,
                "buy_sell_ratio": buy_sell_ratio,
                "delta": delta,
                "period_seconds": last_n_seconds
            }

        except Exception as e:
            logger.error(f"❌ Ошибка расчёта CVD статистики: {e}")
            return {
                "cvd": self.cvd,
                "trend": "NEUTRAL",
                "buy_volume": 0,
                "sell_volume": 0,
                "buy_sell_ratio": 0,
                "delta": 0
            }

    def reset(self):
        """Сбросить CVD (для тестирования или новых сессий)"""
        self.cvd = 0.0
        self.history.clear()
        self.total_buy_volume = 0.0
        self.total_sell_volume = 0.0
        logger.info("🔄 CVD сброшен")

    def get_current_cvd(self) -> float:
        """Получить текущее значение CVD"""
        return self.cvd

    def get_buy_sell_ratio(self) -> float:
        """Получить соотношение покупок к продажам"""
        if self.total_sell_volume == 0:
            return 0
        return self.total_buy_volume / self.total_sell_volume


# Экспорт
__all__ = ['CumulativeVolumeDelta']
