import whisper
import yt_dlp
import os
import time
import sys

# Load the Whisper model
def load_model(model_name="small"):
    return whisper.load_model(model_name)

# Function to download video and transcribe
def transcribe_youtube(url, model_name="small", language="en"):
    start_time = time.time()
    
    # Download video using yt-dlp
    ydl_opts = {
        'format': 'bestaudio/best',
        'outtmpl': 'temp_audio.%(ext)s',
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '192',
        }],
    }
    
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([url])

    # Find the downloaded file
    audio_file = next((f for f in os.listdir() if f.startswith("temp_audio")), None)
    
    if not audio_file:
        print("Error: No audio file found.")
        sys.exit(1)

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
    url = "https://www.youtube.com/watch?v=L-45RFSajXQ"
    model_size = "large"
    language = "ro"

    transcribe_youtube(url, model_size, language)
