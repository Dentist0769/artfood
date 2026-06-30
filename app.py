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
    
    try:
        c.execute('''ALTER TABLE recipes ADD COLUMN description TEXT''')
    except sqlite3.OperationalError:
        pass # Колонка уже существует
        
    c.execute('''CREATE TABLE IF NOT EXISTS prices (
        id INTEGER PRIMARY KEY,
        ingredient TEXT UNIQUE NOT NULL,
        price REAL NOT NULL,
        unit TEXT NOT NULL,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )''')
    conn.commit()
    conn.close()

def save_recipe(name: str, category: str, ingredients: List[Dict], description: str, video_url: Optional[str] = None):
    conn = sqlite3.connect('recipes.db')
    c = conn.cursor()
    import json
    ingredients_json = json.dumps(ingredients)
    c.execute('''INSERT INTO recipes (name, category, ingredients, description, video_url)
                 VALUES (?, ?, ?, ?, ?)''', (name, category, ingredients_json, description, video_url))
    conn.commit()
    conn.close()

def get_recipes(category: Optional[str] = None) -> List[Dict]:
    conn = sqlite3.connect('recipes.db')
    c = conn.cursor()
    if category:
        c.execute('''SELECT id, name, category, ingredients, video_url, created_at, description
                     FROM recipes WHERE category = ? ORDER BY created_at DESC''', (category,))
    else:
        c.execute('''SELECT id, name, category, ingredients, video_url, created_at, description
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
            'created_at': row[5],
            'description': row[6] if row[6] else ""
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
    """Глубокая очистка текста от ссылок, хэштегов, реквизитов, соцсетей и блогерских призывов"""
    if not text:
        return ""

    # Удаляем ссылки
    text = re.sub(r'https?://[^\s]+', '', text)
    text = re.sub(r'www\.[^\s]+', '', text)
    
    # Удаляем номера карт
    text = re.sub(r'\b\d{4}[-\s]?\d{4}[-\s]?\d{4}[-\s]?\d{4}\b', '', text)

    lines = text.split('\n')
    filtered_lines = []
    
    # Расширенный список мусорных фраз (RU + EN из скриншотов)
    junk_keywords = [
        'telegram', 'tg.me', 'монобанк', 'промокод', 'скидка', 'подпишись', 'subscribe',
        'instagram', 'инстаграм', 'vk.com', 'вконтакте', 'facebook', 'patreon', 'paypal', 
        'донат', 'donat', 'поддержать канал', 'сбербанк', 'тинькофф', 'номер карты', 
        'реквизиты', 'сотрудничество', 'cooperation', 'реклама', 'плейлист', 'смотрите также', 
        'предыдущее видео', 'мой канал', 'tiktok', 'тикток', 'дзен', 'dzen',
        'расшифровка', 'transcription', 'как это было сделано', 'жми на колокольчик', 'поставь лайк',
        'dear friends', 'see you on my channel', 'time and attention', 'good mood', 'enjoy watching',
        'turn on subtitles', 'automatically translated', 'write to me', 'happy to answer',
        'with pleasure and love', 'filled with warmth', 'sincerely wish', 'support the channel',
        'helps and motivates', 'give a like', 'leave a comment', 'any questions', 'share the video',
        'for your warmth', 'channel come alive', 'attention!', 'ингредиенты:', 'ingredients:'
    ]
    
    for line in lines:
        line_strip = line.strip()
        line_lower = line_strip.lower()
        if not line_strip:
            continue
        if any(keyword in line_lower for keyword in junk_keywords):
            continue
        filtered_lines.append(line_strip)
        
    text = '\n'.join(filtered_lines)
    text = re.sub(r'#[а-яa-z0-9_]+', '', text, flags=re.IGNORECASE)
    text = re.sub(r'\n{2,}', '\n', text)
    text = re.sub(r' +', ' ', text)

    return text.strip()

def get_youtube_data(video_url: str) -> Dict:
    """Получает описание видео и очищает его"""
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
            clean_desc = clean_description(description)

            return {
                'description': clean_desc,
                'title': info.get('title', 'Unknown'),
                'comments': None
            }
    except Exception as e:
        return {
            'description': '',
            'title': 'Unknown',
            'comments': None,
            'error': str(e)
        }

def get_page_text(url: str) -> Optional[str]:
    """Парсит и очищает текст со страницы сайта, извлекая только чистый контент рецепта"""
    try:
        import requests
        from bs4 import BeautifulSoup
        import json
        
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'}
        response = requests.get(url, headers=headers, timeout=10)
        response.encoding = 'utf-8'
        if response.status_code != 200:
            return None
            
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # --- СТРАТЕГИЯ 1: Извлечение через JSON-LD (микроразметка Schema.org Recipe) ---
        scripts = soup.find_all('script', type='application/ld+json')
        for script in scripts:
            try:
                if not script.string:
                    continue
                data = json.loads(script.string)
                
                recipes = []
                def search_recipe(obj):
                    if isinstance(obj, dict):
                        if obj.get('@type') == 'Recipe' or (isinstance(obj.get('@type'), list) and 'Recipe' in obj.get('@type')):
                            recipes.append(obj)
                        for v in obj.values():
                            search_recipe(v)
                    elif isinstance(obj, list):
                        for item in obj:
                            search_recipe(item)
                            
                search_recipe(data)
                
                if recipes:
                    recipe = recipes[0]
                    clean_lines = []
                    
                    # Собираем ингредиенты для распознавания парсером компонентов
                    ing_list = recipe.get('recipeIngredient', [])
                    if ing_list:
                        for ing in ing_list:
                            if isinstance(ing, str):
                                clean_lines.append(ing.strip())
                        clean_lines.append("") # Отступ
                        
                    # Собираем шаги приготовления
                    instructions_raw = recipe.get('recipeInstructions', [])
                    if instructions_raw:
                        steps = []
                        if isinstance(instructions_raw, list):
                            for step in instructions_raw:
                                if isinstance(step, dict):
                                    steps.append(step.get('text', step.get('name', '')))
                                elif isinstance(step, str):
                                    steps.append(step)
                        elif isinstance(instructions_raw, str):
                            steps.append(instructions_raw)
                            
                        for idx, step_text in enumerate(steps, 1):
                            if step_text:
                                # Очищаем текст шага от возможных внутренних HTML тегов
                                step_pure = BeautifulSoup(step_text, "html.parser").get_text()
                                clean_lines.append(f"Шаг {idx}. {step_pure.strip()}")
                                
                    combined_text = "\n".join(clean_lines).strip()
                    if len(combined_text) > 50:
                        return clean_description(combined_text)
            except:
                continue
                
        # --- СТРАТЕГИЯ 2: Фаллбэк (Если микроразметки нет, жестко чистим структуру HTML) ---
        for trash_tag in ['script', 'style', 'nav', 'header', 'footer', 'aside', 'form', 'noscript', 'button', 'svg']:
            for element in soup.find_all(trash_tag):
                element.decompose()
                
        for selector in ['.header', '.footer', '.menu', '.sidebar', '.nav', '.breadcrumbs', '.comments', '.banner', '.sharing']:
            for element in soup.select(selector):
                element.decompose()
                
        text = soup.get_text('\n')
        return clean_description(text)
        
    except Exception as e:
        return None

def translate_text(text: str) -> str:
    """Переводит иностранный текст на русский язык без использования ключей API"""
    if not text:
        return ""
    
    if not re.search(r'[a-zA-Z]', text):
        return text
        
    import requests
    lines = text.split('\n')
    translated_lines = []
    
    for line in lines:
        line_str = line.strip()
        if not line_str:
            continue
        
        if not re.search(r'[a-zA-Z]', line_str):
            translated_lines.append(line_str)
            continue
            
        try:
            url = "https://translate.googleapis.com/translate_a/single"
            params = {
                "client": "gtx",
                "sl": "auto",
                "tl": "ru",
                "dt": "t",
                "q": line_str
            }
            response = requests.get(url, params=params, timeout=5)
            if response.status_code == 200:
                res_json = response.json()
                translated_chunk = "".join([part[0] for part in res_json[0] if part[0]])
                translated_lines.append(translated_chunk.strip())
            else:
                translated_lines.append(line_str)
        except:
            translated_lines.append(line_str)
            
    return "\n".join(translated_lines)

def find_ingredients(text: str) -> List[Dict]:
    """Автоматически извлекает ингредиенты и объемы из переведенного текста"""
    if not text:
        return []

    lines = text.split('\n')
    ingredients = []
    seen = set()

    exclude_words = {'минут', 'минуты', 'минута', 'второ', 'часо', 'час', 'градусо', 'градусов',
                     'градусе', 'целью', 'цвет', 'время', 'температу', 'температур', 'процесс',
                     'духов', 'духовк', 'разогреть', 'выпекать', 'оставить', 'смешать', 'взбить'}

    units_map = {
        'мл': 'мл', 'ml': 'мл', 'миллилитр': 'мл', 'миллилитров': 'мл', 'миллилитра': 'мл',
        'г': 'г', 'g': 'г', 'грамм': 'г', 'граммов': 'г', 'грамма': 'г',
        'кг': 'кг', 'kg': 'кг', 'килограмм': 'кг', 'килограмма': 'кг',
        'л': 'л', 'l': 'л', 'литр': 'л', 'литров': 'л', 'литра': 'л',
        'шт': 'шт', 'pcs': 'шт', 'штук': 'шт', 'штука': 'шт', 'штуки': 'шт',
        'ст.л': 'ст.л', 'ст л': 'ст.л', 'tbsp': 'ст.л', 'столовая': 'ст.л', 'столовых': 'ст.л', 'столовые': 'ст.л', 'ложка': 'ст.л', 'ложки': 'ст.л',
        'ч.л': 'ч.л', 'ч л': 'ч.л', 'tsp': 'ч.л', 'чайная': 'ч.л', 'чайных': 'ч.л', 'чайные': 'ч.л'
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
        if key not in seen and 0 < quantity < 10000:
            ingredients.append({'name': name.lower(), 'quantity': quantity, 'unit': unit})
            seen.add(key)

    all_units_pattern = "|".join(sorted(units_map.keys(), key=len, reverse=True))

    for line in lines:
        line = line.strip()
        if not line or len(line) < 3:
            continue

        if any(keyword in line.lower() for keyword in ['начинка', 'для теста', 'для сиропа', 'рецепт']):
            continue

        match = re.search(rf'([а-яa-z\s\(\)]+?)\.{2,}\s*(\d+(?:[.,]\d+)?)\s*(?:{all_units_pattern})', line, re.IGNORECASE)
        if match:
            name = match.group(1).strip()
            quantity_str = match.group(2).replace(',', '.')
            try:
                quantity = float(quantity_str)
                unit = 'шт'
                for unit_key, unit_val in units_map.items():
                    if unit_key.lower() in line.lower():
                        unit = unit_val
                        break
                add_ingredient(name, quantity, unit)
                continue
            except:
                pass

        match = re.search(rf'([а-яa-z\s]+?)\s*[-—–]\s*(\d+(?:[.,]\d+)?)\s*({all_units_pattern})', line, re.IGNORECASE)
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

        match = re.search(rf'(\d+(?:[.,]\d+)?)\s*({all_units_pattern})\s+([а-яa-z\s\(\)]+?)(?:[,;]|$)', line, re.IGNORECASE)
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
                with st.spinner("⏳ Загружаю, очищаю и перевожу описание видео..."):
                    data = get_youtube_data(video_url)

                if data.get('error'):
                    st.error(f"❌ Ошибка: {data['error']}")
                else:
                    translated_description = translate_text(data['description'])
                    translated_title = translate_text(data['title'])
                    
                    st.success("✅ Описание успешно переведено и очищено!")
                    
                    ingredients = find_ingredients(translated_description)

                    st.session_state.ingredients = ingredients
                    st.session_state.recipe_description = translated_description
                    st.session_state.video_url = video_url
                    st.session_state.video_title = translated_title
                    
                    if not ingredients:
                        st.warning("⚠️ Список ингредиентов автоматически не определен. Вы сможете настроить его в текстовом поле.")

    else:
        page_url = st.text_input("Ссылка на страницу:", placeholder="https://example.com/recipe...")
        if st.button("🔄 Загрузить", type="primary", use_container_width=True):
            if not page_url.strip():
                st.error("❌ Введите ссылку")
            else:
                with st.spinner("⏳ Загружаю и фильтрую страницу..."):
                    page_text = get_page_text(page_url)

                if page_text and len(page_text) > 100:
                    translated_page = translate_text(page_text)
                    st.success("✅ Страница загружена и очищена от навигационного мусора!")
                    ingredients = find_ingredients(translated_page)
                    
                    st.session_state.ingredients = ingredients
                    st.session_state.recipe_description = translated_page
                    st.session_state.video_url = page_url
                    st.session_state.video_title = "Рецепт со страницы"
                else:
                    st.error("❌ Не удалось загрузить страницу или извлечь чистый текст рецепта")

    if 'recipe_description' in st.session_state:
        st.divider()
        col_ing, col_desc = st.columns([1, 2])
        
        with col_ing:
            st.subheader("🥘 Компоненты:")
            if st.session_state.ingredients:
                for ing in st.session_state.ingredients:
                    st.write(f"• {ing['quantity']} {ing['unit']} {ing['name']}")
            else:
                st.info("Компоненты пустые — добавьте их при необходимости в текст инструкции.")
        
        with col_desc:
            st.subheader("📝 Процесс приготовления:")
            edited_description = st.text_area(
                "Текст рецепта (на русском, без лишнего мусора):", 
                value=st.session_state.recipe_description, 
                height=300
            )

        st.divider()
        st.subheader("💾 Сохранить рецепт")
        default_name = st.session_state.get('video_title', '')
        recipe_name = st.text_input("Название рецепта:", value=default_name)
        category = st.selectbox("Категория:", CATEGORIES)
        
        if st.button("💾 Подтвердить и сохранить", type="primary", use_container_width=True):
            if not recipe_name.strip():
                st.error("❌ Введите название рецепта")
            else:
                v_url = st.session_state.get('video_url')
                save_recipe(recipe_name, category, st.session_state.ingredients, edited_description, v_url)
                st.success(f"✅ Рецепт '{recipe_name}' сохранен!")
                
                del st.session_state.ingredients
                del st.session_state.recipe_description
                st.rerun()

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
                    st.write(f"**Источник:** [Открыть ссылку]({recipe['video_url']})")
                
                st.divider()
                view_col1, view_col2 = st.columns([1, 2])
                
                with view_col1:
                    st.markdown("**Ингредиенты:**")
                    for ing in recipe['ingredients']:
                        st.write(f"• {ing['quantity']} {ing['unit']} {ing['name']}")
                
                with view_col2:
                    st.markdown("**Инструкция по приготовлению:**")
                    if recipe['description']:
                        st.write(recipe['description'])
                    else:
                        st.caption("Описание процесса отсутствует.")
                
                st.divider()
                if st.button("🗑️ Удалить рецепт", key=f"delete_{recipe['id']}", use_container_width=True):
                    delete_recipe(recipe['id'])
                    st.success("✅ Рецепт удален")
                    st.rerun()
    else:
        st.info("📌 Рецептов нет.")

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
        st.info("📌 Цены не загружены.")
