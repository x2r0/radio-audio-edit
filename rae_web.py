import os
import random
import logging
import numpy as np
import pyloudnorm as pyln
import queue
import threading
import time

from flask import (
    Flask, render_template, request, redirect,
    url_for, send_from_directory, jsonify
)
from werkzeug.utils import secure_filename
from pydub import AudioSegment
from pydub.silence import detect_leading_silence

# -------------------------------------------------------------------
# Logging Setup
# -------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,  # or logging.DEBUG for more detail
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

# -------------------------------------------------------------------
# Flask Config
# -------------------------------------------------------------------
app = Flask(__name__)

# Folders
JINGLES_FOLDER = "jingles"
UPLOADS_FOLDER = "uploads"
EDITED_FOLDER = "edited"
os.makedirs(JINGLES_FOLDER, exist_ok=True)
os.makedirs(UPLOADS_FOLDER, exist_ok=True)
os.makedirs(EDITED_FOLDER, exist_ok=True)

# Allowed file extensions
ALLOWED_EXTENSIONS = {'.mp3', '.wav', '.flac'}

def allowed_file(filename):
    ext = os.path.splitext(filename)[1].lower()
    return ext in ALLOWED_EXTENSIONS

# -------------------------------------------------------------------
# Asynchronous Job Handling
# -------------------------------------------------------------------
NUM_WORKERS = 2  # Customize: how many parallel worker threads to run?

job_queue = queue.Queue()
jobs = {}  # job_id -> job dict

def worker_thread(worker_id):
    """
    Background worker that continuously pulls jobs from the queue and processes them.
    """
    while True:
        job = job_queue.get()  # Blocks until a job is available
        if job is None:
            logger.info("Worker %d received stop signal. Exiting.", worker_id)
            job_queue.task_done()
            break

        job_id = job["job_id"]
        logger.info("Worker %d picked up job %s for file %s", worker_id, job_id, job["filename"])

        # If somehow the job was canceled while waiting in the queue, skip immediately
        if job["status"] == "canceled":
            logger.info("Worker %d skipping job %s (already canceled).", worker_id, job_id)
            job_queue.task_done()
            continue

        # Mark as processing
        job["status"] = "processing"
        try:
            process_job(job)
            # If after processing the status is still 'processing', mark done
            if job["status"] == "processing":
                job["status"] = "done"
            logger.info("Worker %d finished job %s with status %s", worker_id, job_id, job["status"])
        except Exception as e:
            job["status"] = "error"
            job["error_message"] = str(e)
            logger.error("Error in job %s: %s", job_id, e)

        job_queue.task_done()

def process_job(job):
    """
    Performs audio editing. If job is canceled mid-process,
    we stop further steps as soon as we detect it.
    """
    job_id = job["job_id"]
    input_path = os.path.join(UPLOADS_FOLDER, job["filename"])

    # Check file existence
    if not os.path.exists(input_path):
        raise FileNotFoundError(f"File not found: {job['filename']}")

    # 1) Load
    if job["status"] == "canceled":  # mid-check
        return
    audio = AudioSegment.from_file(input_path)
    logger.debug("Job %s loaded file: %s ms", job_id, len(audio))

    # 2) Trim Silence
    if job["status"] == "canceled":
        return
    trimmed = trim_silence(audio, silence_threshold=job["silence_thresh"])
    logger.debug("Job %s trimmed to: %s ms", job_id, len(trimmed))

    # 3) Normalize
    if job["status"] == "canceled":
        return
    normalized = loudness_normalize(trimmed, target_lufs=job["target_lufs"])
    logger.debug("Job %s normalized audio length: %s ms", job_id, len(normalized))

    # 4) Append Jingles
    if job["status"] == "canceled":
        return
    jingle_files = [
        f for f in os.listdir(JINGLES_FOLDER)
        if os.path.splitext(f)[1].lower() in ALLOWED_EXTENSIONS
    ]
    if len(jingle_files) < 2:
        raise RuntimeError(f"Need at least 2 jingle files in '{JINGLES_FOLDER}'.")

    intro_seg = pick_jingle(job["intro_jingle"], jingle_files)
    outro_seg = pick_jingle(job["outro_jingle"], jingle_files)
    final_audio = intro_seg + normalized + outro_seg

    # 5) Export
    if job["status"] == "canceled":
        return
    base_name = os.path.splitext(os.path.basename(input_path))[0]
    output_filename = f"{base_name}_edited_{int(time.time())}.mp3"
    output_path = os.path.join(EDITED_FOLDER, output_filename)

    final_audio.export(output_path, format="mp3", bitrate="192k")
    job["output_filename"] = output_filename
    logger.info("Job %s exported to: %s", job_id, output_filename)

def pick_jingle(name, jingle_files):
    """Helper: pick a jingle by name or random if 'RANDOM' or if name not found."""
    if name == "RANDOM":
        chosen = random.choice(jingle_files)
        return AudioSegment.from_file(os.path.join(JINGLES_FOLDER, chosen))
    else:
        path = os.path.join(JINGLES_FOLDER, name)
        if not os.path.exists(path):
            logger.warning("Jingle '%s' not found, picking random instead.", name)
            chosen = random.choice(jingle_files)
            return AudioSegment.from_file(os.path.join(JINGLES_FOLDER, chosen))
        return AudioSegment.from_file(path)

def trim_silence(audio_segment, silence_threshold=-50.0):
    """Simple trim from both ends."""
    start_trim = detect_leading_silence(audio_segment, silence_threshold=silence_threshold)
    reversed_audio = audio_segment.reverse()
    end_trim = detect_leading_silence(reversed_audio, silence_threshold=silence_threshold)
    return audio_segment[start_trim : len(audio_segment) - end_trim]

