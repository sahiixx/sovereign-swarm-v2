"""Dubai Real Estate Campaign — deployable voice agent campaign for Sovereign Swarm v2.

Full pipeline:
  VoiceInput (Groq STT) ➜ DubaiREAgent (parse/qualify/search) ➜ VoiceOutput (local TTS)
  + HermesBus logging
  + Telegram push notifications
  + JSON result export for CRM

Usage:
    campaign = DubaiRECampaign()
    result = await campaign.process_voice(audio_path="/tmp/inquiry.wav")
    # or:
    result = await campaign.process_text("2 bedroom apartment in Dubai Marina")
    # Deploy:
    campaign.deploy_telegram_bot()
"""
import asyncio, json, os, tempfile, time
from pathlib import Path
from typing import Optional, Dict, List
from dataclasses import dataclass, asdict

from ..agents.dubai_re_agent import DubaiREAgent, PropertySearch, LeadProfile
from ..infra.voice import VoiceIO
from ..protocols import hermes_v2

try:
    import httpx
except ImportError:
    httpx = None

TELEGRAM_API = "https://api.telegram.org/bot{token}"
GROQ_STT_URL = "https://api.groq.com/openai/v1/audio/transcriptions"


@dataclass
class CampaignConfig:
    """Runtime configuration for the Dubai RE campaign."""
    enable_voice: bool = True
    enable_telegram: bool = True
    enable_email: bool = False
    telegram_token: str = ""
    telegram_chat_id: str = ""
    groq_key: str = ""
    crm_export_dir: str = "/tmp/dubai_re_crm"
    min_lead_confidence: float = 0.5


