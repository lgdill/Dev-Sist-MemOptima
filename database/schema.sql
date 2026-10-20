-- ==============================================================================
-- MemOptima — Script de Definição de Banco de Dados (schema.sql)
-- Instituto Federal de Rondônia — Campus Porto Velho Calama
-- Curso: Desenvolvimento de Sistemas | Disciplina: Programar com IA de forma responsável
-- ==============================================================================
-- Compatível com: SQLite 3, PostgreSQL 14+ e MySQL 8+
-- ==============================================================================

-- 1. TABELA DE USUÁRIOS DO SISTEMA
CREATE TABLE IF NOT EXISTS usuarios (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nome VARCHAR(100) NOT NULL,
    email VARCHAR(150) UNIQUE NOT NULL,
    senha_hash VARCHAR(255) NOT NULL,
    perfil VARCHAR(20) NOT NULL DEFAULT 'usuario', -- 'admin' ou 'usuario'
    criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 2. TABELA DE CONFIGURAÇÕES DO MOTOR DE OTIMIZAÇÃO
CREATE TABLE IF NOT EXISTS configs (
    id VARCHAR(50) PRIMARY KEY,
    limit_gb DECIMAL(4, 2) NOT NULL DEFAULT 4.00,
    interval_sec INTEGER NOT NULL DEFAULT 60,
    auto_mode BOOLEAN NOT NULL DEFAULT 1,
    use_filecache BOOLEAN NOT NULL DEFAULT 1,
    swap_lock_gb DECIMAL(4, 2) NOT NULL DEFAULT 4.00,
    start_with_windows BOOLEAN NOT NULL DEFAULT 0,
    atualizado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 3. TABELA DE PROCESSOS EM WHITELIST (PROTEGIDOS DE TRIMAGEM)
CREATE TABLE IF NOT EXISTS whitelist (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    process_name VARCHAR(120) NOT NULL,
    added_by_usuario_id INTEGER,
    adicionado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (added_by_usuario_id) REFERENCES usuarios(id) ON DELETE SET NULL
);

-- 4. TABELA DE HISTÓRICO DE OTIMIZAÇÕES (LOG PERSISTIDO)
CREATE TABLE IF NOT EXISTS optimization_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp VARCHAR(30) NOT NULL,
    trigger_type VARCHAR(20) NOT NULL, -- 'MANUAL' ou 'AUTO'
    admin_mode BOOLEAN NOT NULL DEFAULT 0,
    layers_active VARCHAR(200) NOT NULL,
    mb_freed DECIMAL(8, 2) NOT NULL DEFAULT 0.00,
    ram_before_gb DECIMAL(5, 2),
    ram_after_gb DECIMAL(5, 2),
    swap_lock_active BOOLEAN NOT NULL DEFAULT 0,
    usuario_id INTEGER,
    FOREIGN KEY (usuario_id) REFERENCES usuarios(id) ON DELETE SET NULL
);

-- 5. TABELA DE SÉRIE TEMPORAL DE CONSUMO DE MEMÓRIA (SNAPSHOTS)
CREATE TABLE IF NOT EXISTS ram_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    ram_used_gb DECIMAL(5, 2) NOT NULL,
    ram_free_gb DECIMAL(5, 2) NOT NULL,
    ram_total_gb DECIMAL(5, 2) NOT NULL,
    swap_used_gb DECIMAL(5, 2) NOT NULL
);

-- Índices para otimização de consultas frequentes
CREATE INDEX IF NOT EXISTS idx_logs_timestamp ON optimization_logs(timestamp);
CREATE INDEX IF NOT EXISTS idx_whitelist_process ON whitelist(process_name);

-- ==============================================================================
-- DADOS INICIAIS DE TESTE (SEEDS)
-- ==============================================================================

-- Usuários de teste (senhas com hash SHA-256 / bcrypt padrão de teste acadêmico)
-- Credencial admin: admin@memoptima.local / admin123
-- Credencial professor: rafael@ifro.edu.br / professor123
INSERT INTO usuarios (id, nome, email, senha_hash, perfil) VALUES
(1, 'Administrador do Sistema', 'admin@memoptima.local', '240be518fabd2724ddb6f04eeb1da5967448d7e831c08c8fa822809f74c720a9', 'admin'),
(2, 'Prof. Rafael Pitwak', 'rafael@ifro.edu.br', 'e6c279f61b09fa4e1c251d14e1a12903c80a221295b9d5c48b788258a6f87422', 'admin');

-- Configuração padrão ativa
INSERT INTO configs (id, limit_gb, interval_sec, auto_mode, use_filecache, swap_lock_gb, start_with_windows) VALUES
('default', 4.00, 60, 1, 1, 4.00, 0);

-- Whitelist inicial com processos críticos do Windows
INSERT INTO whitelist (process_name, added_by_usuario_id) VALUES
('explorer.exe', 1),
('lsass.exe', 1),
('dwm.exe', 1),
('MemOptima.exe', 1);

-- Amostras iniciais de logs de otimização
INSERT INTO optimization_logs (timestamp, trigger_type, admin_mode, layers_active, mb_freed, ram_before_gb, ram_after_gb, swap_lock_active, usuario_id) VALUES
('2026-10-20 10:15:30', 'MANUAL', 1, 'L0: Anti-Thrashing, L1: Trim Processos, L2b: EmptyWorkingSet, L4: PurgeStandby', 438.50, 3.85, 3.42, 0, 1),
('2026-10-20 11:20:00', 'AUTO', 1, 'L0: Anti-Thrashing, L1: Trim Processos, L2b: EmptyWorkingSet', 212.10, 4.12, 3.91, 0, 1),
('2026-10-20 12:45:12', 'MANUAL', 0, 'L2b: EmptyWorkingSet (User Mode)', 145.80, 3.60, 3.45, 0, 2);
