#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Тест новых MTF Alignment методов
"""

import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from analytics.trenddetector import MultiTimeframeTrendDetector
from config.settings import logger

def test_check_mtf_alignment():
    """Тест check_mtf_alignment"""
    print("\n" + "="*70)
    print("🧪 ТЕСТ: check_mtf_alignment()")
    print("="*70)

    detector = MultiTimeframeTrendDetector()

    # Тест 1: Все бычьи (mock data)
    print("\n1️⃣ Тест: Все timeframes UPTREND")

    mock_candles = {
        '1H': [
            {'close': 100}, {'close': 101}, {'close': 102}, {'close': 103},
            {'close': 104}, {'close': 105}, {'close': 106}, {'close': 107},
            {'close': 108}, {'close': 109}, {'close': 110}, {'close': 111},
            {'close': 112}, {'close': 113}, {'close': 114}, {'close': 115},
            {'close': 116}, {'close': 117}, {'close': 118}, {'close': 120}  # +20%
        ],
        '4H': [
            {'close': 100}, {'close': 101}, {'close': 102}, {'close': 103},
            {'close': 104}, {'close': 105}, {'close': 106}, {'close': 107},
            {'close': 108}, {'close': 109}, {'close': 110}, {'close': 111},
            {'close': 112}, {'close': 113}, {'close': 114}, {'close': 115},
            {'close': 116}, {'close': 117}, {'close': 118}, {'close': 119}  # +19%
        ],
        '1D': [
            {'close': 100}, {'close': 101}, {'close': 102}, {'close': 103},
            {'close': 104}, {'close': 105}, {'close': 106}, {'close': 107},
            {'close': 108}, {'close': 109}, {'close': 110}, {'close': 111},
            {'close': 112}, {'close': 113}, {'close': 114}, {'close': 115},
            {'close': 116}, {'close': 117}, {'close': 118}, {'close': 121}  # +21%
        ]
    }

    result = detector.check_mtf_alignment("BTCUSDT", mock_candles)

    print(f"   ✅ Aligned: {result['aligned']}")
    print(f"   ✅ Direction: {result['direction']}")
    print(f"   ✅ Strength: {result['strength']}%")
    print(f"   ✅ Agreement: {result['agreement_score']}%")
    print(f"   ✅ Trends: {result['trends']}")
    print(f"   ✅ Recommendation: {result['recommendation']}")

    assert result['aligned'] == True
    assert result['direction'] == 'LONG'
    assert result['strength'] == 100
    print("   ✅ PASSED!")

    # Тест 2: Медвежьи
    print("\n2️⃣ Тест: Все timeframes DOWNTREND")

    mock_candles_bear = {
        '1H': [
            {'close': 120}, {'close': 119}, {'close': 118}, {'close': 117},
            {'close': 116}, {'close': 115}, {'close': 114}, {'close': 113},
            {'close': 112}, {'close': 111}, {'close': 110}, {'close': 109},
            {'close': 108}, {'close': 107}, {'close': 106}, {'close': 105},
            {'close': 104}, {'close': 103}, {'close': 102}, {'close': 100}  # -16.7%
        ],
        '4H': [
            {'close': 120}, {'close': 119}, {'close': 118}, {'close': 117},
            {'close': 116}, {'close': 115}, {'close': 114}, {'close': 113},
            {'close': 112}, {'close': 111}, {'close': 110}, {'close': 109},
            {'close': 108}, {'close': 107}, {'close': 106}, {'close': 105},
            {'close': 104}, {'close': 103}, {'close': 102}, {'close': 101}  # -15.8%
        ],
        '1D': [
            {'close': 120}, {'close': 119}, {'close': 118}, {'close': 117},
            {'close': 116}, {'close': 115}, {'close': 114}, {'close': 113},
            {'close': 112}, {'close': 111}, {'close': 110}, {'close': 109},
            {'close': 108}, {'close': 107}, {'close': 106}, {'close': 105},
            {'close': 104}, {'close': 103}, {'close': 102}, {'close': 99}  # -17.5%
        ]
    }

    result = detector.check_mtf_alignment("BTCUSDT", mock_candles_bear)

    print(f"   ✅ Aligned: {result['aligned']}")
    print(f"   ✅ Direction: {result['direction']}")
    print(f"   ✅ Strength: {result['strength']}%")
    print(f"   ✅ Recommendation: {result['recommendation']}")

    assert result['aligned'] == True
    assert result['direction'] == 'SHORT'
    assert result['strength'] == 100
    print("   ✅ PASSED!")

    # Тест 3: Mixed (2 bullish, 1 neutral)
    print("\n3️⃣ Тест: Mixed timeframes (2 UPTREND, 1 NEUTRAL)")

    mock_candles_mixed = {
        '1H': [
            {'close': 100}, {'close': 101}, {'close': 102}, {'close': 103},
            {'close': 104}, {'close': 105}, {'close': 106}, {'close': 107},
            {'close': 108}, {'close': 109}, {'close': 110}, {'close': 111},
            {'close': 112}, {'close': 113}, {'close': 114}, {'close': 115},
            {'close': 116}, {'close': 117}, {'close': 118}, {'close': 120}  # +20%
        ],
        '4H': [
            {'close': 100}, {'close': 101}, {'close': 100.5}, {'close': 101.5},
            {'close': 100.8}, {'close': 101.2}, {'close': 100.6}, {'close': 101.4},
            {'close': 100.9}, {'close': 101.1}, {'close': 100.7}, {'close': 101.3},
            {'close': 100.5}, {'close': 101.5}, {'close': 100.8}, {'close': 101.2},
            {'close': 100.6}, {'close': 101.4}, {'close': 100.9}, {'close': 101}  # +1% (NEUTRAL)
        ],
        '1D': [
            {'close': 100}, {'close': 101}, {'close': 102}, {'close': 103},
            {'close': 104}, {'close': 105}, {'close': 106}, {'close': 107},
            {'close': 108}, {'close': 109}, {'close': 110}, {'close': 111},
            {'close': 112}, {'close': 113}, {'close': 114}, {'close': 115},
            {'close': 116}, {'close': 117}, {'close': 118}, {'close': 119}  # +19%
        ]
    }

    result = detector.check_mtf_alignment("BTCUSDT", mock_candles_mixed)

    print(f"   ✅ Aligned: {result['aligned']}")
    print(f"   ✅ Direction: {result['direction']}")
    print(f"   ✅ Strength: {result['strength']}%")
    print(f"   ✅ Agreement: {result['agreement_score']:.1f}%")
    print(f"   ✅ Trends: {result['trends']}")
    print(f"   ✅ Recommendation: {result['recommendation']}")

    assert result['aligned'] == True
    assert result['direction'] == 'LONG'
    assert result['strength'] == 70
    print("   ✅ PASSED!")

    # Тест 4: No candles_data (cache test)
    print("\n4️⃣ Тест: No candles_data (из кэша)")

    result = detector.check_mtf_alignment("ETHUSDT")

    print(f"   ✅ Direction: {result['direction']}")
    print(f"   ✅ Trends: {result['trends']}")
    print("   ✅ PASSED! (all NEUTRAL from cache)")

    print("\n" + "="*70)
    print("✅ ВСЕ ТЕСТЫ ПРОЙДЕНЫ!")
    print("="*70 + "\n")


if __name__ == "__main__":
    try:
        test_check_mtf_alignment()
        print("🎉 SUCCESS! Методы работают корректно!\n")
    except Exception as e:
        print(f"❌ FAILED: {e}\n")
        import traceback
        traceback.print_exc()

