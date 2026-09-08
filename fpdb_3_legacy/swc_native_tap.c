#if defined(__linux__) || defined(__gnu_linux__)
#ifndef _GNU_SOURCE
#define _GNU_SOURCE
#endif
#endif

#ifdef __APPLE__
#define _DARWIN_C_SOURCE
#endif

#ifdef _WIN32
/* _open/_write/getenv are flagged deprecated by MSVC; we use them deliberately. */
#define _CRT_SECURE_NO_WARNINGS 1
#endif

#include <errno.h>
#include <fcntl.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>

#ifndef _WIN32
#include <arpa/inet.h>
#include <dlfcn.h>
#include <netinet/in.h>
#include <sys/file.h>
#include <sys/socket.h>
#include <sys/time.h>
#include <unistd.h>
#else
/* winsock2.h MUST precede windows.h: windows.h otherwise pulls in the Winsock 1
 * <winsock.h>, and the later winsock2.h then redefines sockaddr et al. MinGW is
 * lax about this, MSVC/clang-cl is not -- and CI only ever compiled with MinGW,
 * so the clash stayed hidden until the DLL was built with the MSVC toolchain. */
#ifndef WIN32_LEAN_AND_MEAN
#define WIN32_LEAN_AND_MEAN 1
#endif
#include <winsock2.h>
#include <ws2tcpip.h>
#include <windows.h>
#include <io.h>
#include <wchar.h>
#if defined(_WIN32) && !defined(__MINGW32__)
typedef int socklen_t; /* winsock getpeername takes int*; MSVC lacks socklen_t */
#endif
#endif

/* Minimal OpenSSL ABI declarations: SwC ships libssl but not development headers. */
typedef struct ssl_st SSL;

#ifdef __APPLE__
extern int SSL_read(SSL *ssl, void *buffer, int size);
extern int SSL_write(SSL *ssl, const void *buffer, int size);
extern int SSL_get_fd(const SSL *ssl);
#else
typedef int (*ssl_read_fn)(SSL *ssl, void *buffer, int size);
typedef int (*ssl_write_fn)(SSL *ssl, const void *buffer, int size);
typedef int (*ssl_get_fd_fn)(const SSL *ssl);
#endif

/*
 * Passive SwC Poker TLS tap (macOS, Linux, Windows).
 *
 * The native client uses OpenSSL and calls SSL_read/SSL_write directly.
 * This interposer records plaintext only after a successful SSL operation.
 * By default it records inbound traffic from game server ports (20002-20999),
 * deliberately excluding the lobby/login connection on port 20001.
 */

#define SWC_TAP_MAGIC 0x53574354u /* "SWCT" */
#define SWC_TAP_VERSION 1u
#define SWC_AUTO_GAME_PORT 0u
#define SWC_LOBBY_PORT 20001u
#define SWC_FIRST_GAME_PORT 20002u
#define SWC_LAST_GAME_PORT 20999u
#define SWC_MAX_RECORD_SIZE (16u * 1024u * 1024u)

struct swc_tap_header {
    uint32_t magic;
    uint16_t version;
    uint8_t direction; /* 0 = server -> client, 1 = client -> server */
    uint8_t reserved;
    uint16_t peer_port;
    uint16_t reserved2;
    uint32_t payload_size;
    uint64_t timestamp_us;
};

static int capture_fd = -1;
static uint16_t capture_port = SWC_AUTO_GAME_PORT;
static int capture_outbound = 0;

#ifdef _WIN32
/* On Windows the tap is injected into an already-running client, so it never
 * inherits the SWC_CAPTURE_* environment the POSIX launcher sets. Instead it
 * locates its files next to its own DLL (see initialize_swc_tap): these hold
 * the wide paths derived there, so status/archive writes need no environment. */
static wchar_t g_status_path[MAX_PATH] = {0};

