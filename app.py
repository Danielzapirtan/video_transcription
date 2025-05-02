import gradio as gr
import whisper
import yt_dlp
import os
import time

# Load the Whisper model
def load_model(model_name="small"):
    return whisper.load_model(model_name)

model = load_model()

# Function to download video and transcribe
def transcribe_youtube(url, model_name="small", language="en"):
    start_time = time.time()
    
    # Download video using yt-dlp
    ydl_opts = {
        'format': 'bestaudio/best',
        'outtmpl': 'temp_audio.%(ext)s',
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '192',
        }],
    }
    
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([url])

    # Find the downloaded file
    audio_file = next((f for f in os.listdir() if f.startswith("temp_audio")), None)
    
    if not audio_file:
        return "Error: No audio file found.", "", None

    # Transcribe using Whisper
    model = load_model(model_name)
    result = model.transcribe(audio_file, language=language)

    # Cleanup
    os.remove(audio_file)

    elapsed_time = time.time() - start_time
    transcript = result["text"]

    # Save transcript to file
    transcript_filename = "transcription.txt"
    with open(transcript_filename, "w", encoding="utf-8") as f:
        f.write(transcript)

    return transcript, elapsed_time, transcript_filename

# Gradio UI
with gr.Blocks() as demo:
    gr.Markdown("## YouTube Video Transcription App")
    
    url_input = gr.Textbox(label="YouTube URL", placeholder="Enter a YouTube video URL (supports mobile URLs)")
    model_selection = gr.Dropdown(choices=["tiny", "small", "medium", "large"], label="Model Size", value="small")
    language_selection = gr.Textbox(label="Language (optional)", placeholder="Enter language code (e.g., 'en')")
    
    transcribe_button = gr.Button("Transcribe")
    output_text = gr.Textbox(label="Transcribed Text", interactive=False)
    timer_text = gr.Textbox(label="Processing Time (seconds)", interactive=False)
    download_button = gr.File(label="Download Transcript")

    transcribe_button.click(
        fn=transcribe_youtube,
        inputs=[url_input, model_selection, language_selection],
        outputs=[output_text, timer_text, download_button]
    )

demo.launch()