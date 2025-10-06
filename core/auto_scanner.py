#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Unified Auto Scanner - Объединённый модуль автоматического сканирования
Интегрирует все компоненты: сценарии, индикаторы, TP/SL, запись в БД, автозапуск
"""

import asyncio
from typing import Dict, List, Optional
from datetime import datetime

from config.settings import logger
from core.scenario_matcher import UnifiedScenarioMatcher, SignalStatus
from trading.risk_calculator import DynamicRiskCalculator
from trading.signal_recorder import SignalRecorder
from trading.position_tracker import PositionTracker
from utils.helpers import current_epoch_ms


class UnifiedAutoScanner:
    """
    Объединённый AutoScanner с полной функциональностью:
    - Ручное сканирование одного/нескольких символов
    - Автоматическое сканирование каждые 5 минут
    - Интеграция с match_scenario()
    - Расчёт TP/SL
    - Сохранение в БД
    - Уведомления в Telegram
    """

    def __init__(
        self,
        bot_instance,
        scenario_matcher: Optional[UnifiedScenarioMatcher] = None,
        risk_calculator: Optional[DynamicRiskCalculator] = None,
        signal_recorder: Optional[SignalRecorder] = None,
        position_tracker: Optional[PositionTracker] = None,
    ):
        """
        Инициализация scanner

        Args:
            bot_instance: Основной экземпляр GIOCryptoBot
            scenario_matcher: Matcher для поиска сценариев (опционально)
            risk_calculator: Калькулятор TP/SL (опционально)
            signal_recorder: Recorder для записи в БД (опционально)
            position_tracker: Tracker для отслеживания позиций (опционально)
        """
        self.bot = bot_instance

        # Компоненты (берём из bot_instance если не переданы)
        self.matcher = scenario_matcher or getattr(
            bot_instance, "scenario_matcher", None
        )
        self.calculator = risk_calculator or getattr(
            bot_instance, "risk_calculator", None
        )
        self.recorder = signal_recorder or getattr(
            bot_instance, "signal_recorder", None
        )
        self.tracker = position_tracker or getattr(
            bot_instance, "position_tracker", None
        )

        # Настройки автосканирования
        self.is_running = False
        self.scan_interval = 300  # 5 минут в секундах
        self.symbols = ["BTCUSDT"]  # По умолчанию только BTC

        # Статистика сканирования
        self.stats = {
            "scans_total": 0,
            "signals_generated": 0,
            "signals_deal": 0,
            "signals_risky": 0,
            "signals_observation": 0,
            "last_scan_time": 0,
            "auto_scans": 0,
        }

        logger.info("✅ UnifiedAutoScanner инициализирован")

    # ========== АВТОМАТИЧЕСКОЕ СКАНИРОВАНИЕ ==========

    async def start(self):
        """Запуск автоматического сканирования"""
        self.is_running = True
        logger.info("🔍 Auto Scanner запущен (интервал: 5 минут)")

        while self.is_running:
            try:
                self.stats["auto_scans"] += 1
                await self.scan_all_symbols()
                await asyncio.sleep(self.scan_interval)
            except Exception as e:
                logger.error(f"❌ Ошибка автосканирования: {e}")
                await asyncio.sleep(60)  # Подождать минуту при ошибке

    async def stop(self):
        """Остановка автоматического сканирования"""
        self.is_running = False
        logger.info("🛑 Auto Scanner остановлен")

    async def scan_all_symbols(self):
        """Автоматическое сканирование всех символов"""
        logger.info(f"🔍 Автосканирование: {len(self.symbols)} символов")

        for symbol in self.symbols:
            try:
                await self.scan_symbol(symbol)
            except Exception as e:
                logger.error(f"❌ Ошибка сканирования {symbol}: {e}")

    # ========== ОСНОВНОЕ СКАНИРОВАНИЕ ==========

    async def scan_symbol(self, symbol: str) -> Optional[int]:
        """
        Полное сканирование одного символа

        Процесс:
        1. Собрать все данные (рынок, индикаторы, MTF, VP, новости)
        2. Вызвать match_scenario()
        3. Если найден сигнал → рассчитать TP/SL
        4. Проверить RR фильтр
        5. Сохранить в БД
        6. Отправить уведомление в Telegram

        Args:
            symbol: Символ (например, "BTCUSDT")

        Returns:
            ID сигнала если сгенерирован, иначе None
        """
        try:
            self.stats["scans_total"] += 1
            self.stats["last_scan_time"] = current_epoch_ms()

            logger.info(f"🔍 Сканирование {symbol}...")

            # Шаг 1: Собираем рыночные данные
            market_data = await self._get_market_data(symbol)
            if not market_data:
                logger.warning(f"⚠️ {symbol}: нет рыночных данных")
                return None

            # Шаг 2: Получаем индикаторы
            indicators = await self._get_indicators(symbol)
            if not indicators:
                logger.warning(f"⚠️ {symbol}: нет индикаторов")
                return None

            # Шаг 3: Получаем MTF тренды
            mtf_trends = await self._get_mtf_trends(symbol)
            if not mtf_trends:
                logger.warning(f"⚠️ {symbol}: нет MTF данных")
                # Не критично, продолжаем
                mtf_trends = {}

            # Шаг 4: Получаем Volume Profile
            volume_profile = await self._get_volume_profile(symbol)
            if not volume_profile:
                logger.debug(f"ℹ️ {symbol}: нет Volume Profile")
                volume_profile = {}

            # Шаг 5: Получаем новостной sentiment
            news_sentiment = await self._get_news_sentiment(symbol)

            # Шаг 6: Получаем CVD (опционально)
            cvd_data = await self._get_cvd_data(symbol)

            # Шаг 7: Получаем VETO проверки
            veto_checks = await self._get_veto_checks(symbol, market_data)

            # Шаг 8: Вызываем match_scenario()
            if not self.matcher:
                logger.warning("⚠️ ScenarioMatcher не инициализирован")
                return None

            # Загружаем сценарии
            scenarios = self.matcher.scenarios

            matched_scenario = self.matcher.match_scenario(
                symbol=symbol,
                market_data=market_data,
                indicators=indicators,
                mtf_trends=mtf_trends,
                volume_profile=volume_profile,
                news_sentiment=news_sentiment,
                veto_checks=veto_checks,
                cvd_data=cvd_data,
            )

            if not matched_scenario:
                logger.debug(f"ℹ️ {symbol}: подходящих сценариев не найдено")
                return None

            # Проверяем статус
            status = matched_scenario.get("status", "observation")

            # Пропускаем только observation
            if status == "observation":
                logger.debug(
                    f"👀️ {symbol}: только наблюдение (score: {matched_scenario['score']:.1f}%)"
                )
                self.stats["signals_observation"] += 1
                return None

            # ИСПРАВЛЕНО: Проверяем что статус DEAL или RISKY_ENTRY
            if status not in ["deal", "risky_entry"]:
                logger.debug(f"⚠️ {symbol}: неизвестный статус '{status}', пропускаем")
                return None

            # Шаг 9: Рассчитываем TP/SL
            signal_with_tpsl = await self._calculate_tpsl(
                matched_scenario=matched_scenario,
                market_data=market_data,
                indicators=indicators,
                volume_profile=volume_profile,
            )

            # Шаг 10: Проверяем RR фильтр
            if signal_with_tpsl.get("risk_reward", 0) < 1.5:
                logger.info(
                    f"⚠️ {symbol}: Сигнал отклонён (RR={signal_with_tpsl['risk_reward']:.2f} < 1.5)"
                )
                return None

            # Шаг 11: Сохраняем в БД
            signal_id = await self._save_signal(signal_with_tpsl)
            if not signal_id:
                logger.warning(f"⚠️ {symbol}: не удалось сохранить сигнал")
                return None

            signal_with_tpsl["id"] = signal_id

            # Обновление статистики
            self.stats["signals_generated"] += 1

            if status == "deal":
                self.stats["signals_deal"] += 1
                status_emoji = "🟢"
            else:  # risky_entry
                self.stats["signals_risky"] += 1
                status_emoji = "🟡"

            # Логирование сигнала
            logger.info(
                f"{status_emoji} СИГНАЛ #{signal_id}: {symbol} {signal_with_tpsl.get('direction', 'LONG')}\n"
                f"  📊 Сценарий: {signal_with_tpsl.get('scenario_name', 'Unknown')}\n"
                f"  💯 Score: {signal_with_tpsl['score']:.1f}% | Status: {status}\n"
                f"  💰 Entry: ${signal_with_tpsl['entry_price']:.2f}\n"
                f"  🛑 SL: ${signal_with_tpsl['stop_loss']:.2f}\n"
                f"  🎯 TP1: ${signal_with_tpsl['tp1']:.2f} (RR: {signal_with_tpsl['rr1']:.2f})\n"
                f"  🎯 TP2: ${signal_with_tpsl['tp2']:.2f} (RR: {signal_with_tpsl['rr2']:.2f})\n"
                f"  🎯 TP3: ${signal_with_tpsl['tp3']:.2f} (RR: {signal_with_tpsl['rr3']:.2f})"
            )

            # Шаг 12: Отправляем уведомление в Telegram
            try:
                if hasattr(self.bot, "telegram_handler") and self.bot.telegram_handler:
                    await self.bot.telegram_handler.notify_new_signal(signal_with_tpsl)
                    logger.debug(f"✅ Telegram уведомление отправлено для #{signal_id}")
            except Exception as e:
                logger.error(f"❌ Ошибка отправки Telegram уведомления: {e}")

            return signal_id

        except Exception as e:
            logger.error(f"❌ Критическая ошибка сканирования {symbol}: {e}")
            return None

    # ========== МНОЖЕСТВЕННОЕ СКАНИРОВАНИЕ ==========

    async def scan_multiple_symbols(
        self,
        symbols: List[str],
        market_data_dict: Optional[Dict[str, Dict]] = None,
        indicators_dict: Optional[Dict[str, Dict]] = None,
    ) -> List[int]:
        """
        Сканирование нескольких символов параллельно

        Args:
            symbols: Список символов
            market_data_dict: {symbol: market_data} (опционально)
            indicators_dict: {symbol: indicators} (опционально)

        Returns:
            Список ID сгенерированных сигналов
        """
        try:
            tasks = []

            for symbol in symbols:
                task = self.scan_symbol(symbol)
                tasks.append(task)

            # Параллельное выполнение
            results = await asyncio.gather(*tasks, return_exceptions=True)

            # Фильтруем успешные результаты
            signal_ids = [
                result
                for result in results
                if isinstance(result, int) and result is not None
            ]

            if signal_ids:
                logger.info(
                    f"✅ Сканирование завершено: {len(signal_ids)} новых сигналов"
                )

            return signal_ids

        except Exception as e:
            logger.error(f"❌ Ошибка сканирования нескольких символов: {e}")
            return []

    # ========== ВСПОМОГАТЕЛЬНЫЕ МЕТОДЫ ==========

    async def _get_market_data(self, symbol: str) -> Optional[Dict]:
        """Получение текущих рыночных данных"""
        try:
            ticker = await self.bot.bybit_connector.get_ticker(symbol)
            if not ticker:
                return None

            return {
                "symbol": symbol,
                "price": float(ticker.get("last_price", 0)),
                "current_price": float(ticker.get("last_price", 0)),
                "volume_24h": float(ticker.get("volume_24h", 0)),
                "price_24h_pcnt": float(ticker.get("price_24h_pcnt", 0)),
                "high_24h": float(ticker.get("high_24h", 0)),
                "low_24h": float(ticker.get("low_24h", 0)),
                "timestamp": datetime.now().isoformat(),
            }
        except Exception as e:
            logger.error(f"❌ Ошибка получения market_data: {e}")
            return None

    async def _get_indicators(self, symbol: str) -> Optional[Dict]:
        """Получение технических индикаторов"""
        try:
            if hasattr(self.bot, "market_data") and symbol in self.bot.market_data:
                data = self.bot.market_data[symbol]

                return {
                    "rsi": data.get("rsi", 50),
                    "rsi_1h": data.get("rsi_1h", data.get("rsi", 50)),
                    "macd": data.get("macd", 0),
                    "macd_signal": data.get("macd_signal", 0),
                    "macd_histogram": data.get("macd_histogram", 0),
                    "atr": data.get("atr", 0),
                    "atr_1h": data.get("atr_1h", data.get("atr", 0)),
                    "ema_20": data.get("ema_20", 0),
                    "ema_50": data.get("ema_50", 0),
                }

            return None
        except Exception as e:
            logger.error(f"❌ Ошибка получения indicators: {e}")
            return None

    async def _get_mtf_trends(self, symbol: str) -> Optional[Dict]:
        """Получение MTF трендов"""
        try:
            if hasattr(self.bot, "mtf_detector"):
                trends = await self.bot.mtf_detector.analyze_symbol(symbol)
                return trends

            return None
        except Exception as e:
            logger.error(f"❌ Ошибка получения MTF trends: {e}")
            return None

    async def _get_volume_profile(self, symbol: str) -> Optional[Dict]:
        """Получение Volume Profile данных"""
        try:
            if hasattr(self.bot, "volume_profile_calculator"):
                vp_data = self.bot.volume_profile_calculator.get_latest_profile(symbol)

                if vp_data:
                    return {
                        "poc": vp_data.get("poc", 0),
                        "vah": vp_data.get("vah", 0),
                        "val": vp_data.get("val", 0),
                        "current_price": vp_data.get("current_price", 0),
                        "volume_nodes": vp_data.get("volume_nodes", []),
                    }

            return None
        except Exception as e:
            logger.error(f"❌ Ошибка получения Volume Profile: {e}")
            return None

    async def _get_news_sentiment(self, symbol: str) -> Dict:
        """Получение новостного sentiment"""
        try:
            if hasattr(self.bot, "enhanced_sentiment"):
                # Используем новый EnhancedSentimentAnalyzer
                sentiment = self.bot.enhanced_sentiment.get_symbol_sentiment(symbol)
                return sentiment
            elif hasattr(self.bot, "news_analyzer"):
                # Legacy
                sentiment = self.bot.news_analyzer.get_symbol_sentiment(symbol)
                return sentiment

            return {"sentiment": "neutral", "score": 0.0, "news_count": 0}
        except Exception as e:
            logger.error(f"❌ Ошибка получения sentiment: {e}")
            return {"sentiment": "neutral", "score": 0.0, "news_count": 0}

    async def _get_cvd_data(self, symbol: str) -> Optional[Dict]:
        """Получение CVD данных"""
        try:
            # TODO: Реализовать расчёт CVD
            return None
        except Exception as e:
            logger.error(f"❌ Ошибка получения CVD: {e}")
            return None

    async def _get_veto_checks(self, symbol: str, market_data: Dict) -> Dict:
        """Получение VETO проверок"""
        try:
            if hasattr(self.bot, "veto_system"):
                veto_result = await self.bot.veto_system.check_conditions(
                    symbol, market_data
                )
                return veto_result

            return {"has_veto": False, "veto_reasons": []}
        except Exception as e:
            logger.error(f"❌ Ошибка получения VETO: {e}")
            return {"has_veto": False, "veto_reasons": []}

    async def _calculate_tpsl(
        self,
        matched_scenario: Dict,
        market_data: Dict,
        indicators: Dict,
        volume_profile: Dict,
    ) -> Dict:
        """Динамический расчёт TP/SL"""
        try:
            entry_price = market_data.get("price", 0) or market_data.get(
                "current_price", 0
            )
            direction = matched_scenario.get("direction", "LONG")
            atr = indicators.get("atr", 0) or indicators.get(
                "atr_1h", entry_price * 0.02
            )

            poc = volume_profile.get("poc", entry_price)
            vah = volume_profile.get("vah", entry_price * 1.02)
            val = volume_profile.get("val", entry_price * 0.98)

            # Расчёт SL
            sl_distance = atr * 1.5  # 1.5x ATR
            stop_loss = (
                entry_price - sl_distance
                if direction == "LONG"
                else entry_price + sl_distance
            )

            # Расчёт TP
            if direction == "LONG":
                tp1 = max(entry_price * 1.015, poc)  # +1.5% или POC
                tp2 = vah  # VAH
                tp3 = vah * 1.015  # +1.5% от VAH
            else:  # SHORT
                tp1 = min(entry_price * 0.985, poc)  # -1.5% или POC
                tp2 = val  # VAL
                tp3 = val * 0.985  # -1.5% от VAL

            # Расчёт RR для каждого TP
            risk = abs(entry_price - stop_loss)
            rr1 = abs(tp1 - entry_price) / risk if risk > 0 else 0
            rr2 = abs(tp2 - entry_price) / risk if risk > 0 else 0
            rr3 = abs(tp3 - entry_price) / risk if risk > 0 else 0

            # Добавляем в matched_scenario
            matched_scenario.update(
                {
                    "entry_price": round(entry_price, 2),
                    "stop_loss": round(stop_loss, 2),
                    "tp1": round(tp1, 2),
                    "tp2": round(tp2, 2),
                    "tp3": round(tp3, 2),
                    "rr1": round(rr1, 2),
                    "rr2": round(rr2, 2),
                    "rr3": round(rr3, 2),
                    "risk_reward": round(rr2, 2),  # Основной RR - по TP2
                    "atr": round(atr, 2),
                }
            )

            return matched_scenario

        except Exception as e:
            logger.error(f"❌ Ошибка расчёта TP/SL: {e}")
            return matched_scenario

    async def _save_signal(self, signal: Dict) -> int:
        """Сохранение сигнала в БД"""
        try:
            if self.recorder:
                signal_id = self.recorder.record_signal(
                    symbol=signal.get("symbol"),
                    direction=signal.get("direction"),
                    entry_price=signal.get("entry_price"),
                    stop_loss=signal.get("stop_loss"),
                    tp1=signal.get("tp1"),
                    tp2=signal.get("tp2"),
                    tp3=signal.get("tp3"),
                    scenario_id=signal.get("scenario_id"),
                    status=signal.get("status"),
                    quality_score=signal.get("score"),
                    risk_reward=signal.get("risk_reward"),
                )
                return signal_id

            return 0
        except Exception as e:
            logger.error(f"❌ Ошибка сохранения сигнала: {e}")
            return 0

    # ========== СТАТИСТИКА ==========

    def get_statistics(self) -> Dict:
        """Получение статистики работы scanner"""
        try:
            # Добавляем статистику из recorder
            db_stats = {}
            if self.recorder:
                db_stats = self.recorder.get_signal_stats(days=30)

            return {
                **self.stats,
                "db_stats": db_stats,
                "conversion_rate": round(
                    (
                        self.stats["signals_generated"]
                        / max(self.stats["scans_total"], 1)
                    )
                    * 100,
                    2,
                ),
            }

        except Exception as e:
            logger.error(f"❌ Ошибка получения статистики: {e}")
            return self.stats


# Алиасы для совместимости
AutoScanner = UnifiedAutoScanner
AutoSignalScanner = UnifiedAutoScanner

# Экспорт
__all__ = ["UnifiedAutoScanner", "AutoScanner", "AutoSignalScanner"]
