import whisper
import yt_dlp
import os
import time

# Load the Whisper model
def load_model(model_name="small"):
    return whisper.load_model(model_name)

model = load_model()

# Function to download video and transcribe
def transcribe_youtube(url, model_name="medium", language="ro"):
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
        return "Error: No audio file found."

    # Transcribe using Whisper
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

    return transcript_filename

if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: python transcribe.py <YouTube URL>")
        sys.exit(1)

    url = sys.argv[1]
    output_file = transcribe_youtube(url)
    print(f"Transcription saved to {output_file}")