def loudness_normalize(audio_segment, target_lufs=-12.0):
    """ITU BS.1770 loudness normalization, with peak-safe check."""
    samples_int16 = np.array(audio_segment.get_array_of_samples()).astype(np.float32)
    sample_rate = audio_segment.frame_rate
    channels = audio_segment.channels

    # Reshape if stereo
    if channels > 1:
        samples_int16 = samples_int16.reshape((-1, channels))

    # Scale to [-1..1]
    samples = samples_int16 / 32768.0

    meter = pyln.Meter(sample_rate)
    current_lufs = meter.integrated_loudness(samples)
    gain_samples = pyln.normalize.loudness(samples, current_lufs, target_lufs)

    # Peak safe
    peak = np.max(np.abs(gain_samples))
    if peak > 1.0:
        scale_factor = 1.0 / peak
        gain_samples *= scale_factor

    # Convert back
    if channels > 1:
        gain_samples = gain_samples.reshape(-1)

    out_int16 = (gain_samples * 32767.0).astype(np.int16)
    return audio_segment._spawn(
        data=out_int16.tobytes(),
        overrides={
            "frame_rate": sample_rate,
            "channels": channels,
            "sample_width": 2
        }
    )

# -------------------------------------------------------------------
# Start Multiple Worker Threads
# -------------------------------------------------------------------
worker_threads = []
for i in range(NUM_WORKERS):
    t = threading.Thread(target=worker_thread, args=(i,), daemon=False)
    t.start()
    worker_threads.append(t)

# -------------------------------------------------------------------
# Flask Routes
# -------------------------------------------------------------------
app.config["MAX_CONTENT_LENGTH"] = 1024 * 1024 * 1024  # Example: limit 1GB if needed

@app.route("/")
def index():
    """
    Main page with:
    - Upload form
    - Lists of uploaded & edited files
    - Job statuses
    """
    uploaded_files = sorted(os.listdir(UPLOADS_FOLDER))
    edited_files = sorted(os.listdir(EDITED_FOLDER))
    jingle_files = sorted(os.listdir(JINGLES_FOLDER))
    return render_template(
        "index.html",
        uploaded_files=uploaded_files,
        edited_files=edited_files,
        jingle_files=jingle_files
    )

@app.route("/upload", methods=["POST"])
def upload_file():
    """Handle file uploads."""
    if "file" not in request.files:
        return redirect(url_for("index"))

    file = request.files["file"]
    if file.filename == "":
        return redirect(url_for("index"))

    if allowed_file(file.filename):
        filename = secure_filename(file.filename)
        file.save(os.path.join(UPLOADS_FOLDER, filename))
        logger.info("Uploaded file: %s", filename)
    return redirect(url_for("index"))

@app.route("/edit/<filename>")
def edit_form(filename):
    """
    Display a form for configuring parameters.
    """
    path = os.path.join(UPLOADS_FOLDER, filename)
    if not os.path.exists(path):
        logger.error("File not found: %s", filename)
        return redirect(url_for("index"))

    jingle_files = [
        f for f in os.listdir(JINGLES_FOLDER)
        if os.path.splitext(f)[1].lower() in ALLOWED_EXTENSIONS
    ]
    return render_template("edit_form.html",
                           filename=filename,
                           jingle_files=jingle_files)

@app.route("/process", methods=["POST"])
def process_file():
    """
    Queue a new job with the chosen parameters.
    """
    filename = request.form.get("filename")
    silence_thresh = float(request.form.get("silence_thresh", "-50.0"))
    target_lufs = float(request.form.get("target_lufs", "-12.0"))
    intro_jingle = request.form.get("intro_jingle", "RANDOM")
    outro_jingle = request.form.get("outro_jingle", "RANDOM")

    job_id = f"job_{int(time.time()*1000)}_{random.randint(1000,9999)}"
    job = {
        "job_id": job_id,
        "filename": filename,
        "silence_thresh": silence_thresh,
        "target_lufs": target_lufs,
        "intro_jingle": intro_jingle,
        "outro_jingle": outro_jingle,
        "status": "queued",
        "output_filename": None,
        "error_message": None,
    }
    jobs[job_id] = job
    job_queue.put(job)  # Enqueue

    logger.info("Queued job %s for file %s", job_id, filename)
    return redirect(url_for("index"))

@app.route("/status")
def job_status():
    """
    Returns JSON status of all known jobs, polled by front-end JavaScript.
    """
    all_jobs = []
    for job_id, j in jobs.items():
        all_jobs.append({
            "job_id": j["job_id"],
            "filename": j["filename"],
            "status": j["status"],
            "output_filename": j["output_filename"],
            "error_message": j["error_message"],
        })
    return jsonify(all_jobs)

@app.route("/cancel/<job_id>")
def cancel_job(job_id):
    """
    Sets a job's status to 'canceled' if it hasn't completed.
    If it's in the queue, we'll skip it. If it's mid-processing,
    the process_job function will see the canceled status and abort.
    """
    if job_id in jobs:
        job = jobs[job_id]
        if job["status"] in ["queued", "processing"]:
            job["status"] = "canceled"
            logger.info("Job %s canceled by user.", job_id)
    return redirect(url_for("index"))

@app.route("/download_edited/<filename>")
def download_edited(filename):
    """Download a final edited file."""
    return send_from_directory(EDITED_FOLDER, filename, as_attachment=True)

@app.teardown_appcontext
def shutdown_workers(exception=None):
    """
    Stop the worker threads gracefully if the server shuts down.
    This is optional. Each thread will see None in the queue and exit.
    
    for _ in range(NUM_WORKERS):
        job_queue.put(None)
    for t in worker_threads:
        t.join(timeout=2.0)

    logger.info("All worker threads have been stopped.")
    """

if __name__ == "__main__":
    app.run(debug=True, port=5000)
