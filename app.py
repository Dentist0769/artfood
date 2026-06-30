import streamlit as st
import re
import sqlite3
from typing import Optional, List, Dict
import pandas as pd
import json
import requests
from bs4 import BeautifulSoup

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
        pass
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
                     VALUES (?, ?, ?)''', (ingredient.lower().strip(), data['price'], data['unit']))
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

def clean_description(text: str) -> str:
    """Очистка текста от ссылок, реквизитов и блогерского спама"""
    if not text:
        return ""
    text = re.sub(r'https?://[^\s]+', '', text)
    text = re.sub(r'www\.[^\s]+', '', text)
    text = re.sub(r'\b\d{4}[-\s]?\d{4}[-\s]?\d{4}[-\s]?\d{4}\b', '', text)

    lines = text.split('\n')
    filtered_lines = []
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
        if not line_strip:
            continue
        if any(keyword in line_strip.lower() for keyword in junk_keywords):
            continue
        filtered_lines.append(line_strip)
        
    text = '\n'.join(filtered_lines)
    text = re.sub(r'#[а-яa-z0-9_]+', '', text, flags=re.IGNORECASE)
    text = re.sub(r'\n{2,}', '\n', text)
    return text.strip()

def get_youtube_data(video_url: str) -> Dict:
    try:
        import yt_dlp
        ydl_opts = {'quiet': True, 'no_warnings': True, 'socket_timeout': 15}
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(video_url, download=False)
            return {
                'description': clean_description(info.get('description', '')),
                'title': info.get('title', 'Unknown'),
                'error': None
            }
    except Exception as e:
        return {'description': '', 'title': 'Unknown', 'error': str(e)}

def get_page_text(url: str) -> Optional[str]:
    """Парсинг кулинарных сайтов с приоритетом на JSON-LD Recipe"""
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
        response = requests.get(url, headers=headers, timeout=10)
        response.encoding = 'utf-8'
        if response.status_code != 200:
            return None
        soup = BeautifulSoup(response.text, 'html.parser')
        
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
                    ing_list = recipe.get('recipeIngredient', [])
                    if ing_list:
                        for ing in ing_list:
                            clean_lines.append(ing.strip())
                        clean_lines.append("")
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
                                steps.append(f"Шаг {idx}. {BeautifulSoup(step_text, 'html.parser').get_text().strip()}")
                    combined = "\n".join(clean_lines).strip()
                    if len(combined) > 50:
                        return clean_description(combined)
            except:
                continue

        for tag in ['script', 'style', 'nav', 'header', 'footer', 'aside', 'form', 'noscript', 'button', 'svg']:
            for element in soup.find_all(tag):
                element.decompose()
        for selector in ['.header', '.footer', '.menu', '.sidebar', '.nav', '.breadcrumbs', '.comments', '.banner', '.sharing']:
            for element in soup.select(selector):
                element.decompose()
        return clean_description(soup.get_text('\n'))
    except:
        return None

def translate_text(text: str) -> str:
    if not text or not re.search(r'[a-zA-Z]', text):
        return text
    lines = text.split('\n')
    translated = []
    for line in lines:
        line_str = line.strip()
        if not line_str or not re.search(r'[a-zA-Z]', line_str):
            translated.append(line_str)
            continue
        try:
            url = "https://translate.googleapis.com/translate_a/single"
            params = {"client": "gtx", "sl": "auto", "tl": "ru", "dt": "t", "q": line_str}
            res = requests.get(url, params=params, timeout=5)
            if res.status_code == 200:
                translated.append("".join([part[0] for part in res.json()[0] if part[0]]).strip())
            else:
                translated.append(line_str)
        except:
            translated.append(line_str)
    return "\n".join(translated)

def find_ingredients(text: str) -> List[Dict]:
    if not text:
        return []
    lines = text.split('\n')
    ingredients = []
    seen = set()
    exclude_words = {'минут', 'минуты', 'минута', 'второ', 'часо', 'час', 'градусо', 'градусов',
                     'процесс', 'духов', 'духовк', 'разогреть', 'выпекать', 'смешать', 'взбить'}
    units_map = {
        'мл': 'мл', 'ml': 'мл', 'миллилитр': 'мл', 'миллилитров': 'мл',
        'г': 'г', 'g': 'г', 'грамм': 'г', 'граммов': 'г', 'грамма': 'г',
        'кг': 'кг', 'kg': 'кг', 'килограмм': 'кг',
        'л': 'л', 'l': 'л', 'литр': 'л', 'литров': 'л',
        'шт': 'шт', 'pcs': 'шт', 'штук': 'шт', 'штука': 'шт', 'штуки': 'шт',
        'ст.л': 'ст.л', 'ст л': 'ст.л', 'tbsp': 'ст.л', 'столовая': 'ст.л', 'ложка': 'ст.л',
        'ч.л': 'ч.л', 'ч л': 'ч.л', 'tsp': 'ч.л', 'чайная': 'ч.л'
    }

    def add_ing(name: str, qty: float, unit: str):
        if any(ex in name.lower() for ex in exclude_words): return
        name = re.sub(r'[,;.!?—()\[\]]', '', name).strip()
        if len(name) < 2 or len(name) > 50 or not any(c.isalpha() for c in name): return
        key = f"{name}_{unit}"
        if key not in seen and 0 < qty < 10000:
            ingredients.append({'name': name.lower(), 'quantity': qty, 'unit': unit})
            seen.add(key)

    all_units = "|".join(sorted(units_map.keys(), key=len, reverse=True))
    for line in lines:
        line = line.strip()
        if not line or len(line) < 3 or any(k in line.lower() for k in ['начинка', 'для теста', 'рецепт']): continue
        line = re.sub(r'(\d+)\s*[-—–]\s*(\d+)', r'\2', line)
        line = re.sub(r'\(.*?\)', '', line).strip()

        m = re.search(rf'([а-яa-z\s]+?)\.{2,}\s*(\d+(?:[.,]\d+)?)\s*({all_units})', line, re.IGNORECASE)
        if m:
            try:
                add_ing(m.group(1), float(m.group(2).replace(',', '.')), units_map.get(m.group(3).lower(), 'шт'))
                continue
            except: pass
        m = re.search(rf'([а-яa-z\s]+?)\s*[-—–:]\s*(\d+(?:[.,]\d+)?)\s*({all_units})', line, re.IGNORECASE)
        if m:
            try:
                add_ing(m.group(1), float(m.group(2).replace(',', '.')), units_map.get(m.group(3).lower(), 'шт'))
                continue
            except: pass
        m = re.search(rf'(\d+(?:[.,]\d+)?)\s*({all_units})\s+([а-яa-z\s]+?)', line, re.IGNORECASE)
        if m:
            try:
                add_ing(m.group(3), float(m.group(1).replace(',', '.')), units_map.get(m.group(2).lower(), 'шт'))
                continue
            except: pass
        m = re.search(rf'([а-яa-z\s]+?)\s+(\d+(?:[.,]\d+)?)\s*({all_units})\b', line, re.IGNORECASE)
        if m:
            try:
                add_ing(m.group(1), float(m.group(2).replace(',', '.')), units_map.get(m.group(3).lower(), 'шт'))
                continue
            except: pass
    return ingredients

def calculate_ingredient_cost(name: str, qty: float, unit: str, prices: dict) -> tuple[float, str]:
    name_clean = name.lower().strip()
    SYNONYMS = {
        'кабачки': 'цуккини', 'кабачок': 'цуккини', 'яйца': 'куриное яйцо', 'яйцо': 'куриное яйцо',
        'оливковое масло': 'масло растительное', 'растительное масло': 'масло растительное',
        'подсолнечное масло': 'масло растительное', 'соевый соус': 'соус соевый',
        'лимонный сок': 'лимон желтый', 'капуста': 'белокочанная капуста', 'картошка': 'картофель'
    }
    if name_clean in SYNONYMS:
        name_clean = SYNONYMS[name_clean]
    p_data = prices.get(name_clean)
    if not p_data:
        for k, v in prices.items():
            if k in name_clean or name_clean in k:
                p_data = v
                break
    if not p_data: return 0.0, "Нет цены в базе"
    
    p_price, p_unit = p_data['price'], p_data['unit'].lower().strip()
    u_rec = unit.lower().strip()
    if u_rec == p_unit: return qty * p_price, ""
    
    if u_rec == 'шт' and p_unit in ['кг', 'kg']:
        weights = {'помидоры': 0.12, 'цуккини': 0.30, 'лук репчатый': 0.10, 'чеснок': 0.01, 'куриное яйцо': 1.0}
        w = weights.get(name_clean, 0.10)
        if w == 1.0: return qty * p_price, ""
        return qty * w * p_price, f" (из шт в кг: ~{w*1000:.0f}г/шт)"
    if p_unit in ['кг', 'kg'] and u_rec in ['г', 'g', 'грамм', 'граммов']:
        return (qty / 1000.0) * p_price, ""
    if p_unit in ['кг', 'kg'] and u_rec in ['ч.л', 'ч л']:
        return (qty * 5.0 / 1000.0) * p_price, " (расчет как ~5г)"
    if p_unit in ['кг', 'kg'] and u_rec in ['ст.л', 'ст л']:
        return (qty * 15.0 / 1000.0) * p_price, " (расчет как ~15г)"
    if p_unit in ['л', 'l'] and u_rec in ['мл', 'ml']:
        return (qty / 1000.0) * p_price, ""
    return 0.0, f"Несоответствие ед. ({u_rec} vs {p_unit})"

init_db()
CATEGORIES = ["Супы", "Вторые блюда", "Десерты и выпечка", "Консервация", "Колбасы", "Напитки", "Разное"]
tab1, tab2, tab3 = st.tabs(["📺 Загрузка", "📋 Рецепты", "💰 Цены"])

with tab1:
    st.subheader("Загрузка рецепта")
    input_mode = st.radio("Источник:", ["YouTube видео", "Ссылка на страницу"], horizontal=True)
    if input_mode == "YouTube видео":
        video_url = st.text_input("YouTube ссылка:", placeholder="https://youtube.com/watch?v=...")
        if st.button("🔄 Загрузить", type="primary", use_container_width=True):
            if video_url.strip():
                with st.spinner("⏳ Обработка видео..."):
                    data = get_youtube_data(video_url)
                if data.get('error'): st.error(f"❌ Ошибка: {data['error']}")
                else:
                    trans_desc = translate_text(data['description'])
                    st.session_state.ingredients = find_ingredients(trans_desc)
                    st.session_state.recipe_description = trans_desc
                    st.session_state.video_url = video_url
                    st.session_state.video_title = translate_text(data['title'])
                    st.success("✅ Описание готово!")
    else:
        page_url = st.text_input("Ссылка на страницу:", placeholder="https://food.ru/recipes/...")
        if st.button("🔄 Загрузить", type="primary", use_container_width=True):
            if page_url.strip():
                with st.spinner("⏳ Анализ страницы..."):
                    page_text = get_page_text(page_url)
                if page_text:
                    trans_page = translate_text(page_text)
                    st.session_state.ingredients = find_ingredients(trans_page)
                    st.session_state.recipe_description = trans_page
                    st.session_state.video_url = page_url
                    st.session_state.video_title = "Рецепт со страницы"
                    st.success("✅ Страница обработана!")
                else: st.error("❌ Не удалось загрузить страницу")

    if 'recipe_description' in st.session_state:
        st.divider()
        col_ing, col_desc = st.columns([1, 2])
        with col_ing:
            st.subheader("🥘 Компоненты:")
            if st.session_state.ingredients:
                for ing in st.session_state.ingredients:
                    st.write(f"• {ing['quantity']} {ing['unit']} {ing['name']}")
            else: st.info("Компоненты пустые — настройте их вручную.")
        with col_desc:
            st.subheader("📝 Инструкция:")
            edited_description = st.text_area("Текст процесса:", value=st.session_state.recipe_description, height=300)
        st.divider()
        recipe_name = st.text_input("Название рецепта:", value=st.session_state.get('video_title', ''))
        category = st.selectbox("Категория:", CATEGORIES)
        if st.button("💾 Подтвердить и сохранить рецепт", type="primary", use_container_width=True):
            if recipe_name.strip():
                save_recipe(recipe_name, category, st.session_state.ingredients, edited_description, st.session_state.get('video_url'))
                st.success("✅ Рецепт успешно сохранен!")
                del st.session_state.ingredients
                del st.session_state.recipe_description
                st.rerun()

with tab2:
    st.subheader("📋 База рецептов")
    filter_category = st.selectbox("Категория:", ["Все"] + CATEGORIES)
    recipes = get_recipes(None if filter_category == "Все" else filter_category)
    system_prices = get_prices()
    if recipes:
        for recipe in recipes:
            with st.expander(f"📄 {recipe['name']} ({recipe['category']})"):
                if recipe['video_url']: st.write(r"**Источник:** [Открыть ссылку](%s)" % recipe['video_url'])
                portions = st.number_input("Количество порций:", min_value=1, value=1, key=f"p_{recipe['id']}")
                st.divider()
                v1, v2 = st.columns([1, 2])
                total_cost = 0.0
                with v1:
                    st.markdown("**Ингредиенты и стоимость:**")
                    for ing in recipe['ingredients']:
                        cost, warn = calculate_ingredient_cost(ing['name'], ing['quantity'], ing['unit'], system_prices)
                        total_cost += cost
                        if warn == "Нет цены в базе":
                            st.write(f"• {ing['quantity']} {ing['unit']} {ing['name']} — <span style='color:gray;'>*{warn}*</span>", unsafe_allow_html=True)
                        elif "Несоответствие" in warn:
                            st.write(f"• {ing['quantity']} {ing['unit']} {ing['name']} — <span style='color:orange;'>*{warn}*</span>", unsafe_allow_html=True)
                        else:
                            st.write(f"• {ing['quantity']} {ing['unit']} {ing['name']} — **${cost:.2f}** <span style='color:green; font-size:11px;'>{warn}</span>", unsafe_allow_html=True)
                    st.divider()
                    st.metric("💰 Стоимость замеса:", f"${total_cost:.2f}")
                    if portions > 1: st.metric("🍽️ Себестоимость 1 порции:", f"${(total_cost / portions):.2f}")
                with v2:
                    st.markdown("**Процесс приготовления:**")
                    st.write(recipe['description'] if recipe['description'] else "Описание отсутствует.")
                st.divider()
                if st.button("🗑️ Удалить рецепт", key=f"del_{recipe['id']}", use_container_width=True):
                    delete_recipe(recipe['id'])
                    st.rerun()
    else: st.info("📌 Рецептов пока нет.")

with tab3:
    st.subheader("💰 Управление ценами")
    uploaded_file = st.file_uploader("Загрузить прайс-лист (.txt, .csv):", type=["txt", "csv"])
    if uploaded_file:
        try:
            content = uploaded_file.read().decode('utf-8')
            prices = {}
            for line in content.strip().split('\n'):
                parts = line.split('\t') if '\t' in line else line.split(',')
                if len(parts) >= 3:
                    try:
                        prices[parts[0].strip()] = {'price': float(parts[1].strip()), 'unit': parts[2].strip()}
                    except: continue
            if prices:
                st.success(f"✅ Найдено {len(prices)} позиций")
                if st.button("💾 Записать цены в базу", type="primary", use_container_width=True):
                    save_prices(prices)
                    st.success("✅ Цены сохранены!")
                st.dataframe(pd.DataFrame([{'Ингредиент': k, 'Цена': v['price'], 'Единица': v['unit']} for k, v in prices.items()]), use_container_width=True)
        except Exception as e: st.error(f"❌ Ошибка: {e}")
    st.divider()
    st.write("**Текущие цены:**")
    current_prices = get_prices()
    if current_prices:
        st.dataframe(pd.DataFrame([{'Ингредиент': k, 'Цена': v['price'], 'Единица': v['unit']} for k, v in current_prices.items()]), use_container_width=True)
        st.write("**Добавить цену вручную:**")
        c1, c2, c3 = st.columns(3)
        with c1: man_name = st.text_input("Ингредиент:", placeholder="Например: мука пшеничная")
        with c2: man_price = st.number_input("Цена ($):", min_value=0.0, step=0.1)
        with c3: man_unit = st.selectbox("Единица:", ["кг", "г", "л", "мл", "шт"])
        if st.button("➕ Добавить позицию", use_container_width=True):
            if man_name.strip():
                save_prices({man_name: {'price': man_price, 'unit': man_unit}})
                st.rerun()
    else: st.info("📌 База цен пуста.")
      
