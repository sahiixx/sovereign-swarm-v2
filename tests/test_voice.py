"""Tests for VoiceIO — basic TTS/STT wrapper."""
import asyncio, unittest
from unittest.mock import patch, MagicMock
from pathlib import Path

from sovereign_swarm.infra.voice import VoiceIO


class TestVoiceIO(unittest.TestCase):
    def _run(self, coro):
        return asyncio.get_event_loop().run_until_complete(coro)

    @patch("sovereign_swarm.infra.voice.subprocess.run")
    @patch("sovereign_swarm.infra.voice.tempfile.mkstemp")
    def test_speak_local_calls_espeak(self, mock_mkstemp, mock_run):
        mock_mkstemp.return_value = (3, "/tmp/swarm_tts_xyz.wav")
        v = VoiceIO(tts_provider="local", stt_provider="local")
        path = self._run(v.speak("Hello"))
        self.assertIn("swarm_tts", path)

    @patch.dict("os.environ", {"OPENAI_API_KEY": "k"}, clear=False)
    @patch("httpx.AsyncClient.post")
    def test_speak_openai(self, mock_post):
        mock_post.return_value = MagicMock(
            content=b"MP3",
            raise_for_status=lambda: None,
        )
        v = VoiceIO(tts_provider="openai")
        with patch("sovereign_swarm.infra.voice.tempfile.mkstemp", return_value=(3, "/tmp/t.mp3")):
            path = self._run(v.speak("Hello"))
        self.assertTrue(path.endswith(".mp3"))

    def test_status(self):
        v = VoiceIO()
        st = v.status()
        self.assertEqual(st["tts_provider"], "local")
        self.assertFalse(st["whisper_model_loaded"])

if __name__ == "__main__":
    unittest.main()
