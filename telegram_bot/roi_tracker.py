# -*- coding: utf-8 -*-
"""
Улучшенный трекер ROI с автоматической фиксацией результатов и Telegram уведомлениями
"""

import asyncio
import aiosqlite
from typing import Dict, List, Optional
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from config.settings import logger, DATABASE_PATH

# ✅ ДОБАВЬТЕ ЭТУ ФУНКЦИЮ ЗДЕСЬ
async def init_wal_mode():
    """Включение WAL mode для SQLite (предотвращает блокировки)"""
    try:
        async with aiosqlite.connect(DATABASE_PATH) as db:
            await db.execute("PRAGMA journal_mode=WAL")
            await db.execute("PRAGMA busy_timeout=30000")  # 30 секунд
            await db.commit()
        logger.info("✅ SQLite WAL mode включён")
    except Exception as e:
        logger.error(f"❌ Ошибка включения WAL mode: {e}")


@dataclass
class ROIMetrics:
    """Метрики ROI для сигнала"""

    signal_id: str
    symbol: str
    direction: str
    entry_price: float
    stop_loss: float
    tp1: float
    tp2: float
    tp3: float
    tp1_hit: bool = False
    tp2_hit: bool = False
    tp3_hit: bool = False
    sl_hit: bool = False
    current_roi: float = 0.0
    status: str = "active"
    entry_time: str = field(default_factory=lambda: datetime.now().isoformat())
    close_time: Optional[str] = None
    fills: List[Dict] = field(default_factory=list)
    quality_score: float = 0.0


