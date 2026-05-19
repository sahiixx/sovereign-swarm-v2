"""VoiceIO — basic TTS listener wrapper for Sovereign Swarm v2.

Provides:
- Text-to-speech via pyttsx3 (local, offline) or OpenAI TTS (cloud)
- Speech-to-text via faster-whisper (local) or OpenAI Whisper (cloud)
- Minimal asyncio interface that integrates with SwarmBus events

Usage:
    voice = VoiceIO(tts_provider="local", stt_provider="local")
    await voice.speak("Mission complete. Agent alpha has returned.")
    text = await voice.listen(timeout=5)   # record 5 seconds, transcribe
"""

import asyncio, io, os, subprocess, tempfile, wave
from pathlib import Path
from typing import Dict, Optional


class VoiceIO:
    """Lightweight voice I/O layer for swarm agents."""

    def __init__(self, tts_provider: str = "local", stt_provider: str = "local",
                 openai_key: str = None, groq_key: str = None, model_dir: str = None):
        """
        Args:
            tts_provider: "local" (pyttsx3), "openai" (cloud TTS), or "gemini" (Google TTS)
            stt_provider: "local" (faster-whisper), "openai" (cloud Whisper), "groq" (Groq Whisper)
            openai_key: fallback if env var unset
            groq_key: Groq API key for fast STT
            model_dir: whisper model cache directory
        """
        self.tts_provider = tts_provider
        self.stt_provider = stt_provider
        self.openai_key = openai_key or os.getenv("OPENAI_API_KEY") or os.getenv("VOICE_TOOLS_OPENAI_KEY")
        self.groq_key = groq_key or os.getenv("GROQ_API_KEY")
        self.model_dir = model_dir or str(Path.home() / ".cache" / "whisper")
        self._whisper_model = None  # lazy init

    # ------------------------------------------------------------------ #
    # TTS
    # ------------------------------------------------------------------ #

    async def speak(self, text: str, voice: str = "nova", speed: float = 1.0, provider: Optional[str] = None) -> str:
        """Speak text aloud or save to file. Returns path to audio file."""
        tts = provider or self.tts_provider
        if tts == "local":
            return await self._speak_local(text)
        elif tts == "openai":
            return await self._speak_openai(text, voice, speed)
        elif tts == "groq":
            # Groq does not have TTS yet, fallback to local
            return await self._speak_local(text)
        else:
            raise ValueError(f"Unknown TTS provider: {tts}")

    async def _speak_local(self, text: str) -> str:
        """Use pyttsx3 for offline TTS."""
        try:
            import pyttsx3
        except ImportError:
            # Fallback: write WAV using speech-dispatcher or espeak
            fd, path = tempfile.mkstemp(suffix=".wav", prefix="swarm_tts_")
            os.close(fd)
            # Best-effort espeak
            subprocess.run(
                ["espeak", "-w", path, text],
                capture_output=True, check=False,
            )
            return path

        engine = pyttsx3.init()
        fd, path = tempfile.mkstemp(suffix=".wav", prefix="swarm_tts_")
        os.close(fd)
        engine.save_to_file(text, path)
        engine.runAndWait()
        return path

    async def _speak_openai(self, text: str, voice: str, speed: float) -> str:
        """Use OpenAI TTS API (requires key)."""
        import httpx
        url = "https://api.openai.com/v1/audio/speech"
        headers = {"Authorization": f"Bearer {self.openai_key}", "Content-Type": "application/json"}
        body = {"model": "tts-1", "input": text, "voice": voice, "speed": speed}

        fd, path = tempfile.mkstemp(suffix=".mp3", prefix="swarm_tts_")
        os.close(fd)

        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(url, headers=headers, json=body)
            resp.raise_for_status()
            Path(path).write_bytes(resp.content)
        return path

    # ------------------------------------------------------------------ #
    # STT
    # ------------------------------------------------------------------ #

    async def listen(self, timeout: int = 5, mic_device: str = None, provider: Optional[str] = None) -> Optional[str]:
        """Record audio from mic and transcribe to text."""
        prov = provider or self.stt_provider
        if prov == "local":
            return await self._listen_local(timeout)
        elif prov == "openai":
            return await self._listen_openai(timeout)
        elif prov == "groq":
            return await self._listen_groq(timeout)
        else:
            raise ValueError(f"Unknown STT provider: {prov}")

    async def _listen_local(self, timeout: int) -> Optional[str]:
        """Record via arecord/SoX + transcribe via faster-whisper."""
        fd, wav_path = tempfile.mkstemp(suffix=".wav", prefix="swarm_stt_")
        os.close(fd)

        # Record
        rec = await asyncio.create_subprocess_exec(
            "arecord", "-d", str(timeout), "-f", "cd", "-t", "wav", wav_path,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        await rec.wait()

        # Transcribe
        return await self._transcribe_whisper(wav_path)

    async def _transcribe_whisper(self, wav_path: str) -> Optional[str]:
        """Transcribe WAV via faster-whisper or whisper.cpp."""
        try:
            from faster_whisper import WhisperModel
            if self._whisper_model is None:
                self._whisper_model = WhisperModel("tiny", device="cpu", compute_type="int8",
                                                   download_root=self.model_dir)
            segments, info = self._whisper_model.transcribe(wav_path, beam_size=5)
            return " ".join(s.text for s in segments).strip()
        except ImportError:
            # Fallback to whisper CLI if available
            result = subprocess.run(
                ["whisper", wav_path, "--model", "tiny", "--output_format", "txt", "--output_dir", "/tmp"],
                capture_output=True, text=True, check=False,
            )
            txt_path = Path(wav_path).with_suffix(".txt")
            if txt_path.exists():
                return txt_path.read_text().strip()
            return None

    async def _listen_openai(self, timeout: int) -> Optional[str]:
        """Record then upload to OpenAI Whisper API."""
        import httpx
        fd, wav_path = tempfile.mkstemp(suffix=".wav", prefix="swarm_stt_")
        os.close(fd)
        rec = await asyncio.create_subprocess_exec(
            "arecord", "-d", str(timeout), "-f", "cd", "-t", "wav", wav_path,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        await rec.wait()

        url = "https://api.openai.com/v1/audio/transcriptions"
        headers = {"Authorization": f"Bearer {self.openai_key}"}
        async with httpx.AsyncClient(timeout=60) as client:
            with open(wav_path, "rb") as f:
                files = {"file": ("audio.wav", f, "audio/wav")}
                data = {"model": "whisper-1"}
                resp = await client.post(url, headers=headers, data=data, files=files)
            resp.raise_for_status()
            return resp.json().get("text")

    async def _listen_groq(self, timeout: int) -> Optional[str]:
        """Record then upload to Groq Whisper API (lightning fast)."""
        import httpx
        fd, wav_path = tempfile.mkstemp(suffix=".wav", prefix="swarm_stt_")
        os.close(fd)
        rec = await asyncio.create_subprocess_exec(
            "arecord", "-d", str(timeout), "-f", "cd", "-t", "wav", wav_path,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        await rec.wait()

        url = "https://api.groq.com/openai/v1/audio/transcriptions"
        headers = {"Authorization": f"Bearer {self.groq_key}"}
        async with httpx.AsyncClient(timeout=30) as client:
            with open(wav_path, "rb") as f:
                files = {"file": ("audio.wav", f, "audio/wav")}
                data = {"model": "whisper-large-v3", "response_format": "json"}
                resp = await client.post(url, headers=headers, data=data, files=files)
            resp.raise_for_status()
            return resp.json().get("text", "").strip()

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #

    def status(self) -> Dict:
        return {
            "tts_provider": self.tts_provider,
            "stt_provider": self.stt_provider,
            "openai_key_set": bool(self.openai_key),
            "whisper_model_loaded": self._whisper_model is not None,
        }
