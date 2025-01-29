import os
import random
import numpy as np
import pyloudnorm as pyln
from pydub import AudioSegment
from pydub.silence import detect_leading_silence

def trim_silence(audio, silence_threshold=-50.0):
    """
    Trims silence from the start and end of an AudioSegment based on dBFS threshold.
    """
    start_trim = detect_leading_silence(audio, silence_threshold=silence_threshold)
    reversed_audio = audio.reverse()
    end_trim = detect_leading_silence(reversed_audio, silence_threshold=silence_threshold)

    duration = len(audio)
    trimmed_audio = audio[start_trim:duration - end_trim]
    return trimmed_audio

def loudness_normalize(audio_segment, target_lufs=-12.0):
    """
    Perform ITU/EBU R128 loudness normalization to a target LUFS.

    :param audio_segment: pydub AudioSegment to process
    :param target_lufs: Desired integrated loudness (in LUFS)
    :return: A new pydub AudioSegment normalized to the target LUFS
    """

    # Convert pydub AudioSegment to a float32 numpy array
    samples = np.array(audio_segment.get_array_of_samples()).astype(np.float32)
    sample_rate = audio_segment.frame_rate
    channels = audio_segment.channels

    # If stereo (2 channels), reshape [samples] to [frame, channels]
    # e.g., shape (num_frames, 2)
    if channels > 1:
        samples = samples.reshape((-1, channels))

    # Create a BS.1770 meter
    meter = pyln.Meter(sample_rate)  # EBU R128 meter

    # Measure integrated loudness
    loudness = meter.integrated_loudness(samples)
    # Calculate the gain (as a float multiplier)
    # Instead of apply_gain in dB, pyloudnorm does the sample-level scaling
    # under the hood with normalize.loudness().
    loudness_normalized_samples = pyln.normalize.loudness(
        samples, loudness, target_lufs
    )

    # Convert float samples back to int16 for pydub (most common bit depth)
    if channels > 1:
        # Reshape back to a single dimension
        loudness_normalized_samples = loudness_normalized_samples.reshape(-1)
    loudness_normalized_samples = (loudness_normalized_samples * 32767.0).astype(np.int16)

    # Spawn a new AudioSegment with normalized samples
    normalized_segment = audio_segment._spawn(
        loudness_normalized_samples.tobytes(),
        overrides={
            "frame_rate": sample_rate,
            "channels": channels,
            "sample_width": 2  # 16-bit audio
        }
    )

    return normalized_segment

def main():
    input_folder = "input"
    output_folder = "output"
    jingle_folder = "jingles"

    os.makedirs(output_folder, exist_ok=True)

    jingle_files = [
        f for f in os.listdir(jingle_folder)
        if f.lower().endswith(('.mp3', '.wav', '.flac'))
    ]
    if len(jingle_files) < 2:
        print("ERROR: Need at least 2 jingle files for beginning and end.")
        return

    for filename in os.listdir(input_folder):
        if not filename.lower().endswith(('.mp3', '.wav', '.flac')):
            continue

        input_path = os.path.join(input_folder, filename)
        audio = AudioSegment.from_file(input_path)

        # 1. Trim Silence
        trimmed_audio = trim_silence(audio, silence_threshold=-50.0)

        # 2. Loudness Normalization to -12 LUFS
        normalized_audio = loudness_normalize(trimmed_audio, target_lufs=-12.0)

        # 3. Randomly choose jingles
        jingle_begin_file = random.choice(jingle_files)
        jingle_end_file = random.choice(jingle_files)
        jingle_begin = AudioSegment.from_file(os.path.join(jingle_folder, jingle_begin_file))
        jingle_end = AudioSegment.from_file(os.path.join(jingle_folder, jingle_end_file))

        # 4. Combine jingle + main show + jingle
        final_audio = jingle_begin + normalized_audio + jingle_end

        # 5. Export
        output_filename = os.path.splitext(filename)[0] + "_edited_lufs.mp3"
        output_path = os.path.join(output_folder, output_filename)
        final_audio.export(output_path, format="mp3", bitrate="192k")

        print(f"Processed and saved: {output_path}")

if __name__ == "__main__":
    main()
