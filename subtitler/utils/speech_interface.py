import os
from google.cloud import speech, storage
import ffmpeg
from subtitler.utils.VTT import *

def transcribe_model_selection(speech_file="", model="", sample_rate = 0) -> list[Line]:
    # """Transcribe the given audio file synchronously with
    # the selected model."""
    
    client = speech.SpeechClient()
    
    audio = speech.RecognitionAudio(uri=speech_file)

    config = speech.RecognitionConfig(
        encoding=speech.RecognitionConfig.AudioEncoding.FLAC,
        sample_rate_hertz = sample_rate,
        language_code="en-US",
        model = "default" if not model else model,
        enable_word_time_offsets=True,
        enable_automatic_punctuation=True
    )

    operation = client.long_running_recognize(config=config, audio=audio)
    
    response = operation.result()

    return response

def process_results(response):
    lines = []
    for result in response.results:
        #get the highest possible alernative
        alternative = result.alternatives[0]
        #if empty next!
        if not alternative.transcript:
            continue
        
        words = []
        
        for i in range(len(alternative.words)):
            wordInfo = alternative.words[i]
            word = wordInfo.word
            nextWord = alternative.words[i+1].word if i < len(alternative.words)-1 else ""
            
            if len(words) == 0:
                line_count = 0
                start_time = round(wordInfo.start_time.seconds + wordInfo.start_time.microseconds / 1000 / 1000, 3)
                num_chars = 0

            words.append(word)
            num_chars += len(word)
        
            if num_chars + len(nextWord) + len(words)-1 > MAX_CHARS:
                line_count +=1
                num_chars = 0

            if line_count == 2 or word[-1] == "." or i == len(alternative.words)-1:
                end_time = round(wordInfo.end_time.seconds + wordInfo.end_time.microseconds / 1000 /1000,3)
                text = " ".join(words)
                line = Line(create_text(text), start_time, end_time)
                lines.append(line)
                words = []  

    return lines

def process_video_and_audio(filepath:str) -> str:
    """extract audio and thumbnail from video."""
    try:
        dir = os.path.dirname(filepath)
        filename = os.path.splitext(os.path.basename(filepath))[0]
        flac_filepath = os.path.join(dir, f"{filename}.flac")
        poster_filepath = os.path.join(dir, f"{filename}-thumb.png")
        (
            ffmpeg
            .input(filepath, ss=2)
            .filter('select', 'gt(scene,.2)')
            .filter('scale', 640, -2)
            .output(poster_filepath, vframes=1)
            .overwrite_output()
            .run(quiet=True)
        )
        (
            ffmpeg
            .input(filepath)
            .output( flac_filepath, vn=None, bits_per_raw_sample='16', acodec='flac', ac=1, ar='44100')
            .overwrite_output()
            .run(quiet=True)
        )
        return flac_filepath

    except ffmpeg.Error as err:
        print(err.stderr)
        raise


def video_info(filepath):
    """Get info about the video."""
    try:
        probe = ffmpeg.probe(filepath)
    except ffmpeg.Error as e:
        print(e.stderr)
        return None

    video_stream = next((stream for stream in probe['streams'] if stream['codec_type'] == 'video'), None)
    return video_stream

def send_to_bucket(bucket_name, source_file_name, destination_blob_name):
    """Uploads a file to the bucket."""

    storage_client = storage.Client()
    bucket = storage_client.bucket(bucket_name)
    blob = bucket.blob(destination_blob_name)

    blob.upload_from_filename(source_file_name)