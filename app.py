import gradio as gr
import tempfile
import os
import time
from pytube import YouTube
import whisper
import subprocess
import requests
from urllib.parse import urlparse

model = whisper.load_model("base")

def is_valid_youtube_url(url):
    try:
        parsed = urlparse(url)
        return parsed.netloc in ["www.youtube.com", "youtube.com", "youtu.be"]
    except:
        return False

def download_youtube_audio(youtube_url):
    try:
        yt = YouTube(youtube_url)
        stream = yt.streams.filter(only_audio=True).order_by('abr').desc().first()
        if not stream:
            raise Exception("No audio stream found")
        
        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".mp4")
        stream.download(filename=temp_file.name)
        return temp_file.name
    except Exception as e:
        # Try with pytube fix for age-restricted content
        try:
            yt = YouTube(youtube_url, use_oauth=True, allow_oauth_cache=True)
            stream = yt.streams.filter(only_audio=True).order_by('abr').desc().first()
            temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".mp4")
            stream.download(filename=temp_file.name)
            return temp_file.name
        except Exception as e2:
            raise Exception(f"Failed to download YouTube video: {str(e2)}")

def transcribe_video(video=None, youtube_url=None):
    # Validate inputs
    if not youtube_url and (video is None or video == ""):
        return "Please upload a video or provide a valid YouTube URL.", None, "0.00s"
    
    if youtube_url and not is_valid_youtube_url(youtube_url):
        return "Please enter a valid YouTube URL.", None, "0.00s"

    start = time.time()
    file_path = None
    audio_path = None
    txt_path = None

    try:
        if youtube_url:
            file_path = download_youtube_audio(youtube_url)
        else:
            file_path = video

        audio_path = tempfile.NamedTemporaryFile(delete=False, suffix=".wav").name
        ffmpeg_cmd = [
            "ffmpeg",
            "-i", file_path,
            "-ar", "16000",
            "-ac", "1",
            "-acodec", "pcm_s16le",
            audio_path
        ]
        
        subprocess.run(ffmpeg_cmd, 
                      stdout=subprocess.DEVNULL, 
                      stderr=subprocess.DEVNULL,
                      check=True)

        result = model.transcribe(audio_path)
        transcript = result["text"]

        txt_path = tempfile.NamedTemporaryFile(delete=False, suffix=".txt").name
        with open(txt_path, "w", encoding="utf-8") as f:
            f.write(transcript)

        elapsed = f"{time.time() - start:.2f}s"
        return transcript, txt_path, elapsed

    except subprocess.CalledProcessError:
        return "Error: Failed to convert audio (ffmpeg error).", None, "0.00s"
    except Exception as e:
        return f"Error: {str(e)}", None, "0.00s"
    finally:
        # Cleanup temporary files
        if audio_path and os.path.exists(audio_path):
            os.remove(audio_path)
        if file_path and youtube_url and os.path.exists(file_path):
            os.remove(file_path)

with gr.Blocks() as demo:
    gr.Markdown("# Video Transcription Tool with Timer and Download")

    with gr.Row():
        video_input = gr.Video(label="Upload Video")
        url_input = gr.Textbox(label="Or Enter YouTube URL", 
                              placeholder="https://www.youtube.com/watch?v=...")

    transcribe_btn = gr.Button("Transcribe")

    with gr.Row():
        output = gr.Textbox(label="Transcription", lines=10)
        download = gr.File(label="Download Transcript")
        timer_display = gr.Textbox(label="Elapsed Time", interactive=False)

    transcribe_btn.click(
        fn=transcribe_video,
        inputs=[video_input, url_input],
        outputs=[output, download, timer_display]
    )

if __name__ == "__main__":
    demo.launch(debug=True)