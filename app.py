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
st.markdown("Управление рецептами, ингредиентами и расчет себестоимости")

MAX_FILE_SIZE = 5 * 1024 * 1024

def init_db():
    conn = sqlite3.connect('recipes.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS recipes (
        id INTEGER PRIMARY KEY,
        name TEXT NOT NULL,
        category TEXT NOT NULL,
        ingredients TEXT NOT NULL,
        video_url TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )''')
    try:
        c.execute('''ALTER TABLE recipes ADD COLUMN description TEXT''')
    except sqlite3.OperationalError:
        pass
    c.execute('''CREATE TABLE IF NOT EXISTS prices (
        id INTEGER PRIMARY KEY,
        ingredient TEXT UNIQUE NOT NULL,
        price REAL NOT NULL,
        unit TEXT NOT NULL,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )''')
    conn.commit()
    conn.close()

def is_safe_string(text: str, max_len: int = 500) -> bool:
    if not text or len(text) > max_len:
        return False
    if re.search(r"(?i)(DROP|DELETE|INSERT|UPDATE|SELECT)\s", text):
        return False
    return True

def save_recipe(name: str, category: str, ingredients: List[Dict], description: str, video_url: Optional[str] = None):
    if not is_safe_string(name, 200) or not is_safe_string(description, 10000):
        st.error("❌ Опасные или слишком длинные данные")
        return False
    conn = sqlite3.connect('recipes.db')
    c = conn.cursor()
    ingredients_json = json.dumps(ingredients)
    try:
        c.execute('''INSERT INTO recipes (name, category, ingredients, description, video_url)
                     VALUES (?, ?, ?, ?, ?)''', (name, category, ingredients_json, description, video_url))
        conn.commit()
        return True
    except Exception as e:
        logger.error(f"Ошибка сохранения рецепта: {e}")
        return False
    finally:
        conn.close()

def update_recipe_full(recipe_id: int, new_name: str, new_ingredients: List[Dict], new_description: str):
    conn = sqlite3.connect('recipes.db')
    c = conn.cursor()
    if not is_safe_string(new_name, 200) or not is_safe_string(new_description, 10000):
        st.error("❌ Опасные или слишком длинные данные")
        return False
    ingredients_json = json.dumps(new_ingredients)
    try:
        c.execute('''UPDATE recipes SET name = ?, ingredients = ?, description = ? WHERE id = ?''',
                  (new_name, ingredients_json, new_description, recipe_id))
        conn.commit()
        return True
    except Exception as e:
        logger.error(f"Ошибка обновления рецепта: {e}")
        return False
    finally:
        conn.close()

def get_recipes(category: Optional[str] = None) -> List[Dict]:
    conn = sqlite3.connect('recipes.db')
    c = conn.cursor()
    if category:
        c.execute('''SELECT id, name, category, ingredients, video_url, created_at, description
                     FROM recipes WHERE category = ? ORDER BY created_at DESC''', (category,))
    else:
        c.execute('''SELECT id, name, category, ingredients, video_url, created_at, description
                     FROM recipes ORDER BY created_at DESC''')
    rows = c.fetchall()
    conn.close()
    recipes = []
    for row in rows:
        try:
            recipes.append({
                'id': row[0],
                'name': row[1],
                'category': row[2],
                'ingredients': json.loads(row[3]),
                'video_url': row[4],
                'created_at': row[5],
                'description': row[6] if row[6] else ""
            })
        except Exception as e:
            logger.error(f"Ошибка парсинга рецепта {row[0]}: {e}")
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
        try:
            c.execute('''INSERT OR REPLACE INTO prices (ingredient, price, unit)
                         VALUES (?, ?, ?)''', (ingredient.lower().strip(), float(data['price']), data['unit']))
        except Exception as e:
            logger.error(f"Ошибка сохранения цены: {e}")
            continue
    conn.commit()
    conn.close()

def get_prices() -> Dict[str, Dict]:
    conn = sqlite3.connect('recipes.db')
    c = conn.cursor()
    c.execute('SELECT ingredient, price, unit FROM prices')
    rows = c.fetchall()
    conn.close()
    prices = {}
    for row in rows:
        prices[row[0]] = {'price': row[1], 'unit': row[2]}
    return prices

def get_requests_session():
    session = requests.Session()
    retry_strategy = Retry(
        total=3,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["HEAD", "GET", "OPTIONS"],
        backoff_factor=1.5
    )
    adapter = HTTPAdapter(max_retries=retry_strategy)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    return session

def validate_parsed_content(text: str) -> bool:
    if not text or len(text) < 100:
        return False
    has_words = bool(re.search(r'[А-Яа-яA-Za-z]{3,}', text))
    if not has_words:
        return False
    cyrillic_count = len(re.findall(r'[А-Яа-яЁё]', text))
    latin_count = len(re.findall(r'[A-Za-z]', text))
    if cyrillic_count + latin_count < 20:
        return False
    return True

def clean_description(text: str) -> str:
    if not text:
        return ""
    text = re.sub(r'<[^>]+>', '', text)
    text = re.sub(r'&[a-z]+;', '', text)
    text = re.sub(r'https?://[^\s]+', '', text)
    text = re.sub(r'www\.[^\s]+', '', text)
    text = re.sub(r'\b\d{4}[-\s]?\d{4}[-\s]?\d{4}[-\s]?\d{4}\b', '', text)

    recipe_words = [
        'шаг', 'добавить', 'смешать', 'варить', 'жарить', 'пекать', 'готовить', 'положить',
        'залить', 'посыпать', 'украсить', 'перемешать', 'поставить', 'выпечь', 'включить',
        'нагреть', 'кипятить', 'тушить', 'мешать', 'взбить', 'натереть', 'нарезать',
        'слой', 'слои', 'минуты', 'часа', 'ингредиент', 'компонент', 'порция', 'порции',
        'тесто', 'соус', 'глазурь', 'крем', 'начинка', 'начин', 'фарш', 'маринад'
    ]

    ad_keywords = [
        'telegram', 'tg.me', 'монобанк', 'промокод', 'скидка', 'подпишись', 'subscribe',
        'instagram', 'инстаграм', 'vk.com', 'вконтакте', 'facebook', 'patreon', 'paypal',
        'донат', 'donat', 'поддержать канал', 'сбербанк', 'тинькофф', 'номер карты',
        'реквизиты', 'сотрудничество', 'cooperation', 'реклама', 'плейлист', 'смотрите также',
        'предыдущее видео', 'мой канал', 'tiktok', 'тикток', 'дзен', 'dzen',
        'жми на колокольчик', 'поставь лайк', 'dear friends', 'see you on my channel',
        'turn on subtitles', 'automatically translated', 'write to me', 'happy to answer',
        'support the channel', 'give a like', 'leave a comment', 'share the video',
        'спасибо за внимание', 'до свидания', 'пока', 'всем пока', 'привет всем'
    ]

    lines = text.split('\n')
    filtered_lines = []
    for line in lines:
        line_strip = line.strip()
        if not line_strip:
            continue
        is_recipe_line = any(keyword in line_strip.lower() for keyword in recipe_words)
        if is_recipe_line:
            filtered_lines.append(line_strip)
            continue
        if any(keyword in line_strip.lower() for keyword in ad_keywords):
            continue
        if re.match(r'^[\d\s:,\.\-/😊😍❤️👍💯🔥😋🤩🎉]+$', line_strip):
            continue
        if len(line_strip) < 25 and re.match(r'^[А-Яа-яA-Za-z\s]+$', line_strip) and ' ' in line_strip:
            if not any(word in line_strip.lower() for word in recipe_words):
                continue
        if re.match(r'^[#@][^\s]*(\s[#@][^\s]*)*$', line_strip):
            continue
        filtered_lines.append(line_strip)

    text = '\n'.join(filtered_lines)
    text = re.sub(r'#[\w]+', '', text, flags=re.UNICODE | re.IGNORECASE)
    text = re.sub(r'\n{2,}', '\n', text)
    return text.strip()

def get_page_text_fallback(url: str) -> Optional[str]:
    max_retries = 3
    timeout = 40
    session = get_requests_session()
    for attempt in range(max_retries):
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Accept-Language': 'ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7',
                'Accept-Charset': 'utf-8, windows-1251, iso-8859-5',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                'Referer': 'https://www.google.com/'
            }
            logger.info(f"Попытка #{attempt + 1}/{max_retries} загрузить {url}")
            response = session.get(url, headers=headers, timeout=timeout, allow_redirects=True)
            if response.status_code != 200:
                logger.warning(f"Статус {response.status_code}, повторяем...")
                if attempt < max_retries - 1:
                    wait_time = 2 ** attempt
                    logger.info(f"Ожидание {wait_time} сек перед повтором...")
                    time.sleep(wait_time)
                continue

            encodings_to_try = []
            if response.encoding and response.encoding.lower() not in ['none', 'utf-8']:
                encodings_to_try.append(response.encoding)
            encodings_to_try.extend(['utf-8', 'windows-1251', 'iso-8859-5', 'cp1251', 'cp866'])
            encodings_to_try = list(dict.fromkeys(encodings_to_try))

            soup = None
            used_encoding = None
            for encoding in encodings_to_try:
                try:
                    text_decoded = response.content.decode(encoding)
                    soup = BeautifulSoup(text_decoded, 'html.parser')
                    text_sample = soup.get_text()[:1000]
                    cyrillic_match = re.findall(r'[А-Яа-яЁё]', text_sample)
                    latin_match = re.findall(r'[A-Za-z]', text_sample)
                    if len(cyrillic_match) + len(latin_match) > 10:
                        used_encoding = encoding
                        logger.info(f"✓ Кодировка {encoding} выбрана (букв найдено: {len(cyrillic_match)} кирилл, {len(latin_match)} латин)")
                        break
                    else:
                        logger.debug(f"Кодировка {encoding}: мало букв ({len(cyrillic_match)} + {len(latin_match)})")
                        soup = None
                        continue
                except (UnicodeDecodeError, LookupError) as e:
                    logger.debug(f"Кодировка {encoding} не подошла: {e}")
                    soup = None
                    continue
                except Exception as e:
                    logger.debug(f"Ошибка при обработке кодировки {encoding}: {e}")
                    soup = None
                    continue

            if not soup:
                logger.warning(f"Не удалось определить кодировку среди {encodings_to_try}, используем utf-8 с fallback")
                try:
                    soup = BeautifulSoup(response.text, 'html.parser')
                    used_encoding = 'utf-8 (fallback)'
                except Exception as e:
                    logger.error(f"Даже utf-8 fallback не сработал: {e}")
                    if attempt < max_retries - 1:
                        time.sleep(2 ** attempt)
                    continue

            logger.info(f"Используется кодировка: {used_encoding}")
            scripts = soup.find_all('script', type='application/ld+json')
            for script in scripts:
                try:
                    if not script.string:
                        continue
                    data = json.loads(script.string)
                    recipes = []
                    def search_recipe(obj):
                        if isinstance(obj, dict):
                            if obj.get('@type') == 'Recipe' or (isinstance(obj.get('@type'), list) and 'Recipe' in obj.get('@type')):
                                recipes.append(obj)
                            for v in obj.values():
                                search_recipe(v)
                        elif isinstance(obj, list):
                            for item in obj:
                                search_recipe(item)
                    search_recipe(data)
                    if recipes:
                        recipe = recipes[0]
                        clean_lines = []
                        ing_list = recipe.get('recipeIngredient', [])
                        if ing_list:
                            for ing in ing_list:
                                if isinstance(ing, str):
                                    clean_lines.append(ing.strip())
                            clean_lines.append("")
                        instructions_raw = recipe.get('recipeInstructions', [])
                        if instructions_raw:
                            raw_steps = []
                            if isinstance(instructions_raw, list):
                                for step in instructions_raw:
                                    if isinstance(step, dict):
                                        raw_steps.append(step.get('text', step.get('name', '')))
                                    elif isinstance(step, str):
                                        raw_steps.append(step)
                            elif isinstance(instructions_raw, str):
                                raw_steps.append(instructions_raw)
                            for idx, step_text in enumerate(raw_steps, 1):
                                if step_text:
                                    step_pure = BeautifulSoup(step_text, 'html.parser').get_text().strip()
                                    clean_lines.append(f"Шаг {idx}. {step_pure}")
                        combined = "\n".join(clean_lines).strip()
                        if validate_parsed_content(combined):
                            logger.info("✓ Рецепт найден в schema.org JSON")
                            result = clean_description(combined)
                            if validate_parsed_content(result):
                                return result
                except Exception as e:
                    logger.debug(f"Ошибка парсинга schema.org: {e}")
                    continue

            for tag in ['script', 'style', 'nav', 'header', 'footer', 'aside', 'form', 'noscript', 'button', 'svg', 'iframe']:
                for element in soup.find_all(tag):
                    element.decompose()

            for selector in ['.header', '.footer', '.menu', '.sidebar', '.nav', '.breadcrumbs', '.comments', '.banner', '.sharing', '.ads', '.advertisement', '.related', '.recommend', '.author-info', '.user-comments', '.review', '.rating', '#comments', '#reviews', '.sidebar-ads']:
                for element in soup.select(selector):
                    element.decompose()

            main_content = soup.find('article') or soup.find('main') or soup.find('div', class_=re.compile(r'recipe|content|post', re.I)) or soup.body
            if main_content:
                text = main_content.get_text('\n')
            else:
                text = soup.get_text('\n')

            lines = [line.strip() for line in text.splitlines() if line.strip()]
            result = clean_description('\n'.join(lines))
            if len(result) > 5000:
                result = result[:5000]

            if validate_parsed_content(result):
                logger.info("✓ Рецепт загружен через fallback парсинг")
                return result
            else:
                logger.warning(f"Результат парсинга не прошел валидацию (len={len(result)})")
                if attempt < max_retries - 1:
                    time.sleep(2 ** attempt)
                continue
        except (requests.exceptions.Timeout, requests.exceptions.ConnectTimeout) as e:
            logger.warning(f"Таймаут #{attempt + 1}: {e}")
            if attempt < max_retries - 1:
                wait_time = 2 ** attempt
                logger.info(f"Ожидание {wait_time} сек перед повтором...")
                time.sleep(wait_time)
            continue
        except requests.exceptions.RequestException as e:
            logger.warning(f"Ошибка сети #{attempt + 1}: {e}")
            if attempt < max_retries - 1:
                wait_time = 2 ** attempt
                logger.info(f"Ожидание {wait_time} сек перед повтором...")
                time.sleep(wait_time)
            continue
        except Exception as e:
            logger.error(f"Неожиданная ошибка: {e}")
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)
            continue
    logger.error(f"❌ Не удалось загрузить {url} после {max_retries} попыток")
    return None

def get_youtube_data(video_url: str) -> Dict:
    try:
        import yt_dlp
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'socket_timeout': 30,
            'skip_unavailable_fragments': True,
            'no_check_certificate': True
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(video_url, download=False)
            return {
                'description': clean_description(info.get('description', '')),
                'title': info.get('title', 'Unknown'),
                'error': None
            }
    except Exception as e:
        error_msg = f"Ошибка YouTube: {str(e)[:100]}"
        logger.error(error_msg)
        return {'description': '', 'title': 'Unknown', 'error': error_msg}

def get_page_text(url: str) -> Optional[str]:
    try:
        return get_page_text_fallback(url)
    except Exception as e:
        logger.error(f"Ошибка парсинга: {e}")
        return None

@lru_cache(maxsize=1000)
def translate_line(line: str) -> str:
    if not line or not re.search(r'[a-zA-Z]', line):
        return line
    max_retries = 3
    for attempt in range(max_retries):
        try:
            url = "https://translate.googleapis.com/translate_a/single"
            params = {
                "client": "gtx",
                "sl": "auto",
                "tl": "ru",
                "dt": "t",
                "q": line
            }
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }
            res = requests.get(url, params=params, headers=headers, timeout=5)
            if res.status_code == 429:
                time.sleep(2 ** attempt)
                continue
            if res.status_code == 200:
                return "".join([part[0] for part in res.json()[0] if part[0]]).strip()
            else:
                return line
        except requests.exceptions.Timeout:
            if attempt == max_retries - 1:
                return line
        except Exception as e:
            logger.warning(f"Ошибка перевода: {e}")
            return line
    return line

def translate_text(text: str) -> str:
    if not text or not re.search(r'[a-zA-Z]', text):
        return text
    lines = text.split('\n')
    translated = [translate_line(line) for line in lines]
    return "\n".join(translated)

def find_ingredients(text: str) -> List[Dict]:
    if not text:
        return []
    text_clean = re.sub(r'\(.*?\)', ' ', text)
    units_map = {
        'мл': 'мл', 'ml': 'мл', 'миллилитр': 'мл', 'миллилитров': 'мл',
        'г': 'г', 'g': 'г', 'грамм': 'г', 'граммов': 'г', 'грамма': 'г',
        'кг': 'кг', 'kg': 'кг', 'килограмм': 'кг',
        'л': 'л', 'l': 'л', 'литр': 'л', 'литров': 'л',
        'шт': 'шт', 'pcs': 'шт', 'штук': 'шт', 'штука': 'шт', 'штуки': 'шт',
        'зубчик': 'шт', 'зубчика': 'шт', 'зубчиков': 'шт', 'зуб.': 'шт',
        'ломтик': 'шт', 'ломтика': 'шт', 'ломтиков': 'шт', 'ломтей': 'шт',
        'долька': 'шт', 'дольки': 'шт',
        'кусок': 'шт', 'куска': 'шт', 'кусков': 'шт',
        'веточка': 'шт', 'веточки': 'шт', 'веточек': 'шт',
        'листок': 'шт', 'листков': 'шт', 'лист': 'шт', 'листья': 'шт', 'листов': 'шт',
        'пучок': 'шт', 'пучка': 'шт', 'пучков': 'шт',
        'горсть': 'шт', 'горсти': 'шт', 'горстей': 'шт',
        'помидор': 'шт', 'помидора': 'шт', 'помидоров': 'шт', 'помидоры': 'шт',
        'яйцо': 'шт', 'яйца': 'шт', 'яиц': 'шт',
        'яблоко': 'шт', 'яблока': 'шт', 'яблок': 'шт',
        'банан': 'шт', 'банана': 'шт', 'бананов': 'шт',
        'ст.л': 'ст.л', 'ст л': 'ст.л', 'tbsp': 'ст.л', 'столовая': 'ст.л',
        'ложка': 'ст.л', 'ложки': 'ст.л', 'ст. л.': 'ст.л',
        'ч.л': 'ч.л', 'ч л': 'ч.л', 'tsp': 'ч.л', 'чайная': 'ч.л',
        'стакан': 'шт', 'стакана': 'шт', 'стаканов': 'шт',
        'чашка': 'шт', 'чашки': 'шт', 'чашек': 'шт',
        'чаша': 'шт', 'чаши': 'шт'
    }
    all_units = "|".join(sorted(units_map.keys(), key=len, reverse=True))
    pattern = rf'(?:^|[\s,;(])(\d+(?:[.,]\d+)?)\s*({all_units})(?:[\s,;)\.]|$)'
    text_clean = re.sub(r'(\d+)\s*[-—–]\s*(\d+)', r'\2', text_clean)
    matches = list(re.finditer(pattern, text_clean, re.IGNORECASE))
    ingredients = []
    seen = set()
    exclude_words = {'минут', 'минуты', 'минута', 'второ', 'часо', 'час', 'градусо', 'градусов',
                     'процесс', 'духов', 'духовк', 'разогреть', 'выпекать', 'смешать', 'взбить', 'шаг'}
    for i, match in enumerate(matches):
        try:
            qty = float(match.group(1).replace(',', '.'))
            unit = units_map[match.group(2).lower()]
            start_idx = match.start()
            prev_end = matches[i-1].end() if i > 0 else 0
            left_chunk = text_clean[prev_end:start_idx]
            if '=' in left_chunk:
                continue
            end_idx = match.end()
            next_start = matches[i+1].start() if i < len(matches) - 1 else len(text_clean)
            right_chunk = text_clean[end_idx:next_start]
            left_name = re.sub(r'[\n,;.!?—–-•:*=…\s]+$', '', left_chunk).strip()
            left_lines = re.split(r'[\n,;=•]', left_name)
            left_name = left_lines[-1].strip()
            right_lines = re.split(r'[\n,;=•]', right_chunk)
            right_name = right_lines[0].strip()
            right_name = re.sub(r'^[-—–_:\s]+', '', right_name).strip()
            right_name = " ".join(right_name.split()[:4])
            name = ""
            if left_name and any(c.isalpha() for c in left_name) and len(left_name) >= 2:
                name = left_name
            elif right_name and any(c.isalpha() for c in right_name) and len(right_name) >= 2:
                name = right_name
            if not name:
                continue
            name = re.sub(r'^(хороший пучок|пучок|долька|дольки|зубчик|зубчика|можно)\s+', '', name, flags=re.IGNORECASE)
            name = name.strip().lower()
            if any(ex in name for ex in exclude_words):
                continue
            if len(name) < 2 or len(name) > 60:
                continue
            key = f"{name}_{unit}"
            if key not in seen and 0 < qty < 10000:
                ingredients.append({'name': name, 'quantity': qty, 'unit': unit})
                seen.add(key)
        except Exception as e:
            logger.debug(f"Ошибка парсинга ингредиента: {e}")
            continue
    if len(ingredients) < 3:
        pattern_simple = r'^(.+?)\s*[-–—:]\s*(.+?)$'
        for line in text.split('\n'):
            if match := re.search(pattern_simple, line):
                ing_part = match.group(1).strip()
                qty_part = match.group(2).strip()
                qty_match = re.search(r'(\d+(?:[.,]\d+)?)\s*(\S+)', qty_part)
                if qty_match and len(ing_part) > 2 and ing_part.lower() not in [i['name'] for i in ingredients]:
                    try:
                        ingredients.append({
                            'name': ing_part.lower(),
                            'quantity': float(qty_match.group(1).replace(',', '.')),
                            'unit': qty_match.group(2)
                        })
                    except Exception as e:
                        logger.debug(f"Ошибка fallback парсинга: {e}")
    return ingredients

INGREDIENT_WEIGHTS = {
    'помидоры': 0.15,
    'помидор': 0.15,
    'цуккини': 0.25,
    'кабачок': 0.25,
    'лук репчатый': 0.08,
    'лук': 0.08,
    'чеснок': 0.005,
    'куриное яйцо': 0.050,
    'яйцо': 0.050,
    'яблоко': 0.180,
    'банан': 0.120,
    'картофель': 0.150,
    'морковь': 0.100,
    'свекла': 0.200,
}

def calculate_ingredient_cost(name: str, qty: float, unit: str, prices: dict) -> tuple:
    name_clean = name.lower().strip()
    SYNONYMS = {
        'кабачки': 'цуккини', 'кабачок': 'цуккини', 'яйца': 'куриное яйцо', 'яйцо': 'куриное яйцо', 'желток': 'куриное яйцо',
        'оливковое масло': 'масло растительное', 'растительное масло': 'масло растительное',
        'подсолнечное масло': 'масло растительное', 'соевый соус': 'соус соевый',
        'лимонный сок': 'лимон желтый', 'капуста': 'белокочанная капуста', 'картошка': 'картофель',
        'картофельный': 'картофель', 'лук': 'лук репчатый', 'репчатый': 'лук репчатый', 'дрожжи': 'дрожжи сухие'
    }
    for syn_k, syn_v in SYNONYMS.items():
        if syn_k in name_clean:
            name_clean = syn_v
            break
    p_data = prices.get(name_clean)
    if not p_data:
        name_words = set(re.findall(r'[а-яa-z0-9]+', name_clean))
        for k, v in prices.items():
            k_words = set(re.findall(r'[а-яa-z0-9]+', k))
            if k_words and (k_words.issubset(name_words) or name_words.issubset(k_words)):
                p_data = v
                name_clean = k
                break
    if not p_data:
        name_words = set(re.findall(r'[а-яa-z0-9]+', name_clean))
        stop_words = {'сухие', 'свежие', 'куриное', 'желток', 'отвар', 'белый', 'красный', 'желтый', 'пшеничная'}
        meaningful_words = name_words - stop_words
        for k, v in prices.items():
            k_words = set(re.findall(r'[а-яa-z0-9]+', k))
            if k_words.intersection(meaningful_words):
                p_data = v
                name_clean = k
                break
    if not p_data:
        if 'вода' in name_clean or 'отвар' in name_clean:
            return 0.0, " (бесплатный компонент)"
        return 0.0, "Нет цены в базе"
    p_price, p_unit = p_data['price'], p_data['unit'].lower().strip()
    u_rec = unit.lower().strip()
    if p_price <= 0:
        return 0.0, "Некорректная цена"
    if u_rec == p_unit:
        return qty * p_price, ""
    if u_rec == 'шт' and p_unit in ['кг', 'kg']:
        w = INGREDIENT_WEIGHTS.get(name_clean, 0.10)
        return qty * w * p_price, f" (из шт в кг: ~{w*1000:.0f}г/шт)"
    if p_unit in ['кг', 'kg'] and u_rec in ['г', 'g', 'грамм', 'граммов']:
        return (qty / 1000.0) * p_price, ""
    if p_unit in ['кг', 'kg'] and u_rec in ['ч.л', 'ч л']:
        return (qty * 5.0 / 1000.0) * p_price, " (расчет как ~5г)"
    if p_unit in ['кг', 'kg'] and u_rec in ['ст.л', 'ст л']:
        return (qty * 15.0 / 1000.0) * p_price, " (расчет как ~15г)"
    if p_unit in ['л', 'l'] and u_rec in ['мл', 'ml']:
        return (qty / 1000.0) * p_price, ""
    return 0.0, f"Несоответствие ед. ({u_rec} vs {p_unit})"

init_db()
CATEGORIES = ["Супы", "Вторые блюда", "Десерты и выпечка", "Консервация", "Колбасы", "Напитки", "Разное"]
tab1, tab2, tab3 = st.tabs(["📺 Загрузка", "📋 Рецепты", "💰 Цены"])

with tab1:
    st.subheader("Загрузка рецепта")
    input_mode = st.radio("Источник:", ["YouTube видео", "Ссылка на страницу"], horizontal=True)
    if input_mode == "YouTube видео":
        video_url = st.text_input("YouTube ссылка:", placeholder="https://youtube.com/watch?v=...")
        if st.button("🔄 Загрузить", type="primary", use_container_width=True):
            if video_url.strip():
                YOUTUBE_REGEX = r'(https?://)?(www\.)?(youtube|youtu|youtube-nocookie)\.(com|be)/'
                if not re.search(YOUTUBE_REGEX, video_url):
                    st.error("❌ Это не похоже на YouTube ссылку. Проверь URL")
                else:
                    with st.spinner("⏳ Обработка видео..."):
                        data = get_youtube_data(video_url)
                    if data.get('error'):
                        st.error(f"❌ {data['error']}")
                    else:
                        trans_desc = translate_text(data['description'])
                        st.session_state.ingredients = find_ingredients(trans_desc)
                        st.session_state.recipe_description = trans_desc
                        st.session_state.video_url = video_url
                        st.session_state.video_title = translate_text(data['title'])
                        st.success("✅ Описание готово!")
    else:
        page_url = st.text_input("Ссылка на страницу:", placeholder="https://food.ru/recipes/...")
        if st.button("🔄 Загрузить", type="primary", use_container_width=True):
            if page_url.strip():
                with st.spinner("⏳ Анализ страницы (может занять 5-10 секунд)..."):
                    page_text = get_page_text(page_url)
                if page_text:
                    trans_page = translate_text(page_text)
                    st.session_state.ingredients = find_ingredients(trans_page)
                    st.session_state.recipe_description = trans_page
                    st.session_state.video_url = page_url
                    st.session_state.video_title = "Рецепт со страницы"
                    st.success("✅ Страница обработана!")
                else:
                    st.error("❌ Не удалось загрузить страницу")
    if 'recipe_description' in st.session_state:
        st.divider()
        col_ing, col_desc = st.columns([1, 2])
        with col_ing:
            st.subheader("🥘 Компоненты:")
            if st.session_state.ingredients:
                for ing in st.session_state.ingredients:
                    st.write(f"• {ing['quantity']} {ing['unit']} {ing['name']}")
            else:
                st.info("Компоненты пустые — настройте их вручную.")
        with col_desc:
            st.subheader("📝 Инструкция:")
            edited_description = st.text_area("Текст процесса:", value=st.session_state.recipe_description, height=300)
        st.divider()
        recipe_name = st.text_input("Название рецепта:", value=st.session_state.get('video_title', ''))
        category = st.selectbox("Категория:", CATEGORIES)
        if st.button("💾 Подтвердить и сохранить рецепт", type="primary", use_container_width=True):
            if recipe_name.strip():
                if save_recipe(recipe_name, category, st.session_state.ingredients, edited_description, st.session_state.get('video_url')):
                    st.success("✅ Рецепт успешно сохранен!")
                    if 'ingredients' in st.session_state:
                        del st.session_state.ingredients
                    if 'recipe_description' in st.session_state:
                        del st.session_state.recipe_description
                    st.rerun()
            else:
                st.error("❌ Введи название рецепта")

with tab2:
    st.subheader("📋 База рецептов")
    filter_category = st.selectbox("Категория:", ["Все"] + CATEGORIES)
    recipes = get_recipes(None if filter_category == "Все" else filter_category)
    system_prices = get_prices()
    if recipes:
        for recipe in recipes:
            with st.expander(f"📄 {recipe['name']} ({recipe['category']})"):
                if recipe['video_url']:
                    st.link_button("🔗 Открыть источник", recipe['video_url'])
                edit_mode = st.checkbox("✏️ Режим редактирования рецепта", key=f"edit_mode_{recipe['id']}")
                if edit_mode:
                    st.write("<div style='padding-top:10px;'></div>", unsafe_allow_html=True)
                    edit_name = st.text_input("Изменить название блюда:", value=recipe['name'], key=f"edit_name_{recipe['id']}")
                    current_ings_text = "\n".join([f"{ing['name']} {ing['quantity']} {ing['unit']}" for ing in recipe['ingredients']])
                    edit_ings_text = st.text_area("Редактировать список ингредиентов (каждый продукт на новой строке, например: мука 450 г):",
                                                   value=current_ings_text, height=200, key=f"edit_ing_{recipe['id']}")
                    edit_desc = st.text_area("Изменить текст процесса приготовления:", value=recipe['description'], height=250, key=f"edit_desc_{recipe['id']}")
                    if st.button("💾 Сохранить изменения рецепта", key=f"save_all_{recipe['id']}", type="primary", use_container_width=True):
                        new_ings = find_ingredients(edit_ings_text)
                        if update_recipe_full(recipe['id'], edit_name.strip(), new_ings, edit_desc):
                            st.success("✅ Все изменения успешно зафиксированы в базе!")
                            st.rerun()
                else:
                    portions = st.number_input("Количество порций:", min_value=1, value=1, key=f"p_{recipe['id']}")
                    st.divider()
                    v1, v2 = st.columns([1, 2])
                    total_cost = 0.0
                    with v1:
                        st.markdown("**Ингредиенты и стоимость:**")
                        for ing in recipe['ingredients']:
                            cost, warn = calculate_ingredient_cost(ing['name'], ing['quantity'], ing['unit'], system_prices)
                            total_cost += cost
                            if warn == "Нет цены в базе":
                                st.write(f"• {ing['quantity']} {ing['unit']} {ing['name']} — <span style='color:gray;'>*{warn}*</span>", unsafe_allow_html=True)
                            elif "Несоответствие" in warn:
                                st.write(f"• {ing['quantity']} {ing['unit']} {ing['name']} — <span style='color:orange;'>*{warn}*</span>", unsafe_allow_html=True)
                            else:
                                st.write(f"• {ing['quantity']} {ing['unit']} {ing['name']} — **${cost:.2f}** <span style='color:green; font-size:11px;'>{warn}</span>", unsafe_allow_html=True)
                        st.divider()
                        st.metric("💰 Стоимость замеса:", f"${total_cost:.2f}")
                        if portions > 1 and portions != 0:
                            st.metric("🍽️ Себестоимость 1 порции:", f"${(total_cost / portions):.2f}")
                    with v2:
                        st.markdown("**Процесс приготовления:**")
                        st.write(recipe['description'] if recipe['description'] else "Описание отсутствует.")
                st.divider()
                if st.button("🗑️ Удалить рецепт", key=f"del_{recipe['id']}", use_container_width=True):
                    delete_recipe(recipe['id'])
                    st.rerun()
    else:
        st.info("📌 Рецептов пока нет.")

with tab3:
    st.subheader("💰 Управление ценами")
    uploaded_file = st.file_uploader("Загрузить прайс-лист (.txt, .csv):", type=["txt", "csv"])
    if uploaded_file:
        if uploaded_file.size > MAX_FILE_SIZE:
            st.error(f"❌ Файл слишком большой ({uploaded_file.size/1024/1024:.1f}MB > 5MB)")
        else:
            try:
                content = uploaded_file.read().decode('utf-8')
                prices = {}
                for line in content.strip().split('\n'):
                    parts = line.split('\t') if '\t' in line else line.split(',')
                    if len(parts) >= 3:
                        try:
                            prices[parts[0].strip()] = {'price': float(parts[1].strip()), 'unit': parts[2].strip()}
                        except ValueError:
                            logger.warning(f"Ошибка парсинга линии: {line}")
                            continue
                if prices:
                    st.success(f"✅ Найдено {len(prices)} позиций")
                    if st.button("💾 Записать цены в базу", type="primary", use_container_width=True):
                        save_prices(prices)
                        st.success("✅ Цены сохранены!")
                    st.dataframe(pd.DataFrame([{'Ингредиент': k, 'Цена': v['price'], 'Единица': v['unit']} for k, v in prices.items()]), use_container_width=True)
            except Exception as e:
                st.error(f"❌ Ошибка: {e}")
                logger.error(f"Ошибка загрузки файла: {e}")
    st.divider()
    st.write("**Текущие цены:**")
    current_prices = get_prices()
    if current_prices:
        st.dataframe(pd.DataFrame([{'Ингредиент': k, 'Цена': v['price'], 'Единица': v['unit']} for k, v in current_prices.items()]), use_container_width=True)
        st.write("**Добавить цену вручную:**")
        c1, c2, c3 = st.columns(3)
        with c1:
            man_name = st.text_input("Ингредиент:", placeholder="Например: мука пшеничная")
        with c2:
            man_price = st.number_input("Цена ($):", min_value=0.0, step=0.1)
        with c3:
            man_unit = st.selectbox("Единица:", ["кг", "г", "л", "мл", "шт"])
        if st.button("➕ Добавить позицию", use_container_width=True):
            if man_name.strip():
                save_prices({man_name: {'price': man_price, 'unit': man_unit}})
                st.rerun()
            else:
                st.error("❌ Введи название ингредиента")
    else:
        st.info("📌 База цен пуста.")
