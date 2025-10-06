#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import time
from typing import List, Dict
from telegram import Update
from telegram.ext import ContextTypes
from config.settings import logger


async def cmd_analyze_batching_with_all(
    self, update: Update, context: ContextTypes.DEFAULT_TYPE
):
    try:
        start_time = time.time()
        if not context.args:
            symbols = ["BTCUSDT"]
            mode = "single"
        elif context.args[0].upper() == "ALL":
            try:
                symbols = list(self.bot_instance.tracked_symbols.keys())
                mode = "all"
                if not symbols:
                    await update.message.reply_text("❌ Нет активных пар!")
                    return
            except Exception as e:
                logger.error(f"❌ Ошибка: {e}")
                await update.message.reply_text(f"❌ Ошибка: {e}")
                return
        else:
            symbols = [context.args[0].upper()]
            mode = "single"
        if mode == "all":
            await update.message.reply_text(
                f"📊 *МАССОВЫЙ АНАЛИЗ*\n\n🎯 Пары: *{len(symbols)}*\n📋 {', '.join(symbols)}\n\n⚡ Запуск...",
                parse_mode="Markdown",
            )
        else:
            await update.message.reply_text(
                f"📊 Запуск анализа *{symbols[0]}*...", parse_mode="Markdown"
            )
        results = []
        for symbol in symbols:
            try:
                analysis_result = await self.bot_instance.analyze_symbol_with_batching(
                    symbol
                )
                if analysis_result and analysis_result.get("status") == "success":
                    results.append(
                        {
                            "symbol": symbol,
                            "result": analysis_result,
                            "time": analysis_result.get("analysis_time", 0),
                            "success": True,
                        }
                    )
                else:
                    results.append(
                        {"symbol": symbol, "error": "No result", "success": False}
                    )
            except Exception as e:
                results.append({"symbol": symbol, "error": str(e), "success": False})
        total_time = time.time() - start_time
        if mode == "all":
            message = await format_multi_analysis_report(results, total_time)
        else:
            message = await format_single_analysis_report(results[0])
        await update.message.reply_text(message, parse_mode="Markdown")
    except Exception as e:
        logger.error(f"❌ Ошибка: {e}", exc_info=True)
        await update.message.reply_text(f"❌ Ошибка: {e}")


async def format_single_analysis_report(result: Dict) -> str:
    if not result["success"]:
        return f"❌ Ошибка: {result.get('error', 'Unknown')}"
    data = result["result"]
    vp = data.get("volume_profile", {})
    return f"✅ *{result['symbol']}*\n⏱️ {result['time']:.2f}s\n📊 Давление: {vp.get('pressure', 'N/A')}\n🎯 Дисбаланс: {abs(vp.get('imbalance', 0)):.1f}%"


async def format_multi_analysis_report(results: List[Dict], total_time: float) -> str:
    successful = [r for r in results if r["success"]]
    if not successful:
        return "❌ Анализ не выполнен!"
    table = "```\nПара         Імбал\n------------ ------\n"
    for r in successful:
        vp = r["result"].get("volume_profile", {})
        table += f"{r['symbol']:<12} {abs(vp.get('imbalance', 0)):>5.1f}%\n"
    table += "```"
    return f"✅ *АНАЛИЗ ЗАВЕРШЁН*\n\n⏱️ Время: {total_time:.2f}s\n📊 Пар: {len(successful)}\n\n{table}"


def apply_analyze_batching_all_patch(bot_instance):
    try:
        logger.info("🔧 Патч...")
        telegram_handler = bot_instance.telegram_bot
        if not telegram_handler:
            return False
        telegram_handler.bot_instance = bot_instance
        import types

        telegram_handler.cmd_analyze_batching = types.MethodType(
            cmd_analyze_batching_with_all, telegram_handler
        )
        logger.info("✅ Патч OK!")
        return True
    except Exception as e:
        logger.error(f"❌ {e}", exc_info=True)
        return False
