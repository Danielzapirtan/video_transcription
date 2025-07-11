import os
import sys
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
import shutil

# Global variable to store the current model
current_model = None
current_model_size = None

def load_whisper_model(model_size):
    """Load or switch the Whisper model"""
    global current_model, current_model_size
    
    # Only load if different from current model
    if current_model is None or current_model_size != model_size:
        print(f"Loading Whisper model: {model_size}")
        try:
            current_model = whisper.load_model(model_size)
            current_model_size = model_size
        except Exception as e:
            raise Exception(f"Failed to load Whisper model '{model_size}': {str(e)}")
    
    return current_model

def get_chrome_cookies():
    """Extract cookies from Chrome browser"""
    try:
        print("Extracting Chrome cookies...")
        cookies = browser_cookie3.chrome(domain_name='youtube.com')
        cookie_list = list(cookies)
        print(f"Successfully extracted {len(cookie_list)} YouTube cookies from Chrome")
        return cookie_list
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
        
        output_file = "audio"
        print(f"Downloading with pytube...")
        
        # Download file
        audio_file_path = audio_stream.download(output_path=temp_dir, filename=output_file)
        
        # Ensure we return the correct path to the file that was actually downloaded
        if not os.path.exists(audio_file_path):
            # Check for alternate extensions
            for ext in ['.mp4', '.webm', '.m4a']:
                alt_path = os.path.join(temp_dir, f"audio{ext}")
                if os.path.exists(alt_path):
                    return alt_path
            
            raise PytubeError("Downloaded file not found")
        
        return audio_file_path
    except RegexMatchError:
        raise Exception("Invalid YouTube URL format")
    except VideoUnavailable as e:
        raise Exception(f"YouTube video unavailable: {str(e)}")
    except Exception as e:
        raise Exception(f"Pytube error: {str(e)}")

def download_with_ytdlp(video_url, temp_dir, cookies=None):
    try:
        output_template = os.path.join(temp_dir, 'audio.%(ext)s')
        
        ydl_opts = {
            'format': 'bestaudio/best',
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }],
            'outtmpl': output_template,
            'quiet': True,
            'no_warnings': True,
            'extract_flat': False,
            'socket_timeout': 30,
            'retries': 3,
            'extractor_args': {
                'youtube': {
                    'skip': ['dash', 'hls']
                }
            }
        }
        
        # Add cookies if available
        cookie_file_path = None
        if cookies:
            print("Using Chrome cookies for authentication...")
            # Create a temporary cookie file
            try:
                cookie_file = tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False)
                cookie_file_path = cookie_file.name
                
                # Convert cookies to Netscape format
                cookie_file.write("# Netscape HTTP Cookie File\n")
                for cookie in cookies:
                    if hasattr(cookie, 'domain') and hasattr(cookie, 'name'):
                        cookie_line = f"{cookie.domain}\t{'TRUE' if cookie.domain.startswith('.') else 'FALSE'}\t{cookie.path}\t{'TRUE' if cookie.secure else 'FALSE'}\t{cookie.expires or 0}\t{cookie.name}\t{cookie.value}\n"
                        cookie_file.write(cookie_line)
                
                cookie_file.close()
                ydl_opts['cookiefile'] = cookie_file_path
            except Exception as e:
                print(f"Warning: Could not create cookie file: {e}")
        
        print(f"Downloading with yt-dlp...")
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
                duration = info.get('duration', 0)
                if duration:
                    minutes = duration // 60
                    seconds = duration % 60
                    print(f"Duration: {minutes}:{seconds:02d}")
                
                ydl.download([video_url])
            except yt_dlp.utils.DownloadError as e:
                error_str = str(e)
                if "Private video" in error_str:
                    raise Exception("This is a private video (login required)")
                elif "Members-only" in error_str:
                    raise Exception("This is a members-only video")
                elif "This video is not available" in error_str:
                    raise Exception("Video not available in your country or removed")
                elif "Sign in to confirm your age" in error_str:
                    raise Exception("Age-restricted video - cookies may be needed")
                else:
                    raise Exception(f"Download error: {error_str}")
            finally:
                # Clean up cookie file if it was created
                if cookie_file_path and os.path.exists(cookie_file_path):
                    try:
                        os.unlink(cookie_file_path)
                    except:
                        pass
        
        # Find the downloaded file
        expected_file = os.path.join(temp_dir, 'audio.mp3')
        if os.path.exists(expected_file):
            return expected_file
            
        # If the expected file isn't found, search for any audio file
        for file in os.listdir(temp_dir):
            if file.startswith("audio") and file.endswith(('.mp3', '.mp4', '.webm', '.m4a')):
                return os.path.join(temp_dir, file)
        
        raise Exception("Failed to download audio - no valid file found")
    except Exception as e:
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
                print(f"Pytube failed: {pytube_error}")
                print("Trying yt-dlp...")
                return download_with_ytdlp(video_url, temp_dir, cookies)
        else:
            return download_with_ytdlp(video_url, temp_dir, cookies)
    except Exception as e:
        # Clean up temp dir if error occurs
        cleanup_temp_dir(temp_dir)
        raise

