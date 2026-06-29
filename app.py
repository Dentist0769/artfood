import streamlit as st
import json
import os
from google import generativeai as genai
from youtube_transcript_api import YouTubeTranscriptApi

st.set_page_config(page_title="Кулинарный ассистент", page_icon="👨‍🍳", layout="centered")

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

if 'products' not in st.session_state:
    st.session_state.products = {}
if 'recipes' not in st.session_state:
    st.session_state.recipes = []

def get_video_id(url):
    if "youtu.be" in url:
        return url.split("/")[-1].split("?")[0]
    elif "youtube.com" in url:
        if "v=" in url:
            return url.split("v=")[1].split("&")[0]
    return None

def get_youtube_transcript(video_id):
    try:
        # Пытаемся забрать сначала родные русские или автоматические субтитры
        transcript_list = YouTubeTranscriptApi.get_transcript(video_id, languages=['ru'])
        return " ".join([item['text'] for item in transcript_list])
    except Exception:
        try:
            # Если русских нет, забираем английские
            transcript_list = YouTubeTranscriptApi.get_transcript(video_id, languages=['en'])
            return " ".join([item['text'] for item in transcript_list])
        except Exception:
            return None

def call_gemini(prompt, api_key):
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel('gemini-2.5-flash')
    response = model.generate_content(prompt)
    return response.text

st.title("👨‍🍳 Кулинарный ассистент")

with st.sidebar:
    st.header("⚙️ Настройки")
    api_key = st.text_input("Gemini API Key", type="password", value=os.getenv("GEMINI_API_KEY", ""))
    if api_key:
        st.success("API ключ подключен!")

tab_calc, tab_book, tab_prices = st.tabs(["🔢 Калькулятор ссылок", "📖 Книга рецептов", "💰 Цены на продукты"])

# ВКЛАДКА 1: КАЛЬКУЛЯТОР
with tab_calc:
    st.subheader("Автоматический расчет по ссылке")
    url_input = st.text_input("Вставь ссылку на YouTube видео:")
    
    if st.button("Рассчитать себестоимость", type="primary"):
        if not api_key:
            st.error("Пожалуйста, введи API ключ в боковой панели!")
        elif not url_input:
            st.warning("Вставь ссылку!")
        else:
            with st.spinner("Извлекаем оригинальный текст видео и строим техкарту..."):
                video_id = get_video_id(url_input)
                transcript = get_youtube_transcript(video_id) if video_id else None
                
                if not transcript:
                    st.error("Ютуб заблокировал чтение субтитров для этого видео. Скопируй текст описания под видео и вставь его вместо ссылки — ИИ всё посчитает!")
                else:
                    prompt = f"""
                    Ты — эксперт-технолог. Перед тобой ОРИГИНАЛЬНЫЙ ТЕКСТ СУБТИТРОВ из видео: "{transcript}".
                    Внимательно прочитай его. Твоя задача — строго по этому тексту составить рецепт. 
                    Ничего не выдумывай со сторонних сайтов! Если в тексте говорят про хлеб или чиабатту, делай хлеб.
                    
                    Выдели:
                    1. Название блюда.
                    2. Категорию ('soups', 'mains', 'salads', 'desserts', 'drinks', 'sausages', 'preserved', 'other').
                    3. Ингредиенты: переведи названия на русский язык, нижний регистр, именительный падеж. Объемы переведи строго в граммы или миллилитры.
                    4. Шаги приготовления.

                    Ответь СТРОГО в формате JSON без markdown разметки:
                    {{
                      "title": "Название блюда",
                      "category": "ключ_категории",
                      "ingredients": [{{"name": "мука", "amount": 500, "unit": "г"}}],
                      "steps": ["Шаг 1..."]
                    }}
                    """
                    
                    try:
                        res_text = call_gemini(prompt, api_key)
                        res_text = res_text.replace("```json", "").replace("```", "").strip()
                        recipe_data = json.loads(res_text)
                        
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
                        st.success(f"✓ Рецепт '{new_recipe['title']}' успешно добавлен!")
                        st.metric("Итого себестоимость:", f"${total_cost:.2f}")
                        
                    except Exception as e:
                        st.error(f"Ошибка анализа ИИ: {e}")

# ВКЛАДКА 2: КНИГА РЕЦЕПТОВ
with tab_book:
    st.subheader("Твоя база рецептов")
    if not st.session_state.recipes:
        st.info("Здесь будут отображаться сохраненные рецепты.")
    else:
        for cat_key, cat_label in CATEGORIES.items():
            cat_recipes = [r for r in st.session_state.recipes if r['category'] == cat_key]
            if cat_recipes:
                with st.expander(f"{cat_label} ({len(cat_recipes)})"):
                    for r in cat_recipes:
                        st.markdown(f"### 🍳 {r['title']}")
                        st.markdown(f"**Себестоимость:** ${r['cost']:.2f}")
                        if r['url']:
                            st.markdown(f"[📺 Смотреть видео]({r['url']})")
                        
                        st.markdown("**Технологическая карта:**")
                        for item in r['tech_card']:
                            cost_str = f"${item['cost']:.2f}" if item['found'] else "❌ нет цены"
                            st.markdown(f"• {item['name']}: {item['amount']} {item.get('unit', 'г')} — {cost_str}")
                        
                        if r['steps']:
                            st.markdown("**Приготовление:**")
                            for idx, step in enumerate(r['steps']):
                                st.markdown(f"{idx+1}. {step}")
                        st.divider()

# ВКЛАДКА 3: ЦЕНЫ
with tab_prices:
    st.subheader("Управление прайс-листом")
    col1, col2, col3 = st.columns([2, 1, 1])
    with col1:
        new_prod = st.text_input("Название продукта:")
    with col2:
        new_price = st.number_input("Цена за 1 кг/л ($):", min_value=0.0, step=0.01)
    with col3:
        st.write("<style>div.row-widget.stButton > button{margin-top:28px;}</style>", unsafe_allow_html=True)
        if st.button("Добавить"):
            if new_prod:
                st.session_state.products[new_prod.lower().strip()] = new_price
                st.success("Добавлено!")

    if st.session_state.products:
        st.markdown("### Текущий прайс-лист ($)")
        for name, price in sorted(st.session_state.products.items()):
            st.markdown(f"🍏 **{name}** — ${price:.2f} за кг/л")
