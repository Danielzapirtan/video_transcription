import gradio as gr
import tempfile
import os
import time
from pytube import YouTube
import whisper
import subprocess

model = whisper.load_model("base")

def download_youtube_audio(youtube_url):
    yt = YouTube(youtube_url)
    stream = yt.streams.filter(only_audio=True).first()
    temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".mp4")
    stream.download(filename=temp_file.name)
    return temp_file.name

def transcribe_video(video=None, youtube_url=None):
    if not video and not youtube_url:
        return "Please upload a video or provide a YouTube URL.", None, "0.00s"

    start = time.time()

    if youtube_url:
        file_path = download_youtube_audio(youtube_url)
    else:
        file_path = video

    audio_path = tempfile.NamedTemporaryFile(delete=False, suffix=".wav").name
    subprocess.run(["ffmpeg", "-i", file_path, "-ar", "16000", "-ac", "1", audio_path],
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    result = model.transcribe(audio_path)
    transcript = result["text"]

    txt_path = tempfile.NamedTemporaryFile(delete=False, suffix=".txt", mode="w", encoding="utf-8").name
    with open(txt_path, "w", encoding="utf-8") as f:
        f.write(transcript)

    os.remove(audio_path)
    if youtube_url:
        os.remove(file_path)

    elapsed = f"{time.time() - start:.2f}s"
    return transcript, txt_path, elapsed

with gr.Blocks() as demo:
    gr.Markdown("# Video Transcription Tool with Timer and Download")

    with gr.Row():
        video_input = gr.Video(label="Upload Video")
        url_input = gr.Textbox(label="Or Enter YouTube URL")

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

demo.launch()
