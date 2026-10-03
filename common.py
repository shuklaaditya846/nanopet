"""Config, clock bootstrap and the microphone recorder (shared by the
demos and the pet)."""
import datetime
import email.utils
import os
import signal
import subprocess
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
# nanopet's own config first; reuse ptt-assistant's key if that's all there is
CONFIG_PATHS = ["/etc/nanopet.conf", os.path.join(HERE, "nanopet.conf"),
                "/etc/assistant.conf"]

DEFAULTS = {
    "MISTRAL_API_KEY": "",
    "MISTRAL_MODEL": "voxtral-small-latest",
    "PET_NAME": "Pip",
    "AUDIO_DEVICE": "mic",
    "SAMPLE_RATE": "16000",
    "MAX_SECONDS": "30",
    "BUTTON_PIN": "PA3",
    "ENCODER_CLK": "PA2",
    "ENCODER_DT": "PA1",
    "ENCODER_REVERSE": "0",
    "ENCODER_STEPS": "4",
    "DATA_DIR": "/var/lib/nanopet", # notes/ (long-term memory), state.json
    "HISTORY_TURNS": "8",           # short-term memory: last N exchanges
    "HISTORY_IDLE_MIN": "15",       # ...forgotten after this much silence
    "TTS": "1",                     # 0 = subtitles only
    "TTS_MODEL": "voxtral-mini-tts-2603",
    "VOICE": "gb_jane_neutral",     # Voxtral preset voice (the base for the effects)
    "VOICE_FX": "cute_robot",       # cute_robot | robot | chipmunk | none
    "VOICE_PITCH": "",              # override the preset's pitch factor, e.g. 1.6
    "SPEAKER": "",                  # ALSA device; empty = first USB sound card
}


def load_config():
    cfg = dict(DEFAULTS)
    for path in reversed(CONFIG_PATHS):          # earlier entries win
        if not os.path.exists(path):
            continue
        with open(path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    cfg[k.strip()] = v.strip().strip('"').strip("'")
    cfg.update({k: v for k, v in os.environ.items() if k in DEFAULTS})
    return cfg


def ensure_clock():
    """No RTC: the board boots in 1970 and HTTPS then rejects every
    certificate. Take the time from a plain-HTTP Date header."""
    if datetime.datetime.now().year >= 2025:
        return True
    import requests
    for url in ("http://www.google.com", "http://example.com"):
        try:
            date = requests.head(url, timeout=10).headers["Date"]
            ts = email.utils.parsedate_to_datetime(date).timestamp()
            subprocess.run(["date", "-u", "-s", "@%d" % ts], check=True,
                           stdout=subprocess.DEVNULL)
            return True
        except Exception:
            continue
    return False


class Recorder:
    """arecord into a temporary WAV; SIGINT makes it finalise the header."""

    def __init__(self, device="mic", rate=16000, max_seconds=30):
        self.device, self.rate, self.max_seconds = device, rate, max_seconds
        self.proc = None

    def start(self):
        fd, self.path = tempfile.mkstemp(suffix=".wav", prefix="pet-")
        os.close(fd)
        self.proc = subprocess.Popen(
            ["arecord", "-q", "-D", self.device, "-f", "S16_LE", "-c", "1",
             "-r", str(self.rate), "-d", str(self.max_seconds), "-t", "wav", self.path],
            stderr=subprocess.PIPE)
        self.t0 = time.monotonic()

    def stop(self):
        """Returns (wav bytes, seconds)."""
        if self.proc.poll() is None:
            self.proc.send_signal(signal.SIGINT)
        try:
            self.proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            self.proc.kill()
            self.proc.wait()
        seconds = time.monotonic() - self.t0
        with open(self.path, "rb") as f:
            data = f.read()
        os.unlink(self.path)
        return data, seconds
