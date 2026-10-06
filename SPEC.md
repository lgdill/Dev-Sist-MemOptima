# SPEC.md — MemOptima

> **Instituto Federal de Rondônia — Campus Porto Velho Calama**
> Curso: Desenvolvimento de Sistemas
> Disciplina: Programar com IA de forma responsável
> Documento: Spec Inicial — Fase 1

---

## 1. Objetivo

O **MemOptima** é um sistema desktop para Windows que monitora o consumo de memória RAM em tempo real e executa otimizações automáticas ou manuais para liberar memória, prolongar a vida útil do SSD e melhorar a responsividade de máquinas com recursos limitados (2–4 GB de RAM).

O sistema é voltado para **usuários domésticos e estudantes** que utilizam computadores com pouca memória e precisam de uma ferramenta leve, confiável e de uso sem conhecimento técnico avançado, sem depender de serviços pagos ou soluções invasivas de terceiros.

---

## 2. Usuários

| Tipo de Usuário | Permissões e Ações |
|---|---|
| **Usuário comum** (sem admin) | Visualizar métricas de RAM em tempo real; executar otimização manual (Camada 2b — EmptyWorkingSet por processo do próprio usuário); configurar limite de RAM e intervalo de auto-modo; gerenciar whitelist de processos protegidos; acessar log de otimizações; minimizar para system tray. |
| **Usuário administrador** (com admin) | Tudo do usuário comum, mais: ativar as 7 camadas de otimização (L0–L6); purgar Standby List do kernel; reduzir file cache do sistema; executar deduplicação de páginas físicas; habilitar/desabilitar serviços pesados do Windows (Amputador); executar modo sobrevivência temporário; gerenciar pagefile/SSD. |

> **Nota:** O sistema detecta automaticamente o nível de privilégio no arranque e exibe badge `ADMIN` ou `USER` na interface. Não há cadastro/login convencional — a autenticação é delegada ao próprio mecanismo de controle de acesso do Windows (UAC/RunAs).

---

## 3. Casos de Uso Principais

| ID | Caso de Uso | Ator |
|---|---|---|
| UC01 | Monitorar uso de RAM e Swap em tempo real | Usuário comum / Admin |
| UC02 | Executar otimização manual de memória | Usuário comum / Admin |
| UC03 | Ativar/desativar Auto-Modo Adaptativo | Usuário comum / Admin |
| UC04 | Configurar limite de RAM e intervalo de otimização | Usuário comum / Admin |
| UC05 | Proteger processo via Whitelist (menu de contexto) | Usuário comum / Admin |
| UC06 | Consultar log de otimizações anteriores | Usuário comum / Admin |
| UC07 | Minimizar para System Tray e otimizar em segundo plano | Usuário comum / Admin |
| UC08 | Executar otimização de Memória Virtual (Pagefile/Swap) | Usuário comum / Admin |
| UC09 | Desativar/restaurar serviços pesados do Windows | Admin |
| UC10 | Ativar modo sobrevivência (emergência) | Admin |
| UC11 | Configurar pagefile fixo no SSD + TRIM | Admin |
| UC12 | Compilar/distribuir o app como executável (.EXE) | Admin |

---

## 4. Requisitos Funcionais (RF)