static void write_status(const char *message) {
    const char *env_path = getenv("SWC_CAPTURE_STATUS_PATH");
    int fd = -1;
    if (env_path != NULL && env_path[0] != '\0') {
        fd = _open(env_path, _O_CREAT | _O_WRONLY | _O_APPEND | _O_BINARY, _S_IREAD | _S_IWRITE);
    } else if (g_status_path[0] != L'\0') {
        fd = _wopen(g_status_path, _O_CREAT | _O_WRONLY | _O_APPEND | _O_BINARY, _S_IREAD | _S_IWRITE);
    }
    if (fd >= 0) {
        _write(fd, message, (unsigned int)strlen(message));
        _close(fd);
    }
}
#else
static void write_status(const char *message) {
    const char *path = getenv("SWC_CAPTURE_STATUS_PATH");
    int fd;

    if (path == NULL || path[0] == '\0') {
        return;
    }
    fd = open(path, O_CREAT | O_WRONLY | O_APPEND | O_CLOEXEC, S_IRUSR | S_IWUSR);
    if (fd >= 0) {
        write(fd, message, strlen(message));
        close(fd);
    }
}
#endif

static uint64_t now_us(void) {
#ifndef _WIN32
    struct timeval tv;
    gettimeofday(&tv, NULL);
    return ((uint64_t)tv.tv_sec * 1000000u) + (uint64_t)tv.tv_usec;
#else
    FILETIME ft;
    GetSystemTimeAsFileTime(&ft);
    ULARGE_INTEGER uli;
    uli.LowPart = ft.dwLowDateTime;
    uli.HighPart = ft.dwHighDateTime;
    return (uli.QuadPart / 10u) - 11644473600000000ULL;
#endif
}

static uint16_t peer_port_for_ssl(SSL *ssl) {
    int fd;
    struct sockaddr_storage address;
    socklen_t address_len = sizeof(address);

#ifdef __APPLE__
    if (ssl == NULL || (fd = SSL_get_fd(ssl)) < 0) {
        return 0;
    }
#else
    static ssl_get_fd_fn real_SSL_get_fd = NULL;
    if (real_SSL_get_fd == NULL) {
#ifndef _WIN32
        real_SSL_get_fd = (ssl_get_fd_fn)dlsym(RTLD_NEXT, "SSL_get_fd");
#else
        HMODULE h_ssl = GetModuleHandleA("ssleay32.dll");
        if (!h_ssl) h_ssl = GetModuleHandleA("libssl-1_1.dll");
        if (!h_ssl) h_ssl = GetModuleHandleA("libssl-1_1-x64.dll");
        if (!h_ssl) h_ssl = GetModuleHandleA("libssl32.dll");
        if (h_ssl) real_SSL_get_fd = (ssl_get_fd_fn)GetProcAddress(h_ssl, "SSL_get_fd");
#endif
    }
    if (ssl == NULL || real_SSL_get_fd == NULL || (fd = real_SSL_get_fd(ssl)) < 0) {
        return 0;
    }
#endif

    if (getpeername(fd, (struct sockaddr *)&address, &address_len) != 0) {
        return 0;
    }
    if (address.ss_family == AF_INET) {
        return ntohs(((struct sockaddr_in *)&address)->sin_port);
    }
    if (address.ss_family == AF_INET6) {
        return ntohs(((struct sockaddr_in6 *)&address)->sin6_port);
    }
    return 0;
}

static void write_all(int fd, const void *buffer, size_t size) {
    const uint8_t *cursor = (const uint8_t *)buffer;
    while (size > 0) {
#ifndef _WIN32
        ssize_t written = write(fd, cursor, size);
#else
        int written = _write(fd, cursor, (unsigned int)size);
#endif
        if (written > 0) {
            cursor += written;
            size -= (size_t)written;
        } else if (written < 0 && errno == EINTR) {
            continue;
        } else {
            break;
        }
    }
}

