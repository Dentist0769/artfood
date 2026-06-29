
"""
🍳 КАЛЬКУЛЯТОР СЕБЕСТОИМОСТИ БЛЮД (ПРОФЕССИОНАЛЬНАЯ ВЕРСИЯ)
3 вкладки: Загрузка, Рецепты, Цены
"""

import streamlit as st
import re
import sqlite3
from typing import Optional, List, Dict
import pandas as pd
from datetime import datetime

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

    # Таблица рецептов
    c.execute('''CREATE TABLE IF NOT EXISTS recipes (
        id INTEGER PRIMARY KEY,
        name TEXT NOT NULL,
        category TEXT NOT NULL,
        ingredients TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )''')

    # Таблица цен
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
# ПАРСИНГ РЕЦЕПТОВ И ИНГРЕДИЕНТОВ
# ============================================================================

def get_video_id(url: str) -> Optional[str]:
    """Извлекает ID видео из ссылки"""
    try:
        pattern = r'(?:youtube\.com\/watch\?v=|youtu\.be\/)([^&\n?#]+)'
        match = re.search(pattern, url)
        return match.group(1) if match else None
    except:
        return None


def get_subtitles_ytdlp(video_url: str) -> Optional[str]:
    """Загружает субтитры через yt-dlp"""
    try:
        import yt_dlp

        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'writesubtitles': True,
            'skip_download': True,
            'subtitlesformat': 'vtt',
            'outtmpl': '/tmp/%(id)s',
            'socket_timeout': 15,
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(video_url, download=False)

            if not info.get('subtitles'):
                return None

            subs_dict = info['subtitles']
            if not subs_dict:
                return None

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
                    else:
                        return None
                else:
                    subtitle_text = vtt_url if isinstance(vtt_url, str) else ''

                lines = subtitle_text.split('\n')
                transcript = []

                for line in lines:
                    if (line.strip() and
                        not line.startswith('WEBVTT') and
                        '-->' not in line and
                        not re.match(r'^\d{2}:\d{2}', line)):
                        clean = re.sub(r'<[^>]+>', '', line).strip()
                        if clean:
                            transcript.append(clean)

                return ' '.join(transcript)

        return None

    except:
        return None


def find_ingredients(text: str) -> List[Dict]:
    """Находит ингредиенты в тексте"""
    pattern = r'(\d+(?:\.\d+)?)\s*(г|мл|шт|ст\.л|ч\.л|л|кг)\s+([а-яa-z\s]+?)(?=[.,:;]|$)'

    ingredients = []
    for match in re.finditer(pattern, text, re.IGNORECASE):
        quantity = float(match.group(1))
        unit = match.group(2).lower()
        name = match.group(3).strip()

        ingredients.append({
            'name': name,
            'quantity': quantity,
            'unit': unit
        })

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

        if st.button("🔄 Загрузить субтитры", type="primary", use_container_width=True):
            if not video_url.strip():
                st.error("❌ Введите ссылку")
            else:
                with st.spinner("⏳ Загружаю субтитры..."):
                    transcript = get_subtitles_ytdlp(video_url)

                if transcript:
                    st.success("✅ Загружено!")
                    st.session_state.transcript = transcript
                    st.session_state.ingredients = find_ingredients(transcript)
                else:
                    st.error("❌ Не удалось загрузить субтитры")

    else:
        recipe_text = st.text_area("Вставьте текст рецепта:", height=300, placeholder="Вставьте текст рецепта сюда...")

        if st.button("📝 Обработать текст", type="primary", use_container_width=True):
            if not recipe_text.strip():
                st.error("❌ Введите текст")
            else:
                st.session_state.transcript = recipe_text
                st.session_state.ingredients = find_ingredients(recipe_text)
                st.success("✅ Текст обработан!")

    # Если есть загруженные данные
    if 'transcript' in st.session_state and st.session_state.transcript:
        st.divider()
        st.subheader("🥘 Найденные ингредиенты:")

        ingredients = st.session_state.ingredients

        if ingredients:
            for ing in ingredients:
                st.write(f"• {ing['quantity']} {ing['unit']} {ing['name']}")

            # Сохранение рецепта
            st.divider()
            st.subheader("💾 Сохранить рецепт")

            recipe_name = st.text_input("Название рецепта:", placeholder="Например: Борщ украинский")
            category = st.selectbox("Категория:", CATEGORIES)

            if st.button("💾 Сохранить", type="primary", use_container_width=True):
                if not recipe_name.strip():
                    st.error("❌ Введите название рецепта")
                else:
                    save_recipe(recipe_name, category, ingredients)
                    st.success(f"✅ Рецепт '{recipe_name}' сохранен в категорию '{category}'!")

                    # Очищаем состояние
                    del st.session_state.transcript
                    del st.session_state.ingredients

        else:
            st.warning("⚠️ Ингредиенты не найдены")

