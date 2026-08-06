#if defined(__linux__) || defined(__gnu_linux__)
#ifndef _GNU_SOURCE
#define _GNU_SOURCE
#endif
#endif

#ifdef __APPLE__
#define _DARWIN_C_SOURCE
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
#include <windows.h>
#include <winsock2.h>
#include <ws2tcpip.h>
#include <io.h>
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

static void write_status(const char *message) {
    const char *path = getenv("SWC_CAPTURE_STATUS_PATH");
    int fd;

    if (path == NULL || path[0] == '\0') {
        return;
    }
#ifndef _WIN32
    fd = open(path, O_CREAT | O_WRONLY | O_APPEND | O_CLOEXEC, S_IRUSR | S_IWUSR);
    if (fd >= 0) {
        write(fd, message, strlen(message));
        close(fd);
    }
#else
    fd = _open(path, _O_CREAT | _O_WRONLY | _O_APPEND | _O_BINARY, _S_IREAD | _S_IWRITE);
    if (fd >= 0) {
        _write(fd, message, (unsigned int)strlen(message));
        _close(fd);
    }
#endif
}

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

#ifndef _WIN32
__attribute__((constructor)) static void initialize_swc_tap(void) {
#else
static void initialize_swc_tap(void) {
#endif
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
#ifndef _WIN32
    capture_fd = open(path, O_CREAT | O_WRONLY | O_APPEND | O_CLOEXEC, S_IRUSR | S_IWUSR);
#else
    capture_fd = _open(path, _O_CREAT | _O_WRONLY | _O_APPEND | _O_BINARY, _S_IREAD | _S_IWRITE);
#endif
    write_status(capture_fd >= 0 ? "tap-loaded\n" : "tap-load-open-failed\n");
}

#ifndef _WIN32
__attribute__((destructor)) static void close_swc_tap(void) {
#else
static void close_swc_tap(void) {
#endif
    if (capture_fd >= 0) {
#ifndef _WIN32
        close(capture_fd);
#else
        _close(capture_fd);
#endif
        capture_fd = -1;
    }
}

#ifdef _WIN32
BOOL WINAPI DllMain(HINSTANCE hinstDLL, DWORD fdwReason, LPVOID lpvReserved) {
    (void)hinstDLL; (void)lpvReserved;
    if (fdwReason == DLL_PROCESS_ATTACH) {
        initialize_swc_tap();
    } else if (fdwReason == DLL_PROCESS_DETACH) {
        close_swc_tap();
    }
    return TRUE;
}
#endif

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
static ssl_read_fn real_SSL_read = NULL;
static ssl_write_fn real_SSL_write = NULL;

static void init_win_ssl(void) {
    if (real_SSL_read && real_SSL_write) return;
    HMODULE h_ssl = GetModuleHandleA("ssleay32.dll");
    if (!h_ssl) h_ssl = GetModuleHandleA("libssl-1_1.dll");
    if (!h_ssl) h_ssl = GetModuleHandleA("libssl-1_1-x64.dll");
    if (!h_ssl) h_ssl = GetModuleHandleA("libssl32.dll");
    if (h_ssl) {
        real_SSL_read = (ssl_read_fn)GetProcAddress(h_ssl, "SSL_read");
        real_SSL_write = (ssl_write_fn)GetProcAddress(h_ssl, "SSL_write");
    }
}

__declspec(dllexport) int SSL_read(SSL *ssl, void *buffer, int size) {
    init_win_ssl();
    int result = real_SSL_read ? real_SSL_read(ssl, buffer, size) : -1;
    if (result > 0) {
        record_plaintext(ssl, buffer, result, 0);
    }
    return result;
}

__declspec(dllexport) int SSL_write(SSL *ssl, const void *buffer, int size) {
    init_win_ssl();
    int result = real_SSL_write ? real_SSL_write(ssl, buffer, size) : -1;
    if (result > 0) {
        record_plaintext(ssl, buffer, result, 1);
    }
    return result;
}
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