static void record_plaintext(SSL *ssl, const void *buffer, int size, uint8_t direction) {
    uint16_t peer_port;
    struct swc_tap_header header;

    if (capture_fd < 0 || buffer == NULL || size <= 0 || (uint32_t)size > SWC_MAX_RECORD_SIZE) {
        return;
    }
    if (direction == 1 && !capture_outbound) {
        return;
    }
    peer_port = peer_port_for_ssl(ssl);
    if (capture_port == SWC_AUTO_GAME_PORT) {
        if (peer_port < SWC_FIRST_GAME_PORT || peer_port > SWC_LAST_GAME_PORT || peer_port == SWC_LOBBY_PORT) {
            return;
        }
    } else if (peer_port != capture_port) {
        return;
    }

    memset(&header, 0, sizeof(header));
    header.magic = SWC_TAP_MAGIC;
    header.version = SWC_TAP_VERSION;
    header.direction = direction;
    header.peer_port = peer_port;
    header.reserved2 = 0;
    header.payload_size = (uint32_t)size;
    header.timestamp_us = now_us();

#ifndef _WIN32
    if (flock(capture_fd, LOCK_EX) == 0) {
        write_all(capture_fd, &header, sizeof(header));
        write_all(capture_fd, buffer, (size_t)size);
        flock(capture_fd, LOCK_UN);
    }
#else
    write_all(capture_fd, &header, sizeof(header));
    write_all(capture_fd, buffer, (size_t)size);
#endif
}

#ifdef _WIN32
/* ------------------------------------------------------------------------- *
 * Windows inline hook engine.
 *
 * The Windows client is a 32-bit Qt app that resolves OpenSSL through
 * QSslSocket, i.e. it LoadLibrary's ssleay32.dll and GetProcAddress's each
 * symbol at run time -- SSL_read/SSL_write are NOT in any module's import
 * table, so IAT hooking (as on the macOS/Linux interposer) catches nothing.
 * The only interception that works regardless of how a caller resolved the
 * symbol is to patch the function itself: overwrite the first bytes of the
 * real SSL_read/SSL_write in ssleay32.dll with a jump to our hook, and keep a
 * trampoline holding the displaced prologue + a jump back so the original is
 * still callable.
 *
 * This is deliberately conservative. The prologue is copied only if a small
 * length decoder can account for whole instructions and none of them is a
 * relative branch (which would break once relocated); otherwise the function
 * is left untouched and capture simply stays empty. A refused hook never
 * corrupts the client. Observed OpenSSL 1.0.x prologues here are
 * `mov ecx,[esp+4]; cmp [ecx+0x20],0` (8 relocatable bytes) -- well clear of
 * the 5 a JMP rel32 needs.
 *
 * These functions are __cdecl (the caller cleans the stack: the disassembly
 * shows `call SSL_read` followed by `add esp,0xC`), so the hooks and the
 * trampoline pointers are __cdecl too.
 * ------------------------------------------------------------------------- */

typedef int(__cdecl *ssl_rw_cdecl_fn)(SSL *ssl, void *buffer, int size);

static ssl_rw_cdecl_fn real_SSL_read = NULL;  /* trampoline to the original */
static ssl_rw_cdecl_fn real_SSL_write = NULL; /* trampoline to the original */
static int g_hooks_installed = 0;

/* Length of the legacy-prefixed x86 instruction at p, or -1 if it is a shape
 * this decoder does not recognise or must not relocate (any relative branch,
 * or a return). Small on purpose: it needs only to cover typical function
 * prologues well enough to sum >= 5 safe bytes, and to fail closed otherwise. */