| ID | Descrição | Caso de Uso |
|---|---|---|
| **RF01** | O sistema deve exibir o percentual de uso de RAM atualizado a cada 2 segundos em um gauge circular animado. | UC01 |
| **RF02** | O sistema deve exibir RAM usada, livre e total em GB em tempo real. | UC01 |
| **RF03** | O sistema deve exibir um sparkline com histórico dos últimos 90 pontos de leitura (aprox. 3 minutos). | UC01 |
| **RF04** | O sistema deve exibir o uso de Swap/Pagefile atualizado a cada 2 segundos. | UC01 |
| **RF05** | O sistema deve executar otimização de memória sob demanda ao clicar no botão "Otimizar Agora". | UC02 |
| **RF06** | A otimização deve aplicar até 7 camadas sequenciais (L0–L6) conforme o nível de privilégio disponível. | UC02 |
| **RF07** | O sistema deve proteger processos críticos do sistema operacional (lista SYSTEM_PROCS) de qualquer trimagem. | UC02, UC05 |
| **RF08** | O sistema deve ativar/desativar o Auto-Modo Adaptativo que dispara otimizações automaticamente quando a RAM ultrapassa o limite configurado. | UC03 |
| **RF09** | O sistema deve ajustar dinamicamente o intervalo de otimização automática com base na pressão de RAM atual. | UC03 |
| **RF10** | O sistema deve permitir ao usuário configurar o limite de RAM (em GB) e o intervalo base de auto-otimização (em segundos). | UC04 |
| **RF11** | O sistema deve persistir as configurações (limite, intervalo, whitelist, auto-modo, iniciar com Windows) em `config.json`. | UC04 |
| **RF12** | O sistema deve permitir adicionar e remover processos da whitelist via menu de contexto na lista de processos. | UC05 |
| **RF13** | A Camada 2b (Smart Trim por processo) deve pular processos com CPU maior que 2%, processos na whitelist, o processo em primeiro plano e processos com saltos bruscos de page faults. | UC02, UC05 |
| **RF14** | O sistema deve bloquear as camadas de trim agressivo se o uso de Swap ultrapassar 4,0 GB (Swap Lock). | UC02 |
| **RF15** | O sistema deve registrar cada otimização no log de histórico com timestamp, trigger (AUTO/MANUAL), camadas ativadas e MB liberados. | UC06 |
| **RF16** | O log deve manter no máximo 30 entradas, removendo as mais antigas ao atingir o limite. | UC06 |
| **RF17** | O sistema deve permitir minimizar para o System Tray, continuando a otimização automática em segundo plano. | UC07 |
| **RF18** | O sistema deve exibir notificações Toast nativas do Windows ao otimizar em segundo plano pelo tray. | UC07 |
| **RF19** | O menu do tray deve oferecer: "Abrir MemOptima", "Otimizar Agora", "Auto-Modo ON/OFF" e "Sair". | UC07 |
| **RF20** | O sistema deve disponibilizar o módulo VirtualRAM Compressor como processo independente, lançável pelo botão na interface principal. | UC08 |
| **RF21** | O VirtualRAM Compressor deve aplicar PageCombine (C1) e PurgeStandby (C2) sobre a memória virtual/Pagefile. | UC08 |
| **RF22** | O sistema deve oferecer o script `windows_amputator.bat` para desativar servicos pesados (SysMain, WSearch, DiagTrack, Xbox, Cortana) e o `windows_restaurador.bat` para reverter. | UC09 |
| **RF23** | O sistema deve oferecer o script `modo_sobrevivencia_temp.bat` para liberação emergencial temporária de RAM (efeito revertido ao reiniciar). | UC10 |
| **RF24** | O sistema deve oferecer os scripts `otimizar_ssd_4gb_ADMIN.bat` e `restaurar_pagefile_ADMIN.bat` para gerenciamento de pagefile e TRIM no SSD. | UC11 |
| **RF25** | O sistema deve ser compilável para um único executável Windows (`.EXE`) via script `build.bat` utilizando PyInstaller. | UC12 |
| **RF26** | O sistema deve exibir na interface o badge de privilégio (`ADMIN` ou `USER`) e adaptar as camadas disponíveis de acordo. | UC01, UC02 |
| **RF27** | O sistema deve suportar alternância para modo tela cheia via F11 e retorno via Escape. | UC01 |

---

## 5. Requisitos Não Funcionais (RNF)

