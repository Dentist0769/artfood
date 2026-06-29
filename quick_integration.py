import requests
import re
from typing import Optional

class YouTubeTranscriptApiFree:
    INVIDIOUS_INSTANCES = [
        "https://invidious.io",
        "https://inv.nadeko.net",
        "https://invidious.be",
        "https://yewtu.be",
        "https://invidious.snopyta.org",
    ]

    @staticmethod
    def extract_video_id(url: str) -> Optional[str]:
        patterns = [
            r'(?:youtube\.com\/watch\?v=|youtu\.be\/|youtube\.com\/embed\/|youtube-nocookie\.com\/embed\/)([^&\n?#]+)',
        ]
        for pattern in patterns:
            if match := re.search(pattern, url):
                return match.group(1)
        return None

    @staticmethod
    def get_transcript(video_url: str, languages: list = None) -> dict:
        video_id = YouTubeTranscriptApiFree.extract_video_id(video_url)
        if not video_id:
            raise ValueError(f"Не могу распознать ID видео из {video_url}")

        if languages is None:
            languages = ['ru', 'en']

        for instance in YouTubeTranscriptApiFree.INVIDIOUS_INSTANCES:
            try:
                api_url = f"{instance}/api/v1/videos/{video_id}"
                response = requests.get(api_url, timeout=8)

                if response.status_code != 200:
                    continue

                data = response.json()
                captions = data.get('captions', [])

                if not captions:
                    continue

                caption = None
                for lang in languages:
                    caption = next((c for c in captions if lang in c.get('language', '').lower()), None)
                    if caption:
                        break

                if not caption:
                    caption = captions[0]

                caption_url = f"{instance}{caption['url']}"
                caption_response = requests.get(caption_url, timeout=8)

                if caption_response.status_code == 200:
                    transcript = YouTubeTranscriptApiFree._parse_vtt_to_json(caption_response.text)
                    return {video_id: transcript}

            except Exception:
                continue

        raise Exception(f"❌ Не удалось получить субтитры для {video_id}")

    @staticmethod
    def _parse_vtt_to_json(vtt_content: str) -> list:
        lines = vtt_content.split('\n')
        transcript = []
        current_start = 0

        for line in lines:
            if line.startswith('WEBVTT') or not line.strip():
                continue

            if '-->' in line:
                time_match = re.match(r'(\d{2}):(\d{2}):(\d{2})', line)
                if time_match:
                    h, m, s = map(int, time_match.groups())
                    current_start = h * 3600 + m * 60 + s
            elif not re.match(r'^\d{2}:\d{2}', line):
                clean_text = re.sub(r'<[^>]+>', '', line).strip()
                if clean_text:
                    transcript.append({
                        'text': clean_text,
                        'start': current_start,
                        'duration': 0
                    })
        return transcript
