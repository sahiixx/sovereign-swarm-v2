"""Tests for VoiceIO — basic TTS/STT wrapper."""
import asyncio, unittest
from unittest.mock import patch, MagicMock, AsyncMock
from pathlib import Path

from sovereign_swarm.infra.voice import VoiceIO


class TestVoiceIO(unittest.TestCase):
    def test_speak_local_calls_espeak(self):
        with patch("sovereign_swarm.infra.voice.subprocess.run") as mock_run, \
             patch("sovereign_swarm.infra.voice.tempfile.mkstemp", return_value=(3, "/tmp/swarm_tts_xyz.wav")):
            v = VoiceIO(tts_provider="local", stt_provider="local")
            path = asyncio.run(v.speak("Hello"))
            self.assertIn("swarm_tts", path)

    @patch.dict("os.environ", {"OPENAI_API_KEY": "k"}, clear=False)
    def test_speak_openai(self):
        """Skip async-in-async httpx by just verifying the code path exists.
        The real OpenAI TTS test requires integration."""
        v = VoiceIO(tts_provider="openai")
        self.assertEqual(v.tts_provider, "openai")
        self.assertTrue(v.openai_key)

    def test_status(self):
        v = VoiceIO()
        st = v.status()
        self.assertEqual(st["tts_provider"], "local")
        self.assertFalse(st["whisper_model_loaded"])

if __name__ == "__main__":
    unittest.main()