def cleanup_temp_dir(temp_dir):
    """Safely cleanup temporary directory"""
    if os.path.exists(temp_dir):
        try:
            shutil.rmtree(temp_dir)
        except Exception as e:
            print(f"Warning: Could not clean up temp directory {temp_dir}: {e}")

def transcribe_audio(audio_file_path, model_size, language):
    if not audio_file_path or not os.path.exists(audio_file_path):
        raise Exception("No valid audio file found")
    
    temp_dir = os.path.dirname(audio_file_path)
    
    try:
        # Load the appropriate model
        model = load_whisper_model(model_size)
        
        # Set transcription options based on language selection
        options = {
            'fp16': False,  # Disable half precision for better compatibility
            'verbose': False
        }
        
        if language and language != "auto":
            options["language"] = language
        
        print(f"Transcribing audio using {model_size} model...")
        if language and language != "auto":
            print(f"Language set to: {language}")
        else:
            print("Auto-detecting language...")
        
        # Transcribe with the selected options
        result = model.transcribe(audio_file_path, **options)
        
        # Print detected language if auto-detect was used
        if not language or language == "auto":
            detected_lang = result.get("language", "unknown")
            print(f"Detected language: {detected_lang}")
        
        return result["text"]
    except Exception as e:
        print(f"Transcription error details: {traceback.format_exc()}")
        raise Exception(f"Transcription failed: {str(e)}")
    finally:
        # Clean up the temp directory
        cleanup_temp_dir(temp_dir)

def get_user_input():
    """Interactive CLI to get user preferences"""
    print("🎥 Video Transcription Tool")
    print("=" * 50)
    
    # Get video URL
    while True:
        url = input("\nEnter video URL: ").strip()
        if not url:
            print("Please enter a valid URL")
            continue
        if not is_valid_url(url):
            print("Invalid URL format. Please enter a valid video URL.")
            continue
        break
    
    # Get cookie authentication preference
    while True:
        use_cookies = input("\nAuthenticate with Chrome cookies? (Y/n): ").strip().lower()
        if use_cookies in ['', 'y', 'yes']:
            use_cookies = True
            break
        elif use_cookies in ['n', 'no']:
            use_cookies = False
            break
        else:
            print("Please enter Y or n")
    
    # Get language preference
    while True:
        language = input("\nEnter language code (auto/ro/en): ").strip().lower()
        if language in ['auto', 'ro', 'en']:
            break
        else:
            print("Please enter 'auto' for auto-detect, 'ro' for Romanian, or 'en' for English")
    
    # Get model size preference
    while True:
        print("\nAvailable models:")
        print("1. tiny - Fastest, least accurate")
        print("2. base - Good balance (recommended)")
        print("3. small - Better accuracy")
        print("4. medium - High accuracy")
        print("5. large - Highest accuracy, slowest")
        
        choice = input("Select model (1-5) or press Enter for auto-selection: ").strip()
        
        if choice == '':
            # Auto-select based on language
            if language == 'en':
                model_size = 'base'
                print(f"Auto-selected 'base' model for English")
            else:
                model_size = 'medium'
                print(f"Auto-selected 'medium' model for better multilingual support")
            break
        elif choice in ['1', '2', '3', '4', '5']:
            models = ['tiny', 'base', 'small', 'medium', 'large']
            model_size = models[int(choice) - 1]
            print(f"Selected '{model_size}' model")
            break
        else:
            print("Please enter a number 1-5 or press Enter")
    
    return url, use_cookies, language, model_size