static int swc_insn_len(const uint8_t *p) {
    int len = 0;
    int operand16 = 0;

    /* Legacy prefixes. */
    for (;;) {
        uint8_t b = p[len];
        if (b == 0x66) {
            operand16 = 1;
            len++;
        } else if (b == 0x67 || b == 0xF0 || b == 0xF2 || b == 0xF3 || b == 0x2E || b == 0x36 ||
                   b == 0x3E || b == 0x26 || b == 0x64 || b == 0x65) {
            len++;
        } else {
            break;
        }
    }

    uint8_t op = p[len++];

    /* Two-byte opcodes. */
    if (op == 0x0F) {
        uint8_t op2 = p[len++];
        if (op2 >= 0x80 && op2 <= 0x8F) {
            return -1; /* jcc rel32 -- not relocatable */
        }
        /* movzx/movsx and the like: ModRM, no immediate. */
        {
            uint8_t modrm = p[len++];
            int mod = modrm >> 6, rm = modrm & 7;
            if (mod != 3 && rm == 4) {
                uint8_t sib = p[len++];
                if (mod == 0 && (sib & 7) == 5) {
                    len += 4;
                }
            }
            if (mod == 1) {
                len += 1;
            } else if (mod == 2) {
                len += 4;
            } else if (mod == 0 && rm == 5) {
                len += 4;
            }
        }
        return len;
    }

    /* Relative branches and returns: never relocate these. */
    if (op == 0xE8 || op == 0xE9 || op == 0xEB || (op >= 0x70 && op <= 0x7F) || op == 0xC3 ||
        op == 0xC2 || op == 0xCC || op == 0xCB || op == 0xCA) {
        return -1;
    }

    /* push/pop reg, single-byte no-ops. */
    if ((op >= 0x50 && op <= 0x5F) || op == 0x90 || op == 0x98 || op == 0x99 || op == 0xF8 ||
        op == 0xF9 || op == 0xFC || op == 0xFD) {
        return len;
    }

    /* mov reg, imm. */
    if (op >= 0xB8 && op <= 0xBF) {
        return len + (operand16 ? 2 : 4);
    }
    if (op >= 0xB0 && op <= 0xB7) {
        return len + 1;
    }
    if (op == 0x68) {
        return len + (operand16 ? 2 : 4); /* push imm */
    }
    if (op == 0x6A) {
        return len + 1; /* push imm8 */
    }

    /* Opcodes taking a ModRM byte. imm_after is the immediate size that trails
     * the ModRM/SIB/displacement, if any. */
    {
        int has_modrm = 0;
        int imm_after = 0;
        switch (op) {
        /* arithmetic/logote r/m,reg and reg,r/m; test; mov; lea; ... */
        case 0x00: case 0x01: case 0x02: case 0x03:
        case 0x08: case 0x09: case 0x0A: case 0x0B:
        case 0x10: case 0x11: case 0x12: case 0x13:
        case 0x18: case 0x19: case 0x1A: case 0x1B:
        case 0x20: case 0x21: case 0x22: case 0x23:
        case 0x28: case 0x29: case 0x2A: case 0x2B:
        case 0x30: case 0x31: case 0x32: case 0x33:
        case 0x38: case 0x39: case 0x3A: case 0x3B:
        case 0x84: case 0x85: case 0x86: case 0x87:
        case 0x88: case 0x89: case 0x8A: case 0x8B:
        case 0x8D: case 0x8F: case 0x63:
        case 0xFF: case 0xFE:
            has_modrm = 1;
            break;
        case 0x80: case 0x82: case 0x83: /* grp1 r/m, imm8 */
        case 0xC0: case 0xC1:            /* shift r/m, imm8 */
        case 0xC6:                       /* mov r/m8, imm8 */
            has_modrm = 1;
            imm_after = 1;
            break;
        case 0x81: /* grp1 r/m, imm16/32 */
        case 0xC7: /* mov r/m, imm16/32 */
            has_modrm = 1;
            imm_after = operand16 ? 2 : 4;
            break;
        case 0xF6: /* grp3 r/m8: test adds imm8 */
            has_modrm = 1;
            if (((p[len]) & 0x38) == 0) {
                imm_after = 1;
            }
            break;
        case 0xF7: /* grp3 r/m: test adds imm16/32 */
            has_modrm = 1;
            if (((p[len]) & 0x38) == 0) {
                imm_after = operand16 ? 2 : 4;
            }
            break;
        default:
            return -1; /* unknown: fail closed */
        }

        if (has_modrm) {
            uint8_t modrm = p[len++];
            int mod = modrm >> 6, rm = modrm & 7;
            if (mod != 3 && rm == 4) {
                uint8_t sib = p[len++];
                if (mod == 0 && (sib & 7) == 5) {
                    len += 4;
                }
            }
            if (mod == 1) {
                len += 1;
            } else if (mod == 2) {
                len += 4;
            } else if (mod == 0 && rm == 5) {
                len += 4;
            }
        }
        len += imm_after;
        return len;
    }
}

