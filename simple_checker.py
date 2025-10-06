#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ПРОСТОЙ ТЕСТЕР МОДУЛЕЙ GIO CRYPTO BOT
Работает без внешних зависимостей - только стандартная библиотека Python
"""

import ast
import sys
import importlib
from pathlib import Path
from typing import Dict, List, Tuple, Any
from datetime import datetime

class Colors:
    SUCCESS = '\033[92m'
    ERROR = '\033[91m'
    WARNING = '\033[93m'
    INFO = '\033[94m'
    RESET = '\033[0m'
    BOLD = '\033[1m'

class SimpleCodeChecker:
    def __init__(self, project_root: str = "."):
        self.project_root = Path(project_root).resolve()
        if str(self.project_root) not in sys.path:
            sys.path.insert(0, str(self.project_root))

    def check_module(self, module_path: str) -> Dict[str, Any]:
        print(f"\n{'='*60}")
        print(f"🔍 Проверка: {Colors.INFO}{Colors.BOLD}{module_path}{Colors.RESET}")

        # Находим файл модуля
        file_path = self.find_module_file(module_path)
        print(f"📁 Файл: {file_path}")
        print(f"{'='*60}")

        result = {
            'module': module_path,
            'file_path': str(file_path) if file_path else None,
            'exists': file_path.exists() if file_path else False,
            'syntax_ok': False,
            'imports_ok': False,
            'errors': [],
            'warnings': []
        }

        if not file_path or not file_path.exists():
            error_msg = f"Файл модуля не найден: {module_path}"
            result['errors'].append(error_msg)
            print(f"  {Colors.ERROR}❌ {error_msg}{Colors.RESET}")
            return result

        # Проверка синтаксиса
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                source = f.read()
            ast.parse(source, filename=str(file_path))
            result['syntax_ok'] = True
            print(f"  {Colors.SUCCESS}✅ Синтаксис OK{Colors.RESET}")
        except SyntaxError as e:
            result['errors'].append(f"SyntaxError line {e.lineno}: {e.msg}")
            print(f"  {Colors.ERROR}❌ SyntaxError line {e.lineno}: {e.msg}{Colors.RESET}")
        except Exception as e:
            result['errors'].append(f"Parse error: {e}")
            print(f"  {Colors.ERROR}❌ Parse error: {e}{Colors.RESET}")

        # Проверка импорта модуля
        if result['syntax_ok']:
            try:
                module_name = self.path_to_module_name(file_path)
                if module_name:
                    importlib.import_module(module_name)
                result['imports_ok'] = True
                print(f"  {Colors.SUCCESS}✅ Импорты OK{Colors.RESET}")
            except Exception as e:
                result['errors'].append(f"Import error: {e}")
                print(f"  {Colors.ERROR}❌ Import error: {e}{Colors.RESET}")

        return result

    def find_module_file(self, module_path: str) -> Path:
        if module_path.endswith('.py'):
            return Path(module_path)

        parts = module_path.split('.')
        possible_paths = [
            self.project_root / f"{module_path.replace('.', '/')}.py",
            self.project_root / f"{'/'.join(parts[:-1])}" / f"{parts[-1]}.py",
            self.project_root / f"{'/'.join(parts)}" / "__init__.py",
            self.project_root / f"{module_path}.py"
        ]

        for path in possible_paths:
            if path.exists():
                return path
        return possible_paths[0]

    def path_to_module_name(self, file_path: Path) -> str:
        try:
            relative_path = file_path.relative_to(self.project_root)
            if relative_path.name == '__init__.py':
                module_parts = relative_path.parent.parts
            else:
                module_parts = relative_path.with_suffix('').parts
            return '.'.join(module_parts)
        except ValueError:
            return ""

def main():
    MODULES = [
        "settings", "config.constants", "utils.logger", "models.trading",
        "indicator.technical", "connectors.bybit_connector",
        "analytics.news_analyzer", "utils.database", "core.bot"
    ]

    print(f"{Colors.BOLD}{Colors.INFO}🔍 ПРОСТОЙ ТЕСТЕР МОДУЛЕЙ GIO CRYPTO BOT{Colors.RESET}")
    print(f"📅 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"🎯 Модулей: {len(MODULES)}")

    checker = SimpleCodeChecker()
    passed_modules = 0
    total_errors = 0

    for module_path in MODULES:
        result = checker.check_module(module_path)
        errors_count = len(result.get('errors', []))
        total_errors += errors_count
        if errors_count == 0:
            passed_modules += 1

    print(f"\n{'='*80}")
    print(f"{Colors.BOLD}📊 ИТОГОВЫЙ ОТЧЕТ{Colors.RESET}")
    print(f"{'='*80}")
    print(f"📈 Всего модулей: {len(MODULES)}")
    print(f"{Colors.SUCCESS}✅ Без ошибок: {passed_modules}{Colors.RESET}")
    print(f"{Colors.ERROR}❌ С ошибками: {len(MODULES) - passed_modules}{Colors.RESET}")
    print(f"📊 Успешность: {(passed_modules/len(MODULES)*100):.1f}%")

    return 0 if total_errors == 0 else 1

if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)
