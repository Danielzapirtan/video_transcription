import os
import re
import subprocess
import torch
import whisper
from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api.formatters import TextFormatter
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import time

def youtube_url_validation(url):
    youtube_regex = (
        r'(https?://)?(www\.)?'
        '(youtube|youtu|youtube-nocookie)\.(com|be)/'
        '(watch\?v=|embed/|v/|/)([a-zA-Z0-9_-]{11})'
    )
    youtube_regex_match = re.match(youtube_regex, url)
    if youtube_regex_match:
        return youtube_regex_match.group(6)
    return False

def get_youtube_title(video_id):
    try:
        command = ['yt-dlp', '--get-title', f'https://www.youtube.com/watch?v={video_id}']
        result = subprocess.run(command, capture_output=True, text=True, check=True)
        return result.stdout.strip()
    except subprocess.CalledProcessError as e:
        print(f"Error getting title: {e}")
        return "Untitled"

def get_transcript_yt_api(video_id, language):
    try:
        transcript = YouTubeTranscriptApi.get_transcript(video_id, languages=[language])
        formatter = TextFormatter()
        text_formatted = formatter.format_transcript(transcript)
        return text_formatted
    except Exception as e:
        print(f"Error fetching transcript with youtube_transcript_api: {e}")
        return None

def get_cookies_selenium(driver, url, save_location="cookies.txt"):
  driver.get(url)
  input("Please log in into your Youtube Account and press any key")
  cookies = driver.get_cookies()
  with open(save_location, 'w') as filehandler:
    import json
    json.dump(cookies, filehandler)
  return cookies

def load_cookies(driver, url, cookies_location="cookies.txt"):
  driver.get(url)
  import json
  with open(cookies_location, 'r') as cookiesfile:
    cookies = json.load(cookiesfile)
    for cookie in cookies:
      driver.add_cookie(cookie)
  driver.get(url)
  print("Cookies loaded")

def transcribe_with_whisper(video_url, language, use_cookies=False):

    video_id = youtube_url_validation(video_url)
    if not video_id:
        print("Invalid YouTube URL.")
        return

    video_title = get_youtube_title(video_id)
    print(f"Transcribing: {video_title}")

    transcript_text = get_transcript_yt_api(video_id, language)
    if transcript_text:
        print("Transcript successfully fetched using YouTubeTranscriptApi.")
        return video_title, transcript_text
    else:
        print("Falling back to Whisper for transcription.")

    model_size = "small" if language == "en" else "medium"
    try:
        device = "cuda" if torch.cuda.is_available() else "cpu"
    except:
        device = "cpu"
    print(f"Using device: {device}")
    model = whisper.load_model(model_size, device=device)
    print(f"Loaded whisper model: {model_size}")

    temp_audio_file = "temp_audio.mp3"
    try:
        subprocess.run(['yt-dlp', '-x', '--audio-format', 'mp3', '-o', temp_audio_file, video_url], check=True, capture_output=True)
        print("Audio downloaded.")
    except subprocess.CalledProcessError as e:
        print(f"Error downloading audio: {e.stderr.decode()}")
        return

    try:
        result = model.transcribe(temp_audio_file, verbose = True, language=language)
        transcript_text = result["text"]
        print("Transcription complete.")
    except Exception as e:
        print(f"Error during transcription: {e}")
        return

    os.remove(temp_audio_file)
    return video_title, transcript_text

def main():
    video_url = input("Enter YouTube video URL: ")
    language = input("Enter language (en for English, ro for Romanian): ").lower()
    if language not in ["en", "ro"]:
        print("Invalid language.  Using English (en).")
        language = "en"

    use_cookies_input = input("Use cookies for YouTube authentication? (yes/no): ").lower()
    use_cookies = use_cookies_input == "yes"

    if use_cookies:
        options = webdriver.ChromeOptions()  # Or FirefoxOptions, EdgeOptions
        options.add_argument('--headless')
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')  # Often needed in Colab
        try:
          driver = webdriver.Chrome(options=options) # or Firefox, Edge
        except Exception as e:
          print(e)
          print("Trying to install Chrome")
          try:
            subprocess.run(['apt-get', 'update'], check=True, capture_output=True)
            subprocess.run(['apt-get', 'install', '-y', 'chromium-chromedriver'], check=True, capture_output=True)
            driver = webdriver.Chrome(options=options)
          except Exception as e:
            print("Install Error", e)
            driver = None

        if driver:
          try:
            get_cookies_selenium(driver, video_url, save_location="cookies.txt")
            driver.quit()
          except Exception as e:
            print("Cookie creation Error", e)
            try:
                driver.quit()
            except:
                pass
        else:
            print("No browser detected")


    try:
        video_title, transcript = transcribe_with_whisper(video_url, language, use_cookies)

        if transcript:
            filename = f"{video_title.replace(' ', '_')}.txt"
            with open(filename, "w", encoding="utf-8") as f:
                f.write(transcript)
            print(f"Transcription saved to {filename}")
        else:
            print("Transcription failed.")
    except Exception as e:
        print(f"An error occurred: {e}")


if __name__ == "__main__":
    main()
