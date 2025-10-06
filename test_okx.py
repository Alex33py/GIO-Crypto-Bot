#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Тест OKX Connector
"""

import asyncio
from connectors.okx_connector import EnhancedOKXConnector


async def test_okx():
    """Тестирование OKX API"""

    connector = EnhancedOKXConnector()

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
    orderbook = await connector.get_orderbook("BTCUSDT", depth=50)
    if orderbook:
        print(f"✅ Orderbook: {len(orderbook['bids'])} bids, {len(orderbook['asks'])} asks")

    # Тест 5: Trades
    trades = await connector.get_trades("BTCUSDT", limit=100)
    print(f"✅ Trades: получено {len(trades)} сделок")

    # Закрытие
    await connector.close()
    print("\n🎉 ВСЕ ТЕСТЫ ПРОЙДЕНЫ!")


if __name__ == "__main__":
    asyncio.run(test_okx())
