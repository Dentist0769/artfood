"""
🍳 КУЛИНАРНЫЙ КАЛЬКУЛЯТОР (ИСПРАВЛЕННАЯ ВЕРСИЯ)
Полностью готовый код - просто скопируйте и используйте!
"""

import streamlit as st
import requests
import re
from typing import Optional

st.set_page_config(page_title="🍳 Кулинарный калькулятор", layout="wide")

st.title("🍳 Калькулятор себестоимости блюд")
st.markdown("Вставьте ссылку на YouTube видео рецепта → приложение загрузит субтитры → рассчитает стоимость")

# ============================================================================
# ПОЛУЧЕНИЕ СУБТИТРОВ
# ============================================================================

def get_video_id(url: str) -> Optional[str]:
    """Извлекает ID видео из ссылки"""
    try:
        pattern = r'(?:youtube\.com\/watch\?v=|youtu\.be\/)([^&\n?#]+)'
        match = re.search(pattern, url)
        return match.group(1) if match else None
    except:
        return None


def get_subtitles(video_id: str) -> Optional[str]:
    """Загружает субтитры через Invidious API"""

    sources = [
        "https://invidious.io",
        "https://inv.nadeko.net",
        "https://invidious.be",
        "https://yewtu.be",
    ]

    for source in sources:
        try:
            # Получаем информацию о видео
            url = f"{source}/api/v1/videos/{video_id}"
            response = requests.get(url, timeout=8)

            if response.status_code != 200:
                continue

            data = response.json()
            captions = data.get('captions', [])

            if not captions:
                continue

            # Загружаем субтитры
            caption_url = f"{source}{captions[0]['url']}"
            caption_response = requests.get(caption_url, timeout=8)

            if caption_response.status_code == 200:
                # Парсим VTT
                lines = caption_response.text.split('\n')
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

        except Exception as e:
            continue

    return None


def find_ingredients(text: str) -> list:
    """Находит ингредиенты"""
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
# ИНТЕРФЕЙС
# ============================================================================

tab1, tab2 = st.tabs(["📺 Загрузка видео", "💰 Расчет стоимости"])

with tab1:
    st.subheader("Шаг 1: Вставьте ссылку на видео")

    col1, col2 = st.columns([4, 1])

    with col1:
        video_url = st.text_input(
            "YouTube ссылка",
            placeholder="https://youtube.com/watch?v=...",
            label_visibility="collapsed"
        )

    with col2:
        load_button = st.button("🔄 Загрузить", type="primary", use_container_width=True)

    if load_button:
        if not video_url.strip():
            st.error("❌ Введите ссылку")
        else:
            try:
                video_id = get_video_id(video_url)

                if not video_id:
                    st.error("❌ Это не YouTube ссылка")
                else:
                    with st.spinner("⏳ Загружаю субтитры (может занять 10-15 сек)..."):
                        transcript = get_subtitles(video_id)

                    if transcript:
                        st.success("✅ Загружено!")

                        st.text_area(
                            "Текст видео",
                            value=transcript,
                            height=200,
                            disabled=True
                        )

                        st.subheader("🥘 Найденные ингредиенты:")
                        ingredients = find_ingredients(transcript)

                        if ingredients:
                            for ing in ingredients:
                                st.write(f"• {ing['quantity']} {ing['unit']} {ing['name']}")

                            st.session_state.ingredients = ingredients
                            st.session_state.transcript = transcript
                            st.info("✅ Перейдите на вкладку 'Расчет стоимости'")
                        else:
                            st.warning("⚠️ Ингредиенты не найдены")

                    else:
                        st.error("❌ Не удалось загрузить субтитры. Возможно видео без субтитров или Invidious недоступен. Попробуйте через 1-2 минуты.")

            except Exception as e:
                st.error(f"❌ Ошибка: {str(e)}")

with tab2:
    st.subheader("Шаг 2: Введите цены ингредиентов")

    if 'ingredients' not in st.session_state or not st.session_state.ingredients:
        st.info("📌 Сначала загрузите видео на вкладке слева")
    else:
        ingredients = st.session_state.ingredients

        try:
            # Форма для ввода цен
            col1, col2, col3 = st.columns(3)

            prices = {}
            for i, ing in enumerate(ingredients):
                if i % 3 == 0:
                    col = col1
                elif i % 3 == 1:
                    col = col2
                else:
                    col = col3

                with col:
                    price = st.number_input(
                        f"{ing['name']}",
                        value=100.0,
                        min_value=0.0,
                        step=10.0,
                        key=f"price_{i}"
                    )
                    prices[ing['name']] = price

            # Расчет
            if st.button("🧮 Рассчитать стоимость", type="primary", use_container_width=True):
                st.subheader("📊 Результат")

                total_cost = 0
                details = []

                for ing in ingredients:
                    price_per_unit = prices[ing['name']]

                    # Конвертируем в граммы
                    if ing['unit'] == 'кг':
                        weight = ing['quantity'] * 1000
                    elif ing['unit'] == 'л':
                        weight = ing['quantity'] * 1000
                    else:
                        weight = ing['quantity']

                    # Рассчитываем стоимость
                    if ing['unit'] in ['г', 'мл']:
                        cost = (weight / 1000) * price_per_unit
                    else:
                        cost = ing['quantity'] * price_per_unit

                    total_cost += cost

                    details.append({
                        "Ингредиент": ing['name'],
                        "Количество": f"{ing['quantity']} {ing['unit']}",
                        "Цена за единицу": f"{price_per_unit} ₽",
                        "Стоимость": f"{cost:.2f} ₽"
                    })

                # Таблица
                import pandas as pd
                df = pd.DataFrame(details)
                st.dataframe(df, use_container_width=True, hide_index=True)

                # Итоги
                st.divider()
                col1, col2, col3 = st.columns(3)

                with col1:
                    st.metric("💵 Общая стоимость", f"{total_cost:.2f} ₽")

                with col2:
                    st.metric("📊 Ингредиентов", len(ingredients))

                with col3:
                    st.metric("💹 За блюдо", f"{total_cost:.0f} ₽")

                # Скачивание
                report = f"""
ОТЧЕТ: Себестоимость блюда
=====================================

ИНГРЕДИЕНТЫ:
"""
                for detail in details:
                    report += f"\n{detail['Ингредиент']}: {detail['Количество']} = {detail['Стоимость']}"

                report += f"\n\nОБЩАЯ СТОИМОСТЬ: {total_cost:.2f} ₽"

                st.download_button(
                    "📥 Скачать отчет",
                    data=report,
                    file_name="recipe_cost.txt",
                    mime="text/plain",
                    use_container_width=True
                )

        except Exception as e:
            st.error(f"❌ Ошибка при расчете: {str(e)}")

       
