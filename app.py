"""
🍳 КАЛЬКУЛЯТОР СЕБЕСТОИМОСТИ БЛЮД (ИСПРАВЛЕННАЯ PRO)
- Загрузка описания видео
- Парсинг из описания ИЛИ субтитров
- Улучшенная обработка ошибок
"""

import streamlit as st
import re
import sqlite3
from typing import Optional, List, Dict
import pandas as pd

st.set_page_config(page_title="🍳 Кулинарный калькулятор PRO", layout="wide")

st.title("🍳 Кулинарный калькулятор (PRO)")
st.markdown("Управление рецептами, ингредиентами и расчет себестоимости")

# ============================================================================
# БАЗА ДАННЫХ
# ============================================================================

def init_db():
    """Инициализирует базу данных"""
    conn = sqlite3.connect('recipes.db')
    c = conn.cursor()

    c.execute('''CREATE TABLE IF NOT EXISTS recipes (
        id INTEGER PRIMARY KEY,
        name TEXT NOT NULL,
        category TEXT NOT NULL,
        ingredients TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS prices (
        id INTEGER PRIMARY KEY,
        ingredient TEXT UNIQUE NOT NULL,
        price REAL NOT NULL,
        unit TEXT NOT NULL,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )''')

    conn.commit()
    conn.close()


def save_recipe(name: str, category: str, ingredients: List[Dict]):
    """Сохраняет рецепт в БД"""
    conn = sqlite3.connect('recipes.db')
    c = conn.cursor()

    import json
    ingredients_json = json.dumps(ingredients)

    c.execute('''INSERT INTO recipes (name, category, ingredients)
                 VALUES (?, ?, ?)''', (name, category, ingredients_json))

    conn.commit()
    conn.close()


def get_recipes(category: Optional[str] = None) -> List[Dict]:
    """Получает рецепты из БД"""
    conn = sqlite3.connect('recipes.db')
    c = conn.cursor()

    if category:
        c.execute('''SELECT id, name, category, ingredients, created_at
                     FROM recipes WHERE category = ?
                     ORDER BY created_at DESC''', (category,))
    else:
        c.execute('''SELECT id, name, category, ingredients, created_at
                     FROM recipes ORDER BY created_at DESC''')

    rows = c.fetchall()
    conn.close()

    recipes = []
    for row in rows:
        import json
        recipes.append({
            'id': row[0],
            'name': row[1],
            'category': row[2],
            'ingredients': json.loads(row[3]),
            'created_at': row[4]
        })

    return recipes


def delete_recipe(recipe_id: int):
    """Удаляет рецепт"""
    conn = sqlite3.connect('recipes.db')
    c = conn.cursor()
    c.execute('DELETE FROM recipes WHERE id = ?', (recipe_id,))
    conn.commit()
    conn.close()


def save_prices(prices: Dict[str, Dict]):
    """Сохраняет цены"""
    conn = sqlite3.connect('recipes.db')
    c = conn.cursor()

    for ingredient, data in prices.items():
        c.execute('''INSERT OR REPLACE INTO prices (ingredient, price, unit)
                     VALUES (?, ?, ?)''',
                  (ingredient, data['price'], data['unit']))

    conn.commit()
    conn.close()


def get_prices() -> Dict[str, Dict]:
    """Получает цены"""
    conn = sqlite3.connect('recipes.db')
    c = conn.cursor()

    c.execute('SELECT ingredient, price, unit FROM prices')
    rows = c.fetchall()
    conn.close()

    prices = {}
    for row in rows:
        prices[row[0]] = {'price': row[1], 'unit': row[2]}

    return prices


# ============================================================================
# РАБОТА С YOUTUBE
# ============================================================================

def get_video_id(url: str) -> Optional[str]:
    """Извлекает ID видео из ссылки"""
    try:
        pattern = r'(?:youtube\.com\/watch\?v=|youtu\.be\/)([^&\n?#]+)'
        match = re.search(pattern, url)
        return match.group(1) if match else None
    except:
        return None


def get_youtube_data(video_url: str) -> Dict:
    """Получает описание и субтитры видео"""
    try:
        import yt_dlp

        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'writesubtitles': True,
            'skip_download': True,
            'subtitlesformat': 'vtt',
            'socket_timeout': 15,
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(video_url, download=False)

            # Описание видео
            description = info.get('description', '')

            # Субтитры
            transcript = None
            if info.get('subtitles'):
                subs_dict = info['subtitles']
                if subs_dict:
                    subs = None
                    for lang in ['ru', 'en']:
                        if lang in subs_dict:
                            subs = subs_dict[lang]
                            break

                    if not subs:
                        subs = list(subs_dict.values())[0]

                    if subs and len(subs) > 0:
                        vtt_url = subs[0].get('url') or subs[0].get('data')

                        if vtt_url and isinstance(vtt_url, str) and vtt_url.startswith('http'):
                            import requests
                            response = requests.get(vtt_url, timeout=10)
                            if response.status_code == 200:
                                subtitle_text = response.text

                                lines = subtitle_text.split('\n')
                                transcript_list = []

                                for line in lines:
                                    if (line.strip() and
                                        not line.startswith('WEBVTT') and
                                        '-->' not in line and
                                        not re.match(r'^\d{2}:\d{2}', line)):
                                        clean = re.sub(r'<[^>]+>', '', line).strip()
                                        if clean:
                                            transcript_list.append(clean)

                                transcript = ' '.join(transcript_list)

            return {
                'description': description,
                'transcript': transcript,
                'title': info.get('title', 'Unknown')
            }

    except Exception as e:
        return {
            'description': '',
            'transcript': None,
            'title': 'Unknown',
            'error': str(e)
        }


