#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Enhanced OKX Connector для GIO Crypto Bot
Полная реализация OKX API v5 с валидацией данных
"""

import asyncio
import aiohttp
from typing import Dict, List, Optional
from config.settings import logger
from utils.validators import DataValidator


class EnhancedOKXConnector:
    """
    Полнофункциональный коннектор к OKX API v5
    Аналог EnhancedBybitConnector и EnhancedBinanceConnector
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        api_secret: Optional[str] = None,
        passphrase: Optional[str] = None
    ):
        """
        Инициализация OKX коннектора

        Args:
            api_key: API ключ OKX
            api_secret: API секрет OKX
            passphrase: Passphrase для API
        """
        self.base_url = "https://www.okx.com"
        self.api_key = api_key
        self.api_secret = api_secret
        self.passphrase = passphrase
        self.session = None
        self.is_initialized = False

        logger.info("✅ EnhancedOKXConnector инициализирован")

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
                logger.info("✅ Подключение к OKX API успешно")
                return True
            else:
                logger.error("❌ Не удалось подключиться к OKX API")
                return False

        except Exception as e:
            logger.error(f"❌ Ошибка инициализации OKX: {e}")
            return False

    async def get_server_time(self) -> Optional[int]:
        """
        Получить время сервера OKX

        Returns:
            Timestamp в миллисекундах или None
        """
        url = f"{self.base_url}/api/v5/public/time"

        try:
            async with self.session.get(url) as response:
                if response.status == 200:
                    data = await response.json()

                    if data['code'] == '0':
                        return int(data['data'][0]['ts'])
                    else:
                        logger.error(f"❌ OKX API ошибка: {data['msg']}")
                        return None
                else:
                    logger.error(f"❌ OKX server time ошибка: {response.status}")
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
            Символ в формате OKX (BTC-USDT)
        """
        # Простая логика для USDT пар
        if 'USDT' in symbol:
            base = symbol.replace('USDT', '')
            return f"{base}-USDT"
        elif 'USDC' in symbol:
            base = symbol.replace('USDC', '')
            return f"{base}-USDC"
        else:
            # Если формат уже правильный
            return symbol

    def _convert_interval(self, interval: str) -> str:
        """
        Преобразовать interval в формат OKX

        Args:
            interval: Интервал (1m, 5m, 1h, 4h, 1d)

        Returns:
            OKX формат (1m, 5m, 1H, 4H, 1D)
        """
        # OKX использует заглавные H и D
        interval_map = {
            '1m': '1m',
            '3m': '3m',
            '5m': '5m',
            '15m': '15m',
            '30m': '30m',
            '1h': '1H',
            '2h': '2H',
            '4h': '4H',
            '6h': '6H',
            '12h': '12H',
            '1d': '1D',
            '1w': '1W',
            '1M': '1M'
        }

        return interval_map.get(interval, interval)

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
            interval: Интервал (1m, 5m, 1h, 4h, 1d)
            limit: Количество свечей (макс 300)

        Returns:
            Список словарей с данными свечей
        """
        url = f"{self.base_url}/api/v5/market/candles"

        # Преобразовать символ и interval
        okx_symbol = self._convert_symbol(symbol)
        okx_interval = self._convert_interval(interval)

        params = {
            'instId': okx_symbol,
            'bar': okx_interval,
            'limit': min(limit, 300)  # OKX лимит 300
        }

        try:
            async with self.session.get(url, params=params) as response:
                if response.status == 200:
                    data = await response.json()

                    if data['code'] == '0':
                        candles = []

                        # OKX возвращает данные в обратном порядке (новые первые)
                        for item in reversed(data['data']):
                            candle = {
                                'timestamp': int(item[0]),
                                'open': float(item[1]),
                                'high': float(item[2]),
                                'low': float(item[3]),
                                'close': float(item[4]),
                                'volume': float(item[5]),  # base volume
                                'quote_volume': float(item[6]),  # quote volume
                                'confirm': item[8]  # 0: не завершена, 1: завершена
                            }

                            # Валидация
                            if DataValidator.validate_candle(candle):
                                candles.append(candle)
                            else:
                                logger.warning(f"⚠️ Невалидная свеча {symbol} отброшена")

                        logger.debug(f"✅ Получено {len(candles)} валидных свечей {symbol} ({interval})")
                        return candles
                    else:
                        logger.error(f"❌ OKX API ошибка: {data['msg']}")
                        return []

                elif response.status == 429:
                    logger.warning(f"⚠️ OKX rate limit превышен для {symbol}")
                    return []

                else:
                    logger.error(f"❌ OKX API ошибка {response.status} для {symbol}")
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
        url = f"{self.base_url}/api/v5/market/ticker"

        okx_symbol = self._convert_symbol(symbol)
        params = {'instId': okx_symbol}

        try:
            async with self.session.get(url, params=params) as response:
                if response.status == 200:
                    data = await response.json()

                    if data['code'] == '0' and data['data']:
                        ticker_data = data['data'][0]

                        ticker = {
                            'symbol': symbol,
                            'last_price': float(ticker_data['last']),
                            'open_price': float(ticker_data['open24h']),
                            'high_24h': float(ticker_data['high24h']),
                            'low_24h': float(ticker_data['low24h']),
                            'volume_24h': float(ticker_data['vol24h']),
                            'quote_volume_24h': float(ticker_data['volCcy24h']),
                            'bid_price': float(ticker_data['bidPx']),
                            'ask_price': float(ticker_data['askPx']),
                            'price_24h_pcnt': float(ticker_data.get('sodUtc8', 0)) * 100
                        }

                        # Валидация
                        if DataValidator.validate_price(ticker['last_price'], symbol):
                            logger.debug(f"✅ Ticker {symbol}: ${ticker['last_price']:,.2f}")
                            return ticker
                        else:
                            logger.warning(f"⚠️ Невалидная цена в ticker {symbol}")
                            return None
                    else:
                        logger.error(f"❌ OKX ticker ошибка: {data.get('msg', 'No data')}")
                        return None

                else:
                    logger.error(f"❌ OKX ticker ошибка {response.status}")
                    return None

        except Exception as e:
            logger.error(f"❌ Ошибка get_ticker {symbol}: {e}")
            return None

    async def get_orderbook(self, symbol: str, depth: int = 100) -> Optional[Dict]:
        """
        Получить L2 orderbook

        Args:
            symbol: Торговая пара
            depth: Глубина стакана (до 400)

        Returns:
            Словарь с bids/asks или None
        """
        url = f"{self.base_url}/api/v5/market/books"

        okx_symbol = self._convert_symbol(symbol)

        params = {
            'instId': okx_symbol,
            'sz': min(depth, 400)  # OKX лимит 400
        }

        try:
            async with self.session.get(url, params=params) as response:
                if response.status == 200:
                    data = await response.json()

                    if data['code'] == '0' and data['data']:
                        book_data = data['data'][0]

                        orderbook = {
                            'symbol': symbol,
                            'timestamp': int(book_data['ts']),
                            'bids': [[float(price), float(qty)] for price, qty, *_ in book_data['bids']],
                            'asks': [[float(price), float(qty)] for price, qty, *_ in book_data['asks']]
                        }

                        logger.debug(f"✅ Orderbook {symbol}: {len(orderbook['bids'])} bids, {len(orderbook['asks'])} asks")
                        return orderbook
                    else:
                        logger.error(f"❌ OKX orderbook ошибка: {data.get('msg', 'No data')}")
                        return None

                else:
                    logger.error(f"❌ OKX orderbook ошибка {response.status}")
                    return None

        except Exception as e:
            logger.error(f"❌ Ошибка get_orderbook {symbol}: {e}")
            return None

    async def get_trades(self, symbol: str, limit: int = 100) -> List[Dict]:
        """
        Получить последние сделки

        Args:
            symbol: Торговая пара
            limit: Количество сделок (макс 500)

        Returns:
            Список последних сделок
        """
        url = f"{self.base_url}/api/v5/market/trades"

        okx_symbol = self._convert_symbol(symbol)

        params = {
            'instId': okx_symbol,
            'limit': min(limit, 500)
        }

        try:
            async with self.session.get(url, params=params) as response:
                if response.status == 200:
                    data = await response.json()

                    if data['code'] == '0':
                        trades = []

                        for trade in data['data']:
                            trades.append({
                                'trade_id': trade['tradeId'],
                                'price': float(trade['px']),
                                'quantity': float(trade['sz']),
                                'timestamp': int(trade['ts']),
                                'side': trade['side']  # buy/sell
                            })

                        logger.debug(f"✅ Получено {len(trades)} сделок для {symbol}")
                        return trades
                    else:
                        logger.error(f"❌ OKX trades ошибка: {data['msg']}")
                        return []

                else:
                    logger.error(f"❌ OKX trades ошибка {response.status}")
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
                logger.info("✅ OKX connector закрыт")
        except Exception as e:
            logger.error(f"❌ Ошибка закрытия OKX connector: {e}")

    def __del__(self):
        """Деструктор"""
        if self.session and not self.session.closed:
            try:
                asyncio.get_event_loop().run_until_complete(self.close())
            except:
                pass


# Экспорт
__all__ = ['EnhancedOKXConnector']