class ROITracker:
    """Усовершенствованный трекер ROI с автоматическим отслеживанием и Telegram уведомлениями"""

    def __init__(self, telegram_handler=None, bot_instance=None):
        """Инициализация ROI трекера"""
        self.active_signals: Dict[str, ROIMetrics] = {}
        self.completed_signals: List[ROIMetrics] = []
        self.telegram = telegram_handler
        self.bot = bot_instance

        self.tp1_percentage = 0.25
        self.tp2_percentage = 0.50
        self.tp3_percentage = 0.25

        # ✅ Включаем WAL mode
        asyncio.create_task(init_wal_mode())

        logger.info(
            "✅ ROITracker инициализирован с автофиксацией и Telegram уведомлениями"
        )

    async def register_signal(self, signal: Dict) -> str:
        """Регистрация нового сигнала для отслеживания"""
        signal_id = f"{signal['symbol']}_{int(datetime.now().timestamp())}"

        metrics = ROIMetrics(
            signal_id=signal_id,
            symbol=signal["symbol"],
            direction=signal["direction"],
            entry_price=signal["entry_price"],
            stop_loss=signal["stop_loss"],
            tp1=signal.get("tp1", 0),
            tp2=signal.get("tp2", 0),
            tp3=signal.get("tp3", 0),
            quality_score=signal.get("quality_score", 0),
        )

        self.active_signals[signal_id] = metrics
        await self._save_signal_to_db(metrics)

        logger.info(f"📝 Зарегистрирован сигнал {signal_id} для отслеживания ROI")
        return signal_id

    async def update_signal_price(
        self, signal_id: str, current_price: float
    ) -> Optional[Dict]:
        """Обновление цены и проверка достижения TP/SL"""
        if signal_id not in self.active_signals:
            return None

        metrics = self.active_signals[signal_id]
        event = None

        if metrics.direction == "long":
            if not metrics.tp3_hit and current_price >= metrics.tp3:
                metrics.tp3_hit = True
                event = await self._handle_tp_hit(metrics, "tp3", current_price)
            elif not metrics.tp2_hit and current_price >= metrics.tp2:
                metrics.tp2_hit = True
                event = await self._handle_tp_hit(metrics, "tp2", current_price)
            elif not metrics.tp1_hit and current_price >= metrics.tp1:
                metrics.tp1_hit = True
                event = await self._handle_tp_hit(metrics, "tp1", current_price)
            elif not metrics.sl_hit and current_price <= metrics.stop_loss:
                metrics.sl_hit = True
                event = await self._handle_sl_hit(metrics, current_price)

        elif metrics.direction == "short":
            if not metrics.tp3_hit and current_price <= metrics.tp3:
                metrics.tp3_hit = True
                event = await self._handle_tp_hit(metrics, "tp3", current_price)
            elif not metrics.tp2_hit and current_price <= metrics.tp2:
                metrics.tp2_hit = True
                event = await self._handle_tp_hit(metrics, "tp2", current_price)
            elif not metrics.tp1_hit and current_price <= metrics.tp1:
                metrics.tp1_hit = True
                event = await self._handle_tp_hit(metrics, "tp1", current_price)
            elif not metrics.sl_hit and current_price >= metrics.stop_loss:
                metrics.sl_hit = True
                event = await self._handle_sl_hit(metrics, current_price)

        metrics.current_roi = await self._calculate_current_roi(metrics, current_price)
        await self._update_signal_in_db(metrics)

        return event

    async def _handle_tp_hit(
        self, metrics: ROIMetrics, tp_level: str, price: float
    ) -> Dict:
        """Обработка достижения Take Profit"""
        if tp_level == "tp1":
            close_percent = self.tp1_percentage
        elif tp_level == "tp2":
            close_percent = self.tp2_percentage
        else:
            close_percent = self.tp3_percentage

        if metrics.entry_price == 0:
            logger.error(f"❌ Entry price = 0 для {metrics.symbol}, пропускаем TP")
            return {
                "type": "error",
                "signal_id": metrics.signal_id,
                "reason": "entry_price_zero",
            }

        if metrics.direction == "long":
            profit_percent = ((price - metrics.entry_price) / metrics.entry_price) * 100
        else:
            profit_percent = ((metrics.entry_price - price) / metrics.entry_price) * 100

        weighted_profit = profit_percent * close_percent

        fill = {
            "level": tp_level,
            "price": price,
            "percentage": close_percent,
            "profit_percent": profit_percent,
            "weighted_profit": weighted_profit,
            "timestamp": datetime.now().isoformat(),
        }

        metrics.fills.append(fill)

        logger.info(
            f"✅ {tp_level.upper()} достигнут для {metrics.signal_id}! Цена: {price}, Прибыль: +{profit_percent:.2f}% (взвешенная: +{weighted_profit:.2f}%)"
        )

        await self._send_tp_notification(metrics, tp_level, price, profit_percent)

        if tp_level == "tp3" or (
            metrics.tp1_hit and metrics.tp2_hit and metrics.tp3_hit
        ):
            await self._close_signal(metrics, "completed")

        return {
            "type": "tp_hit",
            "signal_id": metrics.signal_id,
            "level": tp_level,
            "price": price,
            "profit": weighted_profit,
        }

    async def _handle_sl_hit(self, metrics: ROIMetrics, price: float) -> Dict:
        """Обработка достижения Stop Loss"""

        if metrics.entry_price == 0:
            logger.error(f"❌ Entry price = 0 для {metrics.symbol}, пропускаем SL")
            return {
                "type": "error",
                "signal_id": metrics.signal_id,
                "reason": "entry_price_zero",
            }

        if metrics.direction == "long":
            loss_percent = ((price - metrics.entry_price) / metrics.entry_price) * 100
        else:
            loss_percent = ((metrics.entry_price - price) / metrics.entry_price) * 100

        closed_percent = sum(
            [
                self.tp1_percentage if metrics.tp1_hit else 0,
                self.tp2_percentage if metrics.tp2_hit else 0,
                self.tp3_percentage if metrics.tp3_hit else 0,
            ]
        )

        remaining_percent = 1.0 - closed_percent
        weighted_loss = loss_percent * remaining_percent

        fill = {
            "level": "stop_loss",
            "price": price,
            "percentage": remaining_percent,
            "profit_percent": loss_percent,
            "weighted_profit": weighted_loss,
            "timestamp": datetime.now().isoformat(),
        }

        metrics.fills.append(fill)

        logger.warning(
            f"🛑 STOP LOSS достигнут для {metrics.signal_id}! Цена: {price}, Убыток: {weighted_loss:.2f}%"
        )

        await self._send_stop_notification(metrics, price, weighted_loss)
        await self._close_signal(metrics, "stopped")

        return {
            "type": "sl_hit",
            "signal_id": metrics.signal_id,
            "price": price,
            "loss": weighted_loss,
        }

    async def _send_tp_notification(
        self, metrics: ROIMetrics, tp_level: str, price: float, profit_percent: float
    ):
        """Отправка Telegram уведомления о достижении TP"""
        if not self.telegram:
            return

        try:
            is_risky = metrics.quality_score < 50

            if tp_level == "tp1":
                if is_risky:
                    message = (
                        f"🎯 TP1 ДОСТИГНУТ (RISKY ENTRY) 🎯\n\n"
                        f"⚠️ Повышенный риск!\n\n"
                        f"📊 {metrics.symbol} {metrics.direction.upper()}\n"
                        f"💰 Entry: ${metrics.entry_price:.2f}\n"
                        f"📈 Current: ${price:.2f}\n"
                        f"🎯 TP1: ${metrics.tp1:.2f}\n"
                        f"💵 Profit: {profit_percent:.2f}%\n\n"
                        f"✅ Рекомендация:\n"
                        f"   • Зафиксируй 50% позиции\n"
                        f"   • Переведи стоп в безубыток\n"
                        f"   • Остаток держим до TP2"
                    )
                else:
                    message = (
                        f"🎯 TP1 ДОСТИГНУТ 🎯\n\n"
                        f"📊 {metrics.symbol} {metrics.direction.upper()}\n"
                        f"💰 Entry: ${metrics.entry_price:.2f}\n"
                        f"📈 Current: ${price:.2f}\n"
                        f"🎯 TP1: ${metrics.tp1:.2f}\n"
                        f"💵 Profit: {profit_percent:.2f}%\n\n"
                        f"✅ Рекомендация:\n"
                        f"   • Зафиксируй 25% позиции\n"
                        f"   • Переведи стоп в безубыток\n"
                        f"   • Остаток держим до TP2"
                    )
            elif tp_level == "tp2":
                message = (
                    f"🎯 TP2 ДОСТИГНУТ 🎯\n\n"
                    f"📊 {metrics.symbol} {metrics.direction.upper()}\n"
                    f"💰 Entry: ${metrics.entry_price:.2f}\n"
                    f"📈 Current: ${price:.2f}\n"
                    f"🎯 TP2: ${metrics.tp2:.2f}\n"
                    f"💵 Profit: {profit_percent:.2f}%\n\n"
                    f"✅ Рекомендация:\n"
                    f"   • Зафиксируй 50% позиции\n"
                    f"   • Остаток держим до TP3\n"
                    f"   • Стоп уже в безубытке"
                )
            else:
                message = (
                    f"🎯 TP3 ДОСТИГНУТ 🎯\n\n"
                    f"📊 {metrics.symbol} {metrics.direction.upper()}\n"
                    f"💰 Entry: ${metrics.entry_price:.2f}\n"
                    f"📈 Current: ${price:.2f}\n"
                    f"🎯 TP3: ${metrics.tp3:.2f}\n"
                    f"💵 Profit: {profit_percent:.2f}%\n\n"
                    f"✅ Рекомендация:\n"
                    f"   • Трейлим остаток (trailing stop)\n"
                    f"   • Или фиксируем полностью\n"
                    f"   • Сделка успешна! 🎉"
                )

            await self.telegram.send_alert(message)
            logger.info(
                f"✅ Отправлено Telegram уведомление {tp_level.upper()} для {metrics.symbol}"
            )
        except Exception as e:
            logger.error(f"❌ Ошибка отправки Telegram уведомления TP: {e}")

    async def _send_stop_notification(
        self, metrics: ROIMetrics, price: float, loss_percent: float
    ):
        """Отправка Telegram уведомления об активации стопа"""
        if not self.telegram:
            return

        try:
            message = (
                f"🛑 СТОП АКТИВИРОВАН 🛑\n\n"
                f"📊 {metrics.symbol} {metrics.direction.upper()}\n"
                f"💰 Entry: ${metrics.entry_price:.2f}\n"
                f"📉 Current: ${price:.2f}\n"
                f"🛑 Stop Loss: ${metrics.stop_loss:.2f}\n"
                f"💸 Loss: {loss_percent:.2f}%\n\n"
                f"❌ Сделка закрыта\n"
                f"   • Убыток зафиксирован\n"
                f"   • Анализируем причины\n"
                f"   • Ждём новую возможность"
            )

            await self.telegram.send_alert(message)
            logger.info(f"✅ Отправлено Telegram уведомление STOP для {metrics.symbol}")
        except Exception as e:
            logger.error(f"❌ Ошибка отправки Telegram уведомления STOP: {e}")

    async def _calculate_current_roi(
        self, metrics: ROIMetrics, current_price: float
    ) -> float:
        """Расчёт текущего ROI"""
        closed_roi = sum([fill["weighted_profit"] for fill in metrics.fills])

        closed_percent = sum(
            [
                self.tp1_percentage if metrics.tp1_hit else 0,
                self.tp2_percentage if metrics.tp2_hit else 0,
                self.tp3_percentage if metrics.tp3_hit else 0,
            ]
        )

        remaining_percent = 1.0 - closed_percent

        if remaining_percent > 0:

            if metrics.entry_price == 0:
                logger.warning(
                    f"⚠️ Entry price = 0 для {metrics.symbol}, возвращаем closed_roi = {closed_roi:.2f}%"
                )
                return closed_roi

            if metrics.direction == "long":
                unrealized_profit = (
                    (current_price - metrics.entry_price) / metrics.entry_price
                ) * 100
            else:
                unrealized_profit = (
                    (metrics.entry_price - current_price) / metrics.entry_price
                ) * 100

            unrealized_roi = unrealized_profit * remaining_percent
        else:
            unrealized_roi = 0.0

        return closed_roi + unrealized_roi

    async def _close_signal(self, metrics: ROIMetrics, status: str):
        """Закрытие сигнала"""
        metrics.status = status
        metrics.close_time = datetime.now().isoformat()

        final_roi = sum([fill["weighted_profit"] for fill in metrics.fills])
        metrics.current_roi = final_roi

        self.completed_signals.append(metrics)
        del self.active_signals[metrics.signal_id]

        await self._update_signal_in_db(metrics, final=True)

        logger.info(
            f"🏁 Сигнал {metrics.signal_id} закрыт. Статус: {status}, Финальный ROI: {final_roi:+.2f}%"
        )

    async def get_statistics(self, days: int = 30) -> Dict:
        """Получение статистики ROI"""
        cutoff_date = datetime.now() - timedelta(days=days)

        recent_signals = [
            s
            for s in self.completed_signals
            if s.close_time and datetime.fromisoformat(s.close_time) > cutoff_date
        ]

        if not recent_signals:
            return {
                "total_signals": 0,
                "win_rate": 0.0,
                "average_roi": 0.0,
                "total_roi": 0.0,
            }

        total = len(recent_signals)
        wins = len([s for s in recent_signals if s.current_roi > 0])
        losses = len([s for s in recent_signals if s.current_roi <= 0])

        win_rate = (wins / total) * 100 if total > 0 else 0
        average_roi = sum([s.current_roi for s in recent_signals]) / total
        total_roi = sum([s.current_roi for s in recent_signals])

        return {
            "total_signals": total,
            "wins": wins,
            "losses": losses,
            "win_rate": win_rate,
            "average_roi": average_roi,
            "total_roi": total_roi,
            "period_days": days,
        }

    async def _save_signal_to_db(self, metrics: ROIMetrics):
        """Сохранение сигнала в БД"""
        try:
            async with aiosqlite.connect(DATABASE_PATH) as db:
                await db.execute(
                    """
                    INSERT INTO signals (
                        symbol, direction, entry_price, stop_loss,
                        tp1, tp2, tp3, status, timestamp
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                    (
                        metrics.symbol,
                        metrics.direction,
                        metrics.entry_price,
                        metrics.stop_loss,
                        metrics.tp1,
                        metrics.tp2,
                        metrics.tp3,
                        metrics.status,
                        metrics.entry_time,
                    ),
                )
                await db.commit()
        except Exception as e:
            logger.error(f"❌ Ошибка сохранения сигнала в БД: {e}")

    async def _update_signal_in_db(self, metrics: ROIMetrics, final: bool = False):
        """Обновление сигнала в БД с retry при блокировке"""
        max_retries = 10
        retry_delay = 0.2

        for attempt in range(max_retries):
            try:
                async with aiosqlite.connect(DATABASE_PATH, timeout=30.0) as db:
                    if final:
                        await db.execute(
                            """
                            UPDATE signals
                            SET status = ?, roi = ?, close_time = ?
                            WHERE symbol = ? AND timestamp = ?
                        """,
                            (
                                metrics.status,
                                metrics.current_roi,
                                metrics.close_time,
                                metrics.symbol,
                                metrics.entry_time,
                            ),
                        )
                    else:
                        await db.execute(
                            """
                            UPDATE signals
                            SET roi = ?, tp1_hit = ?, tp2_hit = ?, tp3_hit = ?, sl_hit = ?
                            WHERE symbol = ? AND timestamp = ?
                        """,
                            (
                                metrics.current_roi,
                                metrics.tp1_hit,
                                metrics.tp2_hit,
                                metrics.tp3_hit,
                                metrics.sl_hit,
                                metrics.symbol,
                                metrics.entry_time,
                            ),
                        )
                    await db.commit()
                    return

            except aiosqlite.OperationalError as e:
                if "database is locked" in str(e) and attempt < max_retries - 1:
                    await asyncio.sleep(retry_delay * (2**attempt))
                    logger.warning(
                        f"⚠️ БД заблокирована, попытка {attempt + 1}/{max_retries}, ждём {retry_delay * (2 ** attempt):.2f}s"
                    )
                    continue
                else:
                    logger.error(f"❌ Ошибка обновления сигнала в БД: {e}")
                    break
            except Exception as e:
                logger.error(f"❌ Ошибка обновления сигнала в БД: {e}")
                break

    async def start_monitoring(self):
        """Запуск Real-Time мониторинга"""
        logger.info("🚀 Запуск Real-Time мониторинга ROI...")

        await self._load_active_signals_from_db()

        for signal_id, metrics in self.active_signals.items():
            asyncio.create_task(self._monitor_signal(signal_id))

        logger.info(
            f"✅ Мониторинг запущен для {len(self.active_signals)} активных сигналов"
        )

    async def _monitor_signal(self, signal_id: str):
        """Мониторинг одного сигнала"""
        try:
            logger.info(f"🔍 Запуск мониторинга сигнала {signal_id}")

            while signal_id in self.active_signals:
                metrics = self.active_signals[signal_id]
                symbol = metrics.symbol

                try:
                    current_price = await self._get_current_price(symbol)

                    if current_price:
                        event = await self.update_signal_price(signal_id, current_price)

                        if event:
                            logger.info(f"🎯 Событие для {signal_id}: {event['type']}")

                except Exception as e:
                    logger.error(f"❌ Ошибка получения цены {symbol}: {e}")

                await asyncio.sleep(15)

        except asyncio.CancelledError:
            logger.info(f"🛑 Мониторинг {signal_id} остановлен")
        except Exception as e:
            logger.error(f"❌ Критическая ошибка мониторинга {signal_id}: {e}")

    async def _get_current_price(self, symbol: str) -> Optional[float]:
        """Получение текущей цены из REST API"""
        try:
            if not hasattr(self, "bot") or not self.bot:
                logger.warning(f"⚠️ Bot instance не найден для получения цены {symbol}")
                return None

            if hasattr(self.bot, "binance_connector") and self.bot.binance_connector:
                try:
                    ticker = await self.bot.binance_connector.get_ticker(symbol)
                    if ticker and "price" in ticker:
                        price = float(ticker["price"])
                        if price > 0:
                            logger.debug(f"💰 {symbol}: ${price:.2f} (Binance API)")
                            return price
                except Exception as e:
                    logger.warning(f"⚠️ Binance API error for {symbol}: {e}")

            if hasattr(self.bot, "bybit_connector") and self.bot.bybit_connector:
                try:
                    ticker = await self.bot.bybit_connector.get_ticker(symbol)
                    if ticker:
                        price = float(
                            ticker.get("lastPrice", 0) or ticker.get("last_price", 0)
                        )
                        if price > 0:
                            logger.debug(f"💰 {symbol}: ${price:.2f} (Bybit API)")
                            return price
                except Exception as e:
                    logger.warning(f"⚠️ Bybit API error for {symbol}: {e}")

            logger.warning(f"⚠️ Не удалось получить цену для {symbol}")
            return None

        except Exception as e:
            logger.error(f"❌ Ошибка _get_current_price для {symbol}: {e}")
            return None

    async def _load_active_signals_from_db(self):
        """Загрузка активных сигналов из БД"""
        try:
            async with aiosqlite.connect(DATABASE_PATH) as db:
                cursor = await db.execute(
                    """
                    SELECT id, symbol, direction, entry_price, stop_loss,
                        tp1, tp2, tp3, status, timestamp
                    FROM signals
                    WHERE status = 'active'
                    ORDER BY id DESC
                """
                )

                rows = await cursor.fetchall()

                for row in rows:
                    signal_id = f"{row[1]}_{row[0]}"

                    if row[3] == 0 or row[3] is None:
                        logger.warning(
                            f"⚠️ Пропускаем сигнал {signal_id}: entry_price = {row[3]}"
                        )
                        continue

                    metrics = ROIMetrics(
                        signal_id=signal_id,
                        symbol=row[1],
                        direction=row[2],
                        entry_price=row[3],
                        stop_loss=row[4],
                        tp1=row[5],
                        tp2=row[6],
                        tp3=row[7],
                        status=row[8],
                        entry_time=row[9] or datetime.now().isoformat(),
                    )

                    self.active_signals[signal_id] = metrics
                    logger.info(
                        f"📝 Загружен сигнал {signal_id}: {metrics.symbol} {metrics.direction} @ ${metrics.entry_price:.2f}"
                    )

                logger.info(
                    f"✅ Загружено {len(self.active_signals)} активных сигналов из БД"
                )

        except Exception as e:
            logger.error(f"❌ Ошибка загрузки активных сигналов из БД: {e}")
            import traceback

            logger.error(traceback.format_exc())

    async def stop_monitoring(self):
        """Остановка мониторинга"""
        logger.info("🛑 Остановка мониторинга ROI...")
        self.active_signals.clear()
        logger.info("✅ Мониторинг ROI остановлен")
