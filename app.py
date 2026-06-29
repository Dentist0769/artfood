import streamlit as st
import json
import os
from google import generativeai as genai
from quick_integration import YouTubeTranscriptApiFree

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

tab_calc, tab_book, tab_prices = st.tabs(["🔢 Умный калькулятор", "📖 Книга рецептов", "💰 Цены на продукты"])

# ВКЛАДКА 1: КАЛЬКУЛЯТОР
with tab_calc:
    st.subheader("Расчет по ссылке или тексту")
    user_input = st.text_area("Вставь сюда ссылку на YouTube или готовый текст рецепта:", height=120)
    
    if st.button("Обработать", type="primary"):
        if not api_key:
            st.error("Пожалуйста, введи API ключ в боковой панели!")
        elif not user_input.strip():
            st.warning("Поле пустое!")
        else:
            with st.spinner("Invidious и ИИ анализируют источник..."):
                transcript_text = ""
                
                # Проверяем, вставил ли пользователь ссылку
                if "youtube.com" in user_input or "youtu.be" in user_input:
                    try:
                        # Используем бесплатный обход Клода через Invidious
                        result = YouTubeTranscriptApiFree.get_transcript(user_input, languages=['ru', 'en'])
                        video_id = list(result.keys())[0]
                        transcript_text = " ".join([item['text'] for item in result[video_id]])
                        context = f"Это оригинальный текст субтитров видео YouTube: {transcript_text}"
                    except Exception as e:
                        # Если даже Invidious не справился (например, нет субтитров у видео)
                        context = f"Ссылка на кулинарное видео: {user_input}. Пожалуйста, используй свои знания ИИ, чтобы восстановить точный рецепт этого блюда по названию видео."
                else:
                    # Если пользователь вставил просто скопированный текст
                    context = user_input

                prompt = f"""
                Ты — эксперт-технолог. Перед тобой кулинарные данные: "{context}".
                Твоя цель — составить точный рецепт. 
                Внимательно изучи ингредиенты. Никакой отсебятины! Если речь идет о хлебе или окрошке, делай их.

                Выдели:
                1. Название блюда.
                2. Категорию ('soups', 'mains', 'salads', 'desserts', 'drinks', 'sausages', 'preserved', 'other').
                3. Ингредиенты: названия строго на русском языке (нижний регистр, ед.число, именительный падеж). Все объемы переведи строго в граммы или миллилитры.
                4. Шаги приготовления.

                Ответь СТРОГО в формате JSON без markdown разметки:
                {{
                  "title": "Название блюда",
                  "category": "ключ_категории",
                  "ingredients": [{{"name": "мука", "amount": 1000, "unit": "г"}}],
                  "steps": ["Шаг 1..."]
                }}
                """
                
                try:
                    res_text = call_gemini(prompt, api_key)
                    res_text = res_text.replace("```json", "").replace("```", "").strip()
                    ai_data = json.loads(res_text)
                    
                    total_cost = 0.0
                    tech_card = []
                    for ing in ai_data.get('ingredients', []):
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
                      'title': ai_data['title'],
                      'category': ai_data.get('category', 'other'),
                      'tech_card': tech_card,
                      'cost': total_cost,
                      'steps': ai_data.get('steps', [])
                    }
                    st.session_state.recipes.insert(0, new_recipe)
                    st.success(f"✓ Рецепт '{new_recipe['title']}' успешно сохранен!")
                    st.metric("Себестоимость блюда:", f"${total_cost:.2f}")
                    
                except Exception as e:
                    st.error(f"Ошибка ИИ: {e}")

# ВКЛАДКА 2: КНИГА РЕЦЕПТОВ
with tab_book:
    st.subheader("Твоя база рецептов")
    if not st.session_state.recipes:
        st.info("Здесь будут сохраненные рецепты.")
    else:
        for cat_key, cat_label in CATEGORIES.items():
            cat_recipes = [r for r in st.session_state.recipes if r['category'] == cat_key]
            if cat_recipes:
                with st.expander(f"{cat_label} ({len(cat_recipes)})"):
                    for r in cat_recipes:
                        st.markdown(f"### 🍳 {r['title']}")
                        st.markdown(f"**Себестоимость:** ${r['cost']:.2f}")
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
    st.subheader("Прайс-лист")
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
        st.markdown("### Текущие цены ($)")
        for name, price in sorted(st.session_state.products.items()):
            st.markdown(f"🍏 **{name}** — ${price:.2f} за кг/л")
