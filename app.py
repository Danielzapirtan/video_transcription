import gradio as gr
import tempfile
import os
import time
import re
from pytube import YouTube
import whisper
import subprocess
import traceback

model = whisper.load_model("base")

def is_valid_youtube_url(url):
    if not url or not isinstance(url, str):
        return False
        
    # Comprehensive regex pattern covering all YouTube URL formats
    youtube_regex = (
        r'(https?://)?(www\.|m\.)?'  # http/https, www or m (mobile)
        r'(youtube|youtu|youtube-nocookie)\.(com|be)/'  # domains
        r'(watch\?v=|embed/|v/|.+\?v=)?([^&=%\?]{11})')  # video ID
    
    # Check standard patterns
    if re.match(youtube_regex, url):
        return True
    
    # Check youtu.be short links (including mobile)
    if "youtu.be/" in url:
        return True
    
    # Check mobile-specific patterns
    mobile_patterns = [
        r'https?://m\.youtube\.com/watch\?v=([^&]*)',
        r'https?://youtube\.com/watch\?v=([^&]*)',
        r'https?://m\.youtu\.be/([^&]*)'
    ]
    
    return any(re.match(pattern, url) for pattern in mobile_patterns)

def download_youtube_audio(youtube_url):
    try:
        print(f"Attempting to download: {youtube_url}")
        yt = YouTube(youtube_url)
        
        # Get the best audio stream
        stream = yt.streams.filter(only_audio=True).order_by('abr').desc().first()
        if not stream:
            raise Exception("No audio stream found")
        
        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".mp4")
        print(f"Downloading to temp file: {temp_file.name}")
        stream.download(filename=temp_file.name)
        return temp_file.name
    except Exception as e:
        print(f"Download failed, trying with OAuth: {str(e)}")
        try:
            yt = YouTube(youtube_url, use_oauth=True, allow_oauth_cache=True)
            stream = yt.streams.filter(only_audio=True).order_by('abr').desc().first()
            temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".mp4")
            stream.download(filename=temp_file.name)
            return temp_file.name
        except Exception as e2:
            print(f"OAuth download failed: {str(e2)}")
            raise Exception(f"Failed to download YouTube video. Please check:\n"
                          f"- URL is correct and public\n"
                          f"- Video isn't age-restricted\n"
                          f"- Network connection is working\n"
                          f"Error: {str(e2)}")

def transcribe_video(video=None, youtube_url=None):
    try:
        print("\nStarting transcription...")
        print(f"Inputs - Video: {video}, YouTube URL: {youtube_url}")
        
        # Clean and validate inputs
        youtube_url = youtube_url.strip() if youtube_url else None
        
        if not youtube_url and (video is None or video == ""):
            return "Please upload a video or provide a YouTube URL.", None, "0.00s"
        
        if youtube_url:
            if not is_valid_youtube_url(youtube_url):
                return ("Invalid YouTube URL. Supported formats:\n"
                       "• https://www.youtube.com/watch?v=VIDEO_ID\n"
                       "• https://m.youtube.com/watch?v=VIDEO_ID\n"
                       "• https://youtu.be/VIDEO_ID\n"
                       "• https://m.youtu.be/VIDEO_ID", None, "0.00s")

        start = time.time()
        file_path = None
        audio_path = None
        txt_path = None

        try:
            if youtube_url:
                print("Downloading YouTube audio...")
                file_path = download_youtube_audio(youtube_url)
                print(f"Downloaded to: {file_path}")
            else:
                file_path = video
                print(f"Using uploaded file: {file_path}")

            # Convert to WAV
            audio_path = tempfile.NamedTemporaryFile(delete=False, suffix=".wav").name
            print(f"Converting to WAV: {audio_path}")
            
            ffmpeg_cmd = [
                "ffmpeg",
                "-i", file_path,
                "-ar", "16000",
                "-ac", "1",
                "-acodec", "pcm_s16le",
                "-y",
                audio_path
            ]
            
            print(f"Running ffmpeg: {' '.join(ffmpeg_cmd)}")
            result = subprocess.run(ffmpeg_cmd, 
                                 stdout=subprocess.PIPE, 
                                 stderr=subprocess.PIPE,
                                 check=True)

            # Transcribe
            print("Starting transcription...")
            result = model.transcribe(audio_path)
            transcript = result["text"]
            print("Transcription completed")

            # Save transcript
            txt_path = tempfile.NamedTemporaryFile(delete=False, suffix=".txt").name
            with open(txt_path, "w", encoding="utf-8") as f:
                f.write(transcript)

            elapsed = f"{time.time() - start:.2f}s"
            print(f"Done! Time elapsed: {elapsed}")
            return transcript, txt_path, elapsed

        except subprocess.CalledProcessError as e:
            error_msg = e.stderr.decode('utf-8') if e.stderr else "Unknown ffmpeg error"
            print(f"FFmpeg error: {error_msg}")
            return f"Audio conversion failed: {error_msg}", None, "0.00s"
        except Exception as e:
            print(f"Processing error: {str(e)}")
            traceback.print_exc()
            return f"Error: {str(e)}", None, "0.00s"
        finally:
            # Cleanup
            print("Cleaning up temporary files...")
            for path in [audio_path, file_path if youtube_url else None]:
                if path and os.path.exists(path):
                    try:
                        os.remove(path)
                        print(f"Deleted: {path}")
                    except Exception as e:
                        print(f"Error deleting {path}: {str(e)}")
                        pass

    except Exception as e:
        print(f"Unexpected error: {str(e)}")
        traceback.print_exc()
        return f"Unexpected error occurred. Please check console for details.", None, "0.00s"

# Create interface
with gr.Blocks() as demo:
    gr.Markdown("# YouTube Video Transcription (Mobile Supported)")
    
    with gr.Row():
        video_input = gr.Video(label="Upload Video (or use YouTube URL below)")
        url_input = gr.Textbox(
            label="YouTube URL",
            placeholder="https://m.youtube.com/watch?v=... or https://youtu.be/...",
            info="Supports all YouTube URLs including mobile (m.)"
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