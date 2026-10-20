# MemOptima

> **Instituto Federal de Rondônia — Campus Porto Velho Calama**
> Curso: Desenvolvimento de Sistemas | Disciplina: Programar com IA de forma responsável

**MemOptima** e um otimizador de memoria RAM para Windows voltado a computadores com 2-4 GB de RAM. Monitora o consumo em tempo real e aplica ate 7 camadas de limpeza de memoria usando APIs nativas do Windows — sem software de terceiros, sem internet, sem instalador.

---

## Funcionalidades

| Funcionalidade | Descricao |
|---|---|
| **Gauge circular animado** | Exibe o uso de RAM em % atualizado a cada 2 segundos |
| **Sparkline historico** | Grafico dos ultimos ~3 minutos de uso de RAM |
| **7 Camadas de otimizacao** | L0 a L6, do trim por processo ate combinacao de paginas fisicas |
| **Auto-Modo Adaptativo** | Dispara otimizacao automatica quando RAM ultrapassa o limite configurado |
| **Whitelist de processos** | Protege processos criticos de serem trimados (menu de contexto) |
| **Log persistido** | Historico de otimizacoes salvo em `optimization_log.jsonl` |
| **System Tray** | Continua rodando em segundo plano; notificacoes nativas do Windows |
| **VirtualRAM Compressor** | Modulo independente para otimizar o Pagefile/Swap |
| **Scripts .bat** | Amputador do Windows, Modo Sobrevivencia, otimizacao de SSD |
| **Compilacao .EXE** | Gera executavel unico via PyInstaller — sem Python instalado |

---

## Requisitos

- Windows 10 ou 11 (x64)
- Python 3.8+ **OU** o arquivo `MemOptima.exe` compilado

### Dependencias Python (instaladas automaticamente pelo build.bat)
```
psutil >= 5.9.0
pystray >= 0.19.0   (opcional — necessario para System Tray)
Pillow >= 10.0.0    (opcional — necessario para System Tray)
pyinstaller >= 6.0.0 (apenas para compilar o .EXE)
```

---

## Como usar

### Modo desenvolvimento (Python)

```cmd
:: Instalar dependencias
pip install -r requirements.txt

:: Rodar como usuario comum
python memoptima.py

:: Rodar como Administrador (ativa todas as 7 camadas)
run_admin.bat
```

### Modo distribuicao (executavel)

```cmd
:: Compilar o .EXE
build.bat

:: O executavel estara em:
dist\MemOptima.exe
```

> **Dica:** Para ativar todas as 7 camadas de otimizacao, execute como Administrador.
> Clique direito no `.exe` > *Executar como Administrador*.

---

## As 7 Camadas de Otimizacao

| Camada | Nome | Privilegio | Descricao |
|---|---|---|---|
| **L0** | Privilege Elevation | Admin | Habilita privilegios de memoria no token do processo |
| **L1** | System Empty WS | Admin | `NtSetSystemInformation(MemoryEmptyWorkingSet)` — esvazia working set de todos os processos |
| **L2b** | Smart Trim | Usuario | `EmptyWorkingSet` por processo com protecoes: CPU <2%, whitelist, anti-thrashing, foreground |
| **L4** | Purge Standby | Admin | `NtSetSystemInformation(MemoryPurgeStandbyList)` — libera cache de standby do kernel |
| **L5** | File Cache | Admin | `SetSystemFileCacheSize(256MB)` — reduz cache de arquivos do sistema |
| **L6** | Page Combine | Admin | `NtSetSystemInformation(MemoryCombinePhysicalMemory)` — deduplica paginas fisicas identicas |

### Protecoes de seguranca (sempre ativas)
- **SYSTEM_PROCS**: processos criticos do SO (lsass.exe, csrss.exe, etc.) nunca sao tocados
- **Swap Lock**: bloqueia camadas agressivas se Swap > limite configurado (padrao 4.0 GB)
- **Anti-Thrashing**: processos com spike de page faults sao poupados
- **Foreground Protection**: o processo em primeiro plano nunca e trimado

---

## Scripts .bat disponiveis

| Script | Descricao |
|---|---|
| `run_admin.bat` | Abre o MemOptima com privilegios de Administrador (UAC) |
| `build.bat` | Compila o projeto para `dist\MemOptima.exe` via PyInstaller |
| `windows_amputator.bat` | Desativa servicos pesados (SysMain, WSearch, DiagTrack, Xbox, Cortana) |
| `windows_restaurador.bat` | Restaura os servicos desativados pelo amputador |
| `modo_sobrevivencia_temp.bat` | Liberacao emergencial de RAM (revertida ao reiniciar) |
| `otimizar_ssd_4gb_ADMIN.bat` | Configura pagefile fixo no SSD + TRIM |
| `restaurar_pagefile_ADMIN.bat` | Restaura as configuracoes originais do pagefile |

---

## Estrutura do Projeto

```
MemOptima/
  memoptima.py              # Aplicacao principal
  vram_compressor.py        # Modulo VirtualRAM Compressor (independente)
  shared/
    config.py               # Persistencia: load/save config.json, log .jsonl
    design.py               # Tokens de design (cores, fontes)
    widgets.py              # CircularGauge, Sparkline (Tkinter)
    win_api.py              # APIs nativas do Windows via ctypes
  tests/
    test_config.py          # Testes de config, log, agrupamento de processos
    test_engine.py          # Testes do motor de otimizacao (Swap Lock, whitelist, etc.)
  config.json               # Configuracoes do usuario (gerado automaticamente)
  optimization_log.jsonl    # Historico persistido de otimizacoes
  requirements.txt          # Dependencias Python
  build.bat                 # Script de compilacao para .EXE
  SPEC.md                   # Especificacao completa do sistema
```

---

## Configuracoes (config.json)

| Chave | Padrao | Descricao |
|---|---|---|
| `limit_gb` | `4.0` | RAM usada (em GB) que dispara o Auto-Modo |
| `interval_sec` | `60` | Intervalo base do Auto-Modo (em segundos) |
| `auto_mode` | `true` | Ativar/desativar otimizacao automatica |
| `swap_lock_gb` | `4.0` | Limite do Swap Lock (GB) — acima disso, trim agressivo e bloqueado |
| `use_filecache` | `true` | Habilitar reducao do file cache (Camada L5) |
| `whitelist` | `[]` | Lista de processos protegidos |
| `start_with_windows` | `false` | Iniciar com o Windows (registro) |

---

## Rodando os Testes

```cmd
pip install pytest
python -m pytest tests\ -v
```

Resultado esperado: **29 testes passando**.

---

## Versao

**v3.3** — Outubro/2026

Melhorias em relacao a v3.2:
- `swap_lock_gb` agora configuravel (nao hardcoded)
- `vram_compressor.py` incluido automaticamente no `.EXE` via `--add-data`
- Corrigido: `_on_close` so persiste config quando usuario confirma
- Corrigido: Compressor e `run_admin.bat` usam `pythonw` / `CREATE_NO_WINDOW` (sem janelas de CMD em segundo plano)
- Adicionados testes do `OptimizationEngine` (`tests/test_engine.py`)

---

*MemOptima | Instituto Federal de Rondonia — Campus Porto Velho Calama | 2026*
