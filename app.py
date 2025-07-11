import os
import sys
import argparse
from pytube import YouTube
from pytube.exceptions import PytubeError, VideoUnavailable, RegexMatchError
import yt_dlp
import whisper
import tempfile
import traceback
from pathlib import Path
import re
import browser_cookie3
import requests

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

def get_chrome_cookies():
    """Extract cookies from Chrome browser"""
    try:
        print("Extracting Chrome cookies...")
        cookies = browser_cookie3.chrome(domain_name=None)
        print(f"Successfully extracted {len(list(cookies))} cookies from Chrome")
        return cookies
    except Exception as e:
        print(f"Warning: Could not extract Chrome cookies: {e}")
        print("You may need to:")
        print("1. Close Chrome completely")
        print("2. Run this script as administrator/with sudo")
        print("3. Install browser_cookie3: pip install browser_cookie3")
        return None

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

def download_yt_with_pytube(video_url, temp_dir, cookies=None):
    try:
        # If cookies are available, try to use them (limited support in pytube)
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
        raise Exception("Invalid YouTube URL format")
    except VideoUnavailable as e:
        raise Exception(f"YouTube video unavailable: {str(e)}")
    except Exception as e:
        traceback.print_exc()
        raise Exception(f"Pytube error: {str(e)}")

def download_with_ytdlp(video_url, temp_dir, cookies=None):
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
            'quiet': False,
            'ignoreerrors': True,
            'no_warnings': False,
            'extract_flat': False,
            'socket_timeout': 10,
            'extractor_args': {
                'youtube': {
                    'skip': ['dash', 'hls']
                }
            }
        }
        
        # Add cookies if available
        if cookies:
            print("Using Chrome cookies for authentication...")
            # Convert cookies to the format yt-dlp expects
            cookie_jar = requests.cookies.RequestsCookieJar()
            for cookie in cookies:
                cookie_jar.set(cookie.name, cookie.value, domain=cookie.domain)
            ydl_opts['cookiejar'] = cookie_jar
        
        print(f"Attempting to download with yt-dlp: {video_url}")
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            try:
                info = ydl.extract_info(video_url, download=False)
                if not info:
                    raise Exception("Could not extract video info - the video may be private or restricted")
                
                # Skip live streams
                if info.get('is_live', False):
                    raise Exception("Live streams are not supported")
                
                if info.get('_type', 'video') != 'video':
                    raise Exception("Only single videos are supported (not playlists)")
                
                print(f"Video title: {info.get('title', 'Unknown')}")
                print(f"Duration: {info.get('duration', 'Unknown')} seconds")
                print("Downloading audio...")
                ydl.download([video_url])
            except yt_dlp.utils.DownloadError as e:
                if "Private video" in str(e):
                    raise Exception("This is a private video (login required)")
                elif "Members-only" in str(e):
                    raise Exception("This is a members-only video")
                elif "This video is not available" in str(e):
                    raise Exception("Video not available in your country or removed")
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
        
        raise Exception("Failed to download audio - no valid file found")
    except Exception as e:
        traceback.print_exc()
        if "unable to extract video info" in str(e).lower():
            raise Exception("Could not access video info - the video may be private, age-restricted, or unavailable")
        raise Exception(f"YT-DLP error: {str(e)}")

def download_and_convert_to_mp3(video_url, cookies=None):
    temp_dir = tempfile.mkdtemp()
    
    try:
        if not is_valid_url(video_url):
            raise Exception("Invalid URL format")
        
        if is_youtube_url(video_url):
            try:
                return download_yt_with_pytube(video_url, temp_dir, cookies)
            except Exception as pytube_error:
                print(f"Pytube failed, falling back to yt-dlp: {pytube_error}")
                return download_with_ytdlp(video_url, temp_dir, cookies)
        else:
            return download_with_ytdlp(video_url, temp_dir, cookies)
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
        raise Exception("No valid audio file found")
    
    try:
        # Load the appropriate model
        print(f"Loading Whisper model: {model_size}")
        model = load_whisper_model(model_size)
        
        # Set transcription options based on language selection
        options = {}
        if language and language != "auto":
            options["language"] = language
            print(f"Transcribing in {language}")
        else:
            print("Auto-detecting language")
        
        print("Starting transcription...")
        # Transcribe with the selected options
        result = model.transcribe(audio_file_path, **options)
        
        # Print detected language if auto-detect was used
        if language == "auto" or not language:
            detected_lang = result.get("language", "unknown")
            print(f"Detected language: {detected_lang}")
        
        return result["text"]
    except Exception as e:
        traceback.print_exc()
        raise Exception(f"Transcription failed: {str(e)}")
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

