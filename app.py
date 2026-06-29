import streamlit as st
import re
import sqlite3
from typing import Optional, List, Dict
import pandas as pd

st.set_page_config(page_title="🍳 Кулинарный калькулятор PRO", layout="wide")
st.title("🍳 Кулинарный калькулятор (PRO)")
st.markdown("Управление рецептами, ингредиентами и расчет себестоимости")

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
                     FROM recipes WHERE category = ? ORDER BY created_at DESC''', (category,))
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
                     VALUES (?, ?, ?)''', (ingredient, data['price'], data['unit']))
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

def get_video_id(url: str) -> Optional[str]:
    try:
        pattern = r'(?:youtube\.com\/watch\?v=|youtu\.be\/)([^&\n?#]+)'
        match = re.search(pattern, url)
        return match.group(1) if match else None
    except:
        return None

def clean_description(text: str) -> str:
    """Очищает описание от ссылок, хэштегов и мусора, оставляя рецепт и процесс"""

    # Удаляем ссылки и текст вокруг них (http, www, телеграмм и т.д.)
    text = re.sub(r'https?://[^\s]+', '', text)
    text = re.sub(r'www\.[^\s]+', '', text)

    # Удаляем строки с ссылками на телеграмм, монобанк, промокоды
    lines = text.split('\n')
    filtered_lines = []
    for line in lines:
        # Пропускаем строки с реквизитами, ссылками, промокодами
        if any(keyword in line.lower() for keyword in ['telegram', 'tg.me', 'монобанк', 'промокод', 'скидка', 'подпишись', 'subscribe']):
            continue
        filtered_lines.append(line)
    text = '\n'.join(filtered_lines)

    # Удаляем хэштеги целиком
    text = re.sub(r'#[а-яa-z_]+', '', text, flags=re.IGNORECASE)

    # Удаляем только строки типа "расшифровка видео", "как это было сделано видео"
    text = re.sub(r'(?:расшифровка|transcription|как это было сделано).{0,50}(?:\n|$)', '', text, flags=re.IGNORECASE)

    # Удаляем множественные пробелы и пустые строки
    text = re.sub(r'\n+', '\n', text)
    text = re.sub(r' +', ' ', text)

    return text.strip()

def get_youtube_data(video_url: str) -> Dict:
    """Получает описание видео и закрепленный комментарий"""
    try:
        import yt_dlp
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'socket_timeout': 15,
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(video_url, download=False)
            description = info.get('description', '')

            # Очищаем описание
            clean_desc = clean_description(description)

            return {
                'description': clean_desc,
                'title': info.get('title', 'Unknown'),
                'comments': None  # Для будущего использования
            }
    except Exception as e:
        return {
            'description': '',
            'title': 'Unknown',
            'comments': None,
            'error': str(e)
        }

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
            for script in soup(['script', 'style']):
                script.decompose()
            text = soup.get_text()
            lines = (line.strip() for line in text.splitlines())
            chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
            text = ' '.join(chunk for chunk in chunks if chunk)
            return text if len(text) > 100 else None
        else:
            return None
    except Exception as e:
        return None

def find_ingredients(text: str) -> List[Dict]:
    """Находит ингредиенты в тексте (для YouTube описаний)"""
    if not text:
        return []

    # Разбираем по строкам для лучшего парсинга
    lines = text.split('\n')
    ingredients = []
    seen = set()

    exclude_words = {'минут', 'минуты', 'минута', 'второ', 'часо', 'час', 'градусо', 'градусов',
                     'градусе', 'целью', 'цвет', 'время', 'температу', 'температур', 'процесс',
                     'духов', 'духовк', 'разогреть', 'выпекать', 'оставить', 'смешать', 'взбить'}

    units_map = {
        'мл': 'мл', 'ml': 'мл', 'г': 'г', 'g': 'г', 'кг': 'кг', 'kg': 'кг',
        'л': 'л', 'l': 'л', 'мг': 'мг', 'mg': 'мг',
        'шт': 'шт', 'pcs': 'шт', 'штук': 'шт', 'штука': 'шт', 'штуки': 'шт',
        'ст.л': 'ст.л', 'ст л': 'ст.л', 'tbsp': 'ст.л', 'столов': 'ст.л', 'ложка': 'ст.л',
        'ч.л': 'ч.л', 'ч л': 'ч.л', 'tsp': 'ч.л', 'чайн': 'ч.л',
    }

    def add_ingredient(name: str, quantity: float, unit: str):
        skip = False
        for excl in exclude_words:
            if excl in name.lower():
                skip = True
                break
        if skip:
            return

        name = re.sub(r'[,;.!?—()\[\]]', '', name).strip()
        if len(name) < 2 or len(name) > 50:
            return
        if not any(c.isalpha() for c in name):
            return

        key = f"{name}_{unit}"
        if key not in seen and quantity > 0 and quantity < 10000:
            ingredients.append({'name': name.lower(), 'quantity': quantity, 'unit': unit})
            seen.add(key)

    # Парсим каждую строку отдельно
    for line in lines:
        line = line.strip()
        if not line or len(line) < 3:
            continue

        # Пропускаем заголовки секций но продолжаем парсить
        if any(keyword in line.lower() for keyword in ['начинка', 'для теста', 'для сиропа', 'ингредиент', 'рецепт']):
            continue

        # Паттерн 1: "Название.....кол-во единица" (много точек в описании)
        # Примеры: "Мука пшеничная...............1 кг" или "Масло растительное.......40 мл"
        match = re.search(r'([а-яa-z\s\(\)]+?)\.{2,}\s*(\d+(?:[.,]\d+)?)\s*(?:кг|г|мл|л|шт|ст\.л|ч\.л|ст л|ч л)', line, re.IGNORECASE)
        if match:
            name = match.group(1).strip()
            quantity_str = match.group(2).replace(',', '.')
            try:
                quantity = float(quantity_str)
                # Определяем единицу из строки
                unit = 'шт'
                for unit_key, unit_val in units_map.items():
                    if unit_key.lower() in line.lower():
                        unit = unit_val
                        break
                add_ingredient(name, quantity, unit)
                continue
            except:
                pass

        # Паттерн 2: "Название — количество единица"
        match = re.search(rf'([а-яa-z\s]+?)\s*—\s*(\d+(?:[.,]\d+)?)\s*({"|".join(units_map.keys())})', line, re.IGNORECASE)
        if match:
            name = match.group(1).strip()
            quantity_str = match.group(2).replace(',', '.')
            unit = match.group(3).lower()
            try:
                quantity = float(quantity_str)
                unit = units_map.get(unit, 'шт')
                add_ingredient(name, quantity, unit)
                continue
            except:
                pass

        # Паттерн 3: "кол-во единица название"
        match = re.search(rf'(\d+(?:[.,]\d+)?)\s*({"|".join(units_map.keys())})\s+([а-яa-z\s\(\)]+?)(?:[,;]|$)', line, re.IGNORECASE)
        if match:
            quantity_str = match.group(1).replace(',', '.')
            unit = match.group(2).lower()
            name = match.group(3).strip()
            try:
                quantity = float(quantity_str)
                unit = units_map.get(unit, 'шт')
                add_ingredient(name, quantity, unit)
                continue
            except:
                pass

    return ingredients

