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

# Global variable to store the current model
current_model = None
current_model_size = None

def load_whisper_model(model_size):
    """Load or switch the Whisper model"""
    global current_model, current_model_size
    
    # Only load if different from current model
    if current_model is None or current_model_size != model_size:
        print(f"Loading Whisper model: {model_size}")
        current_model = whisper.load_model(model_size)
        current_model_size = model_size
    
    return current_model

def get_chrome_cookies():
    """Extract cookies from Chrome browser"""
    try:
        print("Extracting Chrome cookies...")
        cookies = browser_cookie3.chrome(domain_name=None)
        cookie_list = list(cookies)
        print(f"Successfully extracted {len(cookie_list)} cookies from Chrome")
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
        
        output_file = "audio.mp3"
        print(f"Downloading with pytube...")
        
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
        
        # Add cookies if available
        if cookies:
            print("Using Chrome cookies for authentication...")
            # Create a temporary cookie file
            import tempfile
            import json
            cookie_file = tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False)
            
            # Convert cookies to Netscape format
            for cookie in cookies:
                if hasattr(cookie, 'domain') and hasattr(cookie, 'name'):
                    cookie_line = f"{cookie.domain}\tTRUE\t{cookie.path}\t{'TRUE' if cookie.secure else 'FALSE'}\t{cookie.expires or 0}\t{cookie.name}\t{cookie.value}\n"
                    cookie_file.write(cookie_line)
            
            cookie_file.close()
            ydl_opts['cookiefile'] = cookie_file.name
        
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
                if "Private video" in str(e):
                    raise Exception("This is a private video (login required)")
                elif "Members-only" in str(e):
                    raise Exception("This is a members-only video")
                elif "This video is not available" in str(e):
                    raise Exception("Video not available in your country or removed")
                else:
                    raise
            finally:
                # Clean up cookie file if it was created
                if cookies and 'cookiefile' in ydl_opts:
                    try:
                        os.unlink(ydl_opts['cookiefile'])
                    except:
                        pass
        
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
                print(f"Pytube failed, trying yt-dlp...")
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
        model = load_whisper_model(model_size)
        
        # Set transcription options based on language selection
        options = {}
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
        language = input("\nEnter language code (ro/en): ").strip().lower()
        if language in ['ro', 'en']:
            break
        else:
            print("Please enter 'ro' for Romanian or 'en' for English")
    
    # Determine model size based on language
    if language == 'en':
        model_size = 'base'
        print(f"\nUsing 'base' model for English")
    else:  # Romanian
        model_size = 'medium'
        print(f"\nUsing 'medium' model for Romanian")
    
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
                    default_filename = f"transcript_{video_id}.txt"
                else:
                    default_filename = "transcript.txt"
            except:
                default_filename = "transcript.txt"
            
            filename = input(f"Enter filename ({default_filename}): ").strip()
            if not filename:
                filename = default_filename
            
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

def main():
    """Main interactive function"""
    try:
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
    
    # Check dependencies
    try:
        import browser_cookie3
    except ImportError:
        print("❌ Missing dependency: browser_cookie3")
        print("Please install: pip install browser_cookie3")
        sys.exit(1)
    
    # Check if yt-dlp is available
    try:
        print("🔄 Checking yt-dlp...")
        with yt_dlp.YoutubeDL({'quiet': True}) as ydl:
            pass
        print("✅ yt-dlp is ready")
    except Exception as e:
        print(f"⚠️  yt-dlp warning: {e}")
    
    print()
    main()