def find_ingredients(text: str) -> List[Dict]:
    """Находит ингредиенты в тексте (улучшенный парсер)"""
    if not text:
        return []

    ingredients = []
    seen = set()

    # Нормализуем текст
    text = text.replace('\n', ' ').replace('\r', ' ')

    # Паттерны поиска (в порядке приоритета)
    patterns = [
        # Паттерн 1: Число + единица (сокращение) + название
        # "400 мл молоко" или "2 шт яйца" или "100g сахара"
        r'(\d+(?:[.,]\d+)?)\s*(?:мл|ml|г|g|мг|mg|кг|kg|шт|pcs|л|l|ст\.л|tbsp|ч\.л|tsp)\s+([а-яa-z\s]+?)(?=[,;.!?\n]|$)',

        # Паттерн 2: Число + полное название единицы + название
        # "400 миллилитров молока" или "2 штуки яиц"
        r'(\d+(?:[.,]\d+)?)\s+(?:миллилитра|миллилитров|грамма|граммов|килограмма|килограммов|штука|штуки|литра|литров)\s+([а-яa-z\s]+?)(?=[,;.!?\n]|$)',

        # Паттерн 3: Только число + название (если единица не указана)
        # "2 яйца" или "400 молоко"
        r'(\d+(?:[.,]\d+)?)\s+([а-яa-z]{3,}(?:\s+[а-яa-z]+)?)\b',
    ]

    # Стандартные единицы
    units_map = {
        'мл': 'мл', 'ml': 'мл', 'миллилитр': 'мл', 'миллилитра': 'мл', 'миллилитров': 'мл',
        'г': 'г', 'g': 'г', 'грамм': 'г', 'грамма': 'г', 'граммов': 'г',
        'кг': 'кг', 'kg': 'кг', 'килограмм': 'кг', 'килограмма': 'кг', 'килограммов': 'кг',
        'л': 'л', 'l': 'л', 'литр': 'л', 'литра': 'л', 'литров': 'л',
        'мг': 'мг', 'mg': 'мг',
        'шт': 'шт', 'pcs': 'шт', 'штука': 'шт', 'штуки': 'шт',
        'ст.л': 'ст.л', 'tbsp': 'ст.л', 'столовая': 'ст.л', 'столовая ложка': 'ст.л',
        'ч.л': 'ч.л', 'tsp': 'ч.л', 'чайная': 'ч.л', 'чайная ложка': 'ч.л',
    }

    # Применяем каждый паттерн
    for pattern in patterns:
        for match in re.finditer(pattern, text, re.IGNORECASE):
            try:
                quantity_str = match.group(1).replace(',', '.')
                quantity = float(quantity_str)

                # Извлекаем имя ингредиента
                if len(match.groups()) >= 2:
                    name = match.group(2).strip().lower()
                else:
                    continue

                # Определяем единицу (если есть)
                full_match = match.group(0)
                unit = 'шт'  # Единица по умолчанию

                # Ищем единицу в match
                for unit_key, unit_val in units_map.items():
                    if unit_key.lower() in full_match.lower():
                        unit = unit_val
                        break

                # Очищаем название от лишних символов
                name = re.sub(r'[,;.!?]', '', name).strip()

                if len(name) < 2 or len(name) > 50:
                    continue

                # Избегаем дубликатов
                key = f"{name}_{unit}"
                if key not in seen and quantity > 0:
                    ingredients.append({
                        'name': name,
                        'quantity': quantity,
                        'unit': unit
                    })
                    seen.add(key)

            except (ValueError, IndexError):
                continue

    return ingredients


# ============================================================================
# ИНИЦИАЛИЗАЦИЯ
# ============================================================================

init_db()

CATEGORIES = ["Супы", "Вторые блюда", "Десерты и выпечка", "Консервация", "Колбасы", "Напитки", "Разное"]

# ============================================================================
# ИНТЕРФЕЙС
# ============================================================================

tab1, tab2, tab3 = st.tabs(["📺 Загрузка", "📋 Рецепты", "💰 Цены"])

