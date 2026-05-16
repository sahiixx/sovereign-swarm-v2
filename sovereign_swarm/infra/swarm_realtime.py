"""
Sovereign Swarm — Real-Time Data Connectors
Web search, news aggregation, market data, weather, and trend monitoring.
Integrates with swarm agents via the message bus.
"""
import asyncio
import aiohttp
import json
import time
from typing import Dict, List, Optional, Any
from sovereign_swarm.infra.swarm_bus import SwarmBus, Message, MessageType

class RealtimeConnector:
    """Base class for real-time data connectors."""
    def __init__(self, bus: SwarmBus, interval: int = 300):
        self.bus = bus
        self.interval = interval
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self.last_data: Optional[Dict] = None
    
    async def start(self):
        self._running = True
        self._task = asyncio.create_task(self._poll_loop())
        print(f"[REALTIME] {self.__class__.__name__} started")
    
    async def stop(self):
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
    
    async def _poll_loop(self):
        while self._running:
            try:
                data = await self.fetch()
                if data:
                    self.last_data = data
                    await self._broadcast(data)
                await asyncio.sleep(self.interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"[REALTIME ERROR] {self.__class__.__name__}: {e}")
                await asyncio.sleep(self.interval)
    
    async def fetch(self) -> Optional[Dict]:
        raise NotImplementedError
    
    async def _broadcast(self, data: Dict):
        await self.bus.broadcast_system({
            "type": "realtime_data",
            "source": self.__class__.__name__,
            "data": data,
            "timestamp": time.time()
        })

class WebSearchConnector(RealtimeConnector):
    """Web search via search APIs."""
    def __init__(self, bus: SwarmBus, queries: List[str] = None, interval: int = 600):
        super().__init__(bus, interval)
        self.queries = queries or ["AI news", "technology trends", "security updates"]
    
    async def fetch(self) -> Optional[Dict]:
        results = {}
        for query in self.queries[:3]:
            try:
                # DuckDuckGo lite (no API key)
                url = f"https://html.duckduckgo.com/html/?q={query.replace(' ', '+')}"
                async with aiohttp.ClientSession() as session:
                    async with session.get(url, timeout=15, headers={
                        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"
                    }) as resp:
                        if resp.status == 200:
                            html = await resp.text()
                            # Extract titles simply
                            import re
                            titles = re.findall(r'<a[^>]+class="result__a"[^>]*>([^<]+)</a>', html)
                            results[query] = titles[:5]
            except Exception as e:
                results[f"{query}_error"] = str(e)
        
        return results if results else None

class WeatherConnector(RealtimeConnector):
    """Weather data via Open-Meteo (free, no API key)."""
    def __init__(self, bus: SwarmBus, lat: float = 51.5, lon: float = -0.1, interval: int = 600):
        super().__init__(bus, interval)
        self.lat = lat
        self.lon = lon
    
    async def fetch(self) -> Optional[Dict]:
        try:
            url = (f"https://api.open-meteo.com/v1/forecast?"
                   f"latitude={self.lat}&longitude={self.lon}"
                   f"&current=temperature_2m,relative_humidity_2m,weather_code"
                   f"&hourly=temperature_2m,precipitation_probability"
                   f"&daily=temperature_2m_max,temperature_2m_min,precipitation_sum"
                   f"&timezone=auto")
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=15) as resp:
                    if resp.status == 200:
                        return await resp.json()
        except Exception as e:
            return {"error": str(e)}
        return None

class CryptoMarketConnector(RealtimeConnector):
    """Crypto market data via CoinGecko."""
    def __init__(self, bus: SwarmBus, coins: List[str] = None, interval: int = 60):
        super().__init__(bus, interval)
        self.coins = coins or ["bitcoin", "ethereum", "solana"]
    
    async def fetch(self) -> Optional[Dict]:
        try:
            coins_str = ",".join(self.coins)
            url = f"https://api.coingecko.com/api/v3/simple/price?ids={coins_str}&vs_currencies=usd&include_24hr_change=true"
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=15) as resp:
                    if resp.status == 200:
                        return await resp.json()
        except Exception as e:
            return {"error": str(e)}
        return None

class HackerNewsConnector(RealtimeConnector):
    """Hacker News front page stories."""
    def __init__(self, bus: SwarmBus, interval: int = 300):
        super().__init__(bus, interval)
    
    async def fetch(self) -> Optional[Dict]:
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get("https://hn.algolia.com/api/v1/search?tags=front_page", timeout=15) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        hits = data.get("hits", [])
                        return {
                            "stories": [
                                {
                                    "title": h["title"],
                                    "url": h.get("url", ""),
                                    "points": h["points"],
                                    "comments": h.get("num_comments", 0)
                                }
                                for h in hits[:10]
                            ]
                        }
        except Exception as e:
            return {"error": str(e)}
        return None

class RSSFeedConnector(RealtimeConnector):
    """Generic RSS feed monitor."""
    def __init__(self, bus: SwarmBus, feeds: List[str] = None, interval: int = 300):
        super().__init__(bus, interval)
        self.feeds = feeds or [
            "https://feeds.bbci.co.uk/news/technology/rss.xml",
            "https://news.ycombinator.com/rss"
        ]
    
    async def fetch(self) -> Optional[Dict]:
        results = {}
        try:
            import feedparser
            for feed_url in self.feeds[:3]:
                try:
                    feed = feedparser.parse(feed_url)
                    entries = []
                    for entry in feed.entries[:5]:
                        entries.append({
                            "title": entry.title,
                            "link": entry.link,
                            "published": entry.get("published", "unknown")
                        })
                    results[feed_url] = entries
                except Exception as e:
                    results[feed_url] = {"error": str(e)}
        except ImportError:
            results["error"] = "feedparser not installed"
        return results if results else None

class RealtimeOrchestrator:
    """Manages all real-time connectors."""
    def __init__(self, bus: SwarmBus, config: Dict[str, Any]):
        self.bus = bus
        self.config = config
        self.connectors: Dict[str, RealtimeConnector] = {}
        self._setup_connectors()
    
    def _setup_connectors(self):
        if self.config.get("news_refresh_interval", 300) > 0:
            self.connectors["rss"] = RSSFeedConnector(
                self.bus, interval=self.config.get("news_refresh_interval", 300)
            )
        if self.config.get("market_refresh_interval", 60) > 0:
            self.connectors["crypto"] = CryptoMarketConnector(
                self.bus, interval=self.config.get("market_refresh_interval", 60)
            )
        if self.config.get("weather_refresh_interval", 600) > 0:
            self.connectors["weather"] = WeatherConnector(
                self.bus, interval=self.config.get("weather_refresh_interval", 600)
            )
        if self.config.get("trend_refresh_interval", 180) > 0:
            self.connectors["hackernews"] = HackerNewsConnector(
                self.bus, interval=self.config.get("trend_refresh_interval", 180)
            )
    
    async def start(self):
        for name, conn in self.connectors.items():
            await conn.start()
    
    async def stop(self):
        for conn in self.connectors.values():
            await conn.stop()
    
    def get_status(self) -> Dict[str, Any]:
        return {
            name: {
                "running": conn._running,
                "last_data": conn.last_data is not None,
                "interval": conn.interval
            }
            for name, conn in self.connectors.items()
        }