class DubaiRECampaign:
    """End-to-end Dubai Real Estate voice/text campaign runner."""

    def __init__(self, config: CampaignConfig = None):
        self.config = config or CampaignConfig()
        self.agent = DubaiREAgent()
        self.voice = VoiceIO(
            tts_provider="local",
            stt_provider="groq" if self.config.groq_key else "local",
            groq_key=self.config.groq_key,
        )
        self.bus = None
        self._crm_dir = Path(self.config.crm_export_dir)
        self._crm_dir.mkdir(parents=True, exist_ok=True)

    # ╭──────────────────────────────────────────────────────────────────╮
    # │  Core Pipeline                                                   │
    # ╰──────────────────────────────────────────────────────────────────╯

    async def process_text(self, query: str) -> dict:
        """Process a text inquiry through the full pipeline."""
        result = self.agent.handle_voice_query(query)
        await self._log_to_bus("dubai_re", {"event": "text_inquiry", "query": query, "result": result})
        await self._export_lead(result)
        return result

    async def process_voice(self, audio_path: str) -> dict:
        """Process a voice recording (WAV) through STT + full pipeline."""
        transcript = await self._stt(audio_path)
        self._log(f"Voice transcript: {transcript}")
        result = await self.process_text(transcript)
        result["transcript"] = transcript
        return result

    async def speak_response(self, text: str) -> str:
        """Generate TTS audio (local/espeak fallback). Returns file path."""
        path = await self.voice.speak(text, provider="local")
        return path

    # ╭──────────────────────────────────────────────────────────────────╮
    # │  STT — Groq fast Whisper endpoint                                 │
    # ╰──────────────────────────────────────────────────────────────────╯

    async def _stt(self, audio_path: str) -> str:
        """Transcribe audio via Groq Whisper API (lightning fast) or local whisper."""
        if self.config.groq_key:
            return await self._stt_groq(audio_path)
        return await self._stt_local(audio_path)

    async def _stt_groq(self, audio_path: str) -> str:
        """Groq Whisper — same API shape as OpenAI, ~10x faster."""
        if httpx is None:
            raise RuntimeError("httpx not installed")
        async with httpx.AsyncClient(timeout=30) as client:
            with open(audio_path, "rb") as f:
                files = {"file": ("audio.wav", f, "audio/wav")}
                data = {"model": "whisper-large-v3", "response_format": "json"}
                headers = {"Authorization": f"Bearer {self.config.groq_key}"}
                resp = await client.post(GROQ_STT_URL, headers=headers, data=data, files=files)
            resp.raise_for_status()
            return resp.json().get("text", "").strip()

    async def _stt_local(self, audio_path: str) -> str:
        """Local whisper via faster-whisper."""
        from faster_whisper import WhisperModel
        model = WhisperModel("tiny", device="cpu", compute_type="int8")
        segments, _ = model.transcribe(audio_path, beam_size=5)
        return " ".join(s.text for s in segments).strip()

    # ╭──────────────────────────────────────────────────────────────────╮
    # │  Hermes Bus Integration                                           │
    # ╰──────────────────────────────────────────────────────────────────╮

    async def _log_to_bus(self, channel: str, payload: dict):
        """Fire-and-forget Hermes bus log — does NOT block pipeline."""
        try:
            bus = hermes_v2.HermesV2()
            msg = hermes_v2.HermesMessage(
                channel=channel,
                payload=payload,
                sender="dubai_re_campaign"
            )
            # Bus.send may not exist; safe fallback
            if hasattr(bus, 'send'):
                await bus.send(msg)
        except Exception:
            pass  # Bus logging is best-effort

    # ╭──────────────────────────────────────────────────────────────────╮
    # │  CRM Export                                                       │
    # ╰──────────────────────────────────────────────────────────────────╯

    async def _export_lead(self, result: dict):
        """Export qualified leads to JSONL for CRM/N8n ingestion."""
        lead = result.get("lead", {})
        if not lead.get("qualified"):
            return
        timestamp = int(time.time())
        filename = self._crm_dir / f"lead_{timestamp}.json"
        with open(filename, "w") as f:
            json.dump(result, f, indent=2)
        self._log(f"Lead exported to {filename}")

    # ╭──────────────────────────────────────────────────────────────────╮
    # │  Telegram Deployment                                              │
    # ╰──────────────────────────────────────────────────────────────────╯

    async def telegram_notify(self, text: str, chat_id: str = None) -> bool:
        """Push a message to Telegram chat."""
        if not self.config.telegram_token:
            self._log("Telegram token not set — skipping push")
            return False
        cid = chat_id or self.config.telegram_chat_id
        if not cid:
            return False
        try:
            url = f"{TELEGRAM_API.format(token=self.config.telegram_token)}/sendMessage"
            payload = {"chat_id": cid, "text": text, "parse_mode": "Markdown"}
            if httpx is None:
                import urllib.request
                req = urllib.request.Request(
                    url, data=json.dumps(payload).encode(),
                    headers={"Content-Type": "application/json"}, method="POST")
                urllib.request.urlopen(req, timeout=10)
            else:
                async with httpx.AsyncClient(timeout=10) as client:
                    await client.post(url, json=payload)
            self._log(f"Telegram sent to {cid}")
            return True
        except Exception as e:
            self._log(f"Telegram error: {e}")
            return False

    async def _whatsapp_notify(self, phone: str, text: str) -> bool:
        """Push a WhatsApp message via wa.me link or API stub.
        
        Note: Full WhatsApp Business API requires Meta approval.
        This opens a wa.me pre-filled message in browser (fallback for MVP).
        """
        try:
            import urllib.parse
            clean = phone.replace("+", "").replace(" ", "")
            msg = urllib.parse.quote(text[:300])  # WA limit
            url = f"https://wa.me/{clean}?text={msg}"
            # Log the link — actual push requires WA Business API
            self._log(f"WhatsApp ready: {url[:80]}...")
            return True
        except Exception as e:
            self._log(f"WhatsApp notify error: {e}")
            return False

    async def notify_lead(self, result: dict):
        """Send a formatted lead notification to Telegram OR WhatsApp (primary)."""
        lead = result.get("lead", {})
        if not lead.get("qualified"):
            return
        lines = [
            f"🎯 *QUALIFIED LEAD* | Score: {int(lead.get('confidence',0)*100)}%",
            f"Intent: _{lead.get('intent', '?')}_ | Urgency: _{lead.get('urgency', '?')}_",
            f"Results: {result.get('results_count', 0)} properties",
            "```",
            result.get("message", "")[:800],
            "```",
            f"\n📱 Agent: {self.agent.agent_profile.get('name', 'Sahil Khan')}",
            f"💬 WhatsApp: {self.agent.agent_profile.get('contact', {}).get('whatsapp', '+971585476077')}",
        ]
        # Try WhatsApp first (most direct for Dubai RE)
        wa = self.agent.agent_profile.get('contact', {}).get('whatsapp')
        if wa:
            await self._whatsapp_notify(wa, "\n".join(lines))
        # Fallback to Telegram
        await self.telegram_notify("\n".join(lines))

    # ╭──────────────────────────────────────────────────────────────────╮
    # │  High-Level Deployment                                            │
    # ╰──────────────────────────────────────────────────────────────────╯

    async def deploy_telegram_bot(self):
        """Placeholder for full webhook-based Telegram bot deployment."""
        # Future: wire to scripts/telegram_bot.py with /find command
        self._log("Telegram bot deployment stub — use scripts/telegram_bot.py for webhook mode")
        return {"status": "stub", "hint": "run scripts/telegram_bot.py"}

    # ─── Voice Query Command Loop ──────────────────────────────────────
    async def run_voice_interactive(self, max_turns: int = 10):
        """Interactive voice RE agent — listens, processes, speaks."""
        self._log("🎤 Voice mode active. Speak your query...")
        for turn in range(max_turns):
            try:
                # Record via arecord (5s bursts)
                fd, wav = tempfile.mkstemp(suffix=".wav", prefix="dubai_re_")
                os.close(fd)
                rec = await asyncio.create_subprocess_exec(
                    "arecord", "-d", "5", "-f", "cd", "-t", "wav", wav,
                    stdout=asyncio.subprocess.DEVNULL,
                    stderr=asyncio.subprocess.DEVNULL,
                )
                await rec.wait()

                result = await self.process_voice(wav)
                print("\n" + result.get("message", ""))

                # Speak the response
                response_text = result.get("message", "")
                if response_text:
                    await self.speak_response(response_text)

                # Push qualified leads
                await self.notify_lead(result)

                os.unlink(wav)
            except KeyboardInterrupt:
                self._log("Voice session interrupted.")
                break
            except Exception as e:
                self._log(f"Turn error: {e}")

        self._log("Voice session ended.")

    # ╭──────────────────────────────────────────────────────────────────╮
    # │  Helpers                                                          │
    # ╰──────────────────────────────────────────────────────────────────╯

    @staticmethod
    def _log(msg: str):
        print(f"[DubaiRECampaign] {msg}")

    def status(self) -> Dict:
        return {
            "agent_loaded": hasattr(self, "agent"),
            "voice_ready": self.voice.status(),
            "config": {k: (v[:6] + "..." if isinstance(v, str) and len(v) > 20 else v)
                        for k, v in asdict(self.config).items()},
            "crm_dir": str(self._crm_dir),
            "crm_files": len(list(self._crm_dir.glob("*.json"))),
        }