/* Bytes of whole instructions at code that cover at least min_len, or -1 if a
 * non-relocatable instruction appears before that. */
static int swc_prologue_len(const uint8_t *code, int min_len) {
    int total = 0;
    while (total < min_len) {
        int n = swc_insn_len(code + total);
        if (n <= 0) {
            return -1;
        }
        total += n;
    }
    return total;
}

/* Install a 5-byte JMP-rel32 hook over *target*, returning a trampoline that
 * runs the displaced prologue then continues into the original, or NULL if the
 * prologue cannot be relocated safely. */
static void *swc_install_inline_hook(void *target, void *hook) {
    uint8_t *fn = (uint8_t *)target;
    int steal = swc_prologue_len(fn, 5);
    if (steal < 5 || steal > 64) {
        return NULL;
    }

    uint8_t *tramp = (uint8_t *)VirtualAlloc(NULL, (SIZE_T)steal + 5, MEM_COMMIT | MEM_RESERVE,
                                             PAGE_EXECUTE_READWRITE);
    if (tramp == NULL) {
        return NULL;
    }
    memcpy(tramp, fn, (size_t)steal);
    tramp[steal] = 0xE9; /* jmp rel32 back into the original past the stolen bytes */
    *(int32_t *)(tramp + steal + 1) = (int32_t)((fn + steal) - (tramp + steal + 5));

    DWORD old_protect = 0;
    if (!VirtualProtect(fn, 5, PAGE_EXECUTE_READWRITE, &old_protect)) {
        VirtualFree(tramp, 0, MEM_RELEASE);
        return NULL;
    }
    /* We patch a live function that other threads may be calling. Write the
     * rel32 displacement first, while fn[0] still holds the original opcode, and
     * only then flip fn[0] to 0xE9 as a single byte store. A thread that reads
     * the site mid-patch therefore sees either the original first instruction or
     * a complete jump, never a 0xE9 with a half-written target. (This narrows
     * the window; it is not a full thread-suspend barrier.) */
    *(int32_t *)(fn + 1) = (int32_t)((uint8_t *)hook - (fn + 5));
    MemoryBarrier();
    fn[0] = 0xE9; /* jmp rel32 to our hook */
    VirtualProtect(fn, 5, old_protect, &old_protect);
    FlushInstructionCache(GetCurrentProcess(), fn, (SIZE_T)steal);
    return tramp;
}

static int __cdecl swc_hook_SSL_read(SSL *ssl, void *buffer, int size) {
    int result = real_SSL_read(ssl, buffer, size);
    if (result > 0) {
        record_plaintext(ssl, buffer, result, 0);
    }
    return result;
}

static int __cdecl swc_hook_SSL_write(SSL *ssl, void *buffer, int size) {
    int result = real_SSL_write(ssl, buffer, size);
    if (result > 0) {
        record_plaintext(ssl, buffer, result, 1);
    }
    return result;
}

/* Try to hook once ssleay32.dll is present. Returns 1 when both hooks are in
 * place (or already were), 0 while the SSL library is not yet loaded. */
static int swc_try_install_hooks(void) {
    if (g_hooks_installed) {
        return 1;
    }
    HMODULE ssl = GetModuleHandleA("ssleay32.dll");
    if (ssl == NULL) {
        ssl = GetModuleHandleA("libssl-1_1.dll");
    }
    if (ssl == NULL) {
        ssl = GetModuleHandleA("libssl-1_1-x64.dll");
    }
    if (ssl == NULL) {
        return 0; /* not loaded yet; the client has not opened a TLS socket */
    }

    void *addr_read = (void *)GetProcAddress(ssl, "SSL_read");
    void *addr_write = (void *)GetProcAddress(ssl, "SSL_write");
    if (addr_read == NULL || addr_write == NULL) {
        return 0;
    }

    real_SSL_read = (ssl_rw_cdecl_fn)swc_install_inline_hook(addr_read, (void *)swc_hook_SSL_read);
    real_SSL_write = (ssl_rw_cdecl_fn)swc_install_inline_hook(addr_write, (void *)swc_hook_SSL_write);
    if (real_SSL_read != NULL && real_SSL_write != NULL) {
        g_hooks_installed = 1;
        write_status("tap-hooked\n");
        return 1;
    }
    write_status("tap-hook-failed\n");
    /* Treat an unsafe prologue as terminal rather than spinning forever. */
    g_hooks_installed = 1;
    return 1;
}