| ID | Categoria | Descrição |
|---|---|---|
| **RNF01** | **Segurança — Processos críticos** | Os processos do sistema listados em `SYSTEM_PROCS` nunca serão tocados por nenhuma camada de otimização, mesmo em modo Admin. |
| **RNF02** | **Segurança — Privilégios mínimos** | O sistema solicita elevação de privilégio (UAC/RunAs) apenas quando o usuário opta por executar como Admin. Em modo usuário, opera exclusivamente sobre os processos do próprio usuário. |
| **RNF03** | **Segurança — Swap Lock** | As camadas de trim agressivo são bloqueadas automaticamente se o uso de Swap for maior que 4,0 GB para evitar thrashing e corrupção de dados. |
| **RNF04** | **Segurança — Anti-Thrashing** | A Camada 2b monitora page faults por processo; processos com aumentos bruscos são poupados para evitar loops de paginação excessiva no SSD. |
| **RNF05** | **Segurança — Reversibilidade** | Para cada script destrutivo existe um script de restauração (`windows_amputator.bat` com `windows_restaurador.bat`; `otimizar_ssd_4gb_ADMIN.bat` com `restaurar_pagefile_ADMIN.bat`). O modo sobrevivência e temporario (revertido com reinicialização). |
| **RNF06** | **Segurança — Thread-safety** | Toda comunicação entre o motor de otimização e a interface gráfica é feita via `root.after(0, callback)` do Tkinter para evitar race conditions. |
| **RNF07** | **Desempenho — Footprint do app** | O próprio processo MemOptima deve manter working set menor ou igual a 30 MB em operação normal, via auto-trim após cada ciclo de otimização. |
| **RNF08** | **Desempenho — Frequência de leitura** | Métricas de RAM/Swap são atualizadas a cada 2 s; a lista de processos é varrida a cada 10 s para reduzir I/O no SSD. |
| **RNF09** | **Desempenho — Responsividade da UI** | A interface gráfica nunca deve travar durante otimizações; todas as operações pesadas rodam em threads daemon separadas da thread principal do Tkinter. |
| **RNF10** | **Compatibilidade** | O sistema deve funcionar no Windows 10/11 x64. Requer Python 3.8+ ou o .EXE compilado. Funciona sem pystray/Pillow instalados (degradação graciosa — sem tray). |
| **RNF11** | **Manutenibilidade — Scripts reversíveis** | Todos os scripts `.bat` que alteram configurações permanentes do sistema devem conter comentários claros e o caminho de reversão explícito. |
| **RNF12** | **Persistência de configurações** | O arquivo `config.json` deve ser escrito de forma atomica para evitar corrupção em caso de encerramento abrupto. |

---

## 6. Modelo de Dados (DER Simplificado)

O MemOptima não utiliza banco de dados relacional tradicional — os dados são persistidos localmente em `config.json` (configurações) e mantidos em memória durante a sessão (histórico de métricas e log). O modelo abaixo descreve as entidades principais do sistema e seus relacionamentos lógicos.

```
+-----------------------------+         +------------------------------+
|         Config              |         |       OptimizationLog        |
+-----------------------------+         +------------------------------+
| PK  id              TEXT   |         | PK  id              INTEGER  |
|     threshold_gb    FLOAT  |         |     timestamp        TEXT    |
|     interval_secs   INT    |         |     trigger          TEXT    | <- 'AUTO' | 'MANUAL'
|     auto_mode       BOOL   |         |     admin_mode       BOOL    |
|     cache_disk      BOOL   |         |     layers_active    TEXT    | <- ex: 'L1,L2b,L4,L6'
|     start_with_win  BOOL   |         |     mb_freed         FLOAT   |
|     swap_lock_gb    FLOAT  |<--------+     config_id        TEXT    | FK -> Config.id
+-----------------------------+         +------------------------------+
             |
             |
             v
+-----------------------------+         +------------------------------+
|        Whitelist            |         |       RamSnapshot            |
+-----------------------------+         +------------------------------+
| PK  id              INT    |         | PK  id              INTEGER  |
|     process_name    TEXT   |         |     timestamp        TEXT    |
|     added_at        TEXT   |         |     ram_used_gb      FLOAT   |
|     config_id       TEXT   | FK      |     ram_free_gb      FLOAT   |
+-----------------------------+         |     ram_total_gb     FLOAT   |
                                        |     swap_used_gb     FLOAT   |
                                        +------------------------------+
```

