# -*- coding: utf-8 -*-
"""
shared/win_api.py — Setup das APIs nativas do Windows via ctypes.

Expõe:
  IS_WINDOWS, IS_ADMIN
  SYSTEM_PROCS        — conjunto de processos críticos que nunca devem ser tocados
  _enable_privileges  — eleva os privilégios de memória do token atual
  _get_foreground_pid — retorna PID da janela em primeiro plano
  Todas as funções/constantes ctypes usadas pelas camadas de otimização.

Importar este módulo em sistemas não-Windows é seguro: as funções degradam
graciosamente retornando False / 0 / None.
"""

import sys
import ctypes

IS_WINDOWS: bool = sys.platform == "win32"
IS_ADMIN:   bool = False

# Processos críticos do SO — NUNCA tocar em nenhuma camada
SYSTEM_PROCS = {
    "system", "registry", "smss.exe", "csrss.exe", "wininit.exe",
    "winlogon.exe", "lsass.exe", "lsm.exe", "services.exe",
    "svchost.exe", "dwm.exe", "fontdrvhost.exe", "lsaiso.exe",
    "memory compression", "secure system", "ntoskrnl.exe",
    "idle", "[system process]", "spoolsv.exe",
}

# Variáveis inicializadas condicionalmente — só em Windows
_adv = _k32 = _ps = _nt = _u32 = None
_OpenProcess = _CloseHandle = _GetCurrentProcess = None
_SetWSEx = _SetProcInfo = _SetFileCache = None
_EmptyWS = _NtSysInfo = None
_OpenProcToken = _LookupPriv = _AdjustToken = None
_GetForegroundWindow = _GetWindowThreadProcessId = None

PROC_ACCESS = TOKEN_ADJUST = SE_PRIV_ENABLED = 0
_SYSINFO_MEMLIST = _MEM_EMPTY_ALL_WS = _MEM_FLUSH_MODIFIED = 0
_MEM_PURGE_STANDBY = _MEM_COMBINE_PAGES = _PROC_MEM_PRIORITY = 0
MEMORY_PRIORITY_LOW = _SIZE_MAX = _FILECACHE_MIN = 0
HAS_PROCINFO = False

if IS_WINDOWS:
    from ctypes import wintypes
    import winreg  # noqa: F401 — usado em outros módulos via from shared.win_api import winreg

    try:
        IS_ADMIN = bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        IS_ADMIN = False

    _adv = ctypes.WinDLL('advapi32', use_last_error=True)
    _k32 = ctypes.WinDLL('kernel32',  use_last_error=True)
    _ps  = ctypes.WinDLL('psapi',     use_last_error=True)
    _nt  = ctypes.WinDLL('ntdll',     use_last_error=True)
    _u32 = ctypes.WinDLL('user32',    use_last_error=True)

    # kernel32 — process handles
    _OpenProcess          = _k32.OpenProcess
    _OpenProcess.restype  = wintypes.HANDLE
    _OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]

    _CloseHandle          = _k32.CloseHandle
    _CloseHandle.restype  = wintypes.BOOL
    _CloseHandle.argtypes = [wintypes.HANDLE]

    _GetCurrentProcess        = _k32.GetCurrentProcess
    _GetCurrentProcess.restype = wintypes.HANDLE

    # kernel32 — working set trim (Layer 2b)
    _SetWSEx          = _k32.SetProcessWorkingSetSizeEx
    _SetWSEx.restype  = wintypes.BOOL
    _SetWSEx.argtypes = [wintypes.HANDLE, ctypes.c_size_t, ctypes.c_size_t, wintypes.DWORD]

    # kernel32 — memory priority (Layer 2c, Win8+)
    try:
        _SetProcInfo          = _k32.SetProcessInformation
        _SetProcInfo.restype  = wintypes.BOOL
        _SetProcInfo.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
        HAS_PROCINFO = True
    except AttributeError:
        HAS_PROCINFO = False

    # kernel32 — file cache reduction (Layer 5)
    _SetFileCache          = _k32.SetSystemFileCacheSize
    _SetFileCache.restype  = wintypes.BOOL
    _SetFileCache.argtypes = [ctypes.c_size_t, ctypes.c_size_t, wintypes.DWORD]

    # psapi — empty working set (Layer 2)
    _EmptyWS          = _ps.EmptyWorkingSet
    _EmptyWS.restype  = wintypes.BOOL
    _EmptyWS.argtypes = [wintypes.HANDLE]

    # ntdll — system-level memory commands (Layers 1, 3, 4, 6)
    _NtSysInfo          = _nt.NtSetSystemInformation
    _NtSysInfo.restype  = ctypes.c_long
    _NtSysInfo.argtypes = [ctypes.c_int, ctypes.c_void_p, ctypes.c_ulong]

    # advapi32 — privilege management (Layer 0)
    _OpenProcToken          = _adv.OpenProcessToken
    _OpenProcToken.restype  = wintypes.BOOL
    _OpenProcToken.argtypes = [wintypes.HANDLE, wintypes.DWORD, ctypes.POINTER(wintypes.HANDLE)]

    _LookupPriv          = _adv.LookupPrivilegeValueW
    _LookupPriv.restype  = wintypes.BOOL
    _LookupPriv.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR, ctypes.c_void_p]

    _AdjustToken          = _adv.AdjustTokenPrivileges
    _AdjustToken.restype  = wintypes.BOOL
    _AdjustToken.argtypes = [wintypes.HANDLE, wintypes.BOOL, ctypes.c_void_p,
                              wintypes.DWORD, ctypes.c_void_p, ctypes.c_void_p]

    # user32 — foreground window detection
    _GetForegroundWindow        = _u32.GetForegroundWindow
    _GetForegroundWindow.restype = wintypes.HANDLE

    _GetWindowThreadProcessId          = _u32.GetWindowThreadProcessId
    _GetWindowThreadProcessId.restype  = wintypes.DWORD
    _GetWindowThreadProcessId.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]

    # Constants
    PROC_ACCESS        = 0x0400 | 0x0100 | 0x0200   # QUERY | SET_QUOTA | SET_INFO
    TOKEN_ADJUST       = 0x0020 | 0x0008             # ADJUST_PRIVILEGES | QUERY
    SE_PRIV_ENABLED    = 0x00000002
    _SYSINFO_MEMLIST   = 80
    _MEM_EMPTY_ALL_WS  = 2    # System-wide working set empty (admin)
    _MEM_FLUSH_MODIFIED = 3   # Flush modified page list
    _MEM_PURGE_STANDBY = 4    # Purge standby list
    _MEM_COMBINE_PAGES = 5    # Memory page combining (Win8+)
    _PROC_MEM_PRIORITY = 39   # ProcessMemoryPriority class
    MEMORY_PRIORITY_LOW = 1
    _SIZE_MAX          = ctypes.c_size_t(-1).value
    _FILECACHE_MIN     = 256 * 1024 * 1024  # 256 MB — mínimo razoável, não destrutivo


