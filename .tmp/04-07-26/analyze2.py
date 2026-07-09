import pandas as pd

# Воронка продаж файлы
paths = [
    r'D:\WB\Бот ИИ менеджер\GitHub\.tmp\04-07-26\5-7-2026 Воронка продаж по дням с 04-07-2026 по 04-07-2026.xlsx',
    r'D:\WB\Бот ИИ менеджер\GitHub\.tmp\04-07-26\5-7-2026 Воронка продаж по дням с 04-07-2026 по 04-07-2026-2.xlsx',
]

for path in paths:
    print(f'\n{"="*60}')
    print(f'Файл: {path.split(chr(92))[-1]}')
    print(f'{"="*60}')
    try:
        xl = pd.ExcelFile(path)
        print(f'Листы: {xl.sheet_names}')
        for name in xl.sheet_names:
            df = pd.read_excel(path, sheet_name=name, header=None)
            print(f'\n--- Лист: {name} (shape: {df.shape}) ---')
            print(df.to_string())
    except Exception as e:
        print(f'Ошибка: {e}')