def process_video_url(video_url, model_size="base", language="auto", use_cookies=True):
    try:
        if not video_url.strip():
            raise Exception("Please provide a video URL")
        
        print("=" * 60)
        print("VIDEO TRANSCRIPTION STARTED")
        print("=" * 60)
        print(f"URL: {video_url}")
        print(f"Model: {model_size}")
        print(f"Language: {language}")
        print(f"Use cookies: {use_cookies}")
        print()
        
        # Get Chrome cookies if requested
        cookies = None
        if use_cookies:
            cookies = get_chrome_cookies()
            if not cookies:
                print("Warning: Could not extract cookies. Some videos may not be accessible.")
        
        print("Validating URL...")
        if not is_valid_url(video_url):
            raise Exception("Invalid URL format")
        
        # Download audio
        print("Downloading audio...")
        audio_file = download_and_convert_to_mp3(video_url, cookies)
        print(f"Audio downloaded to: {audio_file}")
        
        # Transcribe
        print("Transcribing audio...")
        transcription = transcribe_audio(audio_file, model_size, language)
        
        print()
        print("=" * 60)
        print("TRANSCRIPTION COMPLETE")
        print("=" * 60)
        print(transcription)
        print()
        print("=" * 60)
        
        return transcription
    except Exception as e:
        print(f"Error: {str(e)}")
        return None

def main():
    parser = argparse.ArgumentParser(description="Video Transcription with Chrome Cookie Authentication")
    parser.add_argument("url", help="Video URL to transcribe")
    parser.add_argument("-m", "--model", 
                       choices=["tiny", "base", "small", "medium", "large"],
                       default="base",
                       help="Whisper model size (default: base)")
    parser.add_argument("-l", "--language",
                       choices=["auto", "en", "ro", "fr", "de"],
                       default="auto",
                       help="Language for transcription (default: auto)")
    parser.add_argument("--no-cookies", action="store_true",
                       help="Don't use Chrome cookies for authentication")
    parser.add_argument("-o", "--output", 
                       help="Output file to save transcription (optional)")
    
    args = parser.parse_args()
    
    # Process the video
    result = process_video_url(
        args.url, 
        args.model, 
        args.language, 
        not args.no_cookies
    )
    
    # Save to file if requested
    if result and args.output:
        try:
            with open(args.output, 'w', encoding='utf-8') as f:
                f.write(result)
            print(f"Transcription saved to: {args.output}")
        except Exception as e:
            print(f"Error saving to file: {e}")

if __name__ == "__main__":
    print("Video Transcription Tool with Chrome Cookie Authentication")
    print("=" * 60)
    
    # Check if yt-dlp is up to date
    try:
        print("Checking yt-dlp version...")
        with yt_dlp.YoutubeDL() as ydl:
            ydl.update()
        print("yt-dlp is up to date")
    except:
        print("Could not update yt-dlp, continuing with current version")
    
    print()
    
    if len(sys.argv) == 1:
        print("Usage:")
        print("  python transcribe.py <video_url> [options]")
        print()
        print("Examples:")
        print("  python transcribe.py 'https://www.youtube.com/watch?v=dQw4w9WgXcQ'")
        print("  python transcribe.py 'https://youtu.be/dQw4w9WgXcQ' -m large -l en")
        print("  python transcribe.py 'https://youtu.be/dQw4w9WgXcQ' -o transcript.txt")
        print("  python transcribe.py 'https://youtu.be/dQw4w9WgXcQ' --no-cookies")
        print()
        print("Options:")
        print("  -m, --model     Whisper model size: tiny, base, small, medium, large")
        print("  -l, --language  Language: auto, en, ro, fr, de")
        print("  -o, --output    Output file to save transcription")
        print("  --no-cookies    Don't use Chrome cookies")
        print()
        print("Model sizes:")
        print("  tiny   - Fastest, lowest accuracy (1GB VRAM)")
        print("  base   - Good balance for most cases (1GB VRAM)")
        print("  small  - Better accuracy, medium speed (2GB VRAM)")
        print("  medium - High accuracy, slower (5GB VRAM)")
        print("  large  - Highest accuracy, slowest (10GB VRAM)")
        print()
        print("Note: Chrome cookies are used by default for accessing private/restricted videos.")
        print("      Make sure Chrome is closed before running this script.")
    else:
        main()