# ════════════════════════════════════════════════════════════════════════
# CLI entrypoint
# ════════════════════════════════════════════════════════════════════════

async def main():
    import argparse
    parser = argparse.ArgumentParser(description="Dubai RE Voice Agent Campaign")
    parser.add_argument("--text", help="Static text query (no voice)")
    parser.add_argument("--voice", action="store_true", help="Run interactive voice session")
    parser.add_argument("--groq-key", default=os.getenv("GROQ_API_KEY", ""), help="Groq API key")
    parser.add_argument("--tg-token", default=os.getenv("TELEGRAM_BOT_TOKEN", ""), help="Telegram bot token")
    parser.add_argument("--tg-chat", default=os.getenv("TELEGRAM_HOME_CHANNEL_NAME", ""), help="Target chat ID")
    args = parser.parse_args()

    config = CampaignConfig(
        groq_key=args.groq_key,
        telegram_token=args.tg_token,
        telegram_chat_id=args.tg_chat,
    )
    campaign = DubaiRECampaign(config)
    print(json.dumps(campaign.status(), indent=2))

    if args.text:
        result = await campaign.process_text(args.text)
        print("\n" + "=" * 50)
        print(result["message"])
        print("=" * 50)
        print(json.dumps(result["lead"], indent=2))
        await campaign.notify_lead(result)
    elif args.voice:
        await campaign.run_voice_interactive()
    else:
        print("\nUsage: python -m sovereign_swarm.campaigns.dubai_re_campaign --text '2BR in Marina'")
        print("       python -m sovereign_swarm.campaigns.dubai_re_campaign --voice")


if __name__ == "__main__":
    asyncio.run(main())
