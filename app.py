import gradio as gr
import tempfile
import os
import time
import re
from pytube import YouTube
import whisper
import subprocess
import traceback

model = whisper.load_model("medium")

def is_valid_youtube_url(url):
    if not url or not isinstance(url, str):
        return False
        
    youtube_regex = (
        r'(https?://)?(www\.)?'
        r'(youtube|youtu|youtube-nocookie)\.(com|be)/'
        r'(watch\?v=|embed/|v/|.+\?v=)?([^&=%\?]{11})')
    
    return re.match(youtube_regex, url) is not None or "youtu.be/" in url

def download_youtube_audio(youtube_url):
    try:
        print(f"Attempting to download: {youtube_url}")  # Debug
        yt = YouTube(youtube_url)
        stream = yt.streams.filter(only_audio=True).first()
        if not stream:
            raise Exception("No audio stream found")
        
        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".mp4")
        print(f"Downloading to temp file: {temp_file.name}")  # Debug
        stream.download(filename=temp_file.name)
        return temp_file.name
    except Exception as e:
        print(f"Download failed, trying with OAuth: {str(e)}")  # Debug
        try:
            yt = YouTube(youtube_url, use_oauth=True, allow_oauth_cache=True)
            stream = yt.streams.filter(only_audio=True).first()
            temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".mp4")
            stream.download(filename=temp_file.name)
            return temp_file.name
        except Exception as e2:
            print(f"OAuth download failed: {str(e2)}")  # Debug
            raise Exception(f"Failed to download YouTube video. Please check:\n"
                          f"- URL is correct and public\n"
                          f"- Video isn't age-restricted\n"
                          f"- Network connection is working\n"
                          f"Error: {str(e2)}")

def transcribe_video(video=None, youtube_url=None):
    try:
        print("\nStarting transcription...")  # Debug
        print(f"Inputs - Video: {video}, YouTube URL: {youtube_url}")  # Debug
        
        # Clean and validate inputs
        youtube_url = youtube_url.strip() if youtube_url else None
        
        if not youtube_url and (video is None or video == ""):
            return "Please upload a video or provide a YouTube URL.", None, "0.00s"
        
        if youtube_url and not is_valid_youtube_url(youtube_url):
            return ("Invalid YouTube URL. Examples:\n"
                   "https://www.youtube.com/watch?v=VIDEO_ID\n"
                   "https://youtu.be/VIDEO_ID", None, "0.00s")

        start = time.time()
        file_path = None
        audio_path = None
        txt_path = None

        try:
            if youtube_url:
                print("Downloading YouTube audio...")  # Debug
                file_path = download_youtube_audio(youtube_url)
                print(f"Downloaded to: {file_path}")  # Debug
            else:
                file_path = video
                print(f"Using uploaded file: {file_path}")  # Debug

            # Convert to WAV
            audio_path = tempfile.NamedTemporaryFile(delete=False, suffix=".wav").name
            print(f"Converting to WAV: {audio_path}")  # Debug
            
            ffmpeg_cmd = [
                "ffmpeg",
                "-i", file_path,
                "-ar", "16000",
                "-ac", "1",
                "-acodec", "pcm_s16le",
                "-y",
                audio_path
            ]
            
            print(f"Running ffmpeg: {' '.join(ffmpeg_cmd)}")  # Debug
            subprocess.run(ffmpeg_cmd, 
                         stdout=subprocess.PIPE, 
                         stderr=subprocess.PIPE,
                         check=True)

            # Transcribe
            print("Starting transcription...")  # Debug
            result = model.transcribe(audio_path)
            transcript = result["text"]
            print("Transcription completed")  # Debug

            # Save transcript
            txt_path = tempfile.NamedTemporaryFile(delete=False, suffix=".txt").name
            with open(txt_path, "w", encoding="utf-8") as f:
                f.write(transcript)

            elapsed = f"{time.time() - start:.2f}s"
            print(f"Done! Time elapsed: {elapsed}")  # Debug
            return transcript, txt_path, elapsed

        except subprocess.CalledProcessError as e:
            error_msg = e.stderr.decode('utf-8') if e.stderr else "Unknown ffmpeg error"
            print(f"FFmpeg error: {error_msg}")  # Debug
            return f"Audio conversion failed: {error_msg}", None, "0.00s"
        except Exception as e:
            print(f"Processing error: {str(e)}")  # Debug
            traceback.print_exc()  # Print full traceback
            return f"Error: {str(e)}", None, "0.00s"
        finally:
            # Cleanup
            print("Cleaning up temporary files...")  # Debug
            for path in [audio_path, file_path if youtube_url else None]:
                if path and os.path.exists(path):
                    try:
                        os.remove(path)
                        print(f"Deleted: {path}")  # Debug
                    except Exception as e:
                        print(f"Error deleting {path}: {str(e)}")  # Debug
                        pass

    except Exception as e:
        print(f"Unexpected error: {str(e)}")  # Debug
        traceback.print_exc()
        return f"Unexpected error occurred. Please check console for details.", None, "0.00s"

# Create interface
with gr.Blocks() as demo:
    gr.Markdown("# YouTube Video Transcription")
    
    with gr.Row():
        video_input = gr.Video(label="Upload Video (or use YouTube URL below)")
        url_input = gr.Textbox(
            label="YouTube URL",
            placeholder="https://www.youtube.com/watch?v=...",
            info="Paste a YouTube link here"
        )

    transcribe_btn = gr.Button("Transcribe", variant="primary")

    with gr.Row():
        output = gr.Textbox(label="Transcription", lines=10)
        download = gr.File(label="Download Transcript")
        timer_display = gr.Textbox(label="Processing Time")

    transcribe_btn.click(
        fn=transcribe_video,
        inputs=[video_input, url_input],
        outputs=[output, download, timer_display]
    )

if __name__ == "__main__":
    print("Starting Gradio interface...")
    demo.launch(debug=True)