init_db()
CATEGORIES = ["Супы", "Вторые блюда", "Десерты и выпечка", "Консервация", "Колбасы", "Напитки", "Разное"]

tab1, tab2, tab3 = st.tabs(["📺 Загрузка", "📋 Рецепты", "💰 Цены"])

with tab1:
    st.subheader("Загрузка рецепта")
    input_mode = st.radio("Источник рецепта:", ["YouTube видео", "Ссылка на страницу"], horizontal=True)

    if input_mode == "YouTube видео":
        video_url = st.text_input("YouTube ссылка:", placeholder="https://youtube.com/watch?v=...")
        if st.button("🔄 Загрузить", type="primary", use_container_width=True):
            if not video_url.strip():
                st.error("❌ Введите ссылку")
            else:
                with st.spinner("⏳ Загружаю описание видео..."):
                    data = get_youtube_data(video_url)

                if data.get('error'):
                    st.error(f"❌ Ошибка: {data['error']}")
                else:
                    st.success("✅ Описание загружено!")

                    # Ищем рецепт в очищенном описании
                    ingredients = find_ingredients(data['description'])

                    if ingredients:
                        st.info(f"✅ Найдено ингредиентов: {len(ingredients)}")
                        st.session_state.ingredients = ingredients
                        st.session_state.video_url = video_url
                        st.session_state.video_title = data['title']
                    else:
                        st.warning("⚠️ Рецепт не найден в очищенном описании")
                        st.info("💡 Совет: Проверьте видео — там может быть рецепт в закрепленном комментарии")

    else:
        page_url = st.text_input("Ссылка на страницу:", placeholder="https://example.com/recipe...")
        if st.button("🔄 Загрузить", type="primary", use_container_width=True):
            if not page_url.strip():
                st.error("❌ Введите ссылку")
            else:
                with st.spinner("⏳ Загружаю страницу..."):
                    page_text = get_page_text(page_url)

                if page_text and len(page_text) > 100:
                    st.success("✅ Страница загружена!")
                    ingredients = find_ingredients(page_text)
                    if ingredients:
                        st.info(f"✅ Найдено ингредиентов: {len(ingredients)}")
                        st.session_state.ingredients = ingredients
                        st.session_state.video_url = page_url
                        st.session_state.video_title = "Рецепт со страницы"
                    else:
                        st.warning(f"⚠️ Текст загружен ({len(page_text)} символов), но ингредиенты не распознаны")
                else:
                    st.error("❌ Не удалось загрузить страницу или текст слишком короткий")

    if 'ingredients' in st.session_state and st.session_state.ingredients:
        st.divider()
        st.subheader("🥘 Найденные ингредиенты:")
        for ing in st.session_state.ingredients:
            st.write(f"• {ing['quantity']} {ing['unit']} {ing['name']}")

        st.divider()
        st.subheader("💾 Сохранить рецепт")
        default_name = st.session_state.get('video_title', '')
        recipe_name = st.text_input("Название рецепта:", value=default_name)
        category = st.selectbox("Категория:", CATEGORIES)
        if st.button("💾 Сохранить", type="primary", use_container_width=True):
            if not recipe_name.strip():
                st.error("❌ Введите название рецепта")
            else:
                video_url = st.session_state.get('video_url')
                save_recipe(recipe_name, category, st.session_state.ingredients, video_url)
                st.success(f"✅ Рецепт '{recipe_name}' сохранен!")
                if 'ingredients' in st.session_state:
                    del st.session_state.ingredients

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
                if st.button("🗑️ Удалить", key=f"delete_{recipe['id']}", use_container_width=True):
                    delete_recipe(recipe['id'])
                    st.success("✅ Рецепт удален")
                    st.rerun()
    else:
        st.info("📌 Рецептов нет. Загрузите рецепт в вкладке 'Загрузка'")

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

