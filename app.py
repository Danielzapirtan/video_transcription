import gradio as gr
import os
from pytube import YouTube
from pytube.exceptions import PytubeError, VideoUnavailable, RegexMatchError
import yt_dlp
import whisper
import tempfile
import traceback
from pathlib import Path
import re

# Global variable to store the current model
current_model = None

def load_whisper_model(model_size):
    """Load or switch the Whisper model"""
    global current_model
    
    # Only load if different from current model
    if current_model is None or current_model.model_size != model_size:
        print(f"Loading Whisper model: {model_size}")
        current_model = whisper.load_model(model_size)
    
    return current_model

def is_valid_url(url):
    """Basic URL validation"""
    youtube_regex = (
        r'(https?://)?(www\.)?'
        '(youtube|youtu|youtube-nocookie)\.(com|be)/'
        '(watch\?v=|embed/|v/|.+\?v=)?([^&=%\?]{11})')
    
    generic_url_regex = (
        r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|'
        r'[!*\(\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+')
    
    return bool(re.match(youtube_regex, url) or re.match(generic_url_regex, url))

def is_youtube_url(url):
    return "youtube.com" in url or "youtu.be" in url

def download_yt_with_pytube(video_url, temp_dir):
    try:
        yt = YouTube(video_url)
        
        # Check if video is available
        if yt.vid_info.get('playabilityStatus', {}).get('status', '').lower() == 'error':
            reason = yt.vid_info['playabilityStatus'].get('reason', 'Video unavailable')
            raise VideoUnavailable(reason)
        
        # Skip live streams
        if yt.vid_info.get('videoDetails', {}).get('isLive', False):
            raise PytubeError("Live streams are not supported")
        
        audio_stream = yt.streams.filter(only_audio=True).order_by('abr').desc().first()
        if not audio_stream:
            raise PytubeError("No audio stream available")
        
        output_file = "audio.mp3"
        print(f"Downloading with pytube to: {os.path.join(temp_dir, output_file)}")
        
        # Download file (pytube might save as mp4 even if we request mp3)
        audio_file_path = audio_stream.download(output_path=temp_dir, filename=output_file)
        
        # Ensure we return the correct path to the file that was actually downloaded
        if not os.path.exists(audio_file_path):
            # Check for alternate extensions
            for ext in ['.mp4', '.webm', '.m4a']:
                alt_path = os.path.join(temp_dir, f"audio{ext}")
                if os.path.exists(alt_path):
                    # Rename to expected .mp3 extension
                    mp3_path = os.path.join(temp_dir, "audio.mp3")
                    os.rename(alt_path, mp3_path)
                    return mp3_path
            
            raise PytubeError("Downloaded file not found")
        
        return audio_file_path
    except RegexMatchError:
        raise gr.Error("Invalid YouTube URL format")
    except VideoUnavailable as e:
        raise gr.Error(f"YouTube video unavailable: {str(e)}")
    except Exception as e:
        traceback.print_exc()
        raise gr.Error(f"Pytube error: {str(e)}")

def download_with_ytdlp(video_url, temp_dir):
    try:
        output_template = os.path.join(temp_dir, 'audio')
        
        ydl_opts = {
            'format': 'bestaudio/best',
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }],
            'outtmpl': output_template,
            'quiet': True,
            'ignoreerrors': True,
            'no_warnings': True,
            'extract_flat': False,
            'socket_timeout': 10,
            'extractor_args': {
                'youtube': {
                    'skip': ['dash', 'hls']
                }
            }
        }
        
        print(f"Attempting to download with yt-dlp: {video_url}")
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            try:
                info = ydl.extract_info(video_url, download=False)
                if not info:
                    raise gr.Error("Could not extract video info - the video may be private or restricted")
                
                # Skip live streams
                if info.get('is_live', False):
                    raise gr.Error("Live streams are not supported")
                
                if info.get('_type', 'video') != 'video':
                    raise gr.Error("Only single videos are supported (not playlists)")
                
                print(f"Downloading with yt-dlp: {info.get('title', '')}")
                ydl.download([video_url])
            except yt_dlp.utils.DownloadError as e:
                if "Private video" in str(e):
                    raise gr.Error("This is a private video (login required)")
                elif "Members-only" in str(e):
                    raise gr.Error("This is a members-only video")
                elif "This video is not available" in str(e):
                    raise gr.Error("Video not available in your country or removed")
                else:
                    raise
        
        # Find the downloaded file
        expected_file = output_template + '.mp3'
        if os.path.exists(expected_file):
            return expected_file
            
        # If the expected file isn't found, search for any audio file
        for file in os.listdir(temp_dir):
            if file.startswith("audio"):
                return os.path.join(temp_dir, file)
        
        raise gr.Error("Failed to download audio - no valid file found")
    except Exception as e:
        traceback.print_exc()
        if "unable to extract video info" in str(e).lower():
            raise gr.Error("Could not access video info - the video may be private, age-restricted, or unavailable")
        raise gr.Error(f"YT-DLP error: {str(e)}")

def download_and_convert_to_mp3(video_url):
    temp_dir = tempfile.mkdtemp()
    
    try:
        if not is_valid_url(video_url):
            raise gr.Error("Invalid URL format")
        
        if is_youtube_url(video_url):
            try:
                return download_yt_with_pytube(video_url, temp_dir)
            except Exception as pytube_error:
                print(f"Pytube failed, falling back to yt-dlp: {pytube_error}")
                return download_with_ytdlp(video_url, temp_dir)
        else:
            return download_with_ytdlp(video_url, temp_dir)
    except Exception as e:
        # Clean up temp dir if error occurs
        if os.path.exists(temp_dir):
            for file in os.listdir(temp_dir):
                try:
                    os.remove(os.path.join(temp_dir, file))
                except:
                    pass
            try:
                os.rmdir(temp_dir)
            except:
                pass
        raise

