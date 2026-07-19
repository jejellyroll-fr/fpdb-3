#define _DARWIN_C_SOURCE

#include <arpa/inet.h>
#include <dlfcn.h>
#include <errno.h>
#include <fcntl.h>
#include <netinet/in.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include <sys/file.h>
#include <sys/socket.h>
#include <sys/stat.h>
#include <sys/time.h>
#include <unistd.h>

/* Minimal OpenSSL ABI declarations: SwC ships libssl but not development headers. */
typedef struct ssl_st SSL;
extern int SSL_read(SSL *ssl, void *buffer, int size);
extern int SSL_write(SSL *ssl, const void *buffer, int size);
extern int SSL_get_fd(const SSL *ssl);

/*
 * Passive SwC Poker TLS tap.
 *
 * The native macOS client uses its bundled OpenSSL and calls SSL_read/SSL_write
 * directly.  This interposer records plaintext only after a successful SSL
 * operation.  By default it records inbound traffic from the game server port
 * (20013), deliberately excluding the lobby/login connection on port 20001.
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
    fd = open(path, O_CREAT | O_WRONLY | O_APPEND | O_CLOEXEC, S_IRUSR | S_IWUSR);
    if (fd >= 0) {
        write(fd, message, strlen(message));
        close(fd);
    }
}

static uint64_t now_us(void) {
    struct timeval tv;
    gettimeofday(&tv, NULL);
    return ((uint64_t)tv.tv_sec * 1000000u) + (uint64_t)tv.tv_usec;
}

static uint16_t peer_port_for_ssl(SSL *ssl) {
    int fd;
    struct sockaddr_storage address;
    socklen_t address_len = sizeof(address);

    if (ssl == NULL || (fd = SSL_get_fd(ssl)) < 0) {
        return 0;
    }
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
        ssize_t written = write(fd, cursor, size);
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
    header.reserved2 = (uint16_t)SSL_get_fd(ssl);
    header.payload_size = (uint32_t)size;
    header.timestamp_us = now_us();

    if (flock(capture_fd, LOCK_EX) == 0) {
        write_all(capture_fd, &header, sizeof(header));
        write_all(capture_fd, buffer, (size_t)size);
        flock(capture_fd, LOCK_UN);
    }
}

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

static int swc_tap_ssl_read(SSL *ssl, void *buffer, int size) {
    int result;

    /* dyld keeps calls from the replacement image bound to the replacee. */
    result = SSL_read(ssl, buffer, size);
    if (result > 0) {
        record_plaintext(ssl, buffer, result, 0);
    }
    return result;
}

static int swc_tap_ssl_write(SSL *ssl, const void *buffer, int size) {
    int result;

    result = SSL_write(ssl, buffer, size);
    if (result > 0) {
        record_plaintext(ssl, buffer, result, 1);
    }
    return result;
}

/* Explicit dyld interposition is required for Mach-O's two-level namespace. */
struct interpose_entry {
    const void *replacement;
    const void *replacee;
};

__attribute__((used, section("__DATA,__interpose"))) static const struct interpose_entry interposers[] = {
    {(const void *)swc_tap_ssl_read, (const void *)SSL_read},
    {(const void *)swc_tap_ssl_write, (const void *)SSL_write},
};
