import streamlit as st
import re
from quick_integration import YouTubeTranscriptApiFree

st.set_page_config(page_title="Кулинарный ассистент", page_icon="👨‍🍳", layout="centered")

st.title("👨‍🍳 Кулинарный ассистент (Без ИИ)")
st.markdown("Извлекаем рецепты и ингредиенты напрямую из YouTube без блокировок и платных ключей!")

user_input = st.text_input("Вставь сюда ссылку на YouTube видео:")

if st.button("Вытащить рецепт из видео", type="primary"):
    if not user_input.strip():
        st.warning("Поле пустое!")
    else:
        with st.spinner("Invidious выкачивает текст из видео..."):
            try:
                # Используем бесплатный метод Клода
                result = YouTubeTranscriptApiFree.get_transcript(user_input, languages=['ru', 'en'])
                video_id = list(result.keys())[0]
                
                # Собираем все строчки субтитров в один текст
                full_text = " ".join([item['text'] for item in result[video_id]])
                
                st.success("✅ Текст видео успешно получен!")
                
                # Вкладка 1: Полный текст для чтения шагов
                tab_text, tab_ing = st.tabs(["📄 Текст видео (Шаги)", "🥘 Поиск ингредиентов"])
                
                with tab_text:
                    st.text_area("Прокрути текст, чтобы увидеть весь рецепт:", value=full_text, height=400)
                
                with tab_ing:
                    st.markdown("### 🔍 Возможные граммовки в тексте:")
                    # Ищем совпадения чисел и кулинарных мер (г, кг, мл, л)
                    found_measures = re.findall(r'(\d+(?:\s*-\s*\d+)?\s*(?:г|кг|мл|л|шт|ст\.л|ч\.л))\s+([а-яА-Яa-zA-Z]+)', full_text)
                    
                    if found_measures:
                        for measure, word in found_measures:
                            st.write(f"• **{measure}** — {word}")
                    else:
                        st.info("Не удалось автоматически сгруппировать ингредиенты. Ты можешь найти их в общем тексте на первой вкладке.")
                        
            except Exception as e:
                st.error(f"Не удалось прочесть видео: {e}")
                st.info("Попробуй ссылку на другое видео. Убедись, что на самом YouTube у этого видео включены субтитры.")
