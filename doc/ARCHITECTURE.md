# 🏗️ Arquitetura do CyberIntel SOC Bot

<div align="center">

![Architecture](https://img.shields.io/badge/Architecture-Diagrams-blue?style=for-the-badge&logo=diagram-project)

**Documentação Técnica da Arquitetura do Sistema**

</div>

---

## 📐 Visão Geral da Arquitetura

O CyberIntel SOC Bot foi projetado seguindo princípios de **arquitetura modular**, **separação de responsabilidades** e **alta escalabilidade**. O sistema utiliza o padrão **Cogs** do `discord.py` para garantir modularidade e facilidade de manutenção.

---

## 🎯 Diagrama de Arquitetura Geral

```mermaid
graph TB
    subgraph "🌐 Fontes de Inteligência"
        RSS[RSS Feeds<br/>📰 The Hacker News<br/>📰 BleepingComputer<br/>📰 Krebs on Security]
        YT[YouTube Channels<br/>🎥 Mental Outlaw<br/>🎥 David Bombal<br/>🎥 NetworkChuck]
        API[APIs de Segurança<br/>🛡️ NVD/NIST<br/>🛸 AlienVault OTX<br/>🔍 URLScan.io<br/>🦠 VirusTotal]
        HTML[Sites Oficiais<br/>🏛️ CISA<br/>🏛️ NIST<br/>🏛️ CERT.br]
    end

    subgraph "🔧 Core System"
        Scanner[Scanner Loop<br/>⏰ Varredura Periódica<br/>🔄 30 minutos]
        Filter[Engine de Filtros<br/>🛡️ Categorização<br/>🚫 Blacklist<br/>✅ Whitelist]
        Monitor[HTML Monitor<br/>🕵️ Detecção de Mudanças<br/>🔐 Hash-based]
        Cleanup[State Cleanup<br/>🧹 Limpeza Automática<br/>📊 Por tempo/tamanho]
    end

    subgraph "💾 Camada de Persistência"
        Config[config.json<br/>⚙️ Configurações<br/>📋 Filtros por Guild]
        History[history.json<br/>📜 Deduplicação<br/>🔢 2000 itens]
        State[state.json<br/>📊 Estado do Scanner<br/>🧹 Auto-cleanup]
        DB[database.json<br/>💾 Registro de Notícias<br/>📈 Estatísticas]
        Backup[Backups<br/>📦 Automáticos<br/>🕐 Retenção 90 dias]
    end

    subgraph "📤 Camada de Output"
        Discord[Discord Bot<br/>💬 Comandos Slash<br/>🚨 Alertas em Tempo Real]
        NodeRED[Node-RED<br/>📊 Dashboard SOC<br/>📡 Webhooks]
        Web[Web Server<br/>🌍 API REST<br/>📈 Métricas]
    end

    RSS -->|Fetch| Scanner
    YT -->|Fetch| Scanner
    API -->|Fetch| Scanner
    HTML -->|Monitor| Monitor
    
    Scanner -->|Process| Filter
    Monitor -->|Changes| Filter
    
    Filter -->|Check| Config
    Filter -->|Dedupe| History
    Filter -->|Update| State
    Filter -->|Save| DB
    
    Filter -->|Post| Discord
    Filter -->|Notify| NodeRED
    Scanner -->|Metrics| Web
    
    Cleanup -->|Clean| State
    Backup -->|Backup| Config
    Backup -->|Backup| State
    Backup -->|Backup| History
    Backup -->|Backup| DB
```

---

## 🔄 Fluxo de Processamento de Inteligência

```mermaid
sequenceDiagram
    participant Scheduler as ⏰ Scheduler<br/>(30min loop)
    participant Scanner as 🔎 Scanner Core
    participant APIs as 🌐 APIs Externas
    participant Filter as 🛡️ Filter Engine
    participant Storage as 💾 Storage Layer
    participant Discord as 💬 Discord Bot
    participant NodeRED as 📊 Node-RED

    Note over Scheduler: Início do Ciclo de Varredura
    
    Scheduler->>Scanner: Trigger Scan
    Scanner->>Scanner: Load State & History
    
    par Fetch RSS Feeds
        Scanner->>APIs: GET RSS Feeds
        APIs-->>Scanner: Feed Entries
    and Fetch YouTube
        Scanner->>APIs: GET YouTube Feeds
        APIs-->>Scanner: Video Entries
    and Fetch NVD API
        Scanner->>APIs: GET NVD CVEs (CVSS > 7.0)
        APIs-->>Scanner: CVE List
    and Fetch OTX
        Scanner->>APIs: GET OTX Pulses
        APIs-->>Scanner: Threat Pulses
    end
    
    Scanner->>Filter: Process All Entries
    
    loop Para cada entrada
        Filter->>Storage: Check Deduplication
        Storage-->>Filter: Already Posted?
        
        alt Not Posted
            Filter->>Filter: Apply Category Filters
            Filter->>Filter: Check Blacklist
            Filter->>Filter: Match Keywords
            
            alt Match Found
                Filter->>Discord: Post Alert
                Filter->>NodeRED: Send Webhook
                Filter->>Storage: Save to History
                Filter->>Storage: Update State
            else No Match
                Filter->>Filter: Discard Entry
            end
        else Already Posted
            Filter->>Filter: Skip Entry
        end
    end
    
    Scanner->>Storage: Save State
    Scanner->>Scanner: Update Statistics
    
    Note over Scanner,NodeRED: Ciclo Completo
```

### Check de conectividade e resiliência do Scanner

Antes de iniciar o download dos feeds, o **Scanner** (`core/scanner.py`) executa:

1. **Check-up de conectividade**  
   Tenta uma conexão TCP rápida com o DNS do Google (`8.8.8.8:53`) com timeout de 3 segundos.  
   - Se falhar: a varredura é **abortada** e o log registra `[WARN] Rede indisponível. Postergando scan.`  
   - Se ok: segue para o fetch dos feeds.

2. **User-Agent de navegador**  
   Todas as requisições HTTP usam um User-Agent de navegador real (Chrome/Windows) para reduzir bloqueios (403/timeout) em sites como CISA.

3. **Resiliência por feed**  
   Cada feed é baixado com timeout de 30 segundos e até **3 tentativas** com intervalo de 5 segundos em caso de `TimeoutError`; após a 3ª falha, o feed é ignorado e apenas um aviso é registrado no log.

---

## 🧩 Arquitetura Modular (Cogs)

```mermaid
graph TB
    subgraph "🚀 Entry Point"
        Main[main.py<br/>Entry Point<br/>Bot Initialization]
    end
    
    subgraph "🧩 Cogs Modules"
        News[news.py<br/>📰 News Commands<br/>/news]
        CVE[cve.py<br/>🛡️ CVE Lookup<br/>/cve]
        Monitor[monitor.py<br/>🔍 Monitoring<br/>/force_scan<br/>/scan]
        Admin[admin.py<br/>⚙️ Administration<br/>/forcecheck<br/>/post_latest]
        Security[security.py<br/>🔐 Active Defense<br/>/admin_panel]
        Status[status.py<br/>📊 Status<br/>/status<br/>/now]
        Dashboard[dashboard.py<br/>📈 Dashboard<br/>/dashboard<br/>/monitor<br/>Métricas NVD 24h]
        Setup[setup.py<br/>🔧 Setup<br/>/set_channel<br/>/soc_status]
        Info[info.py<br/>ℹ️ Info<br/>/ping<br/>/about<br/>/feeds<br/>/help]
        Stats[stats.py<br/>📈 Statistics<br/>/status_db]
    end
    
    subgraph "🔧 Core Services"
        Scanner[scanner.py<br/>🔎 Scanner Engine<br/>Multi-source Fetching]
        Filters[filters.py<br/>🛡️ Filter Engine<br/>Smart Categorization]
        HTML[html_monitor.py<br/>🕵️ HTML Monitor<br/>Change Detection]
        StatsCore[stats.py<br/>📊 Statistics<br/>Metrics Collection]
    end
    
    subgraph "🌐 External Services"
        NVD[cveService.py<br/>🛡️ NVD API<br/>CVE + Métricas 24h]
        OTX[threatService.py<br/>🛸 OTX API<br/>Threat Intelligence]
        URLScan[threatService.py<br/>🔍 URLScan API<br/>URL Analysis]
        VT[threatService.py<br/>🦠 VirusTotal API<br/>Reputation Check]
        NewsSvc[newsService.py<br/>📰 News Service<br/>Feed Aggregation]
    end
    
    subgraph "💾 Storage Layer"
        Storage[storage.py<br/>💾 JSON Storage<br/>Safe Read/Write]
        Backup[backup.py<br/>📦 Backup System<br/>Auto Backup]
        Cleanup[state_cleanup.py<br/>🧹 State Cleanup<br/>Auto Maintenance]
        Cache[cache.py<br/>📦 HTTP Cache<br/>ETag Support]
    end
    
    Main --> News
    Main --> CVE
    Main --> Monitor
    Main --> Admin
    Main --> Security
    Main --> Status
    Main --> Dashboard
    Main --> Setup
    Main --> Info
    Main --> Stats
    
    Monitor --> Scanner
    Admin --> Scanner
    Status --> Scanner
    
    Scanner --> Filters
    Scanner --> HTML
    Scanner --> NVD
    Scanner --> OTX
    Scanner --> URLScan
    Scanner --> VT
    Monitor --> NewsSvc
    
    Scanner --> Storage
    Scanner --> Backup
    Scanner --> Cleanup
    Scanner --> Cache
    
    Filters --> Storage
    HTML --> Storage
```

---

## 📊 Fluxo de Dados

```mermaid
graph LR
    subgraph "Input"
        I1[RSS Feeds]
        I2[YouTube]
        I3[APIs]
        I4[HTML Sites]
    end
    
    subgraph "Processing"
        P1[Fetch]
        P2[Parse]
        P3[Filter]
        P4[Dedupe]
        P5[Format]
    end
    
    subgraph "Storage"
        S1[History]
        S2[State]
        S3[Database]
        S4[Config]
    end
    
    subgraph "Output"
        O1[Discord]
        O2[Node-RED]
        O3[Logs]
    end
    
    I1 --> P1
    I2 --> P1
    I3 --> P1
    I4 --> P1
    
    P1 --> P2
    P2 --> P3
    P3 --> P4
    P4 --> P5
    
    P4 --> S1
    P4 --> S2
    P5 --> S3
    P3 --> S4
    
    P5 --> O1
    P5 --> O2
    P1 --> O3
    P2 --> O3
    P3 --> O3
```

---

## 🔐 Camada de Segurança

```mermaid
graph TB
    subgraph "🛡️ Security Layers"
        L1[Container Isolation<br/>🐳 Docker]
        L2[Active Defense<br/>🚨 Honeypots]
        L3[Access Control<br/>🔐 Permissions]
        L4[Audit Logging<br/>📝 Logs]
    end
    
    subgraph "🔒 Protection Mechanisms"
        P1[File Locking<br/>🔐 Race Condition Prevention]
        P2[Atomic Writes<br/>💾 Data Integrity]
        P3[Input Validation<br/>✅ Sanitization]
        P4[Rate Limiting<br/>⏱️ API Protection]
    end
    
    L1 --> P1
    L2 --> P3
    L3 --> P4
    L4 --> P2
```

---

## 💾 Estrutura de Persistência

```mermaid
graph TB
    subgraph "📁 Data Files"
        Config[config.json<br/>⚙️ Guild Configurations<br/>📋 Filters per Guild<br/>🌍 Language Settings]
        History[history.json<br/>📜 Link History<br/>🔢 Max 2000 items<br/>🚫 Deduplication]
        State[state.json<br/>📊 Scanner State<br/>🧹 Auto-cleanup<br/>📦 HTTP Cache<br/>🔐 HTML Hashes]
        DB[database.json<br/>💾 News Database<br/>📈 Statistics<br/>📅 Timestamps]
    end
    
    subgraph "📦 Backup System"
        Backup[Backups/<br/>📦 Auto Backups<br/>🕐 Retention: 90 days<br/>🔢 Max: 30 per file]
    end
    
    subgraph "🔧 Storage Utils"
        Storage[storage.py<br/>💾 Safe Read/Write<br/>🔐 File Locking<br/>✅ Atomic Operations]
        Cleanup[state_cleanup.py<br/>🧹 Auto Cleanup<br/>⏰ Time-based<br/>📊 Size-based]
    end
    
    Config --> Storage
    History --> Storage
    State --> Storage
    DB --> Storage
    
    Storage --> Backup
    Cleanup --> State
    
    Backup --> Config
    Backup --> History
    Backup --> State
    Backup --> DB
```

---

## 🌐 Integração com APIs Externas

```mermaid
graph LR
    subgraph "🔎 Scanner"
        S[Scanner Core]
    end
    
    subgraph "🌐 APIs"
        NVD[NVD/NIST<br/>🛡️ CVEs<br/>CVSS > 7.0]
        OTX[AlienVault OTX<br/>🛸 Threat Pulses<br/>Active Campaigns]
        URLScan[URLScan.io<br/>🔍 URL Analysis<br/>Screenshots]
        VT[VirusTotal<br/>🦠 Reputation<br/>File Analysis]
    end
    
    subgraph "📡 Services"
        NS[News Service<br/>📰 RSS Aggregation]
        CS[CVE Service<br/>🛡️ CVE Details]
        TS[Threat Service<br/>🛸 Threat Intel]
    end
    
    S --> NS
    S --> CS
    S --> TS
    
    NS --> NVD
    CS --> NVD
    TS --> OTX
    TS --> URLScan
    TS --> VT
```

---

## 📈 Monitoramento e Telemetria

```mermaid
graph TB
    subgraph "📊 Metrics Collection"
        Stats[Statistics Core<br/>⏱️ Uptime<br/>🔎 Scans<br/>📰 Posts<br/>📦 Cache Hits]
    end
    
    subgraph "📤 Output Channels"
        Discord[Discord<br/>💬 /status command]
        NodeRED[Node-RED<br/>📊 Dashboard]
        Web[Web Server<br/>🌍 /api/stats]
        Logs[Log Files<br/>📝 bot.log]
    end
    
    Stats --> Discord
    Stats --> NodeRED
    Stats --> Web
    Stats --> Logs
```

---

## 🔄 Ciclo de Vida do Bot

```mermaid
stateDiagram-v2
    [*] --> Initializing: Bot Start
    Initializing --> Loading: Load Configs
    Loading --> Connecting: Connect Discord
    Connecting --> Ready: Connected
    Ready --> Scanning: Timer Trigger
    Scanning --> Processing: Fetch Data
    Processing --> Filtering: Apply Filters
    Filtering --> Posting: Match Found
    Posting --> Saving: Save State
    Saving --> Ready: Complete
    Filtering --> Ready: No Match
    Ready --> Scanning: Next Cycle
    Ready --> [*]: Bot Stop
```

---

## 📚 Referências Arquiteturais

- **Padrão Cogs**: Modularização do discord.py
- **Separation of Concerns**: Cada módulo tem responsabilidade única
- **Dependency Injection**: Serviços injetados via bot instance
- **Observer Pattern**: Eventos do Discord
- **Strategy Pattern**: Filtros configuráveis por guild

---

<div align="center">

**🏗️ Arquitetura Modular e Escalável**

[⬆ Voltar ao README](./README.md)

</div>
