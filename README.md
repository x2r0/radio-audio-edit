# Radio Show Editor (Web)

This project extends a basic Flask web application to **asynchronously** process audio edits in the background. Users can:

1. **Upload** audio files (MP3/WAV/FLAC).  
2. **Select** editing parameters (silence threshold, target LUFS, jingles).  
3. **Enqueue** multiple jobs for processing.  
4. **Scale** with multiple worker threads for parallel processing.  
5. **Cancel** jobs if needed (either before they start or mid-process).  
6. **Monitor** real-time status (queued, processing, done, or error) on the home page.

---

## Features

- **Async Processing**: Jobs are queued, processed by worker threads in the background.  
- **No Blocking**: The user is immediately returned to the main page after creating a job.  
- **Scalable**: You can configure any number of worker threads.  
- **Cancel Support**: If a job is queued or even mid-processing, you can set it to “canceled.” The worker will skip or abort further steps.  
- **Status Polling**: The front end periodically calls `/status` to show real-time job updates.  
- **Logging**: Each worker logs which job it picks up, any errors, etc.

---

## Requirements

1. **Python 3.7+**  
2. **ffmpeg** installed on your system  
   - macOS: `brew install ffmpeg`  
   - Linux (Debian/Ubuntu): `sudo apt-get install ffmpeg`  
   - Windows: [Download](https://ffmpeg.org/download.html) and add its `bin` directory to `PATH`  
3. **Python Packages**  
   ```bash
   pip install flask pydub pyloudnorm numpy
   ```

---

## Folder Structure (example):

```
web_radio_editor/
├─ jingles/
│   └─ (at least two jingle files)
├─ uploads/
│   └─ (user-uploaded audio)
├─ edited/
│   └─ (final processed audio)
├─ templates/
│   ├─ index.html        # main page (job listing & status polling)
│   ├─ edit_form.html    # form for editing parameters
└─ web_rae.py            # Flask application + worker code
```

---

## Usage

1. Set up your environment (install dependencies, ensure ffmpeg is on `PATH`).  
2. Place at least two jingle files in `jingles/`.  
3. Run:  
   ```bash
   python web_rae.py
   ```  
4. Open your browser to [http://127.0.0.1:5000/](http://127.0.0.1:5000/).  
5. Upload some audio files to the `uploads/` folder via the web interface.  
6. For each file, click **"Edit"** to configure:  
   - **Silence Threshold** (in dBFS, e.g., `-50`)  
   - **Target LUFS** (e.g., `-12` or `-16`)  
   - **Intro/Outro jingle** (pick a specific file or select “RANDOM”)  
7. Queue the job. It appears in the **Job Queue Status** table with state **queued → processing → done**. If an error occurs, it shows **error** with a message.  
8. Download the final MP3 under **"Edited (Processed) Files"** or from the status table.  
9. Optionally, **cancel a job** if it’s queued or in progress.  

---

# Radio Show Editor (CLI)

This repository contains a Python script that automates the editing of radio shows or similar audio files. The script performs:

1. **Silence Removal**  
   - Automatically trims silence at the start and end of each track.

2. **Accurate Loudness Normalization**  
   - Uses [pyloudnorm](https://github.com/csteinmetz1/pyloudnorm) (ITU-R BS.1770) to measure LUFS, **correctly scaled** to \[-1.0, 1.0\], ensuring realistic readings (e.g., -20 LUFS, -12 LUFS, etc.) rather than extreme or incorrect values.

3. **Peak-Safe Adjustment**  
   - Ensures no sample exceeds 0 dBFS (digital clipping). If peaks are too high, the script automatically scales the file down.

4. **Random Jingle Insertion**  
   - Selects two jingles from the `jingles` folder (intro + outro) and appends them to the processed audio.

5. **Logging & Monitoring**  
   - Logs every step (`INFO`, `DEBUG`, `ERROR`) for transparency.

---

## Features

- **Automated Workflow**: Minimal user intervention needed.  
- **LUFS-Based Normalization**: Matches professional broadcast or podcast standards (default -12 LUFS).  
- **Clipping Prevention**: Dynamically reduces gain if peaks exceed 0 dBFS.  
- **Configurable Thresholds**: Customize silence detection, loudness target, MP3 bitrate, etc.  
- **Extensive Logging**: Uses Python’s `logging` to provide high-level progress and debug details.

---

## Prerequisites

- **Python 3.7+**  
- **[ffmpeg](https://ffmpeg.org/)** (or avconv) in your system’s PATH (pydub backend).  
- **Python Libraries**:  
  - [pydub](https://github.com/jiaaro/pydub)  
  - [numpy](https://numpy.org/)  
  - [pyloudnorm](https://github.com/csteinmetz1/pyloudnorm)

Install dependencies (example using pip):

```bash
pip install pydub pyloudnorm numpy
```

For ffmpeg:

- **macOS**: `brew install ffmpeg`  
- **Windows**: Download from [ffmpeg.org](https://ffmpeg.org/) and add its `bin` folder to your `PATH`.  
- **Linux**:  
  ```bash
  sudo apt-get update && sudo apt-get install ffmpeg
  ```

### Quick Start

Clone or Download this repository:

```bash
git clone https://github.com/YourUsername/radio-show-editor.git
cd radio-show-editor
```

Or download and unzip manually.

#### Check Folder Structure:

```
radio-show-editor/
├─ input/
│   └─ (your raw .mp3/.wav/.flac files)
├─ jingles/
│   └─ (at least two jingle files: jingle1.mp3, jingle2.wav, etc.)
├─ output/        # will be auto-created if missing
└─ rae.py         # the main script
```

#### Run the Script:

```bash
python rae.py
```

The script will process each valid audio file in `input/`, trim silence, normalize loudness, insert jingles, and export to `output/`.

#### Check Logs:

The terminal output will show info-level logs, e.g.:

```
2025-01-29 14:47:47 [INFO] Processing file: MyShow.wav
2025-01-29 14:47:47 [INFO] Trimming silence using threshold of -50.0 dBFS...
2025-01-29 14:47:48 [INFO] Current loudness: -23.45 LUFS. Target: -12.00 LUFS.
2025-01-29 14:47:48 [WARNING] Peak exceeded 0 dBFS (1.054). Scaling down by 0.949...
2025-01-29 14:47:49 [INFO] Exported edited file to: output/MyShow_edited.mp3
```

### Folder Structure

Recommended default organization:

```
radio-show-editor/
├─ input/
│   └─ show1.wav
│   └─ show2.mp3
├─ jingles/
│   └─ jingle1.mp3
│   └─ jingle2.wav
├─ output/
├─ rae.py
└─ README.md
```

- `input/`: Your unedited radio shows or podcasts.  
- `jingles/`: A collection of jingle files. Must have at least two files for intro/outro.  
- `output/`: The processed/normalized results.  
- `rae.py`: The main Python script.  
- `README.md`: This documentation.  

### Configuration

#### Silence Detection

```python
silence_threshold=-50.0  # in the trim_silence() function
```

Adjust if your recordings have less “dead air” or more background noise. For instance, `-40 dBFS` or `-60 dBFS` might fit better.

#### Target LUFS

```python
target_lufs=-12.0  # in the loudness_normalize() function
```

Common podcast standards range from `-16` to `-18 LUFS`. Radio can vary; `-12 LUFS` is fairly loud.

#### Peak Safety

The script automatically scales down audio if the peak exceeds `1.0` (0 dBFS). No extra config needed unless you want additional margin (e.g., `-1 dBFS`). You could adjust:

```python
scale_factor = 0.99 / peak_amplitude
```

to leave `0.99` as headroom, for instance.

#### Output Format

```python
final_audio.export(..., format="mp3", bitrate="192k")
```

Adjust to WAV or higher MP3 bitrate as needed.

#### Logging Level

By default, `logging.INFO`. Change to `logging.DEBUG` in `logging.basicConfig()` for more verbose output.

---

## Troubleshooting

### FileNotFoundError

- Ensure you have the correct paths for `input/`, `jingles/`, and `output/`.  
- If the script can’t find jingles, double-check spelling and directory location.  

### Strange Loudness Measurements

- This script handles scaling to `−1.0..1.0` before `pyloudnorm` analysis.  
- If you still see extreme values (e.g., `+60 LUFS`), confirm your audio truly isn’t corrupt and that `pydub + ffmpeg` are installed correctly.  

### Audio Clipping / Distortion

- The script includes a peak check. If you still hear distortion, it might be in the original recording. Consider using compression or a limiter.  

### Performance

- Normalizing long files can be CPU-intensive. If you have huge WAV files, ensure you have enough RAM and time for the process.  

### No Jingle Selected

- Must have two or more jingle files in `jingles/` or the script will exit.  

---

## Contributing

- **Issues**: If you find a bug or have a feature request, open an issue on GitHub.  
- **Pull Requests**: Fork the repo, create a new branch, commit your changes, and open a pull request.  
- **Development**: We welcome any improvements—such as compression, multi-pass normalization, or metadata handling.  

## License

This project is licensed under the MIT License.

