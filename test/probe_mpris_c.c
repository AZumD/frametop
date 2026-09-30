/* Mirror AskFrametopMpris from screens/vr.cpp for diagnosing @frametop_mpris. */
#include <errno.h>
#include <stdio.h>
#include <string.h>
#include <sys/socket.h>
#include <sys/un.h>
#include <unistd.h>
#include <stddef.h>

int main(void) {
    char reply[512];
    reply[0] = 0;
    int fd = socket(AF_UNIX, SOCK_DGRAM | SOCK_CLOEXEC, 0);
    if (fd < 0) {
        perror("socket");
        return 1;
    }
    struct sockaddr_un local;
    memset(&local, 0, sizeof local);
    local.sun_family = AF_UNIX;
    if (bind(fd, (struct sockaddr *)&local, sizeof(sa_family_t)) != 0) {
        perror("bind autobind");
        close(fd);
        return 2;
    }
    struct timeval tv = {.tv_sec = 0, .tv_usec = 400000};
    setsockopt(fd, SOL_SOCKET, SO_RCVTIMEO, &tv, sizeof tv);
    struct sockaddr_un dest;
    memset(&dest, 0, sizeof dest);
    dest.sun_family = AF_UNIX;
    dest.sun_path[0] = '\0';
    const char kName[] = "frametop_mpris";
    memcpy(dest.sun_path + 1, kName, sizeof kName - 1);
    socklen_t destLen = (socklen_t)(offsetof(struct sockaddr_un, sun_path) + 1 + sizeof kName - 1);
    const char *cmd = "state";
    ssize_t sent = sendto(fd, cmd, strlen(cmd), 0, (struct sockaddr *)&dest, destLen);
    if (sent < 0) {
        perror("sendto");
        close(fd);
        return 3;
    }
    ssize_t n = recvfrom(fd, reply, sizeof reply - 1, 0, NULL, NULL);
    if (n <= 0) {
        perror("recvfrom");
        close(fd);
        return 4;
    }
    reply[n] = 0;
    printf("ok: %s\n", reply);
    close(fd);
    return 0;
}
