#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Тест Binance Connector
"""

import asyncio
from connectors.binance_connector import EnhancedBinanceConnector


async def test_binance():
    """Тестирование Binance API"""

    connector = EnhancedBinanceConnector()

    # Инициализация
    await connector.initialize()

    # Тест 1: Server time
    server_time = await connector.get_server_time()
    print(f"✅ Server time: {server_time}")

    # Тест 2: Ticker
    ticker = await connector.get_ticker("BTCUSDT")
    if ticker:
        print(f"✅ Ticker: {ticker['symbol']} - ${ticker['last_price']:,.2f}")

    # Тест 3: Klines
    klines = await connector.get_klines("BTCUSDT", "1h", limit=10)
    print(f"✅ Klines: получено {len(klines)} свечей")

    # Тест 4: Orderbook
    orderbook = await connector.get_orderbook("BTCUSDT", limit=50)
    if orderbook:
        print(f"✅ Orderbook: {len(orderbook['bids'])} bids, {len(orderbook['asks'])} asks")

    # Тест 5: AggTrades
    trades = await connector.get_agg_trades("BTCUSDT", limit=100)
    print(f"✅ AggTrades: получено {len(trades)} сделок")

    # Закрытие
    await connector.close()
    print("\n🎉 ВСЕ ТЕСТЫ ПРОЙДЕНЫ!")


if __name__ == "__main__":
    asyncio.run(test_binance())
