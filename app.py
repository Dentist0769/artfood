import streamlit as st
import re
import sqlite3
import logging
import time
from typing import Optional, List, Dict
from functools import lru_cache
import pandas as pd
import json
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from bs4 import BeautifulSoup

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

st.set_page_config(page_title="🍳 Кулинарный калькулятор PRO", layout="wide")
st.title("🍳 Кулинарный калькулятор (PRO)")
st.markdown("Управление рецептами и расчет себестоимости")

MAX_FILE_SIZE = 5 * 1024 * 1024

def init_db():
    conn = sqlite3.connect('recipes.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS recipes (
        id INTEGER PRIMARY KEY, name TEXT NOT NULL, category TEXT NOT NULL,
        ingredients TEXT NOT NULL, video_url TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, description TEXT
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS prices (
        id INTEGER PRIMARY KEY, ingredient TEXT UNIQUE NOT NULL, price REAL NOT NULL, unit TEXT NOT NULL, updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )''')
    conn.commit()
    conn.close()

def is_safe_string(text: str, max_len: int = 500) -> bool:
    if not text or len(text) > max_len: return False
    if re.search(r"(?i)(DROP|DELETE|INSERT|UPDATE|SELECT)\s", text): return False
    return True

def save_recipe(name: str, category: str, ingredients: List[Dict], description: str, video_url: Optional[str] = None):
    if not is_safe_string(name, 200) or not is_safe_string(description, 10000): return False
    conn = sqlite3.connect('recipes.db')
    c = conn.cursor()
    try:
        c.execute('''INSERT INTO recipes (name, category, ingredients, description, video_url) VALUES (?, ?, ?, ?, ?)''', 
                  (name, category, json.dumps(ingredients), description, video_url))
        conn.commit()
        return True
    except Exception as e: return False
    finally: conn.close()

def update_recipe_full(recipe_id: int, new_name: str, new_ingredients: List[Dict], new_description: str):
    if not is_safe_string(new_name, 200) or not is_safe_string(new_description, 10000): return False
    conn = sqlite3.connect('recipes.db')
    c = conn.cursor()
    try:
        c.execute('''UPDATE recipes SET name = ?, ingredients = ?, description = ? WHERE id = ?''',
                  (new_name, json.dumps(new_ingredients), new_description, recipe_id))
        conn.commit()
        return True
    except Exception as e: return False
    finally: conn.close()

def get_recipes(category: Optional[str] = None) -> List[Dict]:
    conn = sqlite3.connect('recipes.db')
    c = conn.cursor()
    if category:
        c.execute('SELECT id, name, category, ingredients, video_url, created_at, description FROM recipes WHERE category = ? ORDER BY created_at DESC', (category,))
    else:
        c.execute('SELECT id, name, category, ingredients, video_url, created_at, description FROM recipes ORDER BY created_at DESC')
    rows = c.fetchall()
    conn.close()
    recipes = []
    for row in rows:
        try:
            recipes.append({'id': row[0], 'name': row[1], 'category': row[2], 'ingredients': json.loads(row[3]), 'video_url': row[4], 'created_at': row[5], 'description': row[6] if row[6] else ""})
        except: continue
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
        try: c.execute('INSERT OR REPLACE INTO prices (ingredient, price, unit) VALUES (?, ?, ?)', (ingredient.lower().strip(), float(data['price']), data['unit']))
        except: continue
    conn.commit()
    conn.close()

def get_prices() -> Dict[str, Dict]:
    conn = sqlite3.connect('recipes.db')
    c = conn.cursor()
    c.execute('SELECT ingredient, price, unit FROM prices')
    rows = c.fetchall()
    conn.close()
    return {row[0]: {'price': row[1], 'unit': row[2]} for row in rows}

def clean_description(text: str) -> str:
    if not text: return ""
    text = re.sub(r'<[^>]+>', '', text)
    text = re.sub(r'https?://[^\s]+', '', text)
    text = re.sub(r'www\.[^\s]+', '', text)
    text = re.sub(r'\b\d{4}[-\s]?\d{4}[-\s]?\d{4}[-\s]?\d{4}\b', '', text)
    ad_keywords = ['telegram', 'tg.me', 'монобанк', 'промокод', 'скидка', 'подпишись', 'subscribe', 'instagram', 'инстаграм', 'vk.com', 'донат', 'donat', 'сбербанк', 'тинькофф', 'номер карты', 'жми на колокольчик', 'поставь лайк']
    lines = text.split('\n')
    filtered = [l.strip() for l in lines if l.strip() and not any(k in l.lower() for k in ad_keywords)]
    return '\n'.join(filtered)

def get_page_text(url: str) -> Optional[str]:
    try:
        session = requests.Session()
        session.mount("https://", HTTPAdapter(max_retries=Retry(total=2)))
        res = session.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=15)
        res.encoding = 'utf-8'
        soup = BeautifulSoup(res.text, 'html.parser')
        scripts = soup.find_all('script', type='application/ld+json')
        for script in scripts:
            try:
                data = json.loads(script.string)
                if 'Recipe' in str(data):
                    clean_lines = [ing for ing in data.get('recipeIngredient', [])]
                    return clean_description("\n".join(clean_lines))
            except: continue
        for tag in ['script', 'style', 'nav', 'header', 'footer', 'aside']:
            for el in soup.find_all(tag): el.decompose()
        return clean_description(soup.get_text('\n'))
    except: return None

def get_youtube_data(video_url: str) -> Dict:
    try:
        import yt_dlp
        with yt_dlp.YoutubeDL({'quiet': True, 'socket_timeout': 15}) as ydl:
            info = ydl.extract_info(video_url, download=False)
            return {'description': clean_description(info.get('description', '')), 'title': info.get('title', 'Unknown'), 'error': None}
    except Exception as e: return {'description': '', 'title': 'Unknown', 'error': str(e)}

@lru_cache(maxsize=500)
def translate_line(line: str) -> str:
    if not line or not re.search(r'[a-zA-Z]', line): return line
    try:
        res = requests.get("https://translate.googleapis.com/translate_a/single", params={"client": "gtx", "sl": "auto", "tl": "ru", "dt": "t", "q": line}, timeout=5)
        if res.status_code == 200: return "".join([part[0] for part in res.json()[0] if part[0]]).strip()
    except: pass
    return line

def translate_text(text: str) -> str:
    if not text or not re.search(r'[a-zA-Z]', text): return text
    return "\n".join([translate_line(l) for l in text.split('\n')])

def find_ingredients(text: str) -> List[Dict]:
    if not text: return []
    text_clean = re.sub(r'\(.*?\)', ' ', text)
    units_map = {
        'мл': 'мл', 'ml': 'мл', 'миллилитр': 'мл', 'г': 'г', 'g': 'г', 'грамм': 'г', 'кг': 'кг', 'kg': 'кг', 'л': 'л', 'l': 'л', 'литр': 'л',
        'шт': 'шт', 'pcs': 'шт', 'штук': 'шт', 'ст.л': 'ст.л', 'ст л': 'ст.л', 'tbsp': 'ст.л', 'ч.л': 'ч.л', 'ч л': 'ч.л', 'tsp': 'ч.л'
    }
    all_units = "|".join(sorted(units_map.keys(), key=len, reverse=True))
    text_clean = re.sub(r'(\d+)\s*[-—–]\s*(\d+)', r'\2', text_clean)
    matches = list(re.finditer(rf'\b(\d+(?:[.,]\d+)?)\s*({all_units})\b', text_clean, re.IGNORECASE))
    ingredients = []
    seen = set()
    
    for i, match in enumerate(matches):
        try:
            qty = float(match.group(1).replace(',', '.'))
            unit = units_map[match.group(2).lower()]
            prev_end = matches[i-1].end() if i > 0 else 0
            left_chunk = text_clean[prev_end:match.start()]
            if '=' in left_chunk: continue
            
            left_name = re.sub(r'[\n,;.!?—–-•:*=…\s]+$', '', left_chunk).strip()
            name = re.split(r'[\n,;=•]', left_name)[-1].strip()
            if not name or len(name) < 2:
                right_chunk = text_clean[match.end():(matches[i+1].start() if i < len(matches)-1 else len(text_clean))]
                name = re.split(r'[\n,;=•]', right_chunk)[0].strip()
            
            name = re.sub(r'^(хороший пучок|пучок|долька|зубчик|можно)\s+', '', name, flags=re.IGNORECASE).strip().lower()
            if len(name) < 2 or len(name) > 50 or any(x in name for x in ['минут', 'градус', 'духов']): continue
            
            key = f"{name}_{unit}"
            if key not in seen:
                ingredients.append({'name': name, 'quantity': qty, 'unit': unit})
                seen.add(key)
        except: continue
    return ingredients

INGREDIENT_WEIGHTS = {'помидоры': 0.15, 'цуккини': 0.25, 'кабачки': 0.25, 'лук репчатый': 0.08, 'лук': 0.08, 'чеснок': 0.005, 'куриное яйцо': 0.05, 'яйцо': 0.05, 'огурец': 0.1}

def calculate_ingredient_cost(name: str, qty: float, unit: str, prices: dict) -> tuple:
    name_clean = name.lower().strip()
    SYNONYMS = {'кабачки': 'цуккини', 'кабачок': 'цуккини', 'яйца': 'куриное яйцо', 'яйцо': 'куриное яйцо', 'оливковое масло': 'масло растительное', 'растительное масло': 'масло растительное', 'лук': 'лук репчатый', 'капуста': 'белокочанная капуста', 'сметана': 'сметана emborg'}
    if name_clean in SYNONYMS: name_clean = SYNONYMS[name_clean]
    
    p_data = prices.get(name_clean)
    if not p_data:
        for k, v in prices.items():
            if k in name_clean or name_clean in k: p_data = v; name_clean = k; break
            
    if not p_data:
        if 'вода' in name_clean or 'отвар' in name_clean: return 0.0, " (бесплатный компонент)"
        return 0.0, "Нет цены в базе"
        
    p_price, p_unit = p_data['price'], p_data['unit'].lower().strip()
    u_rec = unit.lower().strip()
    
    if u_rec == p_unit: return qty * p_price, ""
    if u_rec == 'шт' and p_unit in ['кг', 'kg']:
        w = INGREDIENT_WEIGHTS.get(name_clean, 0.1)
        return qty * w * p_price, f" (~{w*1000:.0f}г/шт)"
    if p_unit in ['л', 'l'] and u_rec in ['мл', 'ml']: return (qty / 1000.0) * p_price, ""
    if p_unit in ['л', 'l'] and u_rec in ['ч.л', 'ч л', 'ст.л', 'ст л']:
        coef = 0.005 if 'ч' in u_rec else 0.015
        return qty * coef * p_price, ""
    if p_unit in ['кг', 'kg'] and u_rec in ['г', 'g']: return (qty / 1000.0) * p_price, ""
    if p_unit in ['кг', 'kg'] and u_rec in ['ч.л', 'ч л', 'ст.л', 'ст л']:
        coef = 0.005 if 'ч' in u_rec else 0.015
        return qty * coef * p_price, ""
    return 0.0, "Несоответствие ед."

init_db()
tab1, tab2, tab3 = st.tabs(["📺 Загрузка", "📋 Рецепты", "💰 Цены"])

with tab1:
    st.subheader("Загрузка рецепта")
    input_mode = st.radio("Источник:", ["YouTube видео", "Ссылка на страницу"], horizontal=True)
    if input_mode == "YouTube видео":
        video_url = st.text_input("YouTube ссылка:")
        if st.button("🔄 Загрузить видео", type="primary", use_container_width=True):
            with st.spinner("⏳ Обработка..."): data = get_youtube_data(video_url)
            if data.get('error'): st.error("❌ Ошибка загрузки")
            else:
                t_desc = translate_text(data['description'])
                st.session_state.ingredients = find_ingredients(t_desc)
                st.session_state.recipe_description = t_desc
                st.session_state.video_url = video_url
                st.session_state.video_title = translate_text(data['title'])
    else:
        page_url = st.text_input("Ссылка на страницу:")
        if st.button("🔄 Загрузить страницу", type="primary", use_container_width=True):
            with st.spinner("⏳ Парсинг..."): page_text = get_page_text(page_url)
            if page_text:
                t_page = translate_text(page_text)
                st.session_state.ingredients = find_ingredients(t_page)
                st.session_state.recipe_description = t_page
                st.session_state.video_url = page_url
                st.session_state.video_title = "Рецепт со страницы"
            else: st.error("❌ Не удалось загрузить")

    if 'recipe_description' in st.session_state:
        st.divider()
        c_ing, c_desc = st.columns([1, 2])
        with c_ing:
            st.subheader("🥘 Компоненты:")
            for ing in st.session_state.ingredients: st.write(f"• {ing['quantity']} {ing['unit']} {ing['name']}")
        with c_desc:
            st.subheader("📝 Инструкция:")
            edited_description = st.text_area("Текст процесса:", value=st.session_state.recipe_description, height=250)
        recipe_name = st.text_input("Название рецепта:", value=st.session_state.get('video_title', ''))
        category = st.selectbox("Категория:", CATEGORIES)
        if st.button("💾 Сохранить рецепт в базу", type="primary", use_container_width=True):
            if save_recipe(recipe_name, category, st.session_state.ingredients, edited_description, st.session_state.get('video_url')):
                st.success("✅ Сохранено!")
                del st.session_state.ingredients, st.session_state.recipe_description
                st.rerun()

with tab2:
    st.subheader("📋 База рецептов")
    filter_category = st.selectbox("Категория:", ["Все"] + CATEGORIES)
    recipes = get_recipes(None if filter_category == "Все" else filter_category)
    system_prices = get_prices()
    if recipes:
        for recipe in recipes:
            with st.expander(f"📄 {recipe['name']} ({recipe['category']})"):
                if recipe['video_url']: st.link_button("🔗 Открыть источник", recipe['video_url'])
                
                # Счетчик порций доступен глобально для expander
                portions = st.number_input("Количество порций:", min_value=1, value=1, key=f"p_{recipe['id']}")
                edit_mode = st.checkbox("✏️ Режим редактирования рецепта", key=f"edit_mode_{recipe['id']}")
                st.divider()
                
                if edit_mode:
                    edit_name = st.text_input("Название блюда:", value=recipe['name'], key=f"edit_name_{recipe['id']}")
                    current_ings_text = "\n".join([f"{ing['name']} {ing['quantity']} {ing['unit']}" for ing in recipe['ingredients']])
                    edit_ings_text = st.text_area("Ингредиенты (каждый с новой строки):", value=current_ings_text, height=180, key=f"edit_ing_{recipe['id']}")
                    
                    # ИНТЕРАКТИВНЫЙ РАСЧЕТ ПРЯМО В РЕЖИМЕ РЕДАКТИРОВАНИЯ
                    st.markdown("📉 **Себестоимость на лету (меняется при редактировании текста):**")
                    live_ings = find_ingredients(edit_ings_text)
                    live_total = 0.0
                    for ing in live_ings:
                        cost, warn = calculate_ingredient_cost(ing['name'], ing['quantity'], ing['unit'], system_prices)
                        live_total += cost
                        st.write(f"• {ing['quantity']} {ing['unit']} {ing['name']} — **${cost:.2f}** {warn}" if not warn or "$" in str(cost) else f"• {ing['quantity']} {ing['unit']} {ing['name']} — *{warn}*")
                    st.metric("💰 Итого замес:", f"${live_total:.2f}")
                    if portions > 1: st.metric("🍽️ На 1 порцию:", f"${(live_total / portions):.2f}")
                    st.divider()
                    
                    edit_desc = st.text_area("Процесс приготовления:", value=recipe['description'], height=200, key=f"edit_desc_{recipe['id']}")
                    if st.button("💾 Сохранить изменения", key=f"save_all_{recipe['id']}", type="primary", use_container_width=True):
                        if update_recipe_full(recipe['id'], edit_name.strip(), find_ingredients(edit_ings_text), edit_desc):
                            st.success("✅ Изменения зафиксированы!")
                            st.rerun()
                else:
                    v1, v2 = st.columns([1, 2])
                    total_cost = 0.0
                    with v1:
                        st.markdown("**Компоненты и стоимость:**")
                        for ing in recipe['ingredients']:
                            cost, warn = calculate_ingredient_cost(ing['name'], ing['quantity'], ing['unit'], system_prices)
                            total_cost += cost
                            st.write(f"• {ing['quantity']} {ing['unit']} {ing['name']} — **${cost:.2f}** {warn}" if not warn or "$" in str(cost) else f"• {ing['quantity']} {ing['unit']} {ing['name']} — *{warn}*")
                        st.divider()
                        st.metric("💰 Стоимость замеса:", f"${total_cost:.2f}")
                        if portions > 1: st.metric("🍽️ На 1 порцию:", f"${(total_cost / portions):.2f}")
                    with v2:
                        st.markdown("**Инструкция:**")
                        st.write(recipe['description'] if recipe['description'] else "Описание отсутствует.")
                st.divider()
                if st.button("🗑️ Удалить рецепт", key=f"del_{recipe['id']}", use_container_width=True):
                    delete_recipe(recipe['id']); st.rerun()
    else: st.info("📌 Рецептов пока нет.")

with tab3:
    st.subheader("💰 Управление ценами")
    uploaded_file = st.file_uploader("Загрузить прайс (.txt, .csv):", type=["txt", "csv"])
    if uploaded_file and uploaded_file.size <= MAX_FILE_SIZE:
        try:
            content = uploaded_file.read().decode('utf-8')
            prices = {}
            for line in content.strip().split('\n'):
                parts = line.split('\t') if '\t' in line else line.split(',')
                if len(parts) >= 3:
                    try: prices[parts[0].strip()] = {'price': float(parts[1].strip()), 'unit': parts[2].strip()}
                    except: continue
            if prices:
                st.success(f"✅ Найдено {len(prices)} позиций")
                if st.button("💾 Записать цены", type="primary", use_container_width=True):
                    save_prices(prices); st.success("✅ Сохранено!"); st.rerun()
                st.dataframe(pd.DataFrame([{'Ингредиент': k, 'Цена': v['price'], 'Единица': v['unit']} for k, v in prices.items()]), use_container_width=True)
        except Exception as e: st.error(f"❌ Ошибка: {e}")
    st.divider()
    current_prices = get_prices()
    if current_prices:
        st.dataframe(pd.DataFrame([{'Ингредиент': k, 'Цена': v['price'], 'Единица': v['unit']} for k, v in current_prices.items()]), use_container_width=True)
        st.write("**Добавить цену вручную:**")
        c1, c2, c3 = st.columns(3)
        with c1: man_name = st.text_input("Ингредиент:")
        with c2: man_price = st.number_input("Цена ($):", min_value=0.0, step=0.1)
        with c3: man_unit = st.selectbox("Единица:", ["кг", "г", "л", "мл", "шт"])
        if st.button("➕ Добавить позицию", use_container_width=True):
            if man_name.strip(): save_prices({man_name: {'price': man_price, 'unit': man_unit}}); st.rerun()
    else: st.info("📌 База цен пуста.")
