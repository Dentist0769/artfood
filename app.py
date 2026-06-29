import streamlit as st
import json
import os
from google import generativeai as genai
from youtube_transcript_api import YouTubeTranscriptApi

# Настройка страницы в стиле Apple / чистого интерфейса
st.set_page_config(page_title="Кулинарный ассистент", page_icon="👨‍🍳", layout="centered")

# Категории книги рецептов
CATEGORIES = {
    'soups': '🍲 Супы',
    'mains': '🥩 Вторые блюда',
    'salads': '🥗 Салаты',
    'desserts': '🍰 Десерты',
    'drinks': '🍹 Напитки',
    'sausages': '🌭 Колбасы',
    'preserved': '🫙 Консервация',
    'other': '📦 Разное'
}

# Инициализация локальной базы данных (в памяти сессии)
if 'products' not in st.session_state:
    st.session_state.products = {}
if 'recipes' not in st.session_state:
    st.session_state.recipes = []

# Функция извлечения ID видео из ссылки YouTube
def get_video_id(url):
    if "youtu.be" in url:
        return url.split("/")[-1].split("?")[0]
    elif "youtube.com" in url:
        if "v=" in url:
            return url.split("v=")[1].split("&")[0]
    return None

# Функция получения субтитров YouTube
def get_youtube_transcript(video_id):
    try:
        transcript_list = YouTubeTranscriptApi.get_transcript(video_id, languages=['ru', 'en'])
        return " ".join([item['text'] for item in transcript_list])
    except Exception:
        return None

# Функция вызова Gemini
def call_gemini(prompt, api_key, file_bytes=None, mime_type=None):
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel('gemini-2.5-flash')
    
    contents = []
    if file_bytes:
        contents.append({'data': file_bytes, 'mime_type': mime_type})
    contents.append(prompt)
    
    response = model.generate_content(contents)
    return response.text

# --- ИНТЕРФЕЙС ПРИЛОЖЕНИЯ ---
st.title("👨‍🍳 Кулинарный ассистент")

# Боковая панель для API ключа
with st.sidebar:
    st.header("⚙️ Настройки")
    api_key = st.text_input("Gemini API Key", type="password", value=os.getenv("GEMINI_API_KEY", ""))
    if api_key:
        st.success("API ключ подключен!")

# Главные вкладки приложения
tab_calc, tab_book, tab_prices = st.tabs(["🔢 Калькулятор ссылок", "📖 Книга рецептов", "💰 Цены на продукты"])

# ==========================================
# ВКЛАДКА 1: КАЛЬКУЛЯТОР ССЫЛОК
# ==========================================
with tab_calc:
    st.subheader("Автоматический расчет по ссылке")
    url_input = st.text_input("Вставь ссылку на YouTube видео или кулинарный сайт:")
    
    if st.button("Рассчитать себестоимость", type="primary"):
        if not api_key:
            st.error("Пожалуйста, введи API ключ в боковой панели!")
        elif not url_input:
            st.warning("Вставь ссылку!")
        else:
            with st.spinner("ИИ извлекает субтитры и анализирует рецепт..."):
                video_id = get_video_id(url_input)
                transcript = get_youtube_transcript(video_id) if video_id else None
                
                context_text = f"Ссылка: {url_input}. "
                if transcript:
                    context_text += f"Текст субтитров видео: {transcript}"
                else:
                    context_text += "Субтитры недоступны, используй свои знания интернета или поиск для этого видео."

                prompt = f"""
                Проанализируй этот кулинарный источник: "{context_text}".
                Выдели название блюда, определи категорию и составь список ингредиентов.
                Названия продуктов переведи строго на русский язык, в нижний регистр и именительный падеж (например: 'мука пшеничная', 'масло сливочное'). 
                Все объемы переведи строго в граммы (г) или миллилитры (мл). Если указаны шт или ложки, переведи в примерный вес в граммах (1 яйцо = 50г, 1 ст.л. сахара = 20г).
                Выдели пошаговые шаги приготовления, если они упоминаются.

                Ответь строго в формате JSON без markdown разметки:
                {{
                  "title": "Название блюда",
                  "category": "один из ключей: 'soups', 'mains', 'salads', 'desserts', 'drinks', 'sausages', 'preserved', 'other'",
                  "ingredients": [{{"name": "мука", "amount": 500, "unit": "г"}}],
                  "steps": ["Шаг 1..."]
                }}
                """
                
                try:
                    res_text = call_gemini(prompt, api_key)
                    res_text = res_text.replace("```json", "").replace("```", "").strip()
                    recipe_data = json.loads(res_text)
                    
                    # Расчет себестоимости
                    total_cost = 0.0
                    tech_card = []
                    for ing in recipe_data.get('ingredients', []):
                        name = ing['name'].lower().strip()
                        amount = ing['amount']
                        price = st.session_state.products.get(name, None)
                        
                        cost = (amount / 1000) * price if price is not None else 0.0
                        if price is not None:
                            total_cost += cost
                            
                        tech_card.append({
                            'name': name,
                            'amount': amount,
                            'unit': ing['unit'],
                            'cost': cost,
                            'found': price is not None
                        })
                    
                    # Сохраняем рецепт в базу
                    new_recipe = {
                        'id': len(st.session_state.recipes),
                        'title': recipe_data['title'],
                        'category': recipe_data.get('category', 'other'),
                        'url': url_input,
                        'tech_card': tech_card,
                        'cost': total_cost,
                        'steps': recipe_data.get('steps', [])
                    }
                    st.session_state.recipes.insert(0, new_recipe)
                    
                    st.success(f"✓ Рецепт '{new_recipe['title']}' успешно добавлен в книгу!")
                    st.metric("Итого себестоимость блюда:", f"${total_cost:.2f}")
                    
                except Exception as e:
                    st.error(f"Ошибка обработки: {e}")