static DWORD WINAPI swc_hook_worker(LPVOID param) {
    (void)param;
    /* QSslSocket loads ssleay32.dll lazily on the first TLS connection, which
     * can be seconds after we inject. Poll a while, then give up quietly. */
    for (int i = 0; i < 600; i++) { /* ~60s at 100ms */
        if (swc_try_install_hooks()) {
            return 0;
        }
        Sleep(100);
    }
    write_status("tap-ssl-not-found\n");
    return 0;
}

#endif /* _WIN32 */

#ifndef _WIN32
__attribute__((constructor)) static void initialize_swc_tap(void) {
    const char *path = getenv("SWC_CAPTURE_PATH");
    const char *port = getenv("SWC_CAPTURE_PORT");
    const char *outbound = getenv("SWC_CAPTURE_OUTBOUND");
    char *end = NULL;
    unsigned long parsed_port;

    if (path == NULL || path[0] == '\0') {
        return;
    }
    if (port != NULL && port[0] != '\0') {
        parsed_port = strtoul(port, &end, 10);
        if (end != port && *end == '\0' && parsed_port <= 65535) {
            capture_port = (uint16_t)parsed_port;
        }
    }
    capture_outbound = outbound != NULL && strcmp(outbound, "1") == 0;
    capture_fd = open(path, O_CREAT | O_WRONLY | O_APPEND | O_CLOEXEC, S_IRUSR | S_IWUSR);
    write_status(capture_fd >= 0 ? "tap-loaded\n" : "tap-load-open-failed\n");
}

__attribute__((destructor)) static void close_swc_tap(void) {
    if (capture_fd >= 0) {
        close(capture_fd);
        capture_fd = -1;
    }
}

#else /* _WIN32 */

/* Read `port=` and `outbound=` from an optional sidecar next to the DLL. The
 * launcher writes it so Windows keeps parity with the POSIX SWC_CAPTURE_PORT /
 * SWC_CAPTURE_OUTBOUND variables, which an injected DLL cannot inherit. Absent
 * or unreadable, the safe defaults hold (auto game ports, inbound only). */
static void swc_read_config(const wchar_t *cfg_path) {
    int fd = _wopen(cfg_path, _O_RDONLY | _O_BINARY);
    char buf[256];
    int n;
    const char *p;

    if (fd < 0) {
        return;
    }
    n = _read(fd, buf, (unsigned int)(sizeof(buf) - 1));
    _close(fd);
    if (n <= 0) {
        return;
    }
    buf[n] = '\0';

    p = strstr(buf, "port=");
    if (p != NULL) {
        unsigned long parsed_port = strtoul(p + 5, NULL, 10);
        if (parsed_port <= 65535) {
            capture_port = (uint16_t)parsed_port;
        }
    }
    p = strstr(buf, "outbound=");
    if (p != NULL) {
        capture_outbound = (p[9] == '1');
    }
}

/* Locate the tap's own directory and derive its files from it. The DLL is
 * injected from BUILD_DIR/swc_native_tap.dll, so the archive it must append to
 * is BUILD_DIR/swc-native.raw -- exactly DEFAULT_ARCHIVE on the Python side. */
