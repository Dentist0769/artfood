import streamlit as st
import re

st.set_page_config(page_title="Кулинарный ассистент", page_icon="👨‍🍳", layout="centered")

st.title("👨‍🍳 Умный кулинарный ассистент")
st.markdown("Самый надежный способ без блокировок, API-ключей и оплат!")

# Показываем инструкцию, как вытащить текст за 3 клика
with st.expander("📋 ИНСТРУКЦИЯ: Как скопировать рецепт из любого видео за 10 секунд", expanded=True):
    st.markdown("""
    1. Открой нужное видео на YouTube в браузере на компьютере.
    2. Нажми клавишу **F12** (или нажмите правой кнопкой мыши в любом месте страницы -> *Исследовать элемент / Посмотреть код*).
    3. Перейди во вкладку **Console** (Консоль) вверху открывшейся панели.
    4. Скопируй код ниже, вставь его в самую нижнюю строку консоли и нажми **Enter**:
    """)
    
    js_code = """(async () => {
    try {
        const pageSource = document.documentElement.outerHTML;
        const match = pageSource.match(/"captionTracks":\\[(.*?)\\]/);
        if (!match) { alert("Субтитры не найдены! Включи их на видео."); return; }
        const captionData = JSON.parse('[' + match[1] + ']');
        const response = await fetch(captionData[0].baseUrl);
        const xmlText = await response.text();
        const parser = new DOMParser();
        const xmlDoc = parser.parseFromString(xmlText, "text/xml");
        const texts = Array.from(xmlDoc.querySelectorAll("text")).map(el => el.textContent).join(" ");
        navigator.clipboard.writeText(texts);
        alert("✅ Текст рецепта успешно скопирован в буфер обмена!");
    } catch (e) { alert("Ошибка: " + e); }
})();"""
    
    st.code(js_code, language="javascript")
    st.markdown("5. После этого текст рецепта сам скопируется. Просто вернись сюда и вставь его в окошко ниже!")

st.subheader("⬇️ Вставь скопированный текст рецепта сюда:")
user_text = st.text_area("Вставь текст субтитров или описание из-под видео:", height=200, placeholder="Текст рецепта...")

if st.button("Распознать ингредиенты", type="primary"):
    if not user_text.strip():
        st.warning("Поле пустое! Сначала вставь текст.")
    else:
        st.success("✅ Текст успешно обработан!")
        
        tab_text, tab_ing = st.tabs(["📄 Текст шагов", "🥘 Выделенные граммовки"])
        
        with tab_text:
            st.write(user_text)
            
        with tab_ing:
            st.markdown("### 🔍 Найденные объемы и продукты:")
            # Ищем все цифры с граммовками
            found_measures = re.findall(r'(\d+(?:\s*-\s*\d+)?\s*(?:г|кг|мл|л|шт|ст\.л|ч\.л))\s+([а-яА-Яa-zA-Z]+)', user_text)
            
            if found_measures:
                for measure, word in found_measures:
                    st.write(f"• **{measure}** — {word.lower()}")
            else:
                st.info("Автоматически меры не выделились, но ты можешь прочитать их в тексте на первой вкладке!")
