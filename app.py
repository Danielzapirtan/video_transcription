import whisper
import yt_dlp
import os
import time
import browser_cookie3
import requests
import platform

# Constants
TEMP_AUDIO_FILENAME = "temp_audio"
TRANSCRIPTION_FILENAME = "transcription.txt"

# Function to load the Whisper model
def load_model(model_name="small"):
    """Loads the specified Whisper model.

    Args:
        model_name (str, optional): The name of the Whisper model to load.
            Defaults to "small". Options include "tiny", "base", "small",
            "medium", "large".

    Returns:
        whisper.Whisper: The loaded Whisper model.
    """
    return whisper.load_model(model_name)

def get_browser_cookies(browser_name):
    """Retrieves cookies from the specified browser.

    Args:
        browser_name (str): The name of the browser ("chrome", "firefox", "edge").

    Returns:
        http.cookiejar.CookieJar or None: A CookieJar object containing the cookies,
        or None if the browser is not found or an error occurs.
    """
    try:
        if browser_name == "chrome":
            return browser_cookie3.chrome()
        elif browser_name == "firefox":
            return browser_cookie3.firefox()
        elif browser_name == "edge":
            return browser_cookie3.edge()
        else:
            print(f"Unsupported browser: {browser_name}")
            return None
    except Exception as e:
        print(f"Error loading cookies from {browser_name}: {e}")
        return None

def transcribe_youtube(url, model_name="small", language="en", allow_cookies="y"):
    """Downloads a YouTube video and transcribes its audio using Whisper.

    Args:
        url (str): The YouTube video URL.
        model_name (str, optional): The name of the Whisper model to use.
            Defaults to "small".
        language (str, optional): The language code for transcription (e.g., "en", "fr", "es").
            Defaults to "en".
        allow_cookies (str, optional): Specifies how to handle cookies.
            "y": Attempt to automatically load cookies from supported browsers.
            "n": Do not use cookies.
            "l": Load cookies from a 'cookies.txt' file (for Linux compatibility).
            Defaults to "y".
    """
    start_time = time.time()

    cookies = None
    if allow_cookies == "y":
        # Attempt to load cookies from different browsers
        for browser in ["chrome", "firefox", "edge"]:
            cookies = get_browser_cookies(browser)
            if cookies:
                print(f"Cookies loaded successfully from {browser}.")
                break  # Stop after the first successful load
    elif allow_cookies == 'l':
        #Load cookies from text file.
        pass
    # Configure yt-dlp options
    ydl_opts = {
        'format': 'bestaudio/best',
        'outtmpl': f'{TEMP_AUDIO_FILENAME}.%(ext)s',
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '192',
        }],
    }

    # Handle cookie options
    if allow_cookies == 'l':
        ydl_opts['cookiefile'] = './cookies.txt'
    elif cookies:
        ydl_opts['cookiesfrombrowser'] = True  # Rely on browser_cookie3 to pass cookies


    # Download the video
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([url])

    # Find the downloaded audio file
    audio_file = next((f for f in os.listdir() if f.startswith(TEMP_AUDIO_FILENAME)), None)

    if not audio_file:
        print("Error: No audio file found after download.")
        return

    # Load model and transcribe
    model = load_model(model_name)
    result = model.transcribe(audio_file, language=language)

    # Cleanup the audio file
    os.remove(audio_file)

    elapsed_time = time.time() - start_time
    transcript = result["text"]

    # Save the transcript to a file
    with open(TRANSCRIPTION_FILENAME, "w", encoding="utf-8") as f:
        f.write(transcript)

    print(f"Transcription saved to {TRANSCRIPTION_FILENAME}")
    print(f"Processing time: {elapsed_time:.2f} seconds")

if __name__ == "__main__":
    url = input("Enter YouTube URL: ")
    language = input("Enter language code (e.g., 'en', 'fr', 'es'): ")
    allow_cookies = input("Do you want to use cookies for authentication (y/n/l)? ").strip().lower()

    # Determine model size based on language (English uses smaller model for speed)
    model_size = "medium" if language != "en" else "small"

    transcribe_youtube(url, model_size, language, allow_cookies)
