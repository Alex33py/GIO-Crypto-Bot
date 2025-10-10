#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
GIO Crypto Bot v3.0 Enhanced Modular
Главная точка входа в систему
"""

import sys
import asyncio
from pathlib import Path
from datetime import datetime

# Добавляем корневую директорию в путь
sys.path.insert(0, str(Path(__file__).parent))

try:
    from config.settings import logger
    from config.constants import Colors
    from core.bot import GIOCryptoBot

    logger.info("✅ Все модули импортированы успешно")

except ImportError as e:
    print(f"❌ Критическая ошибка импорта: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)


def print_banner():
    """Красивый баннер при запуске"""
    banner = f"""
╔══════════════════════════════════════════════════════════════════╗
║  🚀 GIO CRYPTO BOT v3.0 Enhanced Modular 🚀                     ║
╠══════════════════════════════════════════════════════════════════╣
║  ✅ Professional Volume Profile Analysis                         ║
║  ✅ Advanced News Sentiment Analysis                             ║
║  ✅ Binance + Bybit WebSocket Streams                           ║
║  ✅ Auto Scanner (каждые 5 мин)                                 ║
║  ✅ Auto ROI Tracker (TP1/TP2/TP3)                             ║
║  ✅ Enhanced Alerts System                                      ║
║  ✅ Confirm Filter (CVD + Volume + Candle)                      ║
║  ✅ Multi-TF Filter (1m/1h/4h/1d согласование)                 ║
╠══════════════════════════════════════════════════════════════════╣
║  📊 Готовность: 100%                                            ║
║  📅 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}               ║
╚══════════════════════════════════════════════════════════════════╝
    """
    print(banner)


async def main():
    """Главная функция"""
    bot = None

    try:
        print_banner()

        logger.info("🚀 Создание экземпляра бота...")
        bot = GIOCryptoBot()

        logger.info("🔧 Инициализация бота...")
        await bot.initialize()

        logger.info("▶️ Запуск бота...")
        await bot.run()

    except KeyboardInterrupt:
        logger.info(f"\n{Colors.WARNING}⚠️ Получен сигнал остановки (Ctrl+C){Colors.ENDC}")
    except Exception as e:
        logger.error(f"{Colors.FAIL}❌ Критическая ошибка: {e}{Colors.ENDC}")
        import traceback
        traceback.print_exc()
    finally:
        if bot:
            try:
                await asyncio.wait_for(bot.shutdown(), timeout=10.0)
            except asyncio.TimeoutError:
                logger.warning("⚠️ Превышено время ожидания остановки")
            except Exception as e:
                logger.error(f"❌ Ошибка при остановке: {e}")

        logger.info(f"{Colors.OKBLUE}👋 GIO Crypto Bot завершён{Colors.ENDC}")


if __name__ == "__main__":
    try:
        # Для Windows
        if sys.platform == "win32":
            asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

        asyncio.run(main())

    except KeyboardInterrupt:
        print(f"\n{Colors.WARNING}⚠️ Остановка...{Colors.ENDC}")
    except Exception as e:
        print(f"{Colors.FAIL}❌ Неожиданная ошибка: {e}{Colors.ENDC}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
