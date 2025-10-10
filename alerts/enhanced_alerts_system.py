#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Enhanced Alerts System - Расширенная система алертов
Мониторинг L2 дисбалансов, ликвидаций, всплесков объёмов и новостей
Версия: 2.0 (с автоматическим мониторингом всех пар)
Дата: 2025-10-06
"""

import asyncio
import time
from typing import Dict, List, Optional
from datetime import datetime, timedelta
from config.settings import logger, TRACKED_SYMBOLS


class EnhancedAlertsSystem:
    """Расширенная система алертов с мониторингом в реальном времени"""

    def __init__(self, bot_instance, telegram_bot=None):
        """
        Инициализация системы алертов

        Args:
            bot_instance: Ссылка на главный экземпляр бота
            telegram_bot: Telegram бот для отправки уведомлений
        """
        self.bot = bot_instance
        self.telegram_bot = telegram_bot

        # Статистика алертов
        self.alerts_count = {
            "l2_imbalance": 0,
            "liquidations": 0,
            "volume_spike": 0,
            "news": 0,
            "total": 0,
        }

        # Throttling для алертов (избегаем спама)
        self.last_alert_time = {}

        # Параметры алертов
        self.config = {
            "l2_imbalance_threshold": 0.70,  # 70% дисбаланс
            "liquidation_min_usd": 100000,  # Минимум $100k ликвидация
            "volume_spike_multiplier": 3.0,  # 3x от среднего объёма
            "news_critical_keywords": [
                "SEC",
                "ETF",
                "lawsuit",
                "hack",
                "regulation",
                "ban",
                "approval",
                "crash",
                "surge",
                "破產",
                "lawsuit",
            ],
            "throttle_seconds": 60,  # Минимум 60 секунд между алертами одного типа
            "monitoring_interval": 30,  # Интервал проверки в секундах
        }

        # Кэш данных для расчётов
        self.volume_history = {}  # Для расчёта среднего объёма
        self.last_news_check = 0  # Timestamp последней проверки новостей

        logger.info(
            f"✅ EnhancedAlertsSystem инициализирована для {len(TRACKED_SYMBOLS)} пар"
        )

    async def start_monitoring(self):
        """
        Запуск автоматического мониторинга всех пар

        Основной цикл, который проверяет все пары каждые 30 секунд:
        - L2 дисбаланс orderbook
        - Критичные новости (каждые 5 минут)
        - Опционально: ликвидации и всплески объёмов
        """
        logger.info(
            f"🚨 Запуск мониторинга Enhanced Alerts для {len(TRACKED_SYMBOLS)} пар: {', '.join(TRACKED_SYMBOLS)}"
        )

        cycle_count = 0

        while True:
            try:
                cycle_count += 1
                cycle_start = time.time()

                logger.debug(f"🔄 Enhanced Alerts цикл #{cycle_count}")

                # ========== ПРОВЕРКА L2 ДИСБАЛАНСА ДЛЯ ВСЕХ ПАР ==========
                for symbol in TRACKED_SYMBOLS:
                    try:
                        await self.check_l2_imbalance(symbol)
                    except Exception as e:
                        logger.error(f"❌ Ошибка check_l2_imbalance для {symbol}: {e}")

                # ========== ПРОВЕРКА НОВОСТЕЙ (раз в 5 минут) ==========
                try:
                    await self.check_news_alerts()
                except Exception as e:
                    logger.error(f"❌ Ошибка check_news_alerts: {e}")

                # ========== ОПЦИОНАЛЬНО: ЛИКВИДАЦИИ И ОБЪЁМЫ ==========
                # Раскомментируйте если хотите мониторить:
                # for symbol in TRACKED_SYMBOLS:
                #     try:
                #         await self.check_liquidations(symbol)
                #     except Exception as e:
                #         logger.error(f"❌ Ошибка check_liquidations для {symbol}: {e}")
                #
                #     try:
                #         await self.check_volume_spike(symbol)
                #     except Exception as e:
                #         logger.error(f"❌ Ошибка check_volume_spike для {symbol}: {e}")

                # Расчёт времени выполнения цикла
                cycle_duration = time.time() - cycle_start
                logger.debug(
                    f"✅ Enhanced Alerts цикл #{cycle_count} завершён за {cycle_duration:.2f}s"
                )

                # Ожидание перед следующим циклом
                sleep_time = max(1, self.config["monitoring_interval"] - cycle_duration)
                logger.debug(f"⏳ Enhanced Alerts: ожидание {sleep_time:.0f} секунд...")
                await asyncio.sleep(sleep_time)

            except Exception as e:
                logger.error(
                    f"❌ Критическая ошибка в цикле мониторинга Enhanced Alerts: {e}"
                )
                import traceback

                logger.debug(traceback.format_exc())
                await asyncio.sleep(60)

    async def check_l2_imbalance(self, symbol: str):
        """
        Проверка L2 дисбаланса стакана заявок

        Args:
            symbol: Торговая пара (BTCUSDT, XRPUSDT, etc.)
        """
        try:
            # Получаем данные из bot.market_data (обновляются через WebSocket)
            if symbol not in self.bot.market_data:
                logger.debug(f"   ⚠️ {symbol}: Нет данных L2 orderbook в market_data")
                return

            market_data = self.bot.market_data[symbol]
            imbalance = market_data.get("orderbook_imbalance", 0)

            # Проверяем порог дисбаланса
            if abs(imbalance) > self.config["l2_imbalance_threshold"]:
                # Throttling: не отправляем алерт чаще раз в минуту
                alert_key = f"l2_{symbol}"
                if self._should_throttle(alert_key):
                    return

                direction = "📈 BUY PRESSURE" if imbalance > 0 else "📉 SELL PRESSURE"
                emoji = "🚨" if abs(imbalance) > 0.80 else "⚠️"

                message = (
                    f"{emoji} L2 ДИСБАЛАНС ALERT\n"
                    f"Пара: {symbol}\n"
                    f"Дисбаланс: {imbalance:.1%}\n"
                    f"Направление: {direction}\n"
                    f"Время: {datetime.now().strftime('%H:%M:%S')}"
                )

                await self.send_alert("l2_imbalance", message, priority="high")
                logger.info(f"🚨 L2 Alert отправлен: {symbol} ({imbalance:.1%})")

        except Exception as e:
            logger.error(f"❌ Ошибка check_l2_imbalance для {symbol}: {e}")

    async def check_liquidations(self, symbol: str):
        """
        Проверка крупных ликвидаций

        Args:
            symbol: Торговая пара (BTCUSDT)
        """
        try:
            logger.debug(f"🔍 Проверка ликвидаций для {symbol}...")

            # Получаем последние сделки из Bybit (aggTrades содержат информацию о крупных сделках)
            try:
                trades = await self.bot.bybit_connector.get_trades(symbol, limit=100)

                if not trades:
                    logger.debug(f"   ⚠️ {symbol}: Нет данных о сделках")
                    return

                # Анализируем крупные сделки (потенциальные ликвидации)
                current_time = time.time() * 1000  # ms
                large_trades = []

                for trade in trades:
                    # Проверяем размер сделки
                    price = float(trade.get("price", 0))
                    qty = float(trade.get("qty", 0))
                    trade_time = int(trade.get("time", 0))
                    side = trade.get("side", "")

                    # Объём сделки в USD
                    trade_usd = price * qty

                    # Фильтр: сделки > $100k за последние 60 секунд
                    if (
                        trade_usd > self.config["liquidation_min_usd"]
                        and (current_time - trade_time) < 60000
                    ):
                        large_trades.append(
                            {
                                "price": price,
                                "qty": qty,
                                "usd": trade_usd,
                                "side": side,
                                "time": datetime.fromtimestamp(
                                    trade_time / 1000
                                ).strftime("%H:%M:%S"),
                            }
                        )

                if large_trades:
                    # Throttling
                    alert_key = f"liq_{symbol}"
                    if self._should_throttle(alert_key):
                        return

                    # Сортируем по объёму (самые крупные первыми)
                    large_trades.sort(key=lambda x: x["usd"], reverse=True)
                    top_trade = large_trades[0]

                    emoji = "💥" if top_trade["usd"] > 500000 else "⚠️"
                    side_emoji = (
                        "🟢 LONG" if top_trade["side"].upper() == "BUY" else "🔴 SHORT"
                    )

                    message = (
                        f"{emoji} КРУПНАЯ ЛИКВИДАЦИЯ\n"
                        f"Пара: {symbol}\n"
                        f"Объём: ${top_trade['usd']:,.0f}\n"
                        f"Сторона: {side_emoji}\n"
                        f"Цена: ${top_trade['price']:,.2f}\n"
                        f"Время: {top_trade['time']}\n"
                        f"Всего крупных сделок: {len(large_trades)}"
                    )

                    await self.send_alert("liquidations", message, priority="high")
                    logger.info(
                        f"💥 Liquidation Alert: {symbol} (${top_trade['usd']:,.0f})"
                    )
                else:
                    logger.debug(f"   ✅ {symbol}: Крупных ликвидаций не обнаружено")

            except Exception as e:
                logger.error(f"❌ Ошибка получения trades для {symbol}: {e}")

        except Exception as e:
            logger.error(f"❌ Ошибка check_liquidations: {e}")

    async def check_volume_spike(self, symbol: str):
        """
        Проверка всплесков объёма торгов

        Args:
            symbol: Торговая пара (BTCUSDT)
        """
        try:
            logger.debug(f"🔍 Проверка всплеска объёма для {symbol}...")

            # Получаем последние свечи (1H для анализа объёма)
            try:
                candles = await self.bot.bybit_connector.get_klines(
                    symbol=symbol, interval="60", limit=24  # 1H  # 24 часа
                )

                if not candles or len(candles) < 10:
                    logger.debug(f"   ⚠️ {symbol}: Недостаточно данных свечей")
                    return

                # Рассчитываем средний объём за последние 20 часов (исключая последние 4)
                volumes = [float(c["volume"]) for c in candles[:-4]]
                avg_volume = sum(volumes) / len(volumes)

                # Текущий объём (последняя свеча)
                current_volume = float(candles[-1]["volume"])

                # Сохраняем историю для анализа
                if symbol not in self.volume_history:
                    self.volume_history[symbol] = []

                self.volume_history[symbol].append(
                    {"volume": current_volume, "time": time.time()}
                )

                # Держим только последние 100 записей
                if len(self.volume_history[symbol]) > 100:
                    self.volume_history[symbol].pop(0)

                # Проверяем всплеск (текущий объём > 3x среднего)
                spike_ratio = current_volume / avg_volume if avg_volume > 0 else 0

                if spike_ratio > self.config["volume_spike_multiplier"]:
                    # Throttling
                    alert_key = f"vol_{symbol}"
                    if self._should_throttle(alert_key):
                        return

                    emoji = "🔥" if spike_ratio > 5.0 else "📊"

                    message = (
                        f"{emoji} ВСПЛЕСК ОБЪЁМА\n"
                        f"Пара: {symbol}\n"
                        f"Текущий объём: {current_volume:,.0f}\n"
                        f"Средний объём: {avg_volume:,.0f}\n"
                        f"Множитель: {spike_ratio:.2f}x\n"
                        f"Время: {datetime.now().strftime('%H:%M:%S')}"
                    )

                    await self.send_alert("volume_spike", message, priority="medium")
                    logger.info(f"📊 Volume Spike Alert: {symbol} ({spike_ratio:.2f}x)")
                else:
                    logger.debug(
                        f"   ✅ {symbol}: Всплеска объёма нет ({spike_ratio:.2f}x)"
                    )

            except Exception as e:
                logger.error(f"❌ Ошибка получения свечей для {symbol}: {e}")

        except Exception as e:
            logger.error(f"❌ Ошибка check_volume_spike: {e}")

    async def check_news_alerts(self):
        """Проверка критичных новостных событий"""
        try:
            # Throttling: проверяем новости не чаще раз в 5 минут
            current_time = time.time()
            if current_time - self.last_news_check < 300:  # 5 минут
                return

            self.last_news_check = current_time

            logger.debug(
                f"🔍 Проверка новостных алертов (кэш: {len(self.bot.news_cache)} новостей)..."
            )

            if not self.bot.news_cache:
                logger.debug("   ⚠️ Кэш новостей пуст")
                return

            # Анализируем последние новости (за последний час)
            one_hour_ago = datetime.now() - timedelta(hours=1)
            critical_news = []

            for news in self.bot.news_cache:
                # Проверяем время новости
                news_time = news.get("published_at", "")
                if not news_time:
                    continue

                try:
                    # Парсинг timestamp
                    news_dt = datetime.fromisoformat(news_time.replace("Z", "+00:00"))

                    # Фильтр: новости за последний час
                    if news_dt < one_hour_ago:
                        continue

                    # Проверяем критичные ключевые слова
                    title = news.get("title", "").lower()
                    body = news.get("body", "").lower()
                    text = f"{title} {body}"

                    for keyword in self.config["news_critical_keywords"]:
                        if keyword.lower() in text:
                            sentiment = news.get("sentiment", 0.0)
                            critical_news.append(
                                {
                                    "title": news.get("title", "N/A"),
                                    "keyword": keyword,
                                    "sentiment": sentiment,
                                    "time": news_dt.strftime("%H:%M"),
                                    "source": news.get("source", "Unknown"),
                                }
                            )
                            break  # Одна новость = один алерт

                except Exception as e:
                    logger.debug(f"   ⚠️ Ошибка парсинга новости: {e}")
                    continue

            if critical_news:
                # Throttling
                alert_key = "news_critical"
                if self._should_throttle(alert_key):
                    return

                # Берём топ-3 критичные новости
                top_news = critical_news[:3]

                message = "🚨 КРИТИЧНЫЕ НОВОСТИ\n\n"
                for idx, news in enumerate(top_news, 1):
                    sentiment_emoji = (
                        "🟢"
                        if news["sentiment"] > 0
                        else "🔴" if news["sentiment"] < 0 else "⚪"
                    )
                    message += (
                        f"{idx}. {news['title'][:80]}...\n"
                        f"   Ключ.слово: {news['keyword']}\n"
                        f"   Тон: {sentiment_emoji} {news['sentiment']:.2f}\n"
                        f"   Источник: {news['source']}\n"
                        f"   Время: {news['time']}\n\n"
                    )

                await self.send_alert("news", message, priority="high")
                logger.info(f"🚨 News Alert: {len(critical_news)} критичных новостей")
            else:
                logger.debug(f"   ✅ Критичных новостей не обнаружено")

        except Exception as e:
            logger.error(f"❌ Ошибка check_news_alerts: {e}")

    async def send_alert(self, alert_type: str, message: str, priority: str = "medium"):
        """Отправка алерта в Telegram"""
        try:
            # Обновляем статистику
            self.alerts_count[alert_type] += 1
            self.alerts_count["total"] += 1

            # Логируем
            logger.info(f"📨 Отправка алерта [{alert_type}]: {message[:50]}...")

            # ✅ ИСПРАВЛЕНО: Прямой вызов Telegram API
            if hasattr(self, "bot") and hasattr(self.bot, "telegram_handler"):
                if self.bot.telegram_handler:
                    try:
                        await self.bot.telegram_handler.application.bot.send_message(
                            chat_id=self.bot.telegram_handler.chat_id,
                            text=message,
                            parse_mode="HTML",
                        )
                        logger.info(f"✅ Алерт отправлен в Telegram: {alert_type}")
                    except Exception as e:
                        logger.error(f"❌ Ошибка отправки в Telegram: {e}")
            else:
                logger.warning("⚠️ telegram_handler не найден")

        except Exception as e:
            logger.error(f"❌ Ошибка send_alert: {e}")

    def _should_throttle(self, alert_key: str) -> bool:
        """
        Проверка, нужно ли пропустить алерт (throttling)

        Args:
            alert_key: Ключ алерта (например, "l2_BTCUSDT")

        Returns:
            True если нужно пропустить, False если можно отправить
        """
        current_time = time.time()
        last_time = self.last_alert_time.get(alert_key, 0)

        if current_time - last_time < self.config["throttle_seconds"]:
            remaining = self.config["throttle_seconds"] - (current_time - last_time)
            logger.debug(f"⏸️ Throttle: {alert_key} (осталось {remaining:.0f}s)")
            return True  # Пропускаем

        self.last_alert_time[alert_key] = current_time
        return False  # Отправляем

    def get_alerts_stats(self) -> Dict:
        """Получение статистики алертов"""
        return self.alerts_count.copy()

    async def stop(self):
        """Остановка системы мониторинга"""
        logger.info("🛑 Остановка EnhancedAlertsSystem...")
        # Здесь можно добавить логику graceful shutdown если нужно
