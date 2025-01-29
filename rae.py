import os
import random
from pydub import AudioSegment
from pydub.silence import detect_leading_silence, detect_nonsilent
import requests

# Optional: If you need to download files from a server, use requests
def download_file(url, output_path):
    """
    Downloads a file from a URL and saves it to output_path.
    """
    response = requests.get(url, stream=True)
    response.raise_for_status()
    with open(output_path, 'wb') as f:
        for chunk in response.iter_content(chunk_size=8192):
            f.write(chunk)

def trim_silence(audio, silence_threshold=-50.0, padding=500):
    """
    Trims silence from the start and end of an AudioSegment.
    - silence_thresh: dBFS threshold below which audio is considered silent
    - padding: the amount of non-silent audio (in ms) to keep at the edges
    """
    # Detect silence at start
    start_trim = detect_leading_silence(audio, silence_threshold=silence_threshold)
    # Detect silence at end (reverse the audio)
    reversed_audio = audio.reverse()
    end_trim = detect_leading_silence(reversed_audio, silence_threshold=silence_threshold)

    duration = len(audio)
    trimmed_audio = audio[start_trim:duration - end_trim]

    # Optional: add padding if you want to ensure no audio is accidentally clipped
    return trimmed_audio

def normalize_audio(audio, target_dBFS=-20.0):
    """
    Normalizes the audio to a target dBFS (loudness).
    """
    change_in_dBFS = target_dBFS - audio.dBFS
    return audio.apply_gain(change_in_dBFS)

def main():
    # --- 1. Download/Load the Audio File ---
    # If your audio files are already in "input/" folder, skip downloading.
    # Otherwise, to download:
    # url = "http://example.com/radio_show.mp3"
    # local_file_path = "input/radio_show.mp3"
    # download_file(url, local_file_path)

    input_folder = "input"
    jingle_folder = "jingles"
    output_folder = "output"

    # Create output folder if it doesn't exist
    os.makedirs(output_folder, exist_ok=True)

    # --- 2. Manage Jingles ---
    # Collect all jingle filenames in a list
    jingle_files = [f for f in os.listdir(jingle_folder) 
                    if f.lower().endswith(('.mp3', '.wav'))]

    # --- 3. Process Each Radio Show File ---
    for filename in os.listdir(input_folder):
        if not filename.lower().endswith(('.mp3', '.wav', '.flac')):
            continue  # skip non-audio files
        input_path = os.path.join(input_folder, filename)
        print(f"Processing {filename}...")

        # Load the audio file
        audio = AudioSegment.from_file(input_path)

        # --- 4. Trim Silence at Start and End ---
        trimmed_audio = trim_silence(audio, silence_threshold=-50.0)

        # --- 5. Normalize Volume ---
        normalized_audio = normalize_audio(trimmed_audio, target_dBFS=-20.0)

        # --- 6. Append Jingles ---
        # Randomly choose one jingle for the beginning and one for the end
        if len(jingle_files) < 2:
            print("ERROR: You need at least 2 jingle files for this logic (beginning and end).")
            return

        # If you want purely random:
        jingle_begin_file = random.choice(jingle_files)
        jingle_end_file = random.choice(jingle_files)

        # Or to avoid the same jingle at the end, you can remove the chosen begin jingle from the list temporarily:
        # jingle_begin_file = random.choice(jingle_files)
        # jingle_files_temp = [jf for jf in jingle_files if jf != jingle_begin_file]
        # jingle_end_file = random.choice(jingle_files_temp)

        jingle_begin = AudioSegment.from_file(os.path.join(jingle_folder, jingle_begin_file))
        jingle_end = AudioSegment.from_file(os.path.join(jingle_folder, jingle_end_file))

        # Concatenate: beginning jingle + main audio + end jingle
        final_audio = jingle_begin + normalized_audio + jingle_end

        # --- 7. Export the Edited File ---
        # Choose your desired output format (e.g., mp3, wav)
        output_filename = os.path.splitext(filename)[0] + "_edited.mp3"
        output_path = os.path.join(output_folder, output_filename)
        final_audio.export(output_path, format="mp3", bitrate="192k")

        print(f"Saved edited file: {output_path}")

if __name__ == "__main__":
    main()
