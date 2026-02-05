# 🔐 CyberIntel Bot — Cybersecurity Intelligence System

<p align="center">
  <img alt="CyberIntel Bot" src="./icon.png" width="300">
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Discord-Bot-5865F2?logo=discord&logoColor=white" alt="Discord Bot" />
  <img src="https://img.shields.io/badge/Python-3.10%2B-blue?logo=python&logoColor=white" alt="Python 3.10+" />
  <img src="https://img.shields.io/badge/Status-Secure-success" alt="Status" />
  <img src="https://img.shields.io/badge/License-MIT-green" alt="License MIT" />
</p>

<p align="center">
  <b>Smart Intelligence Monitoring for Cybersecurity Feeds (RSS/Atom/YouTube)</b><br>
  Surgical Filtering • Interactive Dashboard • Automated Discord Posting
</p>

---

## 📋 Table of Contents

- [✨ Features](#-features)
- [🧱 Architecture](#-architecture)
- [🚀 Installation](#-installation)
- [⚙️ Configuration](#️-configuration)
- [🧰 Commands](#-commands)
- [🎛️ Dashboard](#️-dashboard)
- [🧠 Filter System](#-filter-system)
- [🖥️ Deploy](#️-deploy)
- [📜 License](#-license)

---

## ✨ Features

| Feature | Description |
|---------|-----------|
| 📡 **Periodic Scanner** | Scans RSS/Atom/YouTube feeds every 30 minutes (configurable). |
| 🕵️ **HTML Watcher** | Monitors official sites without RSS (e.g. CISA, NIST) detecting visual changes. |
| 🎛️ **Persistent Dashboard** | Interactive panel with buttons that works even after restarts. |
| 🎯 **Category Filters** | Malware, Ransomware, Vulnerability, Exploit + "ALL" option. |
| 🛡️ **Anti-Spam** | Blacklist to block generic or unrelated tech news. |
| 🔄 **Deduplication** | Never repeats news (history in `history.json`). |
| 🌐 **Multi-Guild** | Independent configuration per Discord server. |
| 🎨 **Rich Embeds** | Premium visual style (Matrix Green, thumbnails, timestamps). |
| 🎞️ **Native Player** | YouTube/Twitch videos play directly in chat. |
| 🌍 **Multi-Language** | Supports EN, PT, ES, IT, JA (auto-detection + `/setlang`). |
| 🔐 **SSL Secure** | Verified connections with certifi (MITM protection). |

---

## 🧱 Architecture

### Data Flow

```mermaid
flowchart LR
  A["sources.json<br>Feeds RSS + HTML"] --> B["Scanner<br>core/scanner.py"]
  B --> C["Log Aggregation"]
  B --> J["HTML Monitor<br>core/html_monitor.py"]
  C --> D["CyberIntel Filters<br>core/filters.py"]
  D -->|Approved| E["Translator (Auto)<br>utils/translator.py"]
  E --> F["Discord Posting<br>Channel per guild"]
  J -->|Change Detected| F
  D -->|Rejected| G["Ignore / Discard"]

  H["config.json<br>Channel + Filters"] --> D
  I["history.json<br>Sent Links"] --> D
  F --> I
```

---

## 🚀 Installation

### Prerequisites

- Python 3.10+
- Discord Bot Token ([Developer Portal](https://discord.com/developers/applications))

### Quick Start

```bash
# 1. Clone repository
git clone https://github.com/carmipa/cyberintel-discord.git
cd cyberintel-discord

# 2. Create virtual env
python -m venv .venv
source .venv/bin/activate  # Linux/Mac
# .venv\Scripts\activate   # Windows

# 3. Install dependencies
pip install -r requirements.txt

# 4. Configure env
cp .env.example .env
# Edit .env with your token
```

---

## ⚙️ Configuration

### Environment Variables (`.env`)

```env
DISCORD_TOKEN=your_token_here
COMMAND_PREFIX=!
LOOP_MINUTES=30
LOG_LEVEL=INFO
```

### Feed Sources (`sources.json`)

```json
{
  "rss_feeds": [
    "https://feeds.feedburner.com/TheHackersNews",
    "https://www.bleepingcomputer.com/feed/"
  ],
  "youtube_feeds": [
    "https://www.youtube.com/feeds/videos.xml?channel_id=UC9-y-6csu5WGm29I7JiwpnA"
  ]
}
```

---

## 🧰 Commands

| Command | Type | Description |
|---------|------|-----------|
| `/dashboard` | Slash | Opens configuration dashboard (Admin) |
| `/setlang` | Slash | Sets bot language for the server (Admin) |
| `/forcecheck` | Slash | Forces immediate scan (Admin) |
| `/status` | Slash | Shows bot statistics (Uptime, Scans) |
| `/feeds` | Slash | Lists all monitored sources |

---

## 🎛️ Dashboard

The interactive panel allows you to configure which categories to monitor:

- 🦠 **Malware**
- 🔒 **Ransomware**
- 🛡️ **Vulnerability**
- 💥 **Exploit**
- 🕵️ **Zero-Day**

---

## 📜 License

This project is licensed under the **MIT License**.

---

<p align="center">
  🔐 <i>CyberIntel System — Secure the network. Protect the future.</i>
</p>