# ═══════════════════════════════════════════════════════════════════════════════
# LAYER 0 — PRIVILEGE ELEVATION
# ═══════════════════════════════════════════════════════════════════════════════
def _enable_privileges(extra_privs: list = None) -> None:
    """Eleva os privilégios de memória do token do processo atual.

    Args:
        extra_privs: lista adicional de nomes de privilégio (opcional).
                     Os 4 padrões são sempre solicitados quando admin.
    """
    if not IS_WINDOWS or not IS_ADMIN:
        return

    from ctypes import wintypes as wt

    class LUID(ctypes.Structure):
        _fields_ = [("LowPart", wt.DWORD), ("HighPart", wt.LONG)]

    class LuidAttr(ctypes.Structure):
        _fields_ = [("Luid", LUID), ("Attributes", wt.DWORD)]

    class TokenPriv(ctypes.Structure):
        _fields_ = [("Count", wt.DWORD), ("Privs", LuidAttr * 1)]

    privs = [
        "SeDebugPrivilege",
        "SeIncreaseQuotaPrivilege",
        "SeProfileSingleProcessPrivilege",
        "SeLockMemoryPrivilege",
    ]
    if extra_privs:
        privs.extend(extra_privs)

    try:
        hToken = wt.HANDLE()
        if not _OpenProcToken(_GetCurrentProcess(), TOKEN_ADJUST, ctypes.byref(hToken)):
            return
        for priv in privs:
            luid = LUID()
            if _LookupPriv(None, priv, ctypes.byref(luid)):
                tp = TokenPriv()
                tp.Count = 1
                tp.Privs[0].Luid = luid
                tp.Privs[0].Attributes = SE_PRIV_ENABLED
                _AdjustToken(hToken, False, ctypes.byref(tp),
                             ctypes.sizeof(tp), None, None)
        _CloseHandle(hToken)
    except Exception:
        pass


# ═══════════════════════════════════════════════════════════════════════════════
# FOREGROUND PROCESS DETECTION
# ═══════════════════════════════════════════════════════════════════════════════
def _get_foreground_pid() -> int:
    """Retorna o PID do processo que possui a janela em primeiro plano, ou 0."""
    if not IS_WINDOWS:
        return 0
    try:
        from ctypes import wintypes as wt
        hwnd = _GetForegroundWindow()
        if not hwnd:
            return 0
        pid = wt.DWORD(0)
        _GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        return pid.value
    except Exception:
        return 0