### Relacionamentos

| Relação | Tipo | Descrição |
|---|---|---|
| `Config` para `OptimizationLog` | 1 : N | Uma configuração ativa pode ter múltiplos registros de otimização. |
| `Config` para `Whitelist` | 1 : N | Uma configuração ativa possui zero ou mais processos na whitelist. |
| `RamSnapshot` | Independente | Série temporal de leituras de RAM; mantida em memória (ring buffer de 90 pontos) e não persiste entre sessões. |

> **Nota de implementação atual:** `Config` e `Whitelist` são serializadas em `config.json`. `OptimizationLog` é mantido em memória (máx. 30 entradas). Uma versão futura pode migrar para SQLite para persistir o log entre sessões.

---

## 7. Critérios de Aceite

### RF01 / RF02 / RF03 — Monitoramento em Tempo Real

- **Dado que** o app está aberto em modo usuário ou admin,
  **quando** a interface é exibida,
  **então** o gauge circular mostra o percentual de RAM atualizado a cada no máximo 2,5 s e os valores de RAM usada/livre/total em GB aparecem abaixo do gauge sem travamento da UI.

- **Dado que** o app está rodando por mais de 10 segundos,
  **quando** o usuário observa a sparkline,
  **então** ela exibe ao menos 5 pontos de histórico crescendo da esquerda para a direita.

### RF05 / RF06 — Otimização Manual

- **Dado que** o usuário clica em "OTIMIZAR MEMÓRIA AGORA",
  **quando** a otimização é concluída,
  **então** o botão retorna ao estado normal, o log registra uma nova entrada com trigger "MANUAL", timestamp correto, camadas ativadas e MB liberados (maior ou igual a 0).

- **Dado que** o app roda sem privilégios de Admin,
  **quando** o usuário clica em "Otimizar Agora",
  **então** apenas a Camada L2b é aplicada e o badge exibe `USER`.

### RF07 / RF13 / RF14 — Proteções de Segurança

- **Dado que** o processo `lsass.exe` está ativo,
  **quando** qualquer camada de otimização é executada,
  **então** `lsass.exe` não é tocado pela trimagem e continua consumindo sua memória normal.

- **Dado que** o uso de Swap está em 4,5 GB,
  **quando** a otimização automática ou manual é disparada,
  **então** o sistema não aplica camadas de trim agressivo e o log registra "Swap Lock ativo".

### RF08 / RF09 — Auto-Modo Adaptativo

- **Dado que** o Auto-Modo está ativado e o limite configurado é 80%,
  **quando** o uso de RAM ultrapassa 80%,
  **então** o sistema dispara uma otimização automática em até 10 segundos e registra trigger "AUTO" no log.

- **Dado que** o Auto-Modo está ativo,
  **quando** a pressão de RAM está alta (acima de 90%),
  **então** o intervalo de verificação é reduzido (mais frequente) em comparação a quando a pressão está baixa.

### RF11 — Persistência de Configurações

- **Dado que** o usuário altera o limite para 2,5 GB e fecha o app,
  **quando** o app é reaberto,
  **então** o campo de limite exibe 2,5 GB e o Auto-Modo respeita esse valor.

### RF12 / RF13 — Whitelist

- **Dado que** o usuário clica com o botão direito em um processo na lista e seleciona "Proteger",
  **quando** a próxima otimização é executada,
  **então** o processo aparece com ícone de escudo na lista e não é trimado pela Camada L2b.

### RF15 / RF16 — Log de Otimizações

- **Dado que** já existem 30 entradas no log,
  **quando** uma nova otimização é executada,
  **então** a entrada mais antiga é removida e a nova entrada aparece no topo do log.

