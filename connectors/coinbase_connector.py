#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Enhanced Coinbase Connector для GIO Crypto Bot
Полная реализация Coinbase Advanced Trade API с валидацией данных
"""

import asyncio
import aiohttp
from typing import Dict, List, Optional
from datetime import datetime
from config.settings import logger
from utils.validators import DataValidator


class EnhancedCoinbaseConnector:
    """
    Полнофункциональный коннектор к Coinbase Advanced Trade API
    Аналог EnhancedBybitConnector, EnhancedBinanceConnector, EnhancedOKXConnector
    """

    def __init__(self, api_key: Optional[str] = None, api_secret: Optional[str] = None):
        """
        Инициализация Coinbase коннектора

        Args:
            api_key: API ключ Coinbase
            api_secret: API секрет Coinbase
        """
        self.base_url = "https://api.coinbase.com"
        self.api_key = api_key
        self.api_secret = api_secret
        self.session = None
        self.is_initialized = False

        logger.info("✅ EnhancedCoinbaseConnector инициализирован")

    async def initialize(self) -> bool:
        """
        Инициализация HTTP сессии и проверка подключения

        Returns:
            True если успешно
        """
        try:
            self.session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=30)
            )

            # Проверяем подключение
            server_time = await self.get_server_time()

            if server_time:
                self.is_initialized = True
                logger.info("✅ Подключение к Coinbase API успешно")
                return True
            else:
                logger.error("❌ Не удалось подключиться к Coinbase API")
                return False

        except Exception as e:
            logger.error(f"❌ Ошибка инициализации Coinbase: {e}")
            return False

    async def get_server_time(self) -> Optional[int]:
        """
        Получить время сервера Coinbase

        Returns:
            Timestamp в миллисекундах или None
        """
        url = f"{self.base_url}/api/v3/brokerage/time"

        try:
            async with self.session.get(url) as response:
                if response.status == 200:
                    data = await response.json()
                    # Coinbase возвращает секунды, преобразуем в миллисекунды
                    return int(data['epochSeconds']) * 1000
                else:
                    logger.error(f"❌ Coinbase server time ошибка: {response.status}")
                    return None

        except Exception as e:
            logger.error(f"❌ Ошибка get_server_time: {e}")
            return None

    def _convert_symbol(self, symbol: str) -> str:
        """
        Преобразовать формат символа: BTCUSDT → BTC-USDT

        Args:
            symbol: Символ в формате Binance (BTCUSDT)

        Returns:
            Символ в формате Coinbase (BTC-USDT)
        """
        if 'USDT' in symbol:
            base = symbol.replace('USDT', '')
            return f"{base}-USDT"
        elif 'USDC' in symbol:
            base = symbol.replace('USDC', '')
            return f"{base}-USDC"
        elif 'USD' in symbol:
            base = symbol.replace('USD', '')
            return f"{base}-USD"
        else:
            return symbol

    def _convert_interval(self, interval: str) -> int:
        """
        Преобразовать interval в granularity (секунды)

        Args:
            interval: Интервал (1m, 5m, 15m, 1h, 6h, 1d)

        Returns:
            Granularity в секундах
        """
        interval_map = {
            '1m': 60,
            '5m': 300,
            '15m': 900,
            '1h': 3600,
            '6h': 21600,
            '1d': 86400
        }

        return interval_map.get(interval, 3600)

    async def get_klines(
        self,
        symbol: str,
        interval: str,
        limit: int = 100
    ) -> List[Dict]:
        """
        Получить исторические свечи (candles)

        Args:
            symbol: Торговая пара (BTCUSDT или BTC-USDT)
            interval: Интервал (1m, 5m, 15m, 1h, 6h, 1d)
            limit: Количество свечей (макс 300)

        Returns:
            Список словарей с данными свечей
        """
        # Преобразовать символ и interval
        coinbase_symbol = self._convert_symbol(symbol)
        granularity = self._convert_interval(interval)

        url = f"{self.base_url}/api/v3/brokerage/products/{coinbase_symbol}/candles"

        params = {
            'granularity': granularity,
            'limit': min(limit, 300)
        }

        try:
            async with self.session.get(url, params=params) as response:
                if response.status == 200:
                    data = await response.json()

                    candles = []

                    # Coinbase возвращает массив свечей
                    for item in data.get('candles', []):
                        candle = {
                            'timestamp': int(item['start']) * 1000,  # секунды → миллисекунды
                            'open': float(item['open']),
                            'high': float(item['high']),
                            'low': float(item['low']),
                            'close': float(item['close']),
                            'volume': float(item['volume'])
                        }

                        # Валидация
                        if DataValidator.validate_candle(candle):
                            candles.append(candle)
                        else:
                            logger.warning(f"⚠️ Невалидная свеча {symbol} отброшена")

                    # Coinbase возвращает в обратном порядке, разворачиваем
                    candles.reverse()

                    logger.debug(f"✅ Получено {len(candles)} валидных свечей {symbol} ({interval})")
                    return candles

                elif response.status == 429:
                    logger.warning(f"⚠️ Coinbase rate limit превышен для {symbol}")
                    return []

                else:
                    logger.error(f"❌ Coinbase API ошибка {response.status} для {symbol}")
                    return []

        except asyncio.TimeoutError:
            logger.error(f"❌ Timeout при запросе свечей {symbol}")
            return []

        except Exception as e:
            logger.error(f"❌ Ошибка get_klines {symbol}: {e}")
            return []

    async def get_ticker(self, symbol: str) -> Optional[Dict]:
        """
        Получить ticker статистику

        Args:
            symbol: Торговая пара (BTCUSDT)

        Returns:
            Словарь с данными ticker или None
        """
        coinbase_symbol = self._convert_symbol(symbol)
        url = f"{self.base_url}/api/v3/brokerage/products/{coinbase_symbol}"

        try:
            async with self.session.get(url) as response:
                if response.status == 200:
                    data = await response.json()

                    ticker = {
                        'symbol': symbol,
                        'last_price': float(data.get('price', 0)),
                        'volume_24h': float(data.get('volume_24h', 0)),
                        'price_24h_pcnt': float(data.get('price_percentage_change_24h', 0)),
                        'base_currency': data.get('base_currency_id', ''),
                        'quote_currency': data.get('quote_currency_id', '')
                    }

                    # Валидация
                    if DataValidator.validate_price(ticker['last_price'], symbol):
                        logger.debug(f"✅ Ticker {symbol}: ${ticker['last_price']:,.2f}")
                        return ticker
                    else:
                        logger.warning(f"⚠️ Невалидная цена в ticker {symbol}")
                        return None

                elif response.status == 429:
                    logger.warning(f"⚠️ Coinbase rate limit для ticker {symbol}")
                    return None

                else:
                    logger.error(f"❌ Coinbase ticker ошибка {response.status} для {symbol}")
                    return None

        except Exception as e:
            logger.error(f"❌ Ошибка get_ticker {symbol}: {e}")
            return None

    async def get_orderbook(self, symbol: str, level: int = 2) -> Optional[Dict]:
        """
        Получить orderbook (product book)

        Args:
            symbol: Торговая пара
            level: Уровень детализации (1, 2, или 3)

        Returns:
            Словарь с bids/asks или None
        """
        coinbase_symbol = self._convert_symbol(symbol)
        url = f"{self.base_url}/api/v3/brokerage/product_book"

        params = {
            'product_id': coinbase_symbol,
            'level': level
        }

        try:
            async with self.session.get(url, params=params) as response:
                if response.status == 200:
                    data = await response.json()

                    pricebook = data.get('pricebook', {})

                    orderbook = {
                        'symbol': symbol,
                        'timestamp': int(pricebook.get('time', 0)),
                        'bids': [[float(bid['price']), float(bid['size'])] for bid in pricebook.get('bids', [])],
                        'asks': [[float(ask['price']), float(ask['size'])] for ask in pricebook.get('asks', [])]
                    }

                    logger.debug(f"✅ Orderbook {symbol}: {len(orderbook['bids'])} bids, {len(orderbook['asks'])} asks")
                    return orderbook

                else:
                    logger.error(f"❌ Coinbase orderbook ошибка {response.status}")
                    return None

        except Exception as e:
            logger.error(f"❌ Ошибка get_orderbook {symbol}: {e}")
            return None

    async def get_trades(self, symbol: str, limit: int = 100) -> List[Dict]:
        """
        Получить последние сделки

        Args:
            symbol: Торговая пара
            limit: Количество сделок

        Returns:
            Список последних сделок
        """
        coinbase_symbol = self._convert_symbol(symbol)
        url = f"{self.base_url}/api/v3/brokerage/products/{coinbase_symbol}/ticker"

        try:
            async with self.session.get(url) as response:
                if response.status == 200:
                    data = await response.json()

                    trades = []

                    # Coinbase ticker API не возвращает список сделок
                    # Для получения trades нужен WebSocket или Market Trades API
                    # Возвращаем последнюю известную цену как одну "сделку"

                    if 'trades' in data:
                        for trade in data['trades'][:limit]:
                            trades.append({
                                'trade_id': trade.get('trade_id', ''),
                                'price': float(trade.get('price', 0)),
                                'size': float(trade.get('size', 0)),
                                'timestamp': trade.get('time', ''),
                                'side': trade.get('side', '')
                            })

                    logger.debug(f"✅ Получено {len(trades)} сделок для {symbol}")
                    return trades

                else:
                    logger.error(f"❌ Coinbase trades ошибка {response.status}")
                    return []

        except Exception as e:
            logger.error(f"❌ Ошибка get_trades: {e}")
            return []

    async def close(self):
        """Закрытие HTTP сессии"""
        try:
            if self.session and not self.session.closed:
                await self.session.close()
                self.is_initialized = False
                logger.info("✅ Coinbase connector закрыт")
        except Exception as e:
            logger.error(f"❌ Ошибка закрытия Coinbase connector: {e}")

    def __del__(self):
        """Деструктор"""
        if self.session and not self.session.closed:
            try:
                asyncio.get_event_loop().run_until_complete(self.close())
            except:
                pass


# Экспорт
__all__ = ['EnhancedCoinbaseConnector']
