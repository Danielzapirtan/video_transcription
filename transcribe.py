import whisper
import yt_dlp
import os
import time
import browser_cookie3
import requests

# Load the Whisper model
def load_model(model_name="small"):
    return whisper.load_model(model_name)

# Function to download video and transcribe
def transcribe_youtube(url, model_name="small", language="en", allow_cookies="y"):
    start_time = time.time()

    # Load cookies automatically from Chrome or Edge
    cookies = None
    try:
        if allow_cookies == "y":
            cookies = browser_cookie3.chrome()  # For Chrome
            # cookies = browser_cookie3.edge()  # Uncomment for Edge
    except Exception as e:
        print(f"Error loading cookies: {e}")
        cookies = None

    # Check if cookies are available
    if cookies:
        print("Cookies loaded successfully.")

    # Download video using yt-dlp with cookies if available
    ydl_opts = {
        'format': 'bestaudio/best',
        'outtmpl': 'temp_audio.%(ext)s',
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '192',
        }],
        'cookiefile': '/home/daniel/yt/cookies.txt'
        #'cookiesfrombrowser': ('chrome',) if cookies else None,  # Pass cookies from Chrome if available
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([url])

    # Find the downloaded file
    audio_file = next((f for f in os.listdir() if f.startswith("temp_audio")), None)

    if not audio_file:
        print("Error: No audio file found.")
        return

    # Load model and transcribe
    model = load_model(model_name)
    result = model.transcribe(audio_file, language=language)

    # Cleanup
    os.remove(audio_file)

    elapsed_time = time.time() - start_time
    transcript = result["text"]

    # Save transcript to file
    transcript_filename = "transcription.txt"
    with open(transcript_filename, "w", encoding="utf-8") as f:
        f.write(transcript)

    print(f"Transcription saved to {transcript_filename}")
    print(f"Processing time: {elapsed_time:.2f} seconds")

if __name__ == "__main__":
    url = input("Enter YouTube URL: ")
    language = input("Enter language code (e.g., 'en', 'fr', 'es'): ")
    allow_cookies = input("Do you want to use cookies for authentification (y/n)").strip().lower()

    model_size = "medium" if language != "en" else "small"

    transcribe_youtube(url, model_size, language, allow_cookies)