# ============================================================================
# ВКЛАДКА 1: ЗАГРУЗКА
# ============================================================================

with tab1:
    st.subheader("Загрузка рецепта")

    input_mode = st.radio("Источник рецепта:", ["YouTube видео", "Текстовый рецепт"], horizontal=True)

    if input_mode == "YouTube видео":
        video_url = st.text_input("YouTube ссылка:", placeholder="https://youtube.com/watch?v=...")

        if st.button("🔄 Загрузить", type="primary", use_container_width=True):
            if not video_url.strip():
                st.error("❌ Введите ссылку")
            else:
                with st.spinner("⏳ Загружаю данные видео..."):
                    data = get_youtube_data(video_url)

                if data.get('error'):
                    st.error(f"❌ Ошибка: {data['error']}")
                else:
                    st.success("✅ Данные загружены!")

                    # Сначала парсим описание
                    ingredients_from_desc = find_ingredients(data['description'])

                    # Если в описании мало ингредиентов - парсим субтитры
                    if len(ingredients_from_desc) < 3 and data['transcript']:
                        ingredients_from_subs = find_ingredients(data['transcript'])
                        # Берем ингредиенты из субтитров
                        ingredients = ingredients_from_subs
                        source = "Субтитры"
                    else:
                        ingredients = ingredients_from_desc
                        source = "Описание видео"

                    if ingredients:
                        st.info(f"📍 Источник: **{source}**")
                        st.session_state.transcript = data['description'] or data['transcript'] or ""
                        st.session_state.ingredients = ingredients
                        st.session_state.video_title = data['title']
                    else:
                        st.warning("⚠️ Ингредиенты не найдены ни в описании, ни в субтитрах")

    else:
        recipe_text = st.text_area("Вставьте текст рецепта:", height=300, placeholder="Вставьте текст рецепта сюда...")

        if st.button("📝 Обработать текст", type="primary", use_container_width=True):
            if not recipe_text.strip():
                st.error("❌ Введите текст")
            else:
                st.session_state.transcript = recipe_text
                st.session_state.ingredients = find_ingredients(recipe_text)
                st.session_state.video_title = "Текстовый рецепт"
                st.success("✅ Текст обработан!")

    # Если есть загруженные данные
    if 'transcript' in st.session_state and st.session_state.ingredients:
        st.divider()
        st.subheader("🥘 Найденные ингредиенты:")

        ingredients = st.session_state.ingredients

        for ing in ingredients:
            st.write(f"• {ing['quantity']} {ing['unit']} {ing['name']}")

        # Сохранение рецепта
        st.divider()
        st.subheader("💾 Сохранить рецепт")

        # Предлагаем название из видео
        default_name = st.session_state.get('video_title', '')

        recipe_name = st.text_input("Название рецепта:", value=default_name, placeholder="Например: Борщ украинский")
        category = st.selectbox("Категория:", CATEGORIES)

        if st.button("💾 Сохранить", type="primary", use_container_width=True):
            if not recipe_name.strip():
                st.error("❌ Введите название рецепта")
            else:
                save_recipe(recipe_name, category, ingredients)
                st.success(f"✅ Рецепт '{recipe_name}' сохранен!")

                # Очищаем состояние
                if 'transcript' in st.session_state:
                    del st.session_state.transcript
                if 'ingredients' in st.session_state:
                    del st.session_state.ingredients

# ============================================================================
# ВКЛАДКА 2: РЕЦЕПТЫ
# ============================================================================

with tab2:
    st.subheader("📋 Сохраненные рецепты")

    filter_category = st.selectbox("Фильтр по категории:", ["Все"] + CATEGORIES)

    if filter_category == "Все":
        recipes = get_recipes()
    else:
        recipes = get_recipes(filter_category)

    if recipes:
        for recipe in recipes:
            with st.expander(f"📄 {recipe['name']} ({recipe['category']})"):
                st.write(f"**Дата добавления:** {recipe['created_at']}")

                st.write("**Ингредиенты:**")
                for ing in recipe['ingredients']:
                    st.write(f"• {ing['quantity']} {ing['unit']} {ing['name']}")

                col1, col2 = st.columns([1, 1])

                with col1:
                    if st.button("🗑️ Удалить", key=f"delete_{recipe['id']}", use_container_width=True):
                        delete_recipe(recipe['id'])
                        st.success("✅ Рецепт удален")
                        st.rerun()

    else:
        st.info("📌 Рецептов нет. Загрузите рецепт в вкладке 'Загрузка'")

# ============================================================================
# ВКЛАДКА 3: ЦЕНЫ
# ============================================================================

with tab3:
    st.subheader("💰 Управление ценами")

    st.write("**Загрузить прайс-лист:**")

    uploaded_file = st.file_uploader("Выберите текстовый файл с ценами (.txt, .csv)", type=["txt", "csv"])

    if uploaded_file:
        try:
            content = uploaded_file.read().decode('utf-8')

            lines = con

