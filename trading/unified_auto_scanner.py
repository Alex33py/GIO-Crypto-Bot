#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Unified Auto Scanner - Автоматический сканер рынка (каждые 5 минут)
Объединённая версия с поддержкой UnifiedScenarioMatcher + ВАЛИДАЦИЯ ДАННЫХ
"""

import asyncio
from typing import Optional, List, Dict
from datetime import datetime
from config.settings import logger, TRACKED_SYMBOLS, SCANNER_CONFIG
from utils.data_validator import DataValidator  # ← ДОБАВЛЕНО!


class UnifiedAutoScanner:
    """Унифицированный автосканер для поиска торговых возможностей"""

    def __init__(
        self,
        bot_instance,
        scenario_matcher,
        risk_calculator=None,
        signal_recorder=None,
        position_tracker=None,
    ):
        """
        Инициализация автосканера

        Args:
            bot_instance: Экземпляр основного бота
            scenario_matcher: UnifiedScenarioMatcher для поиска сценариев
            risk_calculator: Калькулятор рисков (опционально)
            signal_recorder: Рекордер сигналов (опционально)
            position_tracker: Трекер позиций (опционально)
        """
        self.bot = bot_instance
        self.scenario_matcher = scenario_matcher
        self.risk_calculator = risk_calculator
        self.signal_recorder = signal_recorder
        self.position_tracker = position_tracker

        # Настройки
        self.interval_minutes = SCANNER_CONFIG.get("interval_minutes", 5)
        self.symbols = TRACKED_SYMBOLS
        self.is_running = False
        self.scan_task = None

        logger.info(
            f"✅ UnifiedAutoScanner инициализирован (интервал: {self.interval_minutes} мин)"
        )

    async def start(self):
        """Запуск автосканера"""
        if self.is_running:
            logger.warning("⚠️ AutoScanner уже запущен")
            return

        self.is_running = True
        logger.info(f"🔍 Запуск AutoScanner (интервал: {self.interval_minutes} мин)")

        # Запускаем цикл сканирования
        self.scan_task = asyncio.create_task(self._scan_loop())

    async def stop(self):
        """Остановка автосканера"""
        if not self.is_running:
            return

        logger.info("🛑 Остановка AutoScanner...")
        self.is_running = False

        if self.scan_task:
            self.scan_task.cancel()
            try:
                await self.scan_task
            except asyncio.CancelledError:
                pass

        logger.info("✅ AutoScanner остановлен")

    async def _scan_loop(self):
        """Главный цикл сканирования"""
        try:
            while self.is_running:
                try:
                    # Выполняем сканирование
                    await self.scan_market()
                    await asyncio.sleep(self.interval_minutes * 60)

                except Exception as e:
                    logger.error(f"❌ Ошибка в цикле сканирования: {e}")
                    # Продолжаем работу даже при ошибке
                    await asyncio.sleep(60)  # Пауза 1 минута при ошибке

        except asyncio.CancelledError:
            logger.info("🛑 Цикл сканирования отменён")

    async def scan_market(self):
        """Сканирование рынка на всех символах"""
        try:
            logger.info(f"🔍 Начало сканирования рынка ({len(self.symbols)} символов)")

            signals_found = 0

            for symbol in self.symbols:
                try:
                    # Анализируем символ
                    result = await self.analyze_symbol(symbol)

                    if result and result.get("signal"):
                        signals_found += 1
                        logger.info(f"🎯 Найден сигнал: {symbol} {result['direction']}")

                        # Сохраняем сигнал если есть recorder
                        if self.signal_recorder:
                            signal_id = self.signal_recorder.record_signal(
                                symbol=symbol,
                                direction=result["direction"],
                                entry_price=result["entry_price"],
                                stop_loss=result["stop_loss"],
                                tp1=result["tp1"],
                                tp2=result["tp2"],
                                tp3=result["tp3"],
                                scenario_id=result.get("scenario_id", "auto_scanner"),
                                status="active",
                                quality_score=result.get("quality_score", 0),
                                risk_reward=result.get("risk_reward", 0),
                            )

                            logger.info(f"✅ Сигнал #{signal_id} сохранён в БД")

                            # Отправляем уведомление в Telegram
                            if (
                                hasattr(self.bot, "telegram_handler")
                                and self.bot.telegram_handler
                            ):
                                try:
                                    await self.bot.telegram_handler.notify_new_signal(
                                        {
                                            "id": signal_id,
                                            "symbol": symbol,
                                            "direction": result["direction"],
                                            "entry_price": result["entry_price"],
                                            "tp1": result["tp1"],
                                            "tp2": result["tp2"],
                                            "tp3": result["tp3"],
                                            "stop_loss": result["stop_loss"],
                                            "quality_score": result.get(
                                                "quality_score", 0
                                            ),
                                            "risk_reward": result.get("risk_reward", 0),
                                            "timestamp": datetime.now(),
                                        }
                                    )
                                    logger.info(
                                        f"📨 Сигнал #{signal_id} отправлен в Telegram"
                                    )
                                except Exception as e:
                                    logger.error(
                                        f"❌ Ошибка отправки Telegram уведомления: {e}"
                                    )

                    # Небольшая пауза между символами
                    await asyncio.sleep(0.5)

                except Exception as e:
                    logger.error(f"❌ Ошибка анализа {symbol}: {e}")
                    continue

            logger.info(f"✅ Сканирование завершено: найдено {signals_found} сигналов")

        except Exception as e:
            logger.error(f"❌ Ошибка scan_market: {e}")

    # ✅ ДОБАВИТЬ ЭТОТ МЕТОД ЗДЕСЬ:
    async def scan_symbol(self, symbol: str) -> Optional[Dict]:
        """
        Полное сканирование одного символа

        Returns:
            Dict с деталями сигнала если создан, иначе None
        """
        try:
            logger.info(f"🔍 Сканирование {symbol}...")

            # Используем существующий метод analyze_symbol
            result = await self.analyze_symbol(symbol)

            if not result or not result.get("signal"):
                logger.debug(f"ℹ️ {symbol}: подходящих сигналов не найдено")
                return None

            # Сохраняем сигнал если есть recorder
            if self.signal_recorder:
                signal_id = self.signal_recorder.record_signal(
                    symbol=symbol,
                    direction=result["direction"],
                    entry_price=result["entry_price"],
                    stop_loss=result["stop_loss"],
                    tp1=result["tp1"],
                    tp2=result["tp2"],
                    tp3=result["tp3"],
                    scenario_id=result.get("scenario_id", "auto_scanner"),
                    status="active",
                    quality_score=result.get("quality_score", 0),
                    risk_reward=result.get("risk_reward", 0),
                )

                logger.info(f"✅ {symbol}: Сигнал #{signal_id} создан")

                # Отправляем уведомление в Telegram
                if hasattr(self.bot, "telegram_handler") and self.bot.telegram_handler:
                    try:
                        await self.bot.telegram_handler.notify_new_signal(
                            {
                                "id": signal_id,
                                "symbol": symbol,
                                "direction": result["direction"],
                                "entry_price": result["entry_price"],
                                "tp1": result["tp1"],
                                "tp2": result["tp2"],
                                "tp3": result["tp3"],
                                "stop_loss": result["stop_loss"],
                                "quality_score": result.get("quality_score", 0),
                                "risk_reward": result.get("risk_reward", 0),
                                "status": result.get("status", "active"),
                            }
                        )
                        logger.info(f"📨 Сигнал #{signal_id} отправлен в Telegram")
                    except Exception as e:
                        logger.error(f"❌ Ошибка отправки Telegram уведомления: {e}")
                # ✅ ВОЗВРАЩАЕМ ВЕСЬ ОБЪЕКТ С ДЕТАЛЯМИ!
                return {
                    "signal_id": signal_id,
                    "symbol": symbol,
                    "direction": result["direction"],
                    "entry_price": result["entry_price"],
                    "stop_loss": result["stop_loss"],
                    "tp1": result["tp1"],
                    "tp2": result["tp2"],
                    "tp3": result["tp3"],
                    "quality_score": result.get("quality_score", 0),
                    "risk_reward": result.get("risk_reward", 0),
                    "status": result.get("status", "active"),
                }

            return None

        except Exception as e:
            logger.error(f"❌ Критическая ошибка scan_symbol {symbol}: {e}")
            return None

    async def scan_multiple_symbols(self, symbols: List[str]) -> List[Dict]:
        """
        Сканирование нескольких символов параллельно

        Args:
            symbols: Список символов

        Returns:
            Список ID сгенерированных сигналов
        """
        try:
            tasks = [self.scan_symbol(symbol) for symbol in symbols]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            # Фильтруем успешные результаты
            signal_data = [
                result
                for result in results
                if isinstance(result, dict) and result is not None
            ]

            if signal_data:
                logger.info(
                    f"✅ Сканирование завершено: {len(signal_data)} новых сигналов"
                )

            return signal_data

        except Exception as e:
            logger.error(f"❌ Ошибка scan_multiple_symbols: {e}")
            return []

    async def analyze_symbol(self, symbol: str) -> Optional[Dict]:
        """
        Анализ одного символа

        Args:
            symbol: Торговая пара (например, "BTCUSDT")

        Returns:
            Dict с параметрами сигнала или None
        """
        try:
            # Получаем данные рынка
            market_data = await self._get_market_data(symbol)
            if not market_data:
                return None

            # ========== ВАЛИДАЦИЯ MARKET DATA ==========
            current_price = market_data.get("close", 0)
            if not DataValidator.validate_price(current_price, symbol):
                logger.warning(f"⚠️ {symbol}: Невалидная цена, пропускаем")
                return None

            # ========== ВАЛИДАЦИЯ СВЕЧЕЙ ==========
            candles = market_data.get("candles", [])
            if not DataValidator.validate_candles_list(candles, min_length=20):
                logger.warning(f"⚠️ {symbol}: Невалидные свечи, пропускаем")
                return None

            # Подготавливаем данные для UnifiedScenarioMatcher
            indicators = {}
            mtf_trends = {}
            volume_profile = await self.bot.get_volume_profile(symbol)

            # ========== ВАЛИДАЦИЯ VOLUME PROFILE ==========
            if volume_profile:
                poc = volume_profile.get("poc")
                vah = volume_profile.get("vah")
                val = volume_profile.get("val")

                if not all(
                    [
                        DataValidator.validate_price(poc, f"{symbol}.poc"),
                        DataValidator.validate_price(vah, f"{symbol}.vah"),
                        DataValidator.validate_price(val, f"{symbol}.val"),
                    ]
                ):
                    logger.warning(
                        f"⚠️ {symbol}: Невалидный Volume Profile, используем fallback"
                    )
                    volume_profile = {}
            else:
                logger.debug(f"⚠️ {symbol}: Volume Profile не получен")
                volume_profile = {}

            news_sentiment = {}
            veto_checks = {}

            # Если есть MTF analyzer - получаем тренды
            if hasattr(self.bot, "mtf_analyzer") and self.bot.mtf_analyzer:
                try:
                    mtf_trends = {"1h": "neutral", "4h": "neutral", "1d": "neutral"}
                except:
                    pass

            # Если есть sentiment analyzer - получаем sentiment
            if hasattr(self.bot, "enhanced_sentiment") and self.bot.enhanced_sentiment:
                try:
                    news_sentiment = {"overall": "neutral", "score": 0.5}
                except:
                    pass

            # Ищем совпадение сценария через UnifiedScenarioMatcher
            match_result = self.scenario_matcher.match_scenario(
                symbol=symbol,
                market_data=market_data,
                indicators=indicators,
                mtf_trends=mtf_trends,
                volume_profile=volume_profile,
                news_sentiment=news_sentiment,
                veto_checks=veto_checks,
            )

            # Проверяем успешность match
            if not match_result:
                return None

            # ========== ✅ CONFIRM FILTER + MULTI-TF FILTER ==========
            # Применяем фильтры ПЕРЕД созданием сигнала
            if hasattr(self.bot, "confirm_filter") or hasattr(
                self.bot, "multi_tf_filter"
            ):
                logger.info(f"🔍 DEBUG для {symbol}:")
                logger.info(
                    f"   bot.confirm_filter = {getattr(self.bot, 'confirm_filter', None)}"
                )
                logger.info(
                    f"   bot.multi_tf_filter = {getattr(self.bot, 'multi_tf_filter', None)}"
                )

                direction = match_result.get("direction", "LONG")

                # 1. CONFIRM FILTER
                if hasattr(self.bot, "confirm_filter") and self.bot.confirm_filter:
                    logger.info(f"🔍 Применение Confirm Filter для {symbol}...")

                    # ✅ ПРАВИЛЬНО: добавлен await!
                    filters_passed = await self.bot.confirm_filter.validate(
                        symbol, direction, market_data
                    )

                    if not filters_passed:
                        logger.warning(
                            f"❌ {symbol} {direction}: Сигнал ОТКЛОНЁН Confirm Filter"
                        )
                        return None

                    logger.info(f"✅ {symbol}: Confirm Filter пройден")

                # 2. MULTI-TF FILTER
                if hasattr(self.bot, "multi_tf_filter") and self.bot.multi_tf_filter:
                    logger.info(f"🔍 Применение Multi-TF Filter для {symbol}...")

                    # Подготавливаем данные для фильтра
                    signal_dict = {
                        "symbol": symbol,
                        "direction": direction,
                        "entry_price": match_result.get("entry_price", 0),
                    }

                    # ✅ ПРАВИЛЬНО: validate (не validate_signal) + правильный порядок аргументов
                    mtf_valid, mtf_reason = await self.bot.multi_tf_filter.validate(
                        signal_dict,
                        market_data,
                        symbol,
                    )

                    if not mtf_valid:
                        logger.warning(
                            f"❌ {symbol} {direction}: Сигнал ОТКЛОНЁН Multi-TF Filter: {mtf_reason}"
                        )
                        return None  # Блокируем несогласованный сигнал!

                    logger.info(f"✅ {symbol}: Multi-TF Filter пройден: {mtf_reason}")

                logger.info(f"✅ {symbol}: ВСЕ ФИЛЬТРЫ ПРОЙДЕНЫ!")
            else:
                logger.warning(
                    f"⚠️ {symbol}: Фильтры не найдены в bot, пропускаем проверку"
                )
            # =========================================================

            # Проверяем status (observation не считается сигналом)
            if match_result.get("status") == "observation":
                logger.debug(f"⏭️ {symbol}: observation режим, пропускаем")
                return None

            # ========== ВАЛИДАЦИЯ TP/SL ==========
            entry_price = match_result.get("entry_price", 0)
            stop_loss = match_result.get("stop_loss", 0)
            tp1 = match_result.get("tp1", 0)
            tp2 = match_result.get("tp2", 0)
            tp3 = match_result.get("tp3", 0)

            if not all(
                [
                    DataValidator.validate_price(entry_price, f"{symbol}.entry"),
                    DataValidator.validate_price(stop_loss, f"{symbol}.sl"),
                    DataValidator.validate_price(tp1, f"{symbol}.tp1"),
                    DataValidator.validate_price(tp2, f"{symbol}.tp2"),
                    DataValidator.validate_price(tp3, f"{symbol}.tp3"),
                ]
            ):
                logger.warning(f"⚠️ {symbol}: Невалидные TP/SL, пропускаем сигнал")
                return None

            # Формируем сигнал на основе match_result
            signal = {
                "signal": True,
                "symbol": symbol,
                "direction": match_result.get("direction", "LONG"),
                "entry_price": entry_price,
                "stop_loss": stop_loss,
                "tp1": tp1,
                "tp2": tp2,
                "tp3": tp3,
                "scenario_id": match_result.get("scenario_id", "unknown"),
                "scenario_name": match_result.get("scenario_name", "Unknown"),
                "status": match_result.get("status", "active"),
                "quality_score": match_result.get("score", 0),
                "risk_reward": match_result.get("risk_reward", 2.0),
            }

            return signal

        except Exception as e:
            logger.error(f"❌ Ошибка analyze_symbol для {symbol}: {e}")
            return None

    async def _get_market_data(self, symbol: str) -> Optional[Dict]:
        """
        Получение данных рынка для символа

        Args:
            symbol: Торговая пара

        Returns:
            Dict с рыночными данными
        """
        try:
            # Получаем данные через коннектор бота
            if not hasattr(self.bot, "bybit_connector"):
                logger.error("❌ bybit_connector не найден в bot_instance")
                return None

            # Получаем тикер
            ticker = await self.bot.bybit_connector.get_ticker(symbol)
            if not ticker:
                logger.warning(f"⚠️ {symbol}: Не удалось получить ticker")
                return None

            # Получаем свечи (например, 1h)
            candles = await self.bot.bybit_connector.get_klines(
                symbol=symbol, interval="60", limit=100  # 1h
            )

            if not candles or len(candles) == 0:
                logger.warning(f"⚠️ {symbol}: Нет свечей")
                return None

            # ========== ВАЛИДАЦИЯ ЦЕНЫ ИЗ ТИКЕРА ==========
            last_price = float(
                ticker.get("lastPrice", 0) or ticker.get("last_price", 0)
            )

            if not DataValidator.validate_price(last_price, f"{symbol}.ticker"):
                logger.warning(f"⚠️ {symbol}: Невалидная цена в ticker")
                return None

            # Формируем данные для анализа
            market_data = {
                "symbol": symbol,
                "close": last_price,
                "price": last_price,  # Alias
                "volume": float(
                    ticker.get("volume24h", 0) or ticker.get("volume_24h", 0)
                ),
                "candles": candles,
                "timestamp": datetime.now(),
            }

            return market_data

        except Exception as e:
            logger.error(f"❌ Ошибка _get_market_data для {symbol}: {e}")
            return None


# Экспорт
__all__ = ["UnifiedAutoScanner"]
