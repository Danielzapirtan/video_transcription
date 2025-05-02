import gradio as gr
import tempfile
import os
import time
import re
from pytube import YouTube
import whisper
import subprocess

model = whisper.load_model("base")

def is_valid_youtube_url(url):
    # More comprehensive YouTube URL regex pattern
    youtube_regex = (
        r'(https?://)?(www\.)?'
        r'(youtube|youtu|youtube-nocookie)\.(com|be)/'
        r'(watch\?v=|embed/|v/|.+\?v=)?([^&=%\?]{11})')
    
    youtube_regex_match = re.match(youtube_regex, url)
    if youtube_regex_match:
        return True
    
    # Additional check for youtu.be short links
    if "youtu.be/" in url:
        return True
    
    return False

def download_youtube_audio(youtube_url):
    try:
        # Try with standard download first
        yt = YouTube(youtube_url)
        stream = yt.streams.filter(only_audio=True).first()
        if not stream:
            raise Exception("No audio stream found")
        
        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".mp4")
        stream.download(filename=temp_file.name)
        return temp_file.name
    except Exception as e:
        # If first attempt fails, try with OAuth
        try:
            yt = YouTube(youtube_url, use_oauth=True, allow_oauth_cache=True)
            stream = yt.streams.filter(only_audio=True).first()
            temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".mp4")
            stream.download(filename=temp_file.name)
            return temp_file.name
        except Exception as e2:
            raise Exception(f"YouTube download failed. Please check: \n"
                          f"1. The URL is correct\n"
                          f"2. The video isn't private/age-restricted\n"
                          f"3. Your network connection\n"
                          f"Error details: {str(e2)}")

def transcribe_video(video=None, youtube_url=None):
    # Clean inputs
    youtube_url = youtube_url.strip() if youtube_url else None
    
    if not youtube_url and (video is None or video == ""):
        return "Please upload a video or provide a YouTube URL.", None, "0.00s"
    
    if youtube_url:
        if not is_valid_youtube_url(youtube_url):
            return ("Please enter a valid YouTube URL in one of these formats:\n"
                   "• https://www.youtube.com/watch?v=VIDEO_ID\n"
                   "• https://youtu.be/VIDEO_ID", None, "0.00s")

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
            "-ar", "16000",  # Sample rate
            "-ac", "1",      # Mono audio
            "-acodec", "pcm_s16le",  # PCM 16-bit little-endian
            "-y",           # Overwrite without asking
            audio_path
        ]
        
        subprocess.run(ffmpeg_cmd, 
                      stdout=subprocess.DEVNULL, 
                      stderr=subprocess.PIPE,
                      check=True)

        result = model.transcribe(audio_path)
        transcript = result["text"]

        txt_path = tempfile.NamedTemporaryFile(delete=False, suffix=".txt").name
        with open(txt_path, "w", encoding="utf-8") as f:
            f.write(transcript)

        elapsed = f"{time.time() - start:.2f}s"
        return transcript, txt_path, elapsed

    except subprocess.CalledProcessError as e:
        error_msg = e.stderr.decode('utf-8') if e.stderr else "Unknown ffmpeg error"
        return f"Audio conversion failed: {error_msg}", None, "0.00s"
    except Exception as e:
        return f"Error: {str(e)}", None, "0.00s"
    finally:
        # Cleanup temporary files
        for path in [audio_path, file_path]:
            if path and os.path.exists(path) and (youtube_url or path != video):
                try:
                    os.remove(path)
                except:
                    pass

with gr.Blocks() as demo:
    gr.Markdown("# Video Transcription Tool")
    
    with gr.Row():
        video_input = gr.Video(label="Upload Video")
        url_input = gr.Textbox(
            label="YouTube URL",
            placeholder="Example: https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            info="Paste a YouTube link here"
        )

    transcribe_btn = gr.Button("Transcribe", variant="primary")

    with gr.Row():
        output = gr.Textbox(label="Transcription", lines=10)
        download = gr.File(label="Download Transcript")
        timer_display = gr.Textbox(label="Processing Time", interactive=False)

    transcribe_btn.click(
        fn=transcribe_video,
        inputs=[video_input, url_input],
        outputs=[output, download, timer_display]
    )

if __name__ == "__main__":
    demo.launch(debug=True)