"""
🍳 КАЛЬКУЛЯТОР С ЛОГИРОВАНИЕМ (для отладки)
"""

import streamlit as st
import requests
import re
from typing import Optional
import sys

st.set_page_config(page_title="🍳 Кулинарный калькулятор", layout="wide")

st.title("🍳 Калькулятор себестоимости блюд")
st.markdown("Вставьте ссылку на YouTube видео рецепта → приложение загрузит субтитры → рассчитает стоимость")

# ============================================================================
# ЛОГИРОВАНИЕ
# ============================================================================

def log(message: str):
    """Выводит логи в консоль и в приложение"""
    print(f"[LOG] {message}", file=sys.stderr)


def get_video_id(url: str) -> Optional[str]:
    """Извлекает ID видео"""
    try:
        pattern = r'(?:youtube\.com\/watch\?v=|youtu\.be\/)([^&\n?#]+)'
        match = re.search(pattern, url)
        if match:
            video_id = match.group(1)
            log(f"✅ Найден ID видео: {video_id}")
            return video_id
        else:
            log(f"❌ ID видео не найден в URL: {url}")
            return None
    except Exception as e:
        log(f"❌ Ошибка при парсинге URL: {e}")
        return None


def get_subtitles(video_id: str) -> Optional[str]:
    """Загружает субтитры"""

    sources = [
        "https://invidious.io",
        "https://inv.nadeko.net",
        "https://invidious.be",
        "https://yewtu.be",
    ]

    log(f"🔍 Начинаю загрузку субтитров для видео: {video_id}")
    log(f"📍 Всего источников: {len(sources)}")

    for i, source in enumerate(sources, 1):
        log(f"⏳ Пытаюсь источник {i}/{len(sources)}: {source}")

        try:
            # Получаем информацию о видео
            url = f"{source}/api/v1/videos/{video_id}"
            log(f"  🌐 Отправляю запрос: {url}")

            response = requests.get(url, timeout=8)
            log(f"  📬 Ответ: {response.status_code}")

            if response.status_code != 200:
                log(f"  ❌ Ошибка {response.status_code}, переходу к следующему источнику")
                continue

            data = response.json()
            captions = data.get('captions', [])
            log(f"  📋 Найдено субтитров: {len(captions)}")

            if not captions:
                log(f"  ⚠️ Субтитры не найдены, переходу к следующему источнику")
                continue

            # Загружаем субтитры
            caption_url = f"{source}{captions[0]['url']}"
            log(f"  🔗 Загружаю субтитры: {caption_url}")

            caption_response = requests.get(caption_url, timeout=8)
            log(f"  📬 Ответ: {caption_response.status_code}")

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

                result = ' '.join(transcript)
                log(f"✅ УСПЕХ! Загружено {len(result)} символов от источника: {source}")
                return result
            else:
                log(f"  ❌ Не удалось загрузить субтитры (статус {caption_response.status_code})")

        except requests.exceptions.Timeout:
            log(f"  ⏱️ TIMEOUT (превышено время ожидания)")
        except requests.exceptions.ConnectionError as e:
            log(f"  🌐 ОШИБКА СОЕДИНЕНИЯ: {e}")
        except Exception as e:
            log(f"  ❌ ОШИБКА: {type(e).__name__}: {e}")

    log(f"❌ НЕ УДАЛОСЬ загрузить субтитры ни с одного источника!")
    return None


def find_ingredients(text: str) -> list:
    """Находит ингредиенты"""
    log(f"🔍 Ищу ингредиенты в тексте ({len(text)} символов)...")

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

    log(f"✅ Найдено ингредиентов: {len(ingredients)}")
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
            log(f"❌ Пользователь не ввел ссылку")
        else:
            try:
                log(f"🚀 СТАРТ: Пользователь ввел ссылку: {video_url}")

                video_id = get_video_id(video_url)

                if not video_id:
                    st.error("❌ Это не YouTube ссылка")
                    log(f"❌ Не удалось распознать ID видео")
                else:
                    with st.spinner("⏳ Загружаю субтитры (может занять 15-20 сек)..."):
                        log(f"⏳ Начинаю загрузку субтитров...")
                        transcript = get_subtitles(video_id)

                    if transcript:
                        st.success("✅ Загружено!")
                        log(f"✅ Субтитры успешно загружены!")

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
                            log(f"⚠️ Ингредиенты не найдены в тексте")

                    else:
                        st.error("❌ Не удалось загрузить субтитры. Все источники недоступны. Попробуйте через 5-10 минут.")
                        log(f"❌ ВСЕ ИСТОЧНИКИ НЕДОСТУПНЫ")

            except Exception as e:
                error_msg = f"{type(e).__name__}: {e}"
                st.error(f"❌ Ошибка: {error_msg}")
                log(f"❌ КРИТИЧЕСКАЯ ОШИБКА: {error_msg}")

with tab2:
    st.subheader("Шаг 2: Введите цены ингредиентов")

    if 'ingredients' not in st.session_state or not st.session_state.ingredients:
        st.info("📌 Сначала загрузите видео на вкладке слева")
    else:
        ingredients = st.session_state.ingredients

        try:
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

            if st.button("🧮 Рассчитать стоимость", type="primary", use_container_width=True):
                st.subheader("📊 Результат")

                total_cost = 0
                details = []

                for ing in ingredients:
                    price_per_unit = prices[ing['name']]

                    if ing['unit'] == 'кг':
                        weight = ing['quantity'] * 1000
                    elif ing['unit'] == 'л':
                        weight = ing['quantity'] * 1000
                    else:
                        weight = ing['quantity']

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

                import pandas as pd
                df = pd.DataFrame(details)
                st.dataframe(df, use_container_width=True, hide_index=True)

                st.divider()
                col1, col2, col3 = st.columns(3)

                with col1:
                    st.metric("💵 Общая стоимость", f"{total_cost:.2f} ₽")

                with col2:
                    st.metric("📊 Ингредиентов", len(ingredients))

                with col3:
                    st.metric("💹 За блюдо", f"{total_cost:.0f} ₽")

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
            log(f"❌ Ошибка при расчете: {e}")

