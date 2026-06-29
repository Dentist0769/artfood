"""
🍳 КАЛЬКУЛЯТОР СЕБЕСТОИМОСТИ БЛЮД (версия с yt-dlp)
Работает напрямую с YouTube, без зависимости от Invidious
"""

import streamlit as st
import re
from typing import Optional
import os
import json

st.set_page_config(page_title="🍳 Кулинарный калькулятор", layout="wide")

st.title("🍳 Калькулятор себестоимости блюд")
st.markdown("Вставьте ссылку на YouTube видео рецепта → приложение загрузит субтитры → рассчитает стоимость")

# ============================================================================
# ПОЛУЧЕНИЕ СУБТИТРОВ через yt-dlp
# ============================================================================

def get_video_id(url: str) -> Optional[str]:
    """Извлекает ID видео из ссылки"""
    try:
        pattern = r'(?:youtube\.com\/watch\?v=|youtu\.be\/)([^&\n?#]+)'
        match = re.search(pattern, url)
        return match.group(1) if match else None
    except:
        return None


def get_subtitles_ytdlp(video_url: str) -> Optional[str]:
    """Загружает субтитры через yt-dlp"""
    try:
        import yt_dlp

        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'writesubtitles': True,
            'skip_download': True,
            'subtitlesformat': 'vtt',
            'outtmpl': '/tmp/%(id)s',
            'socket_timeout': 15,
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(video_url, download=False)

            if not info.get('subtitles'):
                return None

            # Берем первый доступный язык
            subs_dict = info['subtitles']
            if not subs_dict:
                return None

            # Пробуем русский, потом английский, потом первый доступный
            subs = None
            for lang in ['ru', 'en']:
                if lang in subs_dict:
                    subs = subs_dict[lang]
                    break

            if not subs:
                subs = list(subs_dict.values())[0]

            # Загружаем VTT файл
            if subs and len(subs) > 0:
                vtt_url = subs[0].get('url') or subs[0].get('data')

                if vtt_url and isinstance(vtt_url, str) and vtt_url.startswith('http'):
                    import requests
                    response = requests.get(vtt_url, timeout=10)
                    if response.status_code == 200:
                        subtitle_text = response.text
                    else:
                        return None
                else:
                    # Если это встроенные данные
                    subtitle_text = vtt_url if isinstance(vtt_url, str) else ''

                # Парсим VTT в обычный текст
                lines = subtitle_text.split('\n')
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

        return None

    except ImportError:
        st.error("❌ yt-dlp не установлен. Это не должно было произойти. Перезагрузите приложение.")
        return None
    except Exception as e:
        return None


def find_ingredients(text: str) -> list:
    """Находит ингредиенты в тексте"""
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
                    with st.spinner("⏳ Загружаю субтитры (может занять 15-30 сек)..."):
                        transcript = get_subtitles_ytdlp(video_url)

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
                            st.warning("⚠️ Ингредиенты не найдены в видео")

                    else:
                        st.error("""
❌ Не удалось загрузить субтитры.

**Возможные причины:**
1. Видео без встроенных субтитров
2. Видео приватное или удалено
3. Ошибка сети

**Решение:**
- Проверьте кнопку CC на YouTube
- Выберите другое видео
- Подождите 5 минут и попробуйте снова
                        """)

            except Exception as e:
                st.error(f"❌ Ошибка: {str(e)}")

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