### RF17 / RF18 — System Tray

- **Dado que** o usuário fecha a janela principal do app,
  **quando** o ícone no system tray é exibido,
  **então** o Auto-Modo continua funcionando e, ao disparar uma otimização, uma notificação Toast do Windows é exibida com o resultado.

### RF20 / RF21 — VirtualRAM Compressor

- **Dado que** o usuário clica em "Compressor RAM" na interface principal,
  **quando** o módulo VirtualRAM Compressor é aberto,
  **então** ele abre como janela separada (processo independente), mostra o gauge de Swap e permite executar as camadas C1 (PageCombine) e C2 (PurgeStandby).

### RF25 — Build .EXE

- **Dado que** o ambiente possui Python 3.8+ e acesso à internet,
  **quando** o arquivo `build.bat` é executado,
  **então** o arquivo `dist/MemOptima.exe` é gerado sem erros e pode ser executado em um Windows sem Python instalado.

---

## 8. Decisão de Stack e Deploy

### Stack

| Camada | Tecnologia | Justificativa |
|---|---|---|
| **Linguagem** | Python 3.8+ | Multiplataforma, suporte nativo a `ctypes` para chamar APIs do Windows sem dependências externas; ampla disponibilidade nos laboratórios do IFRO. |
| **Interface gráfica** | Tkinter (stdlib) | Zero dependências externas para GUI; leve em memória (menor que 5 MB); compatível com Python padrão em qualquer instalação Windows; adequado para máquinas com 2–4 GB RAM que são o público-alvo. |
| **APIs do sistema** | ctypes + kernel32 / ntdll / psapi / advapi32 | Acesso direto às APIs de gerenciamento de memória do Windows sem camadas intermediárias; funções como `NtSetSystemInformation` e `EmptyWorkingSet` não possuem wrappers em bibliotecas Python populares. |
| **System Tray** | pystray + Pillow | Integração com a bandeja do sistema; geração de ícones programáticos; opcional — o app degrada graciosamente sem esses pacotes. |
| **Métricas de sistema** | psutil maior ou igual a 5.9.0 | Abstração portável para `virtual_memory()` e `process_iter()`; amplamente testada e mantida. |
| **Distribuição** | PyInstaller maior ou igual a 6.0.0 | Geração de `.EXE` único (`--onefile`), sem necessidade de Python instalado na máquina alvo; padrão de mercado para distribuição de apps Python no Windows. |
| **Persistência** | JSON (config.json) | Leve, legível por humanos, sem necessidade de servidor de banco de dados para dados de configuração de usuário único local. |

### Deploy e Distribuição

| Destino | Estratégia |
|---|---|
| **Execução direta (desenvolvimento)** | `python memoptima.py` ou `run_admin.bat` (eleva via UAC). Dependências instaladas via `pip install -r requirements.txt` no `.venv`. |
| **Distribuição local** | Executável único `dist/MemOptima.exe` gerado pelo `build.bat` (PyInstaller `--onefile --windowed --noconsole`). Pode ser copiado para qualquer pasta e executado sem instalação. |
| **Deploy em laboratório** | Cópia do `.EXE` nos computadores ou disponibilização via rede local (pasta compartilhada). Não requer servidor, banco de dados externo, conexão com internet ou instalador. |
| **Repositório** | Git (controle de versão local ou hospedagem em GitHub/GitLab). O `.venv/` e `__pycache__/` devem estar no `.gitignore`. |

> **Compatibilidade de stack com deploy:** A escolha de PyInstaller garante que o `.EXE` é autocontido e não depende de PHP, Node.js, banco de dados externo ou servidor web — totalmente compatível com o destino de deploy local/laboratorial sem infraestrutura adicional.

---

*MemOptima — Spec Inicial | Instituto Federal de Rondônia — Campus Porto Velho Calama | Setembro/2026*
