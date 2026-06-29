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
    conn = sqlite3.connect('recipes.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS recipes (
        id INTEGER PRIMARY KEY,
        name TEXT NOT NULL,
        category TEXT NOT NULL,
        ingredients TEXT NOT NULL,
        video_url TEXT,
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


def save_recipe(name: str, category: str, ingredients: List[Dict], video_url: Optional[str] = None):
    conn = sqlite3.connect('recipes.db')
    c = conn.cursor()
    import json
    ingredients_json = json.dumps(ingredients)
    c.execute('''INSERT INTO recipes (name, category, ingredients, video_url)
                 VALUES (?, ?, ?, ?)''', (name, category, ingredients_json, video_url))
    conn.commit()
    conn.close()


def get_recipes(category: Optional[str] = None) -> List[Dict]:
    conn = sqlite3.connect('recipes.db')
    c = conn.cursor()
    if category:
        c.execute('''SELECT id, name, category, ingredients, video_url, created_at
                     FROM recipes WHERE category = ?
                     ORDER BY created_at DESC''', (category,))
    else:
        c.execute('''SELECT id, name, category, ingredients, video_url, created_at
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
            'video_url': row[4],
            'created_at': row[5]
        })
    return recipes


def delete_recipe(recipe_id: int):
    conn = sqlite3.connect('recipes.db')
    c = conn.cursor()
    c.execute('DELETE FROM recipes WHERE id = ?', (recipe_id,))
    conn.commit()
    conn.close()


def save_prices(prices: Dict[str, Dict]):
    conn = sqlite3.connect('recipes.db')
    c = conn.cursor()
    for ingredient, data in prices.items():
        c.execute('''INSERT OR REPLACE INTO prices (ingredient, price, unit)
                     VALUES (?, ?, ?)''',
                  (ingredient, data['price'], data['unit']))
    conn.commit()
    conn.close()


def get_prices() -> Dict[str, Dict]:
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
    try:
        pattern = r'(?:youtube\.com\/watch\?v=|youtu\.be\/)([^&\n?#]+)'
        match = re.search(pattern, url)
        return match.group(1) if match else None
    except:
        return None


def get_youtube_data(video_url: str) -> Dict:
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
            description = info.get('description', '')
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
                                    if (line.strip() and not line.startswith('WEBVTT') and
                                        '-->' not in line and not re.match(r'^\d{2}:\d{2}', line)):
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


# ============================================================================
# ПАРСИНГ ТЕКСТА СО СТРАНИЦЫ
# ============================================================================

def get_page_text(url: str) -> Optional[str]:
    """Парсит текст со страницы по ссылке"""
    try:
        import requests
        from bs4 import BeautifulSoup

        headers = {'User-Agent': 'Mozilla/5.0'}
        response = requests.get(url, headers=headers, timeout=10)
        response.encoding = 'utf-8'

        if response.status_code == 200:
            soup = BeautifulSoup(response.text, 'html.parser')

            # Удаляем скрипты и стили
            for script in soup(['script', 'style']):
                script.decompose()

            # Получаем текст
            text = soup.get_text()

            # Очищаем текст
            lines = (line.strip() for line in text.splitlines())
            chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
            text = ' '.join(chunk for chunk in chunks if chunk)

            return text if len(text) > 100 else None
        else:
            return None
    except Exception as e:
        return None


# ============================================================================
# ПАРСИНГ ИНГРЕДИЕНТОВ
# ============================================================================

def find_ingredients(text: str) -> List[Dict]:
    if not text:
        return []

    text = text.replace('\n', ' ').replace('\r', ' ')
    ingredients = []
    seen = set()

    exclude_words = {'минут', 'минуты', 'минута', 'второ', 'часо', 'час', 'градусо', 'градусов',
                     'градусе', 'целью', 'цвет', 'время', 'температу', 'температур', 'процесс',
                     'духов', 'духовк', 'разогреть', 'выпекать', 'оставить', 'смешать', 'взбить'}

    units_map = {
        'мл': 'мл', 'ml': 'мл', 'миллилитр': 'мл', 'миллилитра': 'мл', 'миллилитров': 'мл',
        'г': 'г', 'g': 'г', 'грамм': 'г', 'грамма': 'г', 'граммов': 'г',
        'кг': 'кг', 'kg': 'кг', 'килограмм': 'кг', 'килограмма': 'кг', 'килограммов': 'кг',
        'л': 'л', 'l': 'л', 'литр': 'л', 'литра': 'л', 'литров': 'л',
        'мг': 'мг', 'mg': 'мг',
        'шт': 'шт', 'pcs': 'шт', 'штук': 'шт', 'штука': 'шт', 'штуки': 'шт',
        'ст.л': 'ст.л', 'tbsp': 'ст.л', 'столов': 'ст.л', 'ложк': 'ст.л',
        'ч.л': 'ч.л', 'tsp': 'ч.л', 'чайн': 'ч.л',
    }

    # Паттерн 1: "400 г муки" (количество + единица + ингредиент)
    pattern1 = r'(\d+(?:[.,]\d+)?)\s*(?:мл|ml|г|g|мг|mg|кг|kg|шт|pcs|л|l|ст\.л|tbsp|ч\.л|tsp|миллилитр|грамм|килограмм|штук|литр|ложки|ложки)\s+([а-яa-z\s]+?)(?=[,;.!?\n—]|$)'

    # Паттерн 2: "мука — 400 г" (ингредиент — количество + единица)
    pattern2 = r'([а-яa-z\s]+?)\s*—\s*(\d+(?:[.,]\d+)?)\s*(?:мл|ml|г|g|мг|mg|кг|kg|шт|pcs|л|l|ст\.л|tbsp|ч\.л|tsp|миллилитр|грамм|килограмм|штук|литр|ложки)'

    def add_ingredient(name: str, quantity: float, full_match: str):
        """Добавляет ингредиент если он прошел все фильтры"""
        skip = False
        for excl in exclude_words:
            if excl in name:
                skip = True
                break

        if skip:
            return

        unit = 'шт'
        for unit_key, unit_val in units_map.items():
            if unit_key.lower() in full_match.lower():
                unit = unit_val
                break

        name = re.sub(r'[,;.!?—]', '', name).strip()

        if len(name) < 2 or len(name) > 50:
            return

        if not any(c.isalpha() for c in name):
            return

        key = f"{name}_{unit}"
        if key not in seen and quantity > 0 and quantity < 10000:
            ingredients.append({
                'name': name,
                'quantity': quantity,
                'unit': unit
            })
            seen.add(key)

    # Применяем паттерн 1
    for match in re.finditer(pattern1, text, re.IGNORECASE):
        try:
            quantity_str = match.group(1).replace(',', '.')
            quantity = float(quantity_str)
            name = match.group(2).strip().lower()
            full_match = match.group(0)
            add_ingredient(name, quantity, full_match)
        except (ValueError, IndexError):
            continue

    # Применяем паттерн 2
    for match in re.finditer(pattern2, text, re.IGNORECASE):
        try:
            name = match.group(1).strip().lower()
            quantity_str = match.group(2).replace(',', '.')
            quantity = float(quantity_str)
            full_match = match.group(0)
            add_ingredient(name, quantity, full_match)
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

# ВКЛАДКА 1: ЗАГРУЗКА
with tab1:
    st.subheader("Загрузка рецепта")

    input_mode = st.radio("Источник рецепта:", ["YouTube видео", "Ссылка на страницу"], horizontal=True)

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

                    # Сначала ищем в описании
                    ingredients_from_desc = find_ingredients(data['description'])

                    # Если в описании мало ингредиентов - берем из субтитров
                    if len(ingredients_from_desc) < 5 and data['transcript']:
                        ingredients_from_subs = find_ingredients(data['transcript'])
                        ingredients = ingredients_from_subs
                        source = "Субтитры видео"
                    else:
                        ingredients = ingredients_from_desc
                        source = "Описание видео"

                    if ingredients:
                        st.info(f"📍 Источник: **{source}** ({len(ingredients)} ингредиентов)")
                        st.session_state.ingredients = ingredients
                        st.session_state.video_url = video_url
                        st.session_state.video_title = data['title']
                    else:
                        st.warning("⚠️ Ингредиенты не найдены ни в описании, ни в субтитрах")

    else:
        page_url = st.text_input("Ссылка на страницу:", placeholder="https://example.com/recipe...")

        if st.button("🔄 Загрузить", type="primary", use_container_width=True):
            if not page_url.strip():
                st.error("❌ Введите ссылку")
            else:
                with st.spinner("⏳ Загружаю страницу..."):
                    page_text = get_page_text(page_url)

                if page_text:
                    st.success("✅ Страница загружена!")
                    st.session_state.ingredients = find_ingredients(page_text)
                    st.session_state.video_url = page_url
                    st.session_state.video_title = "Рецепт со страницы"
                else:
                    st.error("❌ Не удалось загрузить страницу или извлечь текст")

    if 'ingredients' in st.session_state and st.session_state.ingredients:
        st.divider()
        st.subheader("🥘 Найденные ингредиенты:")

        ingredients = st.session_state.ingredients
        for ing in ingredients:
            st.write(f"• {ing['quantity']} {ing['unit']} {ing['name']}")

        st.divider()
        st.subheader("💾 Сохранить рецепт")

        default_name = st.session_state.get('video_title', '')
        recipe_name = st.text_input("Название рецепта:", value=default_name, placeholder="Например: Борщ украинский")
        category = st.selectbox("Категория:", CATEGORIES)

        if st.button("💾 Сохранить", type="primary", use_container_width=True):
            if not recipe_name.strip():
                st.error("❌ Введите название рецепта")
            else:
                video_url = st.session_state.get('video_url')
                save_recipe(recipe_name, category, ingredients, video_url)
                st.success(f"✅ Рецепт '{recipe_name}' сохранен!")
                if 'ingredients' in st.session_state:
                    del st.session_state.ingredients

# ВКЛАДКА 2: РЕЦЕПТЫ
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

                if recipe['video_url']:
                    st.write(f"**Ссылка:** [Открыть]({recipe['video_url']})")

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

# ВКЛАДКА 3: ЦЕНЫ
with tab3:
    st.subheader("💰 Управление ценами")

    st.write("**Загрузить прайс-лист:**")

    uploaded_file = st.file_uploader("Выберите текстовый файл с ценами (.txt, .csv)", type=["txt", "csv"])

    if uploaded_file:
        try:
            content = uploaded_file.read().decode('utf-8')
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
    st.write("**Текущие цены в системе:**")

    current_prices = get_prices()

    if current_prices:
        df = pd.DataFrame([
            {'Ингредиент': k, 'Цена': v['price'], 'Единица': v['unit']}
            for k, v in current_prices.items()
        ])
        st.dataframe(df, use_container_width=True)

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
