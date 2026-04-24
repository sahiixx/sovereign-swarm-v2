"""Shared configuration and imports."""

import __main__
import argparse, asyncio, json, math, os, random, re, signal, shutil, sqlite3, statistics
import string, subprocess, sys, textwrap, time
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from ._compat import (
    aiohttp, BaseModel, ValidationError,
    PromCounter, Histogram, Gauge, start_http_server,
    AioWeb,
)

DATA_DIR = Path(os.getenv("SWARM_DATA_DIR", "./data"))
DATA_DIR.mkdir(parents=True, exist_ok=True)