# ============================================================================
# ВКЛАДКА 2: РЕЦЕПТЫ
# ============================================================================

with tab2:
    st.subheader("📋 Сохраненные рецепты")

    # Фильтр по категории
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

                # Действия
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

    # Загрузка прайс-листа
    st.write("**Загрузить прайс-лист:**")

    uploaded_file = st.file_uploader("Выберите текстовый файл с ценами (.txt, .csv)", type=["txt", "csv"])

    if uploaded_file:
        try:
            content = uploaded_file.read().decode('utf-8')

            # Парсим прайс-лист (формат: название\tцена\tединица или название,цена,единица)
            lines = content.strip().split('\n')
            prices = {}

            for line in lines:
                if '\t' in line:
                    parts = line.split('\t')
                elif ',' in line:
                    parts = line.split(',')
                else:
                    continue

                if len(parts) >= 3:
                    ingredient = parts[0].strip()
                    try:
                        price = float(parts[1].strip())
                        unit = parts[2].strip()
                        prices[ingredient] = {'price': price, 'unit': unit}
                    except:
                        continue

            if prices:
                st.success(f"✅ Найдено {len(prices)} позиций")

                if st.button("💾 Сохранить цены", type="primary", use_container_width=True):
                    save_prices(prices)
                    st.success("✅ Цены сохранены!")

                # Показываем загруженные цены
                df = pd.DataFrame([
                    {'Ингредиент': k, 'Цена': v['price'], 'Единица': v['unit']}
                    for k, v in prices.items()
                ])
                st.dataframe(df, use_container_width=True)

            else:
                st.error("❌ Не удалось распознать формат файла")

        except Exception as e:
            st.error(f"❌ Ошибка при загрузке: {e}")

    st.divider()

    # Текущие цены
    st.write("**Текущие цены в системе:**")

    current_prices = get_prices()

    if current_prices:
        df = pd.DataFrame([
            {'Ингредиент': k, 'Цена': v['price'], 'Единица': v['unit']}
            for k, v in current_prices.items()
        ])
        st.dataframe(df, use_container_width=True)

        # Возможность ручного редактирования
        st.write("**Добавить/изменить цену вручную:**")

        col1, col2, col3 = st.columns(3)

        with col1:
            ing_name = st.text_input("Ингредиент:", placeholder="Например: молоко")

        with col2:
            ing_price = st.number_input("Цена:", min_value=0.0, step=10.0)

        with col3:
            ing_unit = st.selectbox("Единица:", ["г", "мл", "шт", "л", "кг"])

        if st.button("➕ Добавить цену", use_container_width=True):
            if ing_name.strip():
                save_prices({ing_name: {'price': ing_price, 'unit': ing_unit}})
                st.success(f"✅ Цена для '{ing_name}' добавлена!")
                st.rerun()

    else:
        st.info("📌 Цены не загружены. Загрузите прайс-лист выше")

        
