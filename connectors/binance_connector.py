#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Enhanced Binance Connector для GIO Crypto Bot
Полная реализация Binance Spot API с валидацией данных
"""

import asyncio
import aiohttp
from typing import Dict, List, Optional
from datetime import datetime
from config.settings import logger
from utils.validators import DataValidator


class EnhancedBinanceConnector:
    """
    Полнофункциональный коннектор к Binance Spot API
    Аналог EnhancedBybitConnector
    """

    def __init__(self, api_key: Optional[str] = None, api_secret: Optional[str] = None):
        """
        Инициализация Binance коннектора

        Args:
            api_key: API ключ Binance (опционально для публичных endpoints)
            api_secret: API секрет Binance
        """
        self.base_url = "https://api.binance.com"
        self.api_key = api_key
        self.api_secret = api_secret
        self.session = None
        self.is_initialized = False

        logger.info("✅ EnhancedBinanceConnector инициализирован")

    async def initialize(self) -> bool:
        """
        Инициализация HTTP сессии и проверка подключения

        Returns:
            True если успешно
        """
        try:
            # Создаём aiohttp сессию
            self.session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=30)
            )

            # Проверяем подключение
            server_time = await self.get_server_time()

            if server_time:
                self.is_initialized = True
                logger.info("✅ Подключение к Binance API успешно")
                return True
            else:
                logger.error("❌ Не удалось подключиться к Binance API")
                return False

        except Exception as e:
            logger.error(f"❌ Ошибка инициализации Binance: {e}")
            return False

    async def get_server_time(self) -> Optional[int]:
        """
        Получить время сервера Binance

        Returns:
            Timestamp в миллисекундах или None
        """
        url = f"{self.base_url}/api/v3/time"

        try:
            async with self.session.get(url) as response:
                if response.status == 200:
                    data = await response.json()
                    return data['serverTime']
                else:
                    logger.error(f"❌ Binance server time ошибка: {response.status}")
                    return None

        except Exception as e:
            logger.error(f"❌ Ошибка get_server_time: {e}")
            return None

    async def get_klines(
        self,
        symbol: str,
        interval: str,
        limit: int = 100
    ) -> List[Dict]:
        """
        Получить исторические свечи (klines/candlesticks)

        Args:
            symbol: Торговая пара (например: BTCUSDT)
            interval: Интервал свечей (1m, 3m, 5m, 15m, 30m, 1h, 2h, 4h, 6h, 8h, 12h, 1d, 3d, 1w, 1M)
            limit: Количество свечей (макс 1000)

        Returns:
            Список словарей с данными свечей
        """
        url = f"{self.base_url}/api/v3/klines"

        params = {
            'symbol': symbol,
            'interval': interval,
            'limit': min(limit, 1000)  # Binance лимит 1000
        }

        try:
            async with self.session.get(url, params=params) as response:
                if response.status == 200:
                    data = await response.json()

                    # Преобразуем в стандартный формат
                    candles = []
                    for item in data:
                        candle = {
                            'timestamp': int(item[0]),
                            'open': float(item[1]),
                            'high': float(item[2]),
                            'low': float(item[3]),
                            'close': float(item[4]),
                            'volume': float(item[5]),
                            'close_time': int(item[6]),
                            'quote_volume': float(item[7]),
                            'trades': int(item[8])
                        }

                        # Валидация свечи
                        if DataValidator.validate_candle(candle):
                            candles.append(candle)
                        else:
                            logger.warning(f"⚠️ Невалидная свеча {symbol} отброшена")

                    logger.debug(f"✅ Получено {len(candles)} валидных свечей {symbol} ({interval})")
                    return candles

                elif response.status == 429:
                    logger.warning(f"⚠️ Binance rate limit превышен для {symbol}")
                    return []

                else:
                    logger.error(f"❌ Binance API ошибка {response.status} для {symbol}")
                    return []

        except asyncio.TimeoutError:
            logger.error(f"❌ Timeout при запросе свечей {symbol}")
            return []

        except Exception as e:
            logger.error(f"❌ Ошибка get_klines {symbol}: {e}")
            return []

    async def get_ticker(self, symbol: str) -> Optional[Dict]:
        """
        Получить 24h ticker статистику

        Args:
            symbol: Торговая пара (BTCUSDT)

        Returns:
            Словарь с данными ticker или None
        """
        url = f"{self.base_url}/api/v3/ticker/24hr"

        params = {'symbol': symbol}

        try:
            async with self.session.get(url, params=params) as response:
                if response.status == 200:
                    data = await response.json()

                    ticker = {
                        'symbol': data['symbol'],
                        'last_price': float(data['lastPrice']),
                        'price_24h_pcnt': float(data['priceChangePercent']),
                        'volume_24h': float(data['volume']),
                        'quote_volume_24h': float(data['quoteVolume']),
                        'high_24h': float(data['highPrice']),
                        'low_24h': float(data['lowPrice']),
                        'bid_price': float(data['bidPrice']),
                        'ask_price': float(data['askPrice']),
                        'open_price': float(data['openPrice']),
                        'trades_count': int(data['count'])
                    }

                    # Валидация цены
                    if DataValidator.validate_price(ticker['last_price'], symbol):
                        logger.debug(f"✅ Ticker {symbol}: ${ticker['last_price']:,.2f}")
                        return ticker
                    else:
                        logger.warning(f"⚠️ Невалидная цена в ticker {symbol}")
                        return None

                elif response.status == 429:
                    logger.warning(f"⚠️ Binance rate limit для ticker {symbol}")
                    return None

                else:
                    logger.error(f"❌ Binance ticker ошибка {response.status} для {symbol}")
                    return None

        except Exception as e:
            logger.error(f"❌ Ошибка get_ticker {symbol}: {e}")
            return None

    async def get_orderbook(self, symbol: str, limit: int = 100) -> Optional[Dict]:
        """
        Получить L2 orderbook (стакан заявок)

        Args:
            symbol: Торговая пара
            limit: Глубина стакана (5, 10, 20, 50, 100, 500, 1000, 5000)

        Returns:
            Словарь с bids/asks или None
        """
        url = f"{self.base_url}/api/v3/depth"

        # Binance поддерживает только определённые лимиты
        valid_limits = [5, 10, 20, 50, 100, 500, 1000, 5000]
        limit = min(valid_limits, key=lambda x: abs(x - limit))

        params = {
            'symbol': symbol,
            'limit': limit
        }

        try:
            async with self.session.get(url, params=params) as response:
                if response.status == 200:
                    data = await response.json()

                    orderbook = {
                        'symbol': symbol,
                        'timestamp': data.get('lastUpdateId', 0),
                        'bids': [[float(price), float(qty)] for price, qty in data['bids']],
                        'asks': [[float(price), float(qty)] for price, qty in data['asks']]
                    }

                    logger.debug(f"✅ Orderbook {symbol}: {len(orderbook['bids'])} bids, {len(orderbook['asks'])} asks")
                    return orderbook

                else:
                    logger.error(f"❌ Binance orderbook ошибка {response.status}")
                    return None

        except Exception as e:
            logger.error(f"❌ Ошибка get_orderbook {symbol}: {e}")
            return None

    async def get_recent_trades(self, symbol: str, limit: int = 500) -> List[Dict]:
        """
        Получить последние сделки

        Args:
            symbol: Торговая пара
            limit: Количество сделок (макс 1000)

        Returns:
            Список последних сделок
        """
        url = f"{self.base_url}/api/v3/trades"

        params = {
            'symbol': symbol,
            'limit': min(limit, 1000)
        }

        try:
            async with self.session.get(url, params=params) as response:
                if response.status == 200:
                    data = await response.json()

                    trades = []
                    for trade in data:
                        trades.append({
                            'id': trade['id'],
                            'price': float(trade['price']),
                            'quantity': float(trade['qty']),
                            'timestamp': trade['time'],
                            'is_buyer_maker': trade['isBuyerMaker']
                        })

                    logger.debug(f"✅ Получено {len(trades)} сделок для {symbol}")
                    return trades

                else:
                    logger.error(f"❌ Binance trades ошибка {response.status}")
                    return []

        except Exception as e:
            logger.error(f"❌ Ошибка get_recent_trades: {e}")
            return []

    async def get_agg_trades(self, symbol: str, limit: int = 1000) -> List[Dict]:
        """
        Получить агрегированные сделки (для Volume Profile)

        Args:
            symbol: Торговая пара
            limit: Количество сделок (макс 1000)

        Returns:
            Список агрегированных сделок
        """
        url = f"{self.base_url}/api/v3/aggTrades"

        params = {
            'symbol': symbol,
            'limit': min(limit, 1000)
        }

        try:
            async with self.session.get(url, params=params) as response:
                if response.status == 200:
                    data = await response.json()

                    agg_trades = []
                    for trade in data:
                        agg_trades.append({
                            'agg_trade_id': trade['a'],
                            'price': float(trade['p']),
                            'quantity': float(trade['q']),
                            'first_trade_id': trade['f'],
                            'last_trade_id': trade['l'],
                            'timestamp': trade['T'],
                            'is_buyer_maker': trade['m']
                        })

                    logger.debug(f"✅ Получено {len(agg_trades)} aggTrades для {symbol}")
                    return agg_trades

                else:
                    logger.error(f"❌ Binance aggTrades ошибка {response.status}")
                    return []

        except Exception as e:
            logger.error(f"❌ Ошибка get_agg_trades: {e}")
            return []

    async def get_exchange_info(self, symbol: Optional[str] = None) -> Optional[Dict]:
        """
        Получить информацию о бирже и торговых парах

        Args:
            symbol: Конкретная пара (опционально)

        Returns:
            Exchange info или None
        """
        url = f"{self.base_url}/api/v3/exchangeInfo"

        params = {}
        if symbol:
            params['symbol'] = symbol

        try:
            async with self.session.get(url, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    logger.debug(f"✅ Exchange info получена")
                    return data
                else:
                    logger.error(f"❌ Exchange info ошибка {response.status}")
                    return None

        except Exception as e:
            logger.error(f"❌ Ошибка get_exchange_info: {e}")
            return None

    async def close(self):
        """Закрытие HTTP сессии"""
        try:
            if self.session and not self.session.closed:
                await self.session.close()
                self.is_initialized = False
                logger.info("✅ Binance connector закрыт")
        except Exception as e:
            logger.error(f"❌ Ошибка закрытия Binance connector: {e}")

    def __del__(self):
        """Деструктор"""
        if self.session and not self.session.closed:
            try:
                asyncio.get_event_loop().run_until_complete(self.close())
            except:
                pass


# Экспорт
__all__ = ['EnhancedBinanceConnector']
