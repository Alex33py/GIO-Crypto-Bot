#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
WebSocket L2 Orderbook для Bybit
"""

import asyncio
import websockets
import json
from typing import Dict, Callable
from config.settings import logger


class BybitOrderbookWebSocket:
    """WebSocket подключение для L2 Orderbook Bybit"""

    def __init__(self, symbol: str, depth: int = 50):
        """
        Args:
            symbol: Торговая пара (например, BTCUSDT)
            depth: Глубина стакана (1, 50, 200)
        """
        self.symbol = symbol
        self.depth = depth
        self.ws_url = "wss://stream.bybit.com/v5/public/spot"
        self.orderbook = {"bids": [], "asks": []}
        self.callbacks = []
        self.is_running = False

    async def connect(self):
        """Подключение к WebSocket"""
        try:
            async with websockets.connect(self.ws_url) as websocket:
                # Подписываемся на orderbook
                subscribe_msg = {
                    "op": "subscribe",
                    "args": [f"orderbook.{self.depth}.{self.symbol}"]
                }
                await websocket.send(json.dumps(subscribe_msg))
                logger.info(f"✅ Подключено к L2 Orderbook: {self.symbol}")

                self.is_running = True

                # Получаем обновления
                async for message in websocket:
                    try:
                        data = json.loads(message)

                        if "data" in data:
                            # Обновляем orderbook
                            self._update_orderbook(data["data"])

                            # Вызываем callbacks
                            for callback in self.callbacks:
                                await callback(self.orderbook)

                    except Exception as e:
                        logger.error(f"❌ Ошибка обработки сообщения: {e}")

        except Exception as e:
            logger.error(f"❌ Ошибка WebSocket L2: {e}")
            self.is_running = False

    def _update_orderbook(self, data: Dict):
        """Обновление orderbook"""
        try:
            if "b" in data:  # bids
                self.orderbook["bids"] = [[float(p), float(q)] for p, q in data["b"]]

            if "a" in data:  # asks
                self.orderbook["asks"] = [[float(p), float(q)] for p, q in data["a"]]

        except Exception as e:
            logger.error(f"❌ Ошибка обновления orderbook: {e}")

    def add_callback(self, callback: Callable):
        """Добавить callback для обработки обновлений"""
        self.callbacks.append(callback)

    async def start(self):
        """Запуск WebSocket в фоне"""
        asyncio.create_task(self.connect())
