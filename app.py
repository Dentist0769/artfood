"""
🍳 КУЛИНАРНЫЙ КАЛЬКУЛЯТОР
Полностью готовый код - просто скопируйте и используйте!
БЕЗ каких-либо изменений
"""

import streamlit as st
import requests
import re
from typing import Optional

st.set_page_config(page_title="🍳 Кулинарный калькулятор", layout="wide")

st.title("🍳 Калькулятор себестоимости блюд")
st.markdown("Вставьте ссылку на YouTube видео рецепта → приложение загрузит субтитры → рассчитает стоимость")

# ============================================================================
# ЧАСТЬ 1: Получение субтитров YouTube (работает везде, без блокировок!)
# ============================================================================

class GetSubtitles:
    """Получает субтитры из YouTube через Invidious"""

    # Список источников (если один не работает, пробует другой)
    SOURCES = [
        "https://invidious.io",
        "https://inv.nadeko.net",
        "https://invidious.be",
        "https://yewtu.be",
    ]

    @staticmethod
    def get_video_id(url: str) -> Optional[str]:
        """Извлекает ID видео из ссылки"""
        pattern = r'(?:youtube\.com\/watch\?v=|youtu\.be\/)([^&\n?#]+)'
        match = re.search(pattern, url)
        return match.group(1) if match else None

    @staticmethod
    def fetch(video_url: str) -> Optional[str]:
        """Загружает субтитры"""
        video_id = GetSubtitles.get_video_id(video_url)

        if not video_id:
            st.error("❌ Это не YouTube ссылка")
            return None

        for source in GetSubtitles.SOURCES:
            try:
                # Получаем информацию о видео
                response = requests.get(
                    f"{source}/api/v1/videos/{video_id}",
                    timeout=8
                )

                if response.status_code != 200:
                    continue

                data = response.json()
                captions = data.get('captions', [])

                if not captions:
                    st.error("❌ Субтитры не найдены. Выберите видео с субтитрами")
                    return None

                # Загружаем субтитры
                caption_url = f"{source}{captions[0]['url']}"
                caption_response = requests.get(caption_url, timeout=8)

                if caption_response.status_code == 200:
                    # Парсим VTT формат в текст
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

            except Exception:
                continue

        return None


# ============================================================================
# ЧАСТЬ 2: Парсинг ингредиентов (находит количество и название)
# ============================================================================

def find_ingredients(text: str) -> list:
    """Находит ингредиенты в тексте (число + единица + название)"""
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
# ЧАСТЬ 3: Интерфейс приложения
# ============================================================================

# Вкладка 1: Загрузка видео
tab1, tab2 = st.tabs(["📺 Загрузка видео", "💰 Расчет стоимости"])

with tab1:
    st.subheader("Шаг 1: Вставьте ссылку на видео")

    video_url = st.text_input(
        "YouTube ссылка",
        placeholder="https://youtube.com/watch?v=...",
        label_visibility="collapsed"
    )

    if st.button("🔄 Загрузить субтитры", type="primary", use_container_width=True):
        if not video_url:
            st.error("❌ Введите ссылку")
        else:
            with st.spinner("⏳ Загружаю субтитры..."):
                transcript = GetSubtitles.fetch(video_url)

            if transcript:
                st.success("✅ Загружено!")

                # Показываем текст
                st.text_area(
                    "Текст видео",
                    value=transcript,
                    height=200,
                    disabled=True
                )

                # Показываем найденные ингредиенты
                st.subheader("🥘 Найденные ингредиенты:")
                ingredients = find_ingredients(transcript)

                if ingredients:
                    for ing in ingredients:
                        st.write(f"• {ing['quantity']} {ing['unit']} {ing['name']}")

                    # Сохраняем в памяти приложения
                    st.session_state.ingredients = ingredients
                    st.session_state.transcript = transcript
                    st.info("✅ Перейдите на вкладку 'Расчет стоимости' и введите цены")
                else:
                    st.warning("⚠️ Ингредиенты не найдены. Возможно, в видео не упоминаются количества (число + единица измерения)")

with tab2:
    st.subheader("Шаг 2: Введите цены ингредиентов")

    if 'ingredients' not in st.session_state:
        st.info("📌 Сначала загрузите видео на вкладке слева")
    else:
        ingredients = st.session_state.ingredients

        if not ingredients:
            st.warning("Нет ингредиентов для расчета")
        else:
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

            # Кнопка расчета
            if st.button("🧮 Рассчитать стоимость", type="primary", use_container_width=True):
                st.subheader("📊 Результат")

                total_cost = 0
                details = []

                for ing in ingredients:
                    price_per_unit = prices[ing['name']]

                    # Конвертируем в граммы для справедливого расчета
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
                    st.metric("📊 Количество ингредиентов", len(ingredients))

                with col3:
                    if total_cost > 0:
                        st.metric("💹 Стоимость блюда", f"≈ {total_cost:.0f} ₽")

                # Скачивание результата
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
