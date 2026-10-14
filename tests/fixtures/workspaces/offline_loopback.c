/* Qualification-only Linux/glibc transport injection, not a security sandbox.
 *
 * Build: cc -shared -fPIC -O2 -Wall -Wextra -Werror -o /tmp/tuldok-offline.so \
 *          tests/fixtures/workspaces/offline_loopback.c -ldl
 * Run: LD_PRELOAD=/tmp/tuldok-offline.so <ordinary app/browser/trainer command>
 *
 * Refused destinations never reach the real libc function. Unix sockets,
 * localhost and 127/8, ::1, ::ffff:127/8 remain usable for local PostgreSQL/HTTP.
 * This does not intercept adversarial direct syscalls, static executables,
 * sendmsg/io_uring, inherited external sockets, or independently launched
 * processes. Use only for the declared ordinary libc client workflow evidence.
 */
#define _GNU_SOURCE
#include <arpa/inet.h>
#include <dlfcn.h>
#include <errno.h>
#include <netdb.h>
#include <stddef.h>
#include <stdint.h>
#include <strings.h>
#include <sys/socket.h>
#include <sys/un.h>

static int local_address(const struct sockaddr *address, socklen_t length) {
    if (address == NULL || length < sizeof(sa_family_t)) return 0;
    if (address->sa_family == AF_UNIX) return 1;
    if (address->sa_family == AF_UNSPEC) return 1; /* UDP disconnect. */
    if (address->sa_family == AF_INET && length >= sizeof(struct sockaddr_in)) {
        const struct sockaddr_in *ipv4 = (const struct sockaddr_in *)address;
        return (ntohl(ipv4->sin_addr.s_addr) >> 24) == 127;
    }
    if (address->sa_family == AF_INET6 && length >= sizeof(struct sockaddr_in6)) {
        const struct in6_addr *ipv6 = &((const struct sockaddr_in6 *)address)->sin6_addr;
        return IN6_IS_ADDR_LOOPBACK(ipv6)
            || (IN6_IS_ADDR_V4MAPPED(ipv6) && ipv6->s6_addr[12] == 127);
    }
    return 0;
}

int connect(int socket, const struct sockaddr *address, socklen_t length) {
    if (!local_address(address, length)) {
        errno = EACCES;
        return -1;
    }
    int (*next_connect)(int, const struct sockaddr *, socklen_t) = dlsym(RTLD_NEXT, "connect");
    if (next_connect == NULL) { errno = ENOSYS; return -1; }
    return next_connect(socket, address, length);
}

ssize_t sendto(int socket, const void *buffer, size_t size, int flags,
               const struct sockaddr *address, socklen_t length) {
    /* No destination means a socket already connected under the same wrapper. */
    if (address != NULL && !local_address(address, length)) {
        errno = EACCES;
        return -1;
    }
    ssize_t (*next_sendto)(int, const void *, size_t, int, const struct sockaddr *, socklen_t)
        = dlsym(RTLD_NEXT, "sendto");
    if (next_sendto == NULL) { errno = ENOSYS; return -1; }
    return next_sendto(socket, buffer, size, flags, address, length);
}

int getaddrinfo(const char *node, const char *service, const struct addrinfo *hints,
                struct addrinfo **result) {
    int allowed = node == NULL || strcasecmp(node, "localhost") == 0;
    struct in_addr ipv4;
    struct in6_addr ipv6;
    if (!allowed && inet_pton(AF_INET, node, &ipv4) == 1)
        allowed = (ntohl(ipv4.s_addr) >> 24) == 127;
    if (!allowed && inet_pton(AF_INET6, node, &ipv6) == 1)
        allowed = IN6_IS_ADDR_LOOPBACK(&ipv6)
            || (IN6_IS_ADDR_V4MAPPED(&ipv6) && ipv6.s6_addr[12] == 127);
    if (!allowed) {
        if (result != NULL) *result = NULL;
        return EAI_NONAME;
    }
    int (*next_getaddrinfo)(const char *, const char *, const struct addrinfo *, struct addrinfo **)
        = dlsym(RTLD_NEXT, "getaddrinfo");
    if (next_getaddrinfo == NULL) return EAI_SYSTEM;
    return next_getaddrinfo(node, service, hints, result);
}