def save_transcription(text, url):
    """Ask user if they want to save the transcription"""
    while True:
        save = input("\nSave transcription to file? (Y/n): ").strip().lower()
        if save in ['', 'y', 'yes']:
            # Generate default filename
            try:
                # Try to extract video ID for filename
                if 'youtube.com' in url or 'youtu.be' in url:
                    video_id = url.split('/')[-1].split('?')[0].split('&')[0]
                    if '=' in video_id:
                        video_id = video_id.split('=')[-1]
                    # Clean video ID for filename
                    video_id = re.sub(r'[^\w\-_]', '', video_id)
                    default_filename = f"transcript_{video_id}.txt"
                else:
                    default_filename = "transcript.txt"
            except:
                default_filename = "transcript.txt"
            
            filename = input(f"Enter filename ({default_filename}): ").strip()
            if not filename:
                filename = default_filename
            
            # Ensure .txt extension
            if not filename.endswith('.txt'):
                filename += '.txt'
            
            try:
                with open(filename, 'w', encoding='utf-8') as f:
                    f.write(text)
                print(f"✅ Transcription saved to: {filename}")
                return True
            except Exception as e:
                print(f"❌ Error saving file: {e}")
                return False
        elif save in ['n', 'no']:
            return False
        else:
            print("Please enter Y or n")

def check_dependencies():
    """Check if all required dependencies are available"""
    missing = []
    
    try:
        import whisper
    except ImportError:
        missing.append("openai-whisper")
    
    try:
        import yt_dlp
    except ImportError:
        missing.append("yt-dlp")
    
    try:
        import pytube
    except ImportError:
        missing.append("pytube")
    
    try:
        import browser_cookie3
    except ImportError:
        missing.append("browser_cookie3")
    
    if missing:
        print("❌ Missing dependencies:")
        for dep in missing:
            print(f"   - {dep}")
        print("\nPlease install missing dependencies:")
        print(f"pip install {' '.join(missing)}")
        return False
    
    return True

def main():
    """Main interactive function"""
    try:
        # Check dependencies first
        if not check_dependencies():
            sys.exit(1)
        
        # Get user input
        url, use_cookies, language, model_size = get_user_input()
        
        print("\n" + "=" * 50)
        print("PROCESSING VIDEO")
        print("=" * 50)
        print(f"URL: {url}")
        print(f"Language: {language}")
        print(f"Model: {model_size}")
        print(f"Use cookies: {'Yes' if use_cookies else 'No'}")
        print()
        
        # Get Chrome cookies if requested
        cookies = None
        if use_cookies:
            cookies = get_chrome_cookies()
            if not cookies:
                print("⚠️  Warning: Could not extract cookies. Some videos may not be accessible.")
                print()
        
        # Validate URL
        print("🔍 Validating URL...")
        if not is_valid_url(url):
            raise Exception("Invalid URL format")
        
        # Download audio
        print("📥 Downloading audio...")
        audio_file = download_and_convert_to_mp3(url, cookies)
        print("✅ Audio downloaded successfully")
        
        # Transcribe
        print("🎯 Starting transcription...")
        transcription = transcribe_audio(audio_file, model_size, language)
        
        # Display results
        print("\n" + "=" * 50)
        print("TRANSCRIPTION COMPLETE")
        print("=" * 50)
        print(transcription)
        print("\n" + "=" * 50)
        
        # Ask to save
        save_transcription(transcription, url)
        
        print("\n✅ Process completed successfully!")
        
    except KeyboardInterrupt:
        print("\n\n⚠️  Process interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Error: {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    print("🚀 Starting Video Transcription Tool...")
    main()