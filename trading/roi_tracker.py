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
    status: str = 'active'
    entry_time: str = field(default_factory=lambda: datetime.now().isoformat())
    close_time: Optional[str] = None
    fills: List[Dict] = field(default_factory=list)
    quality_score: float = 0.0  # Добавлено для risky entry detection


class ROITracker:
    """Усовершенствованный трекер ROI с автоматическим отслеживанием и Telegram уведомлениями"""

    def __init__(self, telegram_handler=None):
        """Инициализация ROI трекера"""
        self.active_signals: Dict[str, ROIMetrics] = {}
        self.completed_signals: List[ROIMetrics] = []

        # Telegram handler для отправки уведомлений
        self.telegram = telegram_handler

        # Настройки фиксации прибыли
        self.tp1_percentage = 0.25  # 25% позиции на TP1
        self.tp2_percentage = 0.50  # 50% позиции на TP2
        self.tp3_percentage = 0.25  # 25% позиции на TP3

        logger.info("✅ ROITracker инициализирован с автофиксацией и Telegram уведомлениями")

    async def register_signal(self, signal: Dict) -> str:
        """
        Регистрация нового сигнала для отслеживания
        """
        signal_id = f"{signal['symbol']}_{int(datetime.now().timestamp())}"

        metrics = ROIMetrics(
            signal_id=signal_id,
            symbol=signal['symbol'],
            direction=signal['direction'],
            entry_price=signal['entry_price'],
            stop_loss=signal['stop_loss'],
            tp1=signal.get('tp1', 0),
            tp2=signal.get('tp2', 0),
            tp3=signal.get('tp3', 0),
            quality_score=signal.get('quality_score', 0)  # Добавлено
        )

        self.active_signals[signal_id] = metrics

        # Сохраняем в БД
        await self._save_signal_to_db(metrics)

        logger.info(f"📝 Зарегистрирован сигнал {signal_id} для отслеживания ROI")
        return signal_id

    async def update_signal_price(self, signal_id: str, current_price: float) -> Optional[Dict]:
        """
        Обновление цены и проверка достижения TP/SL
        Возвращает событие если TP/SL достигнут
        """
        if signal_id not in self.active_signals:
            return None

        metrics = self.active_signals[signal_id]

        # Проверяем TP/SL
        event = None

        if metrics.direction == 'long':
            # Для лонга
            # TP3 (самая высокая цель)
            if not metrics.tp3_hit and current_price >= metrics.tp3:
                metrics.tp3_hit = True
                event = await self._handle_tp_hit(metrics, 'tp3', current_price)

            # TP2
            elif not metrics.tp2_hit and current_price >= metrics.tp2:
                metrics.tp2_hit = True
                event = await self._handle_tp_hit(metrics, 'tp2', current_price)

            # TP1
            elif not metrics.tp1_hit and current_price >= metrics.tp1:
                metrics.tp1_hit = True
                event = await self._handle_tp_hit(metrics, 'tp1', current_price)

            # Stop Loss
            elif not metrics.sl_hit and current_price <= metrics.stop_loss:
                metrics.sl_hit = True
                event = await self._handle_sl_hit(metrics, current_price)

        elif metrics.direction == 'short':
            # Для шорта
            # TP3 (самая низкая цель)
            if not metrics.tp3_hit and current_price <= metrics.tp3:
                metrics.tp3_hit = True
                event = await self._handle_tp_hit(metrics, 'tp3', current_price)

            # TP2
            elif not metrics.tp2_hit and current_price <= metrics.tp2:
                metrics.tp2_hit = True
                event = await self._handle_tp_hit(metrics, 'tp2', current_price)

            # TP1
            elif not metrics.tp1_hit and current_price <= metrics.tp1:
                metrics.tp1_hit = True
                event = await self._handle_tp_hit(metrics, 'tp1', current_price)

            # Stop Loss
            elif not metrics.sl_hit and current_price >= metrics.stop_loss:
                metrics.sl_hit = True
                event = await self._handle_sl_hit(metrics, current_price)

        # Пересчитываем текущий ROI
        metrics.current_roi = await self._calculate_current_roi(metrics, current_price)

        # Обновляем в БД
        await self._update_signal_in_db(metrics)

        return event

    async def _handle_tp_hit(self, metrics: ROIMetrics, tp_level: str, price: float) -> Dict:
        """Обработка достижения Take Profit с отправкой Telegram уведомления"""

        # Определяем процент закрытия позиции
        if tp_level == 'tp1':
            close_percent = self.tp1_percentage
        elif tp_level == 'tp2':
            close_percent = self.tp2_percentage
        else:  # tp3
            close_percent = self.tp3_percentage

        # Рассчитываем прибыль
        if metrics.direction == 'long':
            profit_percent = ((price - metrics.entry_price) / metrics.entry_price) * 100
        else:
            profit_percent = ((metrics.entry_price - price) / metrics.entry_price) * 100

        weighted_profit = profit_percent * close_percent

        # Сохраняем фиксацию
        fill = {
            'level': tp_level,
            'price': price,
            'percentage': close_percent,
            'profit_percent': profit_percent,
            'weighted_profit': weighted_profit,
            'timestamp': datetime.now().isoformat()
        }

        metrics.fills.append(fill)

        logger.info(f"✅ {tp_level.upper()} достигнут для {metrics.signal_id}! Цена: {price}, Прибыль: +{profit_percent:.2f}% (взвешенная: +{weighted_profit:.2f}%)")

        # ✅ ОТПРАВКА TELEGRAM УВЕДОМЛЕНИЯ
        await self._send_tp_notification(metrics, tp_level, price, profit_percent)

        # Если это TP3 или все TP достигнуты, закрываем сигнал
        if tp_level == 'tp3' or (metrics.tp1_hit and metrics.tp2_hit and metrics.tp3_hit):
            await self._close_signal(metrics, 'completed')

        return {
            'type': 'tp_hit',
            'signal_id': metrics.signal_id,
            'level': tp_level,
            'price': price,
            'profit': weighted_profit
        }

    async def _handle_sl_hit(self, metrics: ROIMetrics, price: float) -> Dict:
        """Обработка достижения Stop Loss с отправкой Telegram уведомления"""

        # Рассчитываем убыток
        if metrics.direction == 'long':
            loss_percent = ((price - metrics.entry_price) / metrics.entry_price) * 100
        else:
            loss_percent = ((metrics.entry_price - price) / metrics.entry_price) * 100

        # Определяем оставшийся процент позиции
        closed_percent = sum([
            self.tp1_percentage if metrics.tp1_hit else 0,
            self.tp2_percentage if metrics.tp2_hit else 0,
            self.tp3_percentage if metrics.tp3_hit else 0
        ])

        remaining_percent = 1.0 - closed_percent
        weighted_loss = loss_percent * remaining_percent

        fill = {
            'level': 'stop_loss',
            'price': price,
            'percentage': remaining_percent,
            'profit_percent': loss_percent,
            'weighted_profit': weighted_loss,
            'timestamp': datetime.now().isoformat()
        }

        metrics.fills.append(fill)

        logger.warning(f"🛑 STOP LOSS достигнут для {metrics.signal_id}! Цена: {price}, Убыток: {weighted_loss:.2f}%")

        # ✅ ОТПРАВКА TELEGRAM УВЕДОМЛЕНИЯ
        await self._send_stop_notification(metrics, price, weighted_loss)

        # Закрываем сигнал
        await self._close_signal(metrics, 'stopped')

        return {
            'type': 'sl_hit',
            'signal_id': metrics.signal_id,
            'price': price,
            'loss': weighted_loss
        }

    async def _send_tp_notification(self, metrics: ROIMetrics, tp_level: str, price: float, profit_percent: float):
        """Отправка Telegram уведомления о достижении TP"""
        if not self.telegram:
            return

        try:
            # Проверка на risky entry
            is_risky = metrics.quality_score < 50

            if tp_level == 'tp1':
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

            elif tp_level == 'tp2':
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

            else:  # tp3
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
            logger.info(f"✅ Отправлено Telegram уведомление {tp_level.upper()} для {metrics.symbol}")

        except Exception as e:
            logger.error(f"❌ Ошибка отправки Telegram уведомления TP: {e}")

    async def _send_stop_notification(self, metrics: ROIMetrics, price: float, loss_percent: float):
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

    async def _calculate_current_roi(self, metrics: ROIMetrics, current_price: float) -> float:
        """Расчёт текущего ROI с учётом закрытых частей"""

        # ROI от закрытых частей
        closed_roi = sum([fill['weighted_profit'] for fill in metrics.fills])

        # ROI от открытой части
        closed_percent = sum([
            self.tp1_percentage if metrics.tp1_hit else 0,
            self.tp2_percentage if metrics.tp2_hit else 0,
            self.tp3_percentage if metrics.tp3_hit else 0
        ])

        remaining_percent = 1.0 - closed_percent

        if remaining_percent > 0:
            if metrics.direction == 'long':
                unrealized_profit = ((current_price - metrics.entry_price) / metrics.entry_price) * 100
            else:
                unrealized_profit = ((metrics.entry_price - current_price) / metrics.entry_price) * 100

            unrealized_roi = unrealized_profit * remaining_percent
        else:
            unrealized_roi = 0.0

        total_roi = closed_roi + unrealized_roi

        return total_roi

    async def _close_signal(self, metrics: ROIMetrics, status: str):
        """Закрытие сигнала и перенос в completed"""
        metrics.status = status
        metrics.close_time = datetime.now().isoformat()

        # Финальный ROI
        final_roi = sum([fill['weighted_profit'] for fill in metrics.fills])
        metrics.current_roi = final_roi

        # Переносим в completed
        self.completed_signals.append(metrics)
        del self.active_signals[metrics.signal_id]

        # Обновляем в БД
        await self._update_signal_in_db(metrics, final=True)

        logger.info(f"🏁 Сигнал {metrics.signal_id} закрыт. Статус: {status}, Финальный ROI: {final_roi:+.2f}%")

    async def get_statistics(self, days: int = 30) -> Dict:
        """Получение статистики ROI за период"""

        cutoff_date = datetime.now() - timedelta(days=days)

        # Фильтруем сигналы за период
        recent_signals = [
            s for s in self.completed_signals
            if s.close_time and datetime.fromisoformat(s.close_time) > cutoff_date
        ]

        if not recent_signals:
            return {
                'total_signals': 0,
                'win_rate': 0.0,
                'average_roi': 0.0,
                'total_roi': 0.0
            }

        # Статистика
        total = len(recent_signals)
        wins = len([s for s in recent_signals if s.current_roi > 0])
        losses = len([s for s in recent_signals if s.current_roi <= 0])

        win_rate = (wins / total) * 100 if total > 0 else 0
        average_roi = sum([s.current_roi for s in recent_signals]) / total
        total_roi = sum([s.current_roi for s in recent_signals])

        return {
            'total_signals': total,
            'wins': wins,
            'losses': losses,
            'win_rate': win_rate,
            'average_roi': average_roi,
            'total_roi': total_roi,
            'period_days': days
        }

    async def _save_signal_to_db(self, metrics: ROIMetrics):
        """Сохранение сигнала в БД"""
        try:
            async with aiosqlite.connect(DATABASE_PATH) as db:
                await db.execute("""
                    INSERT INTO signals (
                        signal_id, symbol, side, entry_price, stop_loss,
                        tp1, tp2, tp3, status, timestamp
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    metrics.signal_id, metrics.symbol, metrics.direction,
                    metrics.entry_price, metrics.stop_loss,
                    metrics.tp1, metrics.tp2, metrics.tp3,
                    metrics.status, metrics.entry_time
                ))
                await db.commit()
        except Exception as e:
            logger.error(f"❌ Ошибка сохранения сигнала в БД: {e}")

    async def _update_signal_in_db(self, metrics: ROIMetrics, final: bool = False):
        """Обновление сигнала в БД"""
        try:
            async with aiosqlite.connect(DATABASE_PATH) as db:
                if final:
                    await db.execute("""
                        UPDATE signals
                        SET status = ?, roi = ?, close_time = ?
                        WHERE signal_id = ?
                    """, (metrics.status, metrics.current_roi, metrics.close_time, metrics.signal_id))
                else:
                    await db.execute("""
                        UPDATE signals
                        SET roi = ?, tp1_hit = ?, tp2_hit = ?, tp3_hit = ?, sl_hit = ?
                        WHERE signal_id = ?
                    """, (
                        metrics.current_roi, metrics.tp1_hit, metrics.tp2_hit,
                        metrics.tp3_hit, metrics.sl_hit, metrics.signal_id
                    ))
                await db.commit()
        except Exception as e:
            logger.error(f"❌ Ошибка обновления сигнала в БД: {e}")