def transcribe_audio(audio_file_path, model_size, language):
    if not audio_file_path or not os.path.exists(audio_file_path):
        raise gr.Error("No valid audio file found")
    
    try:
        # Load the appropriate model
        model = load_whisper_model(model_size)
        
        # Set transcription options based on language selection
        options = {}
        if language != "auto":
            options["language"] = language
        
        # Transcribe with the selected options
        result = model.transcribe(audio_file_path, **options)
        return result["text"]
    except Exception as e:
        traceback.print_exc()
        raise gr.Error(f"Transcription failed: {str(e)}")
    finally:
        # Clean up the audio file and its directory
        if audio_file_path and os.path.exists(audio_file_path):
            temp_dir = os.path.dirname(audio_file_path)
            try:
                os.remove(audio_file_path)
                # Only remove directory if it's empty
                if not os.listdir(temp_dir):
                    os.rmdir(temp_dir)
            except:
                pass

def process_video_url(video_url, model_size, language, progress=gr.Progress()):
    try:
        if not video_url.strip():
            raise gr.Error("Please enter a video URL")
        
        progress(0.1, desc="Validating URL...")
        
        # Download audio
        progress(0.3, desc="Downloading audio...")
        audio_file = download_and_convert_to_mp3(video_url)
        
        # Transcribe
        progress(0.6, desc=f"Loading {model_size} model...")
        progress(0.7, desc=f"Transcribing audio in {language if language != 'auto' else 'auto-detected language'}...")
        transcription = transcribe_audio(audio_file, model_size, language)
        
        progress(1.0, desc="Complete!")
        return transcription
    except gr.Error as e:
        # Pass through Gradio errors directly
        raise
    except Exception as e:
        traceback.print_exc()
        raise gr.Error(str(e))

# Define language mapping for UI
LANGUAGE_OPTIONS = {
    "auto": "Auto-detect language",
    "en": "English",
    "ro": "Romanian",
    "fr": "French", 
    "de": "German"
}

# Create Gradio interface
with gr.Blocks(title="Video Transcription", theme="soft") as app:
    gr.Markdown("""
    # 🎥 Video to Transcription
    Convert YouTube or other video URLs to text using Whisper AI
    
    **Note**: 
    - Live streams, private videos, and age-restricted videos may not work
    - For YouTube links, tries pytube first, then falls back to yt-dlp
    """)
    
    with gr.Row():
        with gr.Column(scale=4):
            video_url = gr.Textbox(
                label="Video URL",
                placeholder="https://www.youtube.com/watch?v=... or any video URL",
                max_lines=1
            )
        with gr.Column(scale=1):
            submit_btn = gr.Button("Transcribe", variant="primary")
    
    with gr.Row():
        with gr.Column(scale=1):
            model_dropdown = gr.Dropdown(
                ["tiny", "base", "small", "medium", "large"],
                value="base",
                label="Whisper Model Size",
                info="Larger models are more accurate but slower"
            )
        with gr.Column(scale=1):
            language_dropdown = gr.Dropdown(
                list(LANGUAGE_OPTIONS.keys()),
                value="auto",
                label="Language",
                info="Select 'auto' to let Whisper detect the language"
            )
    
    with gr.Row():
        output_text = gr.Textbox(
            label="Transcription",
            interactive=True,
            lines=10,
            show_copy_button=True,
            autoscroll=True
        )
    
    with gr.Row():
        gr.Examples(
            examples=[
                ["https://www.youtube.com/watch?v=dQw4w9WgXcQ"],
                ["https://www.youtube.com/watch?v=YQHsXMglC9A"],
                ["https://www.youtube.com/watch?v=JGwWNGJdvx8"]
            ],
            inputs=video_url,
            label="Try these examples (click to load)"
        )
    
    # Display selected language name (not code)
    language_dropdown.change(
        fn=lambda lang: gr.Dropdown.update(info=f"Selected: {LANGUAGE_OPTIONS[lang]}"),
        inputs=language_dropdown,
        outputs=language_dropdown
    )
    
    # Process button click
    submit_btn.click(
        fn=process_video_url,
        inputs=[video_url, model_dropdown, language_dropdown],
        outputs=output_text,
    )
    
    # Add information about model sizes
    gr.Markdown("""
    ### About Model Sizes
    - **tiny**: Fastest, lowest accuracy (1GB VRAM)
    - **base**: Good balance for most cases (1GB VRAM)
    - **small**: Better accuracy, medium speed (2GB VRAM)
    - **medium**: High accuracy, slower (5GB VRAM)
    - **large**: Highest accuracy, slowest (10GB VRAM)
    
    ### Supported Languages
    Auto-detect, English, Romanian, French, and German
    """)

if __name__ == "__main__":
    # Check if yt-dlp is up to date
    try:
        with yt_dlp.YoutubeDL() as ydl:
            ydl.update()
    except:
        print("Could not update yt-dlp, continuing with current version")
    
    # Pre-load the base model on startup
    try:
        load_whisper_model("base")
    except Exception as e:
        print(f"Warning: Failed to pre-load Whisper model: {e}")
    
    app.launch()