# ==========================================
# ВКЛАДКА 2: КНИГА РЕЦЕПТОВ
# ==========================================
with tab_book:
    st.subheader("Твоя база рецептов")
    if not st.session_state.recipes:
        st.info("Здесь будут отображаться сохраненные рецепты по категориям.")
    else:
        for cat_key, cat_label in CATEGORIES.items():
            cat_recipes = [r for r in st.session_state.recipes if r['category'] == cat_key]
            if cat_recipes:
                with st.expander(f"{cat_label} ({len(cat_recipes)})"):
                    for r in cat_recipes:
                        st.markdown(f"### 🍳 {r['title']}")
                        st.markdown(f"**Себестоимость:** ${r['cost']:.2f}")
                        if r['url']:
                            st.markdown(f"[📺 Смотреть видео / Источник]({r['url']})")
                        
                        # Таблица ингредиентов
                        st.markdown("**Технологическая карта:**")
                        for item in r['tech_card']:
                            cost_str = f"${item['cost']:.2f}" if item['found'] else "❌ нет цены"
                            st.markdown(f"• {item['name']}: {item['amount']}{item.get('unit', 'г')} — {cost_str}")
                        
                        if r['steps']:
                            st.markdown("**Приготовление:**")
                            for idx, step in enumerate(r['steps']):
                                st.markdown(f"{idx+1}. {step}")
                        st.divider()

# ==========================================
# ВКЛАДКА 3: ЦЕНЫ НА ПРОДУКТЫ
# ==========================================
with tab_prices:
    st.subheader("Управление прайс-листом")
    
    # Мощная функция: загрузка PDF прайса напрямую
    uploaded_file = st.file_uploader("📁 Загрузить PDF прайс поставщика (P&P)", type=["pdf"])
    if uploaded_file and st.button("Распознать и обновить цены из PDF", type="secondary"):
        if not api_key:
            st.error("Введи API-ключ в боковую панель для перевода прайса!")
        else:
            with st.spinner("Gemini читает PDF, переводит названия на русский язык и вытаскивает цены в $..."):
                try:
                    file_bytes = uploaded_file.read()
                    prompt = """
                    Изучи этот прайс-лист поставщика. Извлеки ВСЕ продукты и их цены.
                    Переведи названия продуктов строго на русский язык, приведи к именительному падежу, единственному числу и нижнему регистру (например: 'мука пшеничная', 'брокколи', 'томат'). 
                    Цены оставь как есть (в долларах) за 1 кг или 1 литр. 
                    Верни ответ строго в формате чистого JSON:
                    {"products": [{"name": "брокколи", "price": 2.50}, {"name": "томат", "price": 1.50}]}
                    """
                    res_prices = call_gemini(prompt, api_key, file_bytes, "application/pdf")
                    res_prices = res_prices.replace("```json", "").replace("```", "").strip()
                    prices_data = json.loads(res_prices)
                    
                    added_count = 0
                    for p in prices_data.get('products', []):
                        if p.get('name') and p.get('price'):
                            st.session_state.products[p['name'].lower().strip()] = float(p['price'])
                            added_count += 1
                    st.success(f"✓ Успешно загружено и переведено {added_count} позиций из PDF прайса!")
                except Exception as e:
                    st.error(f"Не удалось считать PDF: {e}")

    st.divider()
    
    # Ручное добавление
    col1, col2, col3 = st.columns([2, 1, 1])
    with col1:
        new_prod = st.text_input("Название продукта вручную:")
    with col2:
        new_price = st.number_input("Цена за 1 кг/л ($):", min_value=0.0, step=0.01)
    with col3:
        st.write("<style>div.row-widget.stButton > button{margin-top:28px;}</style>", unsafe_allow_html=True)
        if st.button("Добавить"):
            if new_prod:
                st.session_state.products[new_prod.lower().strip()] = new_price
                st.success("Добавлено!")

    # Вывод таблицы продуктов
    if st.session_state.products:
        st.markdown("### Текущий прайс-лист ($)")
        sorted_prods = sorted(st.session_state.products.items())
        for name, price in sorted_prods:
            st.markdown(f"🍏 **{name}** — ${price:.2f} за кг/л")
