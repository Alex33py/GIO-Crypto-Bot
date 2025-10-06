# -*- coding: utf-8 -*-
"""
Модуль определения трендов на разных таймфреймах
Использует EMA crossover и MACD для классификации
"""

import pandas as pd
import numpy as np
from typing import Dict, List, Optional

from config.settings import logger
from config.constants import TrendDirectionEnum
from utils.data_validator import DataValidator


class MultiTimeframeTrendDetector:
    """Определение трендов на 1H, 4H, 1D таймфреймах"""

    def __init__(self):
        """Инициализация detector"""
        self.timeframes = {
            '1h': {'ema_fast': 12, 'ema_slow': 26},
            '4h': {'ema_fast': 12, 'ema_slow': 26},
            '1d': {'ema_fast': 12, 'ema_slow': 26}
        }

        logger.info("✅ MultiTimeframeTrendDetector инициализирован")

    def detect_trends(
        self,
        candles_1h: pd.DataFrame,
        candles_4h: pd.DataFrame,
        candles_1d: pd.DataFrame
    ) -> Dict[str, TrendDirectionEnum]:
        """
        Определение трендов на всех таймфреймах

        Параметры:
            candles_1h: DataFrame со свечами 1H
            candles_4h: DataFrame со свечами 4H
            candles_1d: DataFrame со свечами 1D

        Возвращает:
            Словарь {timeframe: trend_direction}
        """
        try:
            trends = {}

            # Валидация данных
            candles_1h = DataValidator.clean_dataframe(candles_1h)
            candles_4h = DataValidator.clean_dataframe(candles_4h)
            candles_1d = DataValidator.clean_dataframe(candles_1d)

            # Определяем тренд для каждого ТФ
            if not candles_1h.empty:
                trends['trend_1h'] = self._detect_trend(candles_1h, '1h')
            else:
                trends['trend_1h'] = TrendDirectionEnum.NEUTRAL

            if not candles_4h.empty:
                trends['trend_4h'] = self._detect_trend(candles_4h, '4h')
            else:
                trends['trend_4h'] = TrendDirectionEnum.NEUTRAL

            if not candles_1d.empty:
                trends['trend_1d'] = self._detect_trend(candles_1d, '1d')
            else:
                trends['trend_1d'] = TrendDirectionEnum.NEUTRAL

            logger.debug(
                f"📈 Тренды: 1H={trends['trend_1h'].value}, "
                f"4H={trends['trend_4h'].value}, "
                f"1D={trends['trend_1d'].value}"
            )

            return trends

        except Exception as e:
            logger.error(f"❌ Ошибка определения трендов: {e}")
            return {
                'trend_1h': TrendDirectionEnum.NEUTRAL,
                'trend_4h': TrendDirectionEnum.NEUTRAL,
                'trend_1d': TrendDirectionEnum.NEUTRAL
            }

    def _detect_trend(
        self,
        df: pd.DataFrame,
        timeframe: str
    ) -> TrendDirectionEnum:
        """
        Определение тренда для одного таймфрейма

        Логика:
        1. Рассчитываем EMA (fast и slow)
        2. Рассчитываем MACD histogram
        3. Если EMA_fast > EMA_slow И MACD > 0 → BULLISH
        4. Если EMA_fast < EMA_slow И MACD < 0 → BEARISH
        5. Иначе → NEUTRAL
        """
        try:
            if df.empty or len(df) < 30:
                return TrendDirectionEnum.NEUTRAL

            # Параметры EMA
            params = self.timeframes.get(timeframe, {'ema_fast': 12, 'ema_slow': 26})
            ema_fast_period = params['ema_fast']
            ema_slow_period = params['ema_slow']

            # Рассчитываем EMA
            df = df.copy()
            df['ema_fast'] = df['close'].ewm(span=ema_fast_period, adjust=False).mean()
            df['ema_slow'] = df['close'].ewm(span=ema_slow_period, adjust=False).mean()

            # Рассчитываем MACD
            df['macd'] = df['ema_fast'] - df['ema_slow']
            df['macd_signal'] = df['macd'].ewm(span=9, adjust=False).mean()
            df['macd_histogram'] = df['macd'] - df['macd_signal']

            # Последние значения
            last = df.iloc[-1]

            ema_fast = last['ema_fast']
            ema_slow = last['ema_slow']
            macd_hist = last['macd_histogram']

            # Определение тренда
            if ema_fast > ema_slow and macd_hist > 0:
                return TrendDirectionEnum.BULLISH
            elif ema_fast < ema_slow and macd_hist < 0:
                return TrendDirectionEnum.BEARISH
            else:
                return TrendDirectionEnum.NEUTRAL

        except Exception as e:
            logger.warning(f"⚠️ Ошибка определения тренда для {timeframe}: {e}")
            return TrendDirectionEnum.NEUTRAL

    def calculate_trend_strength(
        self,
        df: pd.DataFrame,
        timeframe: str
    ) -> float:
        """
        Расчёт силы тренда (0.0 - 1.0)

        Логика:
        - Расстояние между EMA fast и slow
        - Величина MACD histogram
        - Консистентность направления (последние N свечей)
        """
        try:
            if df.empty or len(df) < 30:
                return 0.5

            # Рассчитываем индикаторы если их нет
            if 'ema_fast' not in df.columns:
                params = self.timeframes.get(timeframe, {'ema_fast': 12, 'ema_slow': 26})
                df = df.copy()
                df['ema_fast'] = df['close'].ewm(span=params['ema_fast'], adjust=False).mean()
                df['ema_slow'] = df['close'].ewm(span=params['ema_slow'], adjust=False).mean()
                df['macd'] = df['ema_fast'] - df['ema_slow']
                df['macd_signal'] = df['macd'].ewm(span=9, adjust=False).mean()
                df['macd_histogram'] = df['macd'] - df['macd_signal']

            last = df.iloc[-1]

            # 1. Расстояние между EMA (нормализованное)
            ema_distance = abs(last['ema_fast'] - last['ema_slow']) / last['close']
            ema_score = min(ema_distance * 100, 1.0)  # 0-1

            # 2. Величина MACD histogram (нормализованная)
            macd_magnitude = abs(last['macd_histogram']) / last['close']
            macd_score = min(macd_magnitude * 1000, 1.0)  # 0-1

            # 3. Консистентность (последние 10 свечей)
            last_10 = df.tail(10)
            bullish_count = sum(1 for _, row in last_10.iterrows() if row['ema_fast'] > row['ema_slow'])
            consistency_score = abs((bullish_count / 10) - 0.5) * 2  # 0-1

            # Общая сила тренда (взвешенная сумма)
            strength = (ema_score * 0.4 + macd_score * 0.3 + consistency_score * 0.3)

            return round(strength, 3)

        except Exception as e:
            logger.warning(f"⚠️ Ошибка расчёта силы тренда: {e}")
            return 0.5

    def get_mtf_alignment(
        self,
        trends: Dict[str, TrendDirectionEnum]
    ) -> Dict:
        """
        Анализ согласованности трендов

        Возвращает:
            Словарь с информацией о согласованности
        """
        try:
            trend_1h = trends.get('trend_1h', TrendDirectionEnum.NEUTRAL)
            trend_4h = trends.get('trend_4h', TrendDirectionEnum.NEUTRAL)
            trend_1d = trends.get('trend_1d', TrendDirectionEnum.NEUTRAL)

            trend_list = [trend_1h, trend_4h, trend_1d]

            # Подсчёт
            bullish_count = sum(1 for t in trend_list if t == TrendDirectionEnum.BULLISH)
            bearish_count = sum(1 for t in trend_list if t == TrendDirectionEnum.BEARISH)
            neutral_count = sum(1 for t in trend_list if t == TrendDirectionEnum.NEUTRAL)

            # Определение общего направления
            if bullish_count == 3:
                alignment = "full_bullish"
                score = 1.0
            elif bearish_count == 3:
                alignment = "full_bearish"
                score = 1.0
            elif bullish_count >= 2:
                alignment = "majority_bullish"
                score = 0.7
            elif bearish_count >= 2:
                alignment = "majority_bearish"
                score = 0.7
            else:
                alignment = "mixed"
                score = 0.3

            return {
                "alignment": alignment,
                "score": score,
                "bullish_count": bullish_count,
                "bearish_count": bearish_count,
                "neutral_count": neutral_count,
                "trends": {
                    "1h": trend_1h.value,
                    "4h": trend_4h.value,
                    "1d": trend_1d.value
                }
            }

        except Exception as e:
            logger.error(f"❌ Ошибка анализа MTF alignment: {e}")
            return {
                "alignment": "unknown",
                "score": 0.0,
                "bullish_count": 0,
                "bearish_count": 0,
                "neutral_count": 3
            }


# Экспорт
__all__ = ['MultiTimeframeTrendDetector']
