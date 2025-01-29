import os
import random
import numpy as np
import pyloudnorm as pyln
import logging
from pydub import AudioSegment
from pydub.silence import detect_leading_silence

# -------------------------------------------------------------------
# Set up logging
# -------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

def trim_silence(audio_segment, silence_threshold=-50.0):
    """
    Trims silence from the start and end of an AudioSegment based on dBFS threshold.

    :param audio_segment: pydub AudioSegment to trim
    :param silence_threshold: dBFS threshold, below which is considered silence
    :return: Trimmed AudioSegment
    """
    logger.info("Trimming silence using threshold of %s dBFS...", silence_threshold)

    start_trim = detect_leading_silence(audio_segment, silence_threshold=silence_threshold)
    logger.debug("Detected %d ms of silence at the start.", start_trim)

    reversed_audio = audio_segment.reverse()
    end_trim = detect_leading_silence(reversed_audio, silence_threshold=silence_threshold)
    logger.debug("Detected %d ms of silence at the end.", end_trim)

    duration = len(audio_segment)
    trimmed_audio = audio_segment[start_trim : duration - end_trim]

    logger.info("Trimmed audio length: %d ms (from %d ms).", len(trimmed_audio), duration)
    return trimmed_audio

def loudness_normalize(audio_segment, target_lufs=-12.0):
    """
    Perform ITU/EBU R128 loudness normalization to a target LUFS, 
    with proper scaling to avoid incorrect measurements, and
    a peak-safe step to prevent clipping.

    :param audio_segment: pydub AudioSegment
    :param target_lufs: Desired integrated loudness (e.g., -12.0)
    :return: A new AudioSegment normalized to near the target LUFS but guaranteed not to exceed 0 dBFS.
    """
    logger.info("Measuring integrated loudness...")

    # Get raw samples as int16 range (-32768..32767), then convert to float32
    samples_int16 = np.array(audio_segment.get_array_of_samples()).astype(np.float32)
    sample_rate = audio_segment.frame_rate
    channels = audio_segment.channels

    # Reshape for multi-channel
    if channels > 1:
        samples_int16 = samples_int16.reshape((-1, channels))

    # --- 1) Scale samples to [-1.0, 1.0] ---
    logger.debug("Scaling samples to [-1.0, 1.0] for pyloudnorm.")
    samples = samples_int16 / 32768.0

    meter = pyln.Meter(sample_rate)  # EBU R128 meter
    current_lufs = meter.integrated_loudness(samples)
    logger.info("Current loudness: %.2f LUFS. Target: %.2f LUFS.", current_lufs, target_lufs)

    # --- 2) Loudness normalization ---
    loudness_normalized = pyln.normalize.loudness(samples, current_lufs, target_lufs)

    # --- 3) Peak-safe check ---
    peak_amplitude = np.max(np.abs(loudness_normalized))
    if peak_amplitude > 1.0:
        scale_factor = 1.0 / peak_amplitude
        loudness_normalized *= scale_factor
        logger.warning(
            "Peak exceeded 0 dBFS (%.3f). Scaling down by %.3f to avoid clipping.",
            peak_amplitude, scale_factor
        )

    # --- 4) Convert back to int16 for pydub ---
    if channels > 1:
        loudness_normalized = loudness_normalized.reshape(-1)

    loudness_normalized_int16 = (loudness_normalized * 32767.0).astype(np.int16)
    logger.debug("Finished normalizing audio (peak-safe).")

    # Create a new AudioSegment with the normalized samples
    normalized_segment = audio_segment._spawn(
        data=loudness_normalized_int16.tobytes(),
        overrides={
            "frame_rate": sample_rate,
            "channels": channels,
            "sample_width": 2,  # 16-bit
        },
    )
    return normalized_segment

def main():
    logger.info("Starting the radio show editing process...")

    # Folders
    input_folder = "input"
    output_folder = "output"
    jingle_folder = "jingles"

    os.makedirs(output_folder, exist_ok=True)

    jingle_files = [
        f for f in os.listdir(jingle_folder)
        if f.lower().endswith(('.mp3', '.wav', '.flac'))
    ]
    if len(jingle_files) < 2:
        logger.error("Not enough jingle files found in '%s'. Need at least 2.", jingle_folder)
        return

    for filename in os.listdir(input_folder):
        if not filename.lower().endswith(('.mp3', '.wav', '.flac')):
            logger.debug("Skipping non-audio file: %s", filename)
            continue

        input_path = os.path.join(input_folder, filename)
        logger.info("Processing file: %s", filename)

        # 1) Load the file
        try:
            audio = AudioSegment.from_file(input_path)
            logger.debug("Loaded audio file: %s ms long", len(audio))
        except Exception as e:
            logger.error("Error loading file %s: %s", filename, e)
            continue

        # 2) Trim silence
        trimmed_audio = trim_silence(audio, silence_threshold=-50.0)

        # 3) Loudness normalization (with correct scaling + peak-safe check)
        normalized_audio = loudness_normalize(trimmed_audio, target_lufs=-12.0)

        # 4) Choose jingles (randomly)
        jingle_begin_file = random.choice(jingle_files)
        jingle_end_file = random.choice(jingle_files)
        logger.info("Selected jingles: begin -> %s, end -> %s", jingle_begin_file, jingle_end_file)

        try:
            jingle_begin = AudioSegment.from_file(os.path.join(jingle_folder, jingle_begin_file))
            jingle_end = AudioSegment.from_file(os.path.join(jingle_folder, jingle_end_file))
        except Exception as e:
            logger.error("Error loading jingle: %s", e)
            continue

        # 5) Combine jingles + main content
        final_audio = jingle_begin + normalized_audio + jingle_end
        logger.info("Final audio length: %d ms", len(final_audio))

        # 6) Export
        output_filename = os.path.splitext(filename)[0] + "_edited_normalized.mp3"
        output_path = os.path.join(output_folder, output_filename)

        try:
            final_audio.export(output_path, format="mp3", bitrate="192k")
            logger.info("Exported edited file to: %s", output_path)
        except Exception as e:
            logger.error("Error exporting file %s: %s", output_filename, e)

    logger.info("All done. Process completed.")

if __name__ == "__main__":
    main()
