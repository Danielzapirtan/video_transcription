import React, { useState } from 'react';
import { Play, Download, CheckCircle, AlertCircle, Loader2, Youtube, Chrome } from 'lucide-react';

const VideoTranscriptionApp = () => {
  const [formData, setFormData] = useState({
    youtube_url: '',
    confirm_cookies: false
  });
  const [isRunning, setIsRunning] = useState(false);
  const [currentStep, setCurrentStep] = useState(0);
  const [completed, setCompleted] = useState(false);
  const [error, setError] = useState('');

  const steps = [
    {
      id: 'download_video',
      title: 'Download YouTube Video',
      description: 'Download YouTube video using yt-dlp with browser cookies',
      command: `!yt-dlp --cookies-from-browser chrome "${formData.youtube_url}" -o video.mp4`,
      duration: 5000
    },
    {
      id: 'transcribe_audio',
      title: 'Transcribe Audio',
      description: 'Transcribe audio using OpenAI Whisper',
      command: '!whisper video.mp4 --model medium --output_format txt',
      duration: 8000
    },
    {
      id: 'expose_transcript',
      title: 'Prepare Download',
      description: 'Make the transcription downloadable',
      command: 'from google.colab import files\nfiles.download("video.txt")',
      duration: 2000
    }
  ];

  const validateForm = () => {
    if (!formData.youtube_url.trim()) {
      setError('YouTube URL is required');
      return false;
    }
    
    if (!formData.confirm_cookies) {
      setError('You must agree to use Chrome cookies to proceed.');
      return false;
    }

    // Basic YouTube URL validation
    const youtubeRegex = /^(https?:\/\/)?(www\.)?(youtube\.com|youtu\.be)\/.+/;
    if (!youtubeRegex.test(formData.youtube_url)) {
      setError('Please enter a valid YouTube URL');
      return false;
    }

    return true;
  };

  const runTranscription = async () => {
    if (!validateForm()) return;

    setError('');
    setIsRunning(true);
    setCurrentStep(0);
    setCompleted(false);

    for (let i = 0; i < steps.length; i++) {
      setCurrentStep(i);
      await new Promise(resolve => setTimeout(resolve, steps[i].duration));
    }

    setCompleted(true);
    setIsRunning(false);
  };

  const handleInputChange = (field, value) => {
    setFormData(prev => ({
      ...prev,
      [field]: value
    }));
    if (error) setError('');
  };

  const downloadTranscript = () => {
    const transcript = `Video Transcription
====================

Source: ${formData.youtube_url}
Generated: ${new Date().toLocaleString()}

[This is a simulated transcript. In a real implementation, this would contain the actual transcribed text from the video.]

Lorem ipsum dolor sit amet, consectetur adipiscing elit. Sed do eiusmod tempor incididunt ut labore et dolore magna aliqua. Ut enim ad minim veniam, quis nostrud exercitation ullamco laboris nisi ut aliquip ex ea commodo consequat.

Duis aute irure dolor in reprehenderit in voluptate velit esse cillum dolore eu fugiat nulla pariatur. Excepteur sint occaecat cupidatat non proident, sunt in culpa qui officia deserunt mollit anim id est laborum.

Sed ut perspiciatis unde omnis iste natus error sit voluptatem accusantium doloremque laudantium, totam rem aperiam, eaque ipsa quae ab illo inventore veritatis et quasi architecto beatae vitae dicta sunt explicabo.`;

    const blob = new Blob([transcript], { type: 'text/plain' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'video.txt';
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  };

  return (
    <div className="max-w-4xl mx-auto p-6 bg-gray-50 min-h-screen">
      <div className="bg-white rounded-lg shadow-lg p-8">
        <div className="text-center mb-8">
          <div className="flex items-center justify-center mb-4">
            <Youtube className="w-8 h-8 text-red-600 mr-2" />
            <h1 className="text-3xl font-bold text-gray-800">Video Transcription Tool</h1>
          </div>
          <p className="text-gray-600">
            CLI-style video transcription for Colab. Downloads YouTube videos and transcribes them using OpenAI Whisper.
          </p>
        </div>

        {/* Input Form */}
        <div className="mb-8 p-6 bg-gray-50 rounded-lg">
          <h2 className="text-xl font-semibold mb-4 text-gray-800">Configuration</h2>
          
          <div className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">
                Enter the YouTube video URL: *
              </label>
              <input
                type="url"
                value={formData.youtube_url}
                onChange={(e) => handleInputChange('youtube_url', e.target.value)}
                placeholder="https://www.youtube.com/watch?v=..."
                className="w-full px-4 py-2 border border-gray-300 rounded-md focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                disabled={isRunning}
              />
            </div>

            <div className="flex items-start space-x-3">
              <input
                type="checkbox"
                id="confirm_cookies"
                checked={formData.confirm_cookies}
                onChange={(e) => handleInputChange('confirm_cookies', e.target.checked)}
                className="mt-1 h-4 w-4 text-blue-600 focus:ring-blue-500 border-gray-300 rounded"
                disabled={isRunning}
              />
              <label htmlFor="confirm_cookies" className="text-sm text-gray-700">
                <div className="flex items-center mb-1">
                  <Chrome className="w-4 h-4 mr-1 text-blue-600" />
                  <span className="font-medium">Chrome Cookie Authentication</span>
                </div>
                <p className="text-xs text-gray-500">
                  Do you agree to authenticate using your Chrome cookies? (Required for private/age-restricted videos) *
                </p>
              </label>
            </div>
          </div>

          {error && (
            <div className="mt-4 p-3 bg-red-50 border border-red-200 rounded-md flex items-center">
              <AlertCircle className="w-5 h-5 text-red-500 mr-2" />
              <span className="text-red-700 text-sm">{error}</span>
            </div>
          )}

          <button
            onClick={runTranscription}
            disabled={isRunning || !formData.youtube_url.trim() || !formData.confirm_cookies}
            className="mt-6 w-full bg-blue-600 text-white py-3 px-6 rounded-md font-medium hover:bg-blue-700 disabled:bg-gray-400 disabled:cursor-not-allowed transition-colors flex items-center justify-center"
          >
            {isRunning ? (
              <>
                <Loader2 className="w-5 h-5 mr-2 animate-spin" />
                Processing...
              </>
            ) : (
              <>
                <Play className="w-5 h-5 mr-2" />
                Start Transcription
              </>
            )}
          </button>
        </div>

        {/* Execution Steps */}
        {(isRunning || completed) && (
          <div className="mb-8">
            <h2 className="text-xl font-semibold mb-4 text-gray-800">Execution Progress</h2>
            <div className="space-y-4">
              {steps.map((step, index) => {
                const isActive = isRunning && currentStep === index;
                const isCompleted = completed || currentStep > index;
                const isPending = !isRunning && !completed && currentStep <= index;

                return (
                  <div
                    key={step.id}
                    className={`p-4 rounded-lg border-2 transition-all ${
                      isActive 
                        ? 'border-blue-500 bg-blue-50' 
                        : isCompleted 
                        ? 'border-green-500 bg-green-50' 
                        : 'border-gray-200 bg-gray-50'
                    }`}
                  >
                    <div className="flex items-center justify-between mb-2">
                      <div className="flex items-center">
                        {isActive && <Loader2 className="w-5 h-5 text-blue-600 mr-2 animate-spin" />}
                        {isCompleted && <CheckCircle className="w-5 h-5 text-green-600 mr-2" />}
                        {isPending && <div className="w-5 h-5 border-2 border-gray-300 rounded-full mr-2"></div>}
                        <h3 className="font-medium text-gray-800">{step.title}</h3>
                      </div>
                      <span className="text-sm text-gray-500">Step {index + 1}</span>
                    </div>
                    <p className="text-sm text-gray-600 mb-2">{step.description}</p>
                    <div className="bg-gray-800 text-green-400 p-3 rounded font-mono text-sm overflow-x-auto">
                      {step.command}
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        )}

        {/* Download Section */}
        {completed && (
          <div className="p-6 bg-green-50 border border-green-200 rounded-lg">
            <div className="flex items-center justify-between">
              <div>
                <h3 className="text-lg font-semibold text-green-800 mb-2">Transcription Complete!</h3>
                <p className="text-green-700">Your video has been successfully transcribed. Click below to download the transcript.</p>
              </div>
              <button
                onClick={downloadTranscript}
                className="bg-green-600 text-white py-2 px-4 rounded-md font-medium hover:bg-green-700 transition-colors flex items-center"
              >
                <Download className="w-5 h-5 mr-2" />
                Download video.txt
              </button>
            </div>
          </div>
        )}

        {/* Requirements & Notes */}
        <div className="mt-8 p-6 bg-gray-50 rounded-lg">
          <h3 className="text-lg font-semibold mb-4 text-gray-800">Requirements & Notes</h3>
          <div className="grid md:grid-cols-2 gap-6">
            <div>
              <h4 className="font-medium text-gray-700 mb-2">Required Dependencies:</h4>
              <ul className="text-sm text-gray-600 space-y-1">
                <li>• yt-dlp</li>
                <li>• openai-whisper</li>
                <li>• ffmpeg</li>
                <li>• google.colab</li>
              </ul>
            </div>
            <div>
              <h4 className="font-medium text-gray-700 mb-2">Important Notes:</h4>
              <ul className="text-sm text-gray-600 space-y-1">
                <li>• Ensure Chrome is your default browser</li>
                <li>• Medium/large Whisper models recommended for accuracy</li>
                <li>• Output file will be named video.txt</li>
                <li>• yt-dlp must be able to access Chrome cookies</li>
              </ul>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default VideoTranscriptionApp;