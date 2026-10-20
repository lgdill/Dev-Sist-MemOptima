# CHANGELOG — MemOptima

Todas as mudanças notáveis no projeto **MemOptima** estão documentadas neste arquivo.

O formato baseia-se no [Keep a Changelog](https://keepachangelog.com/pt-BR/1.0.0/) e este projeto adere ao [Versionamento Semântico](https://semver.org/lang/pt-BR/).

> **Nota Acadêmica (IFRO - Programar com IA de forma responsável):**  
> Este changelog documenta expressamente o processo de **revisão humana ativa** sobre as sugestões geradas pelos agentes de IA (Google Antigravity / Claude), comprovando decisões críticas tomadas pela equipe para garantir segurança, estabilidade e aderência à especificação.

---

## [3.3.0] — 2026-10-20

### 🛡️ Revisão Crítica Humana sobre Sugestões da IA
- **Supressão de janelas pretas de console do CMD:**
  - *Proposta da IA:* A IA sugeriu originalmente apenas utilizar `subprocess.DETACHED_PROCESS` no lançamento do compressor.
  - *Intervenção Humana / Correção:* Durante os testes em bancada, constatou-se que o `python.exe` continuava alocando janelas de terminal pretas que ficavam presas na área de trabalho. A equipe identificou a necessidade de adotar o binário **`pythonw.exe`** e a flag `subprocess.CREATE_NO_WINDOW`, além de ajustar o `run_admin.bat` com `-WindowStyle Hidden` para eliminar totalmente janelas órfãs em segundo plano.
- **Segurança na persistência no fechamento (`_on_close`):**
  - *Proposta da IA:* Chamar `_persist_config()` no início de `_on_close()`.
  - *Intervenção Humana:* Rejeitado. Se o usuário clicasse em "Cancelar" no diálogo de confirmação, suas preferências não confirmadas já teriam sobrescrito o arquivo. A chamada foi movida estritamente para dentro dos blocos onde há confirmação real de fechamento ou minimização para a bandeja.
- **Isolamento de CPU em formatação de log:**
  - *Intervenção Humana:* A função utilitária `fmt()` estava sendo redefinida dinamicamente a cada linha iterada no histórico de logs. Foi refatorada para escopo de módulo, eliminando overhead desnecessário de alocação de memória em loops.

### ✨ Adicionado
- Cobertura de testes unitários para o `OptimizationEngine` em [`tests/test_engine.py`](tests/test_engine.py) (12 novos testes: Swap Lock, Whitelist, Anti-Thrashing por spike de page faults e disparo de Auto-Modo).
- Configuração dinâmica de `swap_lock_gb` via `config.json` e `shared/config.py` (substituindo valor fixo hardcoded de 4.0 GB).
- Empacotamento automático do `vram_compressor.py` no build único do PyInstaller (`build.bat`) via `--add-data` e `--hidden-import`.
- Roteamento CLI no `memoptima.py`: ao ser invocado com `--vram-compressor`, executa o compressor diretamente dentro do binário compilado.
- Arquivo de especificação de banco de dados relacional [`database/schema.sql`](database/schema.sql) com tabelas de usuários, configurações, whitelist, logs e snapshots de memória.
- Template de variáveis de ambiente [`.env.example`](.env.example) e configuração no `.gitignore`.
- Simulador Web interativo [`index.html`](index.html) para uso imediato em navegador sem necessidade de instalação local.

### 🐛 Corrigido
- Janelas de prompt de comando (CMD) permanecendo abertas ao rodar [`run_admin.bat`](run_admin.bat) ou ao abrir o VirtualRAM Compressor.
- Falhas em testes unitários em ambientes não-Windows através de mocks refinados de chamadas Win32 `ctypes`.

---

## [3.2.0] — 2026-10-19

### 🛡️ Revisão Crítica Humana sobre Sugestões da IA
- **Substituição de comandos WMI legados por CIM Cmdlets:**
  - *Proposta da IA:* Uso de comandos `wmic pagefilesetting` e chamadas `wmi` diretas.
  - *Intervenção Humana:* O utilitário `wmic.exe` foi descontinuado pela Microsoft no Windows 11 24H2. A equipe substituiu todas as chamadas pelos cmdlets modernos do PowerShell (`Get-CimInstance` e `Set-CimInstance`), prevenindo falhas silenciosas do sistema.
- **Segurança no Pagefile fixo de 4 GB:**
  - *Intervenção Humana:* Travar permanentemente o pagefile em 4 GB em SSDs poderia degradar a estabilidade do sistema a longo prazo. Foi implementado o agendamento de restauração temporária via Agendador de Tarefas do Windows (`schtasks`), revertendo para gerenciamento automático na reinicialização subsequente.

### ✨ Adicionado
- Refatoração modular criando o pacote `shared/`:
  - `shared/design.py`: design tokens (cores neon, violet, fontes e estilos).
  - `shared/widgets.py`: componentes desacoplados `CircularGauge` e `Sparkline`.
  - `shared/win_api.py`: centralização segura de chamadas `ctypes` para Win32 e NTDLL.
  - `shared/config.py`: leitura e escrita atômica de configuração e logs.
- Suíte inicial de testes unitários para persistência em [`tests/test_config.py`](tests/test_config.py).

---

## [3.0.0] — 2026-10-15

### ✨ Adicionado
- Arquitetura de 7 camadas de otimização de memória (L0 a L6):
  - L0: Anti-Thrashing (ignora processos com alta taxa de page faults).
  - L1: Trim seletivo de processos não-essenciais.
  - L2: EmptyWorkingSet do usuário.
  - L3: Flush global do sistema operacional via `NtSetSystemInformation`.
  - L4: Esvaziamento de Standby List do kernel.
  - L5: Redução de cache do sistema de arquivos.
  - L6: Deduplicação de páginas idênticas de memória física (Page Combining).
- Suporte a execução em segundo plano com ícone na bandeja do sistema (System Tray) via `pystray`.
- Notificações Toast nativas do Windows para alertas de memória crítica.
- Whitelist de proteção de processos com menu de contexto com clique com o botão direito.

---

## [2.0.0] — 2026-10-05

### ✨ Adicionado
- Interface gráfica com tema escuro Cyberpunk Neon desenvolvida em Tkinter nativo (sem dependências pesadas de GUI).
- Sparkline com histórico dinâmico de consumo de RAM.
- Módulo independente VirtualRAM Compressor para otimização de Pagefile/Swap.
- Scripts de automação administrativa: `windows_amputator.bat`, `modo_sobrevivencia_temp.bat`, `otimizar_ssd_4gb_ADMIN.bat`.

---

## [1.0.0] — 2026-09-25

### ✨ Adicionado
- Versão inicial do motor de monitoramento de memória RAM baseado em `psutil`.
- Script básico de limpeza de memória de processos locais.
- Planejamento e elaboração da Spec Inicial (`SPEC.md`).