static void initialize_swc_tap(HINSTANCE self) {
    wchar_t dir[MAX_PATH];
    wchar_t archive_path[MAX_PATH];
    wchar_t cfg_path[MAX_PATH];
    wchar_t *slash;
    DWORD len = GetModuleFileNameW(self, dir, MAX_PATH);

    if (len == 0 || len >= MAX_PATH) {
        return;
    }
    slash = wcsrchr(dir, L'\\');
    if (slash == NULL) {
        return;
    }
    slash[1] = L'\0';

    _snwprintf(archive_path, MAX_PATH, L"%sswc-native.raw", dir);
    _snwprintf(g_status_path, MAX_PATH, L"%sswc-native.status", dir);
    _snwprintf(cfg_path, MAX_PATH, L"%sswc-native.cfg", dir);
    swc_read_config(cfg_path);

    capture_fd = _wopen(archive_path, _O_CREAT | _O_WRONLY | _O_APPEND | _O_BINARY, _S_IREAD | _S_IWRITE);
    write_status(capture_fd >= 0 ? "tap-loaded\n" : "tap-load-open-failed\n");

    /* Hook off the DllMain thread: the SSL library may not be loaded yet, and
     * DllMain must not block or call LoadLibrary-triggering code under the
     * loader lock. */
    if (capture_fd >= 0) {
        HANDLE worker = CreateThread(NULL, 0, swc_hook_worker, NULL, 0, NULL);
        if (worker != NULL) {
            CloseHandle(worker);
        }
    }
}

static void close_swc_tap(void) {
    if (capture_fd >= 0) {
        _close(capture_fd);
        capture_fd = -1;
    }
}

BOOL WINAPI DllMain(HINSTANCE hinstDLL, DWORD fdwReason, LPVOID lpvReserved) {
    (void)lpvReserved;
    if (fdwReason == DLL_PROCESS_ATTACH) {
        DisableThreadLibraryCalls(hinstDLL);
        initialize_swc_tap(hinstDLL);
    } else if (fdwReason == DLL_PROCESS_DETACH) {
        close_swc_tap();
    }
    return TRUE;
}
#endif /* _WIN32 */

#ifdef __APPLE__
static int swc_tap_ssl_read(SSL *ssl, void *buffer, int size) {
    int result = SSL_read(ssl, buffer, size);
    if (result > 0) {
        record_plaintext(ssl, buffer, result, 0);
    }
    return result;
}

static int swc_tap_ssl_write(SSL *ssl, const void *buffer, int size) {
    int result = SSL_write(ssl, buffer, size);
    if (result > 0) {
        record_plaintext(ssl, buffer, result, 1);
    }
    return result;
}

struct interpose_entry {
    const void *replacement;
    const void *replacee;
};

__attribute__((used, section("__DATA,__interpose"))) static const struct interpose_entry interposers[] = {
    {(const void *)swc_tap_ssl_read, (const void *)SSL_read},
    {(const void *)swc_tap_ssl_write, (const void *)SSL_write},
};
#elif defined(_WIN32)
/* The Windows interception is an inline hook installed at load time by
 * swc_hook_worker (see the engine above), not an exported symbol: the client
 * resolves SSL_read/SSL_write dynamically, so nothing would ever call an
 * exported override here. Nothing to define in this section on Windows. */
#else /* Linux / POSIX LD_PRELOAD */
static ssl_read_fn real_SSL_read = NULL;
static ssl_write_fn real_SSL_write = NULL;

int SSL_read(SSL *ssl, void *buffer, int size) {
    if (real_SSL_read == NULL) {
        real_SSL_read = (ssl_read_fn)dlsym(RTLD_NEXT, "SSL_read");
    }
    int result = real_SSL_read ? real_SSL_read(ssl, buffer, size) : -1;
    if (result > 0) {
        record_plaintext(ssl, buffer, result, 0);
    }
    return result;
}

int SSL_write(SSL *ssl, const void *buffer, int size) {
    if (real_SSL_write == NULL) {
        real_SSL_write = (ssl_write_fn)dlsym(RTLD_NEXT, "SSL_write");
    }
    int result = real_SSL_write ? real_SSL_write(ssl, buffer, size) : -1;
    if (result > 0) {
        record_plaintext(ssl, buffer, result, 1);
    }
    return result;
}
#endif

