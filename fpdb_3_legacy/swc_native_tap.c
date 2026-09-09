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
#include <tlhelp32.h>
#include <io.h>
#include <stdio.h>
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
static SRWLOCK g_capture_lock = SRWLOCK_INIT;

/* One archive record is two writes (header, then payload), and the SRWLOCK above
 * only orders the threads of *this* process. attach_to_windows_client injects
 * every running SwCPoker.exe, and they all append to the same DLL-relative
 * archive, so two clients could otherwise put one record's header between
 * another's header and payload -- which desynchronises iter_capture_records for
 * good. A named mutex in the client's session namespace makes the pair atomic
 * across processes, the same guarantee flock gives the POSIX path. */
#define SWC_CAPTURE_MUTEX_NAME L"Local\\fpdb-swc-native-capture"
/* Bounded because this runs on the client's network thread: a wedged peer must
 * not stall the game. Dropping one record keeps the archive readable, which an
 * interleaved one is not. */
#define SWC_CAPTURE_LOCK_TIMEOUT_MS 2000u
static HANDLE g_capture_mutex = NULL;

static void write_status(const char *message) {
    const char *env_path = getenv("SWC_CAPTURE_STATUS_PATH");
    const char *text = message;
    char line[128];
    int written;
    int fd = -1;

    /* Every injected client appends to this same file, so a bare line cannot be
     * attributed to a process: with two clients running, one process's
     * "tap-hooked" reads as the other's and a client that failed to hook goes
     * unreported. The PID prefix is what lets the Python side wait for one
     * terminal status per process it injected. Messages are short literals, so
     * one that would not fit is written unqualified rather than dropped. */
    written = _snprintf(line, sizeof(line), "%lu %s", (unsigned long)GetCurrentProcessId(), message);
    if (written > 0 && written < (int)sizeof(line)) {
        text = line;
    }

    if (env_path != NULL && env_path[0] != '\0') {
        fd = _open(env_path, _O_CREAT | _O_WRONLY | _O_APPEND | _O_BINARY, _S_IREAD | _S_IWRITE);
    } else if (g_status_path[0] != L'\0') {
        fd = _wopen(g_status_path, _O_CREAT | _O_WRONLY | _O_APPEND | _O_BINARY, _S_IREAD | _S_IWRITE);
    }
    if (fd >= 0) {
        _write(fd, text, (unsigned int)strlen(text));
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

/* The peer port of this SSL connection, and (through *out_fd) the socket it
 * runs on. The socket is what tells two concurrent connections apart: the
 * reassembler downstream has to keep their byte streams separate, and a peer
 * port alone does not, because two connections can share one. */
static uint16_t peer_port_for_ssl(SSL *ssl, int *out_fd) {
    int fd;
    struct sockaddr_storage address;
    socklen_t address_len = sizeof(address);

    if (out_fd != NULL) {
        *out_fd = -1;
    }

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
    if (out_fd != NULL) {
        *out_fd = fd;
    }
    if (address.ss_family == AF_INET) {
        return ntohs(((struct sockaddr_in *)&address)->sin_port);
    }
    if (address.ss_family == AF_INET6) {
        return ntohs(((struct sockaddr_in6 *)&address)->sin6_port);
    }
    return 0;
}

/* A byte identifying this process among the clients sharing one archive.
 * Several injected clients append to the same file, so a stream key built only
 * from (peer port, socket) can still collide across processes: two processes
 * routinely hold the same small socket number. Folding the process in keeps
 * their streams apart.
 *
 * The launcher assigns this (see swc_read_stream_id): it knows every client it
 * is injecting into, so it can hand out distinct ids. Deriving one here instead
 * could only hash the process id down to a byte, and a hash collides -- pids 4
 * and 1024 both fold to 4 -- which is exactly the splice this field exists to
 * prevent. The hash survives only as the fallback for a tap injected without an
 * assignment, where it still beats the constant every client shared before. */
static uint8_t g_source_id = 0;

static uint8_t capture_source_id(void) {
    return g_source_id;
}

static uint8_t swc_fallback_source_id(unsigned long pid) {
    /* Mix the high bits down so ids that differ only above bit 8 still differ. */
    return (uint8_t)((pid ^ (pid >> 8) ^ (pid >> 16)) & 0xFFu);
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
    int socket_fd = -1;
    struct swc_tap_header header;

    if (capture_fd < 0 || buffer == NULL || size <= 0 || (uint32_t)size > SWC_MAX_RECORD_SIZE) {
        return;
    }
    if (direction == 1 && !capture_outbound) {
        return;
    }
    peer_port = peer_port_for_ssl(ssl, &socket_fd);
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
    /* Stream identity, so the reassembler never splices two connections'
     * plaintext into one buffer. Both fields were reserved and written as zero,
     * so an archive recorded before this still decodes as the single stream it
     * was. */
    header.reserved = capture_source_id();
    header.reserved2 = (uint16_t)(socket_fd >= 0 ? (socket_fd & 0xFFFF) : 0);
    header.payload_size = (uint32_t)size;
    header.timestamp_us = now_us();

#ifndef _WIN32
    if (flock(capture_fd, LOCK_EX) == 0) {
        write_all(capture_fd, &header, sizeof(header));
        write_all(capture_fd, buffer, (size_t)size);
        flock(capture_fd, LOCK_UN);
    }
#else
    {
        DWORD wait = (g_capture_mutex != NULL) ? WaitForSingleObject(g_capture_mutex, SWC_CAPTURE_LOCK_TIMEOUT_MS)
                                               : WAIT_OBJECT_0;
        /* WAIT_ABANDONED still grants ownership: a peer died holding the mutex,
         * and records are only ever appended whole, so there is no shared state
         * to recover. Anything else drops this record rather than risk writing
         * it into another process's half-written one. */
        if (wait == WAIT_OBJECT_0 || wait == WAIT_ABANDONED) {
            AcquireSRWLockExclusive(&g_capture_lock);
            write_all(capture_fd, &header, sizeof(header));
            write_all(capture_fd, buffer, (size_t)size);
            ReleaseSRWLockExclusive(&g_capture_lock);
            if (g_capture_mutex != NULL) {
                ReleaseMutex(g_capture_mutex);
            }
        }
    }
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

/* Suspend every other thread while the entry point is changed. Merely writing
 * the JMP displacement before its opcode is not safe: bytes 1-4 are operands of
 * the original instruction until byte 0 changes. We also inspect each suspended
 * thread's instruction pointer and retry if one is currently inside the displaced
 * prologue, so no thread resumes in bytes whose meaning changed under it.
 *
 * A thread snapshot is a fixed list, so a thread created after it was taken is
 * invisible to it and stays runnable through the patch. Suspension therefore
 * repeats until a whole pass finds nothing new: once every other thread is
 * stopped, none of them can create another, so a pass that suspends nothing
 * proves the set is closed. */
#define SWC_MAX_SUSPENDED_THREADS 256u
/* Bound on those passes. A client creating threads faster than they can be
 * suspended would otherwise keep this spinning; failing closed leaves the
 * client's entry points untouched and the capture simply stays empty. */
#define SWC_MAX_SUSPEND_PASSES 8u

struct swc_suspended_threads {
    HANDLE handles[SWC_MAX_SUSPENDED_THREADS];
    DWORD ids[SWC_MAX_SUSPENDED_THREADS];
    size_t count;
};

static void swc_resume_threads(struct swc_suspended_threads *state) {
    while (state->count > 0) {
        HANDLE thread = state->handles[--state->count];
        ResumeThread(thread);
        CloseHandle(thread);
    }
}

static int swc_thread_is_suspended(const struct swc_suspended_threads *state, DWORD thread_id) {
    for (size_t index = 0; index < state->count; index++) {
        if (state->ids[index] == thread_id) {
            return 1;
        }
    }
    return 0;
}

/* Stop one thread and refuse the patch if it is inside the prologue being
 * displaced. 1 = suspended, 2 = inside the prologue, 0 = failure. A thread that
 * is rejected here is resumed before returning, so it is never left in `state`. */
static int swc_suspend_thread(struct swc_suspended_threads *state, DWORD thread_id,
                              const uint8_t *start, SIZE_T length) {
    HANDLE thread = OpenThread(THREAD_SUSPEND_RESUME | THREAD_GET_CONTEXT, FALSE, thread_id);
    CONTEXT context;
    uintptr_t ip;

    if (thread == NULL) {
        /* The thread exited between the snapshot and here: nothing left to stop. */
        return GetLastError() == ERROR_INVALID_PARAMETER ? 1 : 0;
    }
    if (SuspendThread(thread) == (DWORD)-1) {
        CloseHandle(thread);
        return 0;
    }
    memset(&context, 0, sizeof(context));
    context.ContextFlags = CONTEXT_CONTROL;
    if (!GetThreadContext(thread, &context)) {
        ResumeThread(thread);
        CloseHandle(thread);
        return 0;
    }
#ifdef _WIN64
    ip = (uintptr_t)context.Rip;
#else
    ip = (uintptr_t)context.Eip;
#endif
    if (ip >= (uintptr_t)start && ip < (uintptr_t)(start + length)) {
        ResumeThread(thread);
        CloseHandle(thread);
        return 2;
    }
    if (state->count >= SWC_MAX_SUSPENDED_THREADS) {
        ResumeThread(thread);
        CloseHandle(thread);
        return 0;
    }
    state->handles[state->count] = thread;
    state->ids[state->count] = thread_id;
    state->count++;
    return 1;
}

/* 0 = failure, 1 = ready to patch, 2 = a thread is inside the prologue. */
static int swc_suspend_other_threads(struct swc_suspended_threads *state,
                                     const uint8_t *start, SIZE_T length) {
    const DWORD process_id = GetCurrentProcessId();
    const DWORD current_thread_id = GetCurrentThreadId();

    state->count = 0;
    for (DWORD pass = 0; pass < SWC_MAX_SUSPEND_PASSES; pass++) {
        HANDLE snapshot = CreateToolhelp32Snapshot(TH32CS_SNAPTHREAD, 0);
        THREADENTRY32 entry;
        size_t suspended_this_pass = 0;
        int outcome = 1;

        if (snapshot == INVALID_HANDLE_VALUE) {
            swc_resume_threads(state);
            return 0;
        }
        memset(&entry, 0, sizeof(entry));
        entry.dwSize = sizeof(entry);
        if (!Thread32First(snapshot, &entry)) {
            CloseHandle(snapshot);
            swc_resume_threads(state);
            return 0;
        }

        for (;;) {
            if (entry.th32OwnerProcessID == process_id && entry.th32ThreadID != current_thread_id &&
                !swc_thread_is_suspended(state, entry.th32ThreadID)) {
                size_t before = state->count;
                int suspended = swc_suspend_thread(state, entry.th32ThreadID, start, length);
                if (suspended != 1) {
                    outcome = suspended;
                    break;
                }
                /* A thread that was already gone counts as stopped but not as
                 * new, so it cannot keep this loop asking for another pass. */
                suspended_this_pass += (state->count > before) ? 1 : 0;
            }
            if (!Thread32Next(snapshot, &entry)) {
                if (GetLastError() != ERROR_NO_MORE_FILES) {
                    outcome = 0;
                }
                break;
            }
        }
        CloseHandle(snapshot);

        if (outcome != 1) {
            swc_resume_threads(state);
            return outcome;
        }
        if (suspended_this_pass == 0) {
            return 1; /* every other thread, including ones created mid-pass, is stopped */
        }
    }

    swc_resume_threads(state);
    return 0;
}

/* Install a 5-byte JMP-rel32 hook over *target*. The trampoline is published
 * through published_trampoline while all other threads are still suspended,
 * before the patched entry point can be executed by another SSL caller. */
static void *swc_install_inline_hook(void *target, void *hook, ssl_rw_cdecl_fn *published_trampoline) {
    uint8_t *fn = (uint8_t *)target;
    if (published_trampoline == NULL) {
        return NULL;
    }
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
    tramp[steal] = 0xE9;
    int32_t back = (int32_t)((fn + steal) - (tramp + steal + 5));
    memcpy(tramp + steal + 1, &back, sizeof(back));

    uint8_t patch[5];
    int32_t forward = (int32_t)((uint8_t *)hook - (fn + 5));
    patch[0] = 0xE9;
    memcpy(patch + 1, &forward, sizeof(forward));

    struct swc_suspended_threads suspended;
    int suspension = 0;
    for (int attempt = 0; attempt < 100; attempt++) {
        suspension = swc_suspend_other_threads(&suspended, fn, (SIZE_T)steal);
        if (suspension == 1) {
            break;
        }
        if (suspension == 0) {
            VirtualFree(tramp, 0, MEM_RELEASE);
            return NULL;
        }
        Sleep(1);
    }
    if (suspension != 1) {
        VirtualFree(tramp, 0, MEM_RELEASE);
        return NULL;
    }

    DWORD old_protect = 0;
    if (!VirtualProtect(fn, sizeof(patch), PAGE_EXECUTE_READWRITE, &old_protect)) {
        swc_resume_threads(&suspended);
        VirtualFree(tramp, 0, MEM_RELEASE);
        return NULL;
    }

    memcpy(fn, patch, sizeof(patch));
    FlushInstructionCache(GetCurrentProcess(), fn, sizeof(patch));

    DWORD ignored = 0;
    if (!VirtualProtect(fn, sizeof(patch), old_protect, &ignored)) {
        /* Fail closed: restore the original entry point before resuming callers. */
        memcpy(fn, tramp, sizeof(patch));
        FlushInstructionCache(GetCurrentProcess(), fn, sizeof(patch));
        VirtualProtect(fn, sizeof(patch), old_protect, &ignored);
        swc_resume_threads(&suspended);
        VirtualFree(tramp, 0, MEM_RELEASE);
        return NULL;
    }

    *published_trampoline = (ssl_rw_cdecl_fn)tramp;
    MemoryBarrier();
    swc_resume_threads(&suspended);
    return tramp;
}

static int __cdecl swc_hook_SSL_read(SSL *ssl, void *buffer, int size) {
    if (real_SSL_read == NULL) {
        return -1;
    }
    int result = real_SSL_read(ssl, buffer, size);
    if (result > 0) {
        record_plaintext(ssl, buffer, result, 0);
    }
    return result;
}

static int __cdecl swc_hook_SSL_write(SSL *ssl, void *buffer, int size) {
    if (real_SSL_write == NULL) {
        return -1;
    }
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

    swc_install_inline_hook(addr_read, (void *)swc_hook_SSL_read, &real_SSL_read);
    swc_install_inline_hook(addr_write, (void *)swc_hook_SSL_write, &real_SSL_write);
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
    /* QSslSocket loads OpenSSL lazily, potentially long after fpdb attaches.
     * The injected DLL remains resident for the client lifetime, so keep this
     * lightweight worker alive until TLS appears or hook installation reaches
     * a terminal result. Re-injecting an already-loaded DLL does not rerun DllMain. */
    for (;;) {
        if (swc_try_install_hooks()) {
            return 0;
        }
        Sleep(250);
    }
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
/* The stream id the launcher assigned this process, or 0 if it assigned none.
 * Written to a per-pid sidecar so each injected client reads only its own. */
static uint8_t swc_read_stream_id(const wchar_t *dir, unsigned long pid) {
    wchar_t path[MAX_PATH];
    int fd;
    char buf[64];
    int n;
    const char *p;

    _snwprintf(path, MAX_PATH, L"%sswc-native-%lu.cfg", dir, pid);
    fd = _wopen(path, _O_RDONLY | _O_BINARY);
    if (fd < 0) {
        return 0;
    }
    n = _read(fd, buf, (unsigned int)(sizeof(buf) - 1));
    _close(fd);
    if (n <= 0) {
        return 0;
    }
    buf[n] = '\0';
    p = strstr(buf, "stream=");
    if (p == NULL) {
        return 0;
    }
    return (uint8_t)(strtoul(p + 7, NULL, 10) & 0xFFu);
}

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

    {
        unsigned long pid = (unsigned long)GetCurrentProcessId();
        g_source_id = swc_read_stream_id(dir, pid);
        if (g_source_id == 0) {
            g_source_id = swc_fallback_source_id(pid);
        }
    }

    /* Opened before any record can be written, and reported before tap-loaded so
     * that line stays the last status the Python side reads. Without it, records
     * are ordered per process only; say so, because a desynchronised archive is
     * otherwise silent. */
    g_capture_mutex = CreateMutexW(NULL, FALSE, SWC_CAPTURE_MUTEX_NAME);
    if (g_capture_mutex == NULL) {
        write_status("tap-cross-process-lock-unavailable\n");
    }

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
    if (g_capture_mutex != NULL) {
        CloseHandle(g_capture_mutex);
        g_capture_mutex = NULL;
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
