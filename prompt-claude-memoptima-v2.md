# MemOptima v3.1 ULTIMATE — Documentação Completa do Projeto

> Otimizador de memória RAM de 7 camadas para Windows, com interface gráfica premium (Tkinter), monitoramento em tempo real, system tray, e módulo adicional de compressão de memória virtual. Atualizado com inteligência de contexto na v3.1.

---

## 📋 Índice

1. [Visão Geral](#-visão-geral)
2. [Arquitetura do Projeto](#-arquitetura-do-projeto)
3. [Estrutura de Arquivos](#-estrutura-de-arquivos)
4. [Requisitos e Dependências](#-requisitos-e-dependências)
5. [Motor de Otimização — 7 Camadas](#-motor-de-otimização--7-camadas)
6. [Interface Gráfica (memoptima.py)](#-interface-gráfica-memoptimapy)
7. [VirtualRAM Compressor (vram_compressor.py)](#-virtualram-compressor-vram_compressorpy)
8. [Scripts Utilitários (.bat)](#-scripts-utilitários-bat)
9. [Como Instalar e Executar](#-como-instalar-e-executar)
10. [Compilação para .EXE](#-compilação-para-exe)
11. [Decisões Técnicas e Design](#-decisões-técnicas-e-design)
12. [Segurança e Proteções](#-segurança-e-proteções)
13. [Referência de APIs do Windows Utilizadas](#-referência-de-apis-do-windows-utilizadas)

---

## 🎯 Visão Geral

O **MemOptima v3 ULTIMATE** é um otimizador de memória RAM avançado para Windows, escrito inteiramente em Python. Ele é projetado especialmente para máquinas com pouca RAM (2–4 GB), onde cada megabyte conta.

### Principais Funcionalidades (v3.1)

- **Motor de 7 camadas Smart** que poupa processos ativos, o aplicativo em primeiro plano e processos na whitelist
- **Auto-Modo Adaptativo** que ajusta o intervalo dinamicamente com base na pressão da RAM
- **Notificações Toast** nativas do Windows quando otimiza em segundo plano (tray)
- **Lista de Processos Agrupados** para melhor visualização, com menu de contexto para proteção (Whitelist)
- **Persistência de Configurações** via `config.json` e opção de **Iniciar com o Windows**
- **Gauge circular animado** com exibição de uso de RAM em tempo real
- **Sparkline** com histórico de uso dos últimos 3 minutos
- **VirtualRAM Compressor** — módulo add-on independente para otimização de memória virtual (Pagefile/Swap)
- **7 scripts .bat** para otimizações complementares no nível do sistema operacional
- **Tema Dark Ocean / Neon Blue** com design premium

---

## 🏗️ Arquitetura do Projeto

```
┌─────────────────────────────────────────────────────┐
│                  MemOptima v3 ULTIMATE               │
├─────────────────────────────────────────────────────┤
│                                                     │
│  ┌─────────────────┐    ┌────────────────────────┐  │
│  │  MemOptimaApp   │    │  OptimizationEngine    │  │
│  │  (Interface)     │◄──►│  (7 Camadas)           │  │
│  │                  │    │                        │  │
│  │ • CircularGauge  │    │ L0: Privilege Elev.    │  │
│  │ • Sparkline      │    │ L1: SystemEmptyWS      │  │
│  │ • Process List   │    │ L2b: Per-Process Trim  │  │
│  │ • Settings       │    │ L3: (reservado)        │  │
│  │ • History Log    │    │ L4: PurgeStandby       │  │
│  └────────┬─────────┘    │ L5: FileCache          │  │
│           │              │ L6: PageCombine        │  │
│           │              └────────────────────────┘  │
│           │                                          │
│  ┌────────▼─────────┐    ┌────────────────────────┐  │
│  │  System Tray     │    │  VirtualRAM Compressor │  │
│  │  (pystray)       │    │  (processo separado)   │  │
│  └──────────────────┘    │                        │  │
│                          │ C1: PageCombine        │  │
│                          │ C2: PurgeStandby       │  │
│                          └────────────────────────┘  │
└─────────────────────────────────────────────────────┘
```

### Padrão de Comunicação

- O `OptimizationEngine` roda em **threads separadas** (auto-loop + otimização manual) e se comunica com a UI via **callbacks** + `root.after()` para thread-safety com Tkinter.
- O `VirtualRAM Compressor` é lançado como um **processo independente** (`subprocess.Popen`) — não compartilha estado com o processo principal.

---

## 📁 Estrutura de Arquivos

```
MemOptima/
│
├── memoptima.py                    # Aplicação principal (1211 linhas)
│                                   #   → OptimizationEngine (7 camadas)
│                                   #   → MemOptimaApp (GUI Tkinter)
│                                   #   → CircularGauge + Sparkline (widgets)
│                                   #   → System Tray (pystray)
│
├── vram_compressor.py              # Add-on: Otimizador de Memória Virtual (789 linhas)
│                                   #   → VirtualMemoryEngine (2 camadas: PageCombine + PurgeStandby)
│                                   #   → VirtualMemoryApp (GUI Tkinter independente)
│
├── requirements.txt                # Dependências: psutil, pystray, Pillow, pyinstaller
├── build.bat                       # Script de compilação para .EXE via PyInstaller
├── run_admin.bat                   # Lança memoptima.py com privilégios de Administrador
│
├── windows_amputator.bat           # ⚠ Desativa serviços pesados do Windows (permanente)
├── windows_restaurador.bat         # 🚑 Desfaz as alterações do Amputator
│
├── modo_sobrevivencia_temp.bat     # ☢ Modo de emergência: mata Explorer e serviços (temporário)
│
├── otimizar_ssd_4gb_ADMIN.bat      # Configura TRIM + trava pagefile em 4 GB
├── restaurar_pagefile_ADMIN.bat    # Restaura pagefile para gerenciamento automático
├── restaurar_memoria_virtual.bat   # Restaura memória virtual para padrão do sistema
│
├── test_spark.py                   # Script de teste (sparkline)
├── .venv/                          # Ambiente virtual Python
└── __pycache__/                    # Cache do Python
```

---

## 🛠️ Requisitos e Dependências

### Sistema Operacional
- **Windows 10/11** (x64) — APIs `ntdll`, `kernel32`, `psapi`, `advapi32`
- Recomendado: execução como **Administrador** para ativar todas as 7 camadas

### Python
- **Python 3.8+** (testado com 3.10, 3.11, 3.12)

### Bibliotecas (`requirements.txt`)

| Pacote       | Versão Mínima | Função                                      |
|-------------|---------------|----------------------------------------------|
| `psutil`    | ≥ 5.9.0       | Métricas de memória, CPU e lista de processos |
| `pystray`   | ≥ 0.19.0      | Ícone na bandeja do sistema (System Tray)     |
| `Pillow`    | ≥ 10.0.0      | Geração do ícone para o System Tray           |
| `pyinstaller`| ≥ 6.0.0      | Compilação para executável .EXE               |

> **Nota:** `pystray` e `Pillow` são opcionais — o app funciona sem System Tray caso não estejam instalados. `pyinstaller` é necessário apenas para compilar o .EXE.

---

## ⚡ Motor de Otimização — 7 Camadas

O coração do MemOptima é o `OptimizationEngine`, que aplica **até 7 camadas** de otimização de memória em sequência. As camadas de sistema (L1, L3–L6) requerem privilégios de **Administrador**.

### Diagrama de Camadas

```
Camada │ API Usada                             │ Admin? │ Descrição
───────┼───────────────────────────────────────┼────────┼──────────────────────────────────
  L0   │ AdjustTokenPrivileges (advapi32)      │  Sim   │ Habilita SeDebugPrivilege,
       │                                       │        │ SeIncreaseQuotaPrivilege, etc.
───────┼───────────────────────────────────────┼────────┼──────────────────────────────────
  L1   │ NtSetSystemInformation(MemEmptyAllWS) │  Sim   │ Esvazia working set de TODOS
       │ (ntdll)                               │        │ os processos no sistema
───────┼───────────────────────────────────────┼────────┼──────────────────────────────────
  L2b  │ EmptyWorkingSet (psapi) +             │ Não*   │ Smart Trim per-process: pula app
       │ SetProcessWorkingSetSizeEx (kernel32)  │        │ ativo, CPU > 2% e whitelisted.
───────┼───────────────────────────────────────┼────────┼──────────────────────────────────
  L4   │ NtSetSystemInformation(MemPurge       │  Sim   │ Purga a Standby List do kernel
       │ StandbyList) (ntdll)                   │        │ (libera cache de disco da RAM)
───────┼───────────────────────────────────────┼────────┼──────────────────────────────────
  L5   │ SetSystemFileCacheSize (kernel32)     │  Sim   │ Reduz o file cache do sistema
       │                                       │        │ para mínimo razoável (256 MB)
───────┼───────────────────────────────────────┼────────┼──────────────────────────────────
  L6   │ NtSetSystemInformation(MemCombine     │  Sim   │ Deduplicação de páginas físicas
       │ PhysicalMemory) (ntdll)               │        │ idênticas (3 passes, zero I/O)
───────┼───────────────────────────────────────┼────────┼──────────────────────────────────
  Auto │ EmptyWorkingSet (psapi)               │  Não   │ Auto-trim do próprio processo
  Trim │                                       │        │ MemOptima após cada ciclo
```

> **\* L2b sem Admin:** Consegue fazer `EmptyWorkingSet` nos processos do próprio usuário, mas não consegue fazer `SetProcessWorkingSetSizeEx` (requer `PROCESS_SET_QUOTA`).

### Proteção de Swap (Swap Lock)

O motor verifica o uso de swap antes de cada otimização. Se o swap ultrapassar **3.4 GB**, as camadas de trim agressivo são **bloqueadas** para evitar que o sistema entre em thrashing (paginação excessiva).

### Processos Protegidos (Nunca Tocados)

```python
SYSTEM_PROCS = {
    "system", "registry", "smss.exe", "csrss.exe", "wininit.exe",
    "winlogon.exe", "lsass.exe", "lsm.exe", "services.exe",
    "svchost.exe", "dwm.exe", "fontdrvhost.exe", "lsaiso.exe",
    "memory compression", "secure system", "ntoskrnl.exe",
    "idle", "[system process]", "spoolsv.exe"
}
```

### Fluxo de Execução

```
optimize_now() → Thread → _run("manual") → _do_optimize()
                                │
                                ├─ Verificar Swap Lock (> 3.4 GB?)
                                ├─ Layer 1:  NtSetSystemInformation (SystemEmptyWS)    [Admin]
                                ├─ Layer 2b: EmptyWorkingSet + SetWSEx por processo     [Todos]
                                ├─ Layer 4:  NtSetSystemInformation (PurgeStandby)      [Admin]
                                ├─ Layer 5:  SetSystemFileCacheSize(1)                  [Admin]
                                ├─ Layer 6:  NtSetSystemInformation (PageCombine) ×3    [Admin]
                                ├─ Auto-Trim do próprio processo MemOptima
                                └─ Emitir callback "done" com métricas
```

---

## 🖥️ Interface Gráfica (`memoptima.py`)

### Design System — Dark Ocean / Neon Blue

| Token     | Hex       | Uso                           |
|-----------|-----------|-------------------------------|
| `BG`      | `#060913` | Fundo principal (deep ocean)  |
| `CARD`    | `#0b1021` | Cartões e painéis             |
| `C2`      | `#11182c` | Headers de seção              |
| `C3`      | `#192440` | Hover / Input backgrounds     |
| `WHT`     | `#f8fafc` | Texto principal               |
| `GRY`     | `#64748b` | Texto secundário (slate)      |
| `NEON`    | `#00d2ff` | Cor primária (Cyan/Neon Blue) |
| `NE2`     | `#00a1cc` | Estado ativo do cyan          |
| `ACCNT`   | `#a78bfa` | Violeta (acento secundário)   |
| `WARN`    | `#f59e0b` | Avisos (âmbar)                |
| `RED`     | `#f43f5e` | Alertas críticos (rosa/vermelho)|
| `BLU`     | `#38bdf8` | Informações (badge Admin)     |

### Componentes da UI

#### 1. Header
- Título "Mem" (branco) + "Optima" (neon) + "v3" (cinza)
- Badge de status: `★ ADMIN` (azul) ou `⚠ USER` (âmbar)
- Botão fullscreen (`⛶`) + botão para lançar o VirtualRAM Compressor (`🗜`)

#### 2. Card de Métricas (CircularGauge + Stats)
- **Gauge circular animado** (190px) com arco de 270° e dot indicator
  - Cor dinâmica: Cyan (< 65%) → Âmbar (65–85%) → Vermelho (> 85%)
  - Animação suave com interpolação (`diff * 0.12` por frame a 60fps)
- Labels: RAM Usada, Livre e Total em GB
- Indicador de limite: `✓ dentro do limite` ou `⚠ acima do limite`
- **Sparkline** com histórico de 90 pontos (≈ 3 minutos a cada 2s)

#### 3. Card de Ação
- Botão principal: `⚡ OTIMIZAR MEMÓRIA AGORA`
  - Hover effect (cyan → cyan escuro)
  - Estado disabled com animação de "OTIMIZANDO..."
  - Pulsação quando Auto-Modo está ativo
- Estatísticas: Última otimização, Total acumulado, Número de runs

#### 4. Barra de Camadas Ativas
- Exibe quais camadas foram disparadas na última otimização
- Formato: `L1: SystemEmptyWS  •  L2b: Trim(43)  •  L4: PurgeStandby`

#### 5. Card de Configurações
- Toggle Auto-Modo Adaptativo (ON/OFF)
- Campos: Limite (GB) e Intervalo base (segundos) com botão "Aplicar"
- Checkboxes: Cache Disco (L5) e Iniciar com Windows
- Visualização de processos na Whitelist

#### 6. Lista de Processos
- Top Consumidores de RAM (RSS) agrupados por nome (evita duplicatas)
- Ícone 🛡️ para processos protegidos na Whitelist
- Menu de contexto (botão direito) para proteger/desproteger
- Atualização a cada 10s (separada das métricas de 2s para reduzir I/O)

#### 7. Log de Otimizações
- Histórico com timestamp, trigger (AUTO/MANUAL), badge admin, MB recuperados
- Máximo de 30 linhas, com cores diferenciadas (neon = sucesso, âmbar = nada liberado)

### Intervalos de Monitoramento

| Métrica            | Intervalo | Motivo                                        |
|-------------------|-----------|-----------------------------------------------|
| RAM/Swap stats    | 2s        | Leitura leve de contadores do kernel          |
| Lista de processos| 10s       | Varredura pesada — reduz picos de I/O no SSD  |
| Auto-otimização   | 5s (check)| Verifica se ultrapassa limite configurado      |

---

## 🗜️ VirtualRAM Compressor (`vram_compressor.py`)

Módulo **add-on independente** focado na otimização da memória virtual (Pagefile/Swap). Roda como processo separado, lançável pelo botão `🗜 Compressor RAM` no MemOptima principal.

### Camadas do VirtualRAM Compressor

| Camada | API                                   | Admin? | Descrição                           |
|--------|---------------------------------------|--------|-------------------------------------|
| C1     | NtSetSystemInformation(PageCombine)   | Não    | Deduplicação de páginas (zero I/O)  |
| C2     | NtSetSystemInformation(PurgeStandby)  | Sim    | Purga cache de disco da RAM física  |

### Tema Visual

- Mesmo layout do MemOptima principal, mas com **acento Violeta** (`#a78bfa`) em vez de Cyan
- Gauge mostra uso de **SWAP** em vez de RAM
- Lista de processos ordena por **VMS** (Virtual Memory Size) em vez de RSS

---

## 🔧 Scripts Utilitários (.bat)

### Execução e Build

| Script                   | Admin? | Descrição                                           |
|--------------------------|--------|-----------------------------------------------------|
| `run_admin.bat`          | Sim    | Lança `memoptima.py` com `RunAs` (eleva privilégios)|
| `build.bat`              | Não    | Compila para `dist/MemOptima.exe` via PyInstaller   |

### Otimização do Sistema

| Script                          | Admin? | Permanente? | Descrição                                              |
|---------------------------------|--------|-------------|--------------------------------------------------------|
| `windows_amputator.bat`         | Sim    | **Sim**     | Desativa SysMain, WSearch, DiagTrack, Xbox, Cortana    |
| `windows_restaurador.bat`       | Sim    | **Sim**     | Desfaz todas as alterações do Amputator                |
| `modo_sobrevivencia_temp.bat`   | Sim    | **Não**     | Mata Explorer + serviços pesados (volta ao reiniciar)  |

### Gerenciamento de Pagefile/SSD

| Script                           | Admin? | Descrição                                            |
|----------------------------------|--------|------------------------------------------------------|
| `otimizar_ssd_4gb_ADMIN.bat`     | Sim    | Ativa TRIM no SSD + trava pagefile em 4 GB fixo      |
| `restaurar_pagefile_ADMIN.bat`   | Sim    | Restaura pagefile para gerenciamento automático       |
| `restaurar_memoria_virtual.bat`  | Sim    | Restaura memória virtual para padrão do Windows       |

### Detalhamento do Windows Amputator

O script `windows_amputator.bat` desativa os seguintes serviços do Windows para reduzir o consumo de RAM base:

1. **SysMain (Superfetch)** — pré-carrega apps na RAM; pesado em sistemas com pouca memória
2. **WSearch (Windows Search)** — indexador de arquivos; consome RAM e I/O no SSD
3. **DiagTrack + dmwappushservice** — telemetria da Microsoft
4. **Aplicativos em Segundo Plano** — desativa globalmente via registro
5. **Xbox Live Services + Cortana** — XblAuthManager, XblGameSave, XboxNetApiSvc

> ⚠ **Essas alterações são permanentes** até executar o `windows_restaurador.bat`. Requer reinicialização.

### Detalhamento do Modo Sobrevivência

O script `modo_sobrevivencia_temp.bat` é para situações extremas (ex: < 1 GB de RAM livre):

1. Para: Windows Update, DiagTrack, BITS, WSearch, SysMain, Spooler, Themes, Xbox
2. Abre o Gerenciador de Tarefas como "área de trabalho" substituta
3. **Mata o `explorer.exe`** — tela preta, sem barra de tarefas
4. Para abrir programas: `Arquivo → Executar nova tarefa` no Gerenciador de Tarefas
5. **Tudo volta ao normal ao reiniciar o computador**

---

## 🚀 Como Instalar e Executar

### 1. Clonar / Baixar o Projeto

```bash
git clone <url-do-repositório>
cd MemOptima
```

### 2. Criar Ambiente Virtual (Recomendado)

```bash
python -m venv .venv
.venv\Scripts\activate
```

### 3. Instalar Dependências

```bash
pip install -r requirements.txt
```

### 4. Executar (Modo Usuário)

```bash
python memoptima.py
```

> Neste modo, apenas a **Camada 2b** (EmptyWorkingSet por processo) estará ativa.

### 5. Executar com Administrador (Recomendado — 7 Camadas)

```bash
# Opção A: Usar o script fornecido
run_admin.bat

# Opção B: Manualmente
# Abrir o cmd/PowerShell como Administrador, depois:
python memoptima.py
```

### 6. Executar o VirtualRAM Compressor (Opcional)

```bash
python vram_compressor.py
```

Ou clique no botão `🗜 Compressor RAM` dentro do MemOptima.

---

## 📦 Compilação para .EXE

Execute o script de build:

```bash
build.bat
```

Isso irá:
1. Instalar `pystray`, `Pillow`, `psutil`, `pyinstaller`
2. Compilar com `pyinstaller --onefile --windowed --noconsole`
3. Gerar `dist/MemOptima.exe`

Para executar como Administrador:
> Clique direito em `MemOptima.exe` → **Executar como Administrador**

---

## 🧠 Decisões Técnicas e Design

### Por que Tkinter?
- **Zero dependências externas** para a GUI — incluso no Python padrão
- Máxima compatibilidade com sistemas Windows antigos / limitados
- Leve em consumo de RAM (comparado a Electron, Qt, etc.)

### Por que `ctypes` direto e não wrappers?
- Controle total sobre as APIs do Windows sem dependências intermediárias
- `EmptyWorkingSet`, `NtSetSystemInformation`, `SetProcessWorkingSetSizeEx` não têm wrappers em nenhuma biblioteca Python popular
- Tipagem explícita (`restype`, `argtypes`) evita bugs silenciosos em chamadas FFI

### Separação de Intervalos (2s vs 10s)
- Ler `psutil.virtual_memory()` é uma chamada leve ao kernel (microsegundos)
- Ler `psutil.process_iter(['memory_info'])` para 50+ processos gera I/O significativo
- Em SSDs de baixa capacidade, os picos de leitura a cada 2s causavam desgaste desnecessário

### Layer 3 (FlushModifiedList) — Removida Intencionalmente
- Forçar flush da Modified Page List causava **picos de escrita no SSD**
- O Windows já faz flush automático quando necessário
- Para SSDs de 128 GB (comum em máquinas de 4 GB RAM), reduzir escritas é prioridade

### Auto-Trim do Próprio Processo
- O processo Python acumula working set ao longo do tempo (GC, imports, etc.)
- Após cada ciclo de otimização, o MemOptima esvazia seu próprio WS
- Isso mantém o footprint do app em ≈ 15–25 MB consistentemente

---

## 🔒 Segurança e Proteções

1. **Lista de processos críticos** — 19 processos do sistema são sempre ignorados
2. **Swap Lock** — Se swap > 3.4 GB, trim agressivo é bloqueado
3. **Tratamento silencioso** — `AccessDenied` e `NoSuchProcess` são capturados sem travar o app
4. **Thread-safety** — Toda comunicação Engine → GUI passa por `root.after(0, ...)`
5. **Daemon threads** — Todas as threads são daemon (morrem com o processo principal)
6. **Modo Sobrevivência é temporário** — Tudo volta ao normal com reinicialização
7. **Restauradores** — Para cada script destrutivo, existe um script de restauração

---

## 📚 Referência de APIs do Windows Utilizadas

### kernel32.dll

| Função                       | Uso no MemOptima                                |
|------------------------------|-------------------------------------------------|
| `OpenProcess`                | Obter handle de processo com permissões de trim |
| `CloseHandle`                | Liberar handles após uso                        |
| `GetCurrentProcess`          | Obter handle do próprio processo (auto-trim)    |
| `SetProcessWorkingSetSizeEx` | Forçar trim agressivo do WS (Layer 2b, Admin)   |
| `SetSystemFileCacheSize`     | Reduzir file cache do sistema (Layer 5, Admin)   |

### psapi.dll

| Função           | Uso no MemOptima                                      |
|------------------|-------------------------------------------------------|
| `EmptyWorkingSet`| Esvaziar working set de um processo (Layer 2b / auto-trim) |

### ntdll.dll

| Função                    | Constante | Uso no MemOptima                           |
|---------------------------|-----------|--------------------------------------------|
| `NtSetSystemInformation`  | 80 + 2    | System-wide empty WS (Layer 1, Admin)      |
| `NtSetSystemInformation`  | 80 + 4    | Purge standby list (Layer 4, Admin)        |
| `NtSetSystemInformation`  | 80 + 5    | Page combining/dedup (Layer 6, Admin)      |

### advapi32.dll

| Função                    | Uso no MemOptima                                        |
|---------------------------|---------------------------------------------------------|
| `OpenProcessToken`        | Abrir token de segurança do processo atual               |
| `LookupPrivilegeValueW`   | Resolver nome de privilégio para LUID                    |
| `AdjustTokenPrivileges`   | Habilitar SeDebugPrivilege, SeIncreaseQuotaPrivilege, etc.|

### Privilégios Habilitados (Layer 0)

| Privilégio                        | Necessário Para                          |
|-----------------------------------|------------------------------------------|
| `SeDebugPrivilege`                | Abrir handles de processos de outros usuários |
| `SeIncreaseQuotaPrivilege`        | `SetProcessWorkingSetSizeEx`             |
| `SeProfileSingleProcessPrivilege` | Operações de profiling de memória        |
| `SeLockMemoryPrivilege`           | Operações de lock/unlock de páginas      |

---

## 🎮 Atalhos de Teclado

| Tecla     | Ação                              |
|-----------|-----------------------------------|
| `F11`     | Alternar modo tela cheia          |
| `Escape`  | Sair do modo tela cheia           |

---

## 📊 Métricas Exibidas na UI

### MemOptima Principal (RAM Física)
- **Uso de RAM (%)** — Gauge circular + Sparkline
- **RAM Usada / Livre / Total** — Em GB, atualizado a cada 2s
- **Status do Limite** — Compara uso atual vs limite configurado
- **Top 8 Processos** — Nome, RAM (MB), PID, barra visual
- **Log de Otimizações** — Timestamp, trigger, camadas ativadas, MB liberados

### VirtualRAM Compressor (Pagefile/Swap)
- **Uso de Swap (%)** — Gauge circular + Sparkline
- **Swap Usado / Livre / Total** — Em GB
- **Top 8 Processos por VMS** — Virtual Memory Size
- **Log de Compressões** — Timestamp, trigger, camadas ativadas

---

## 🔄 System Tray

O MemOptima pode rodar em segundo plano na bandeja do sistema. O ícone é gerado programaticamente via `Pillow`:

- Círculo escuro com borda neon (cyan para MemOptima, violeta para VRAM)
- Linha em "M" estilizada (MemOptima) ou linhas convergentes (VRAM)

### Menu do System Tray

| Item                  | Ação                               |
|-----------------------|------------------------------------|
| Abrir MemOptima       | Restaura a janela principal        |
| ⚡ Otimizar Agora     | Dispara otimização manual          |
| Auto-Modo: ON/OFF     | Liga/desliga o auto-modo           |
| Sair                  | Encerra completamente o programa   |

---

*Documentação gerada para o MemOptima v3 ULTIMATE — Setembro 2026*
