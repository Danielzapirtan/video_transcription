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
    youtube_regex = (
        r'(https?://)?(www\.|m\.)?'
        r'(youtube|youtu|youtube-nocookie)\.(com|be)/'
        r'(watch\?v=|embed/|v/|.+\?v=)?([^&=%\?]{11})')
    if re.match(youtube_regex, url):
        return True
    if "youtu.be/" in url:
        return True
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
        youtube_url = youtube_url.strip() if youtube_url else None

        if not youtube_url and not video:
            return "Please upload a video or provide a YouTube URL.", None, "0.00s"

        if youtube_url and not is_valid_youtube_url(youtube_url):
            return ("Invalid YouTube URL. Supported formats:\n"
                    "• https://www.youtube.com/watch?v=VIDEO_ID\n"
                    "• https://m.youtube.com/watch?v=VIDEO_ID\n"
                    "• https://youtu.be/VIDEO_ID\n"
                    "• https://m.youtu.be/VIDEO_ID