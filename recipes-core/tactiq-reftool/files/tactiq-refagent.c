/*
 * tactiq-refagent: a reference agent for the TactiQ OS tool boundary.
 * Development image only.
 *
 * Runs in tactiq_refagent_t, a domain of tactiq_ai_agent_domain, and makes
 * four attempts, each reported on one line on standard output. The first
 * three go around the gateway and must be refused by SELinux with EACCES:
 *
 *   exec     run the tool binary itself (assertion 3 in tactiq_fixes);
 *   stop     connect to tactiq-stop on 127.0.0.1:49318 (assertion 5);
 *   plant    connect to 10.0.0.1:502, a Modbus address (assertion 5);
 *
 * and the fourth goes through it:
 *
 *   gateway  an MCP tools/call of valve_status, POST to agentgateway on
 *            127.0.0.1:49317. 200 with the tool's answer when the agent is
 *            running, 403 with a TQSR stop receipt when it is stopped.
 *
 * Only EACCES counts as the policy refusing. Any other error (ENOENT,
 * ENETUNREACH, ECONNREFUSED) says nothing about the boundary and is reported
 * as inconclusive, not as a pass. SELinux checks a connect before routing,
 * so on a board without a network the plant attempt still shows the policy.
 *
 * Exit status:
 *   0  exec, stop and plant refused with EACCES, and the gateway answered;
 *   1  at least one of them succeeded: the boundary did not hold;
 *   2  none succeeded, but the gateway could not be reached or did not answer;
 *   3  none succeeded, but at least one failed for a reason other than EACCES.
 *
 * The same binary run from a root shell (unconfined_t) is the control: there
 * exec and stop succeed, which shows the targets were reachable and that the
 * refusals in tactiq_refagent_t came from the policy.
 *
 * SPDX-License-Identifier: MIT
 */
#include <arpa/inet.h>
#include <errno.h>
#include <fcntl.h>
#include <netinet/in.h>
#include <stdio.h>
#include <string.h>
#include <sys/socket.h>
#include <sys/time.h>
#include <sys/wait.h>
#include <unistd.h>

#ifndef TOOL_BIN
#define TOOL_BIN "/opt/tactiq/bin/tactiq-reftool"
#endif
#define GATEWAY_PORT 49317
#define STOP_PORT 49318

enum { HELD, BROKE, UNSURE };

static int report(const char *what, int err, const char *ok_detail)
{
    if (err == 0) {
        printf("%s: SUCCEEDED (%s), the boundary did not hold\n", what, ok_detail);
        return BROKE;
    }
    if (err == EACCES) {
        printf("%s: denied (%s), as the policy requires\n", what, strerror(err));
        return HELD;
    }
    printf("%s: failed (%s), inconclusive: not a policy denial\n", what, strerror(err));
    return UNSURE;
}

/* fork and execve the tool with stdin at end of file; the errno of execve, or 0. */
static int try_exec(void)
{
    int p[2];
    if (pipe2(p, O_CLOEXEC) < 0)
        return errno;
    pid_t pid = fork();
    if (pid < 0)
        return errno;
    if (pid == 0) {
        int devnull = open("/dev/null", O_RDWR);
        if (devnull >= 0) {
            dup2(devnull, 0);
            dup2(devnull, 1);
        }
        char *argv[] = {TOOL_BIN, NULL};
        char *envp[] = {NULL};
        execve(TOOL_BIN, argv, envp);
        int e = errno;
        if (write(p[1], &e, sizeof e) < 0) {
        }
        _exit(127);
    }
    close(p[1]);
    int e = 0;
    ssize_t r = read(p[0], &e, sizeof e);
    close(p[0]);
    waitpid(pid, NULL, 0);
    return r == (ssize_t)sizeof e ? e : 0;
}

static int connect_to(const char *ip, int port, int *fd)
{
    int s = socket(AF_INET, SOCK_STREAM, 0);
    if (s < 0)
        return errno;
    struct sockaddr_in a;
    memset(&a, 0, sizeof a);
    a.sin_family = AF_INET;
    a.sin_port = htons((unsigned short)port);
    inet_pton(AF_INET, ip, &a.sin_addr);
    struct timeval tv = {3, 0};
    setsockopt(s, SOL_SOCKET, SO_SNDTIMEO, &tv, sizeof tv);
    if (connect(s, (struct sockaddr *)&a, sizeof a) < 0) {
        int e = errno;
        close(s);
        return e;
    }
    if (fd)
        *fd = s;
    else
        close(s);
    return 0;
}

static int worst(int a, int b)
{
    return a == BROKE || b == BROKE ? BROKE : (a == UNSURE || b == UNSURE ? UNSURE : HELD);
}

int main(void)
{
    int v = HELD;
    v = worst(v, report("exec", try_exec(), "the tool binary ran"));
    v = worst(v, report("stop", connect_to("127.0.0.1", STOP_PORT, NULL), "connected"));
    v = worst(v, report("plant", connect_to("10.0.0.1", 502, NULL), "connected"));

    int g = -1;
    int e = connect_to("127.0.0.1", GATEWAY_PORT, &g);
    if (e != 0) {
        printf("gateway: cannot connect to 127.0.0.1:%d (%s)\n", GATEWAY_PORT, strerror(e));
        fflush(stdout);
        return v == BROKE ? 1 : (v == UNSURE ? 3 : 2);
    }
    /* A signed refusal takes a few seconds: four TPM operations. */
    struct timeval tv = {15, 0};
    setsockopt(g, SOL_SOCKET, SO_RCVTIMEO, &tv, sizeof tv);
    static const char BODY[] = "{\"jsonrpc\":\"2.0\",\"id\":1,\"method\":\"tools/call\","
                               "\"params\":{\"name\":\"valve_status\",\"arguments\":{}}}";
    char req[512];
    int n = snprintf(req, sizeof req,
                     "POST /mcp HTTP/1.1\r\nHost: 127.0.0.1:%d\r\n"
                     "Content-Type: application/json\r\n"
                     "Accept: application/json, text/event-stream\r\n"
                     "Content-Length: %zu\r\nConnection: close\r\n\r\n%s",
                     GATEWAY_PORT, sizeof BODY - 1, BODY);
    if (n <= 0 || write(g, req, (size_t)n) != n) {
        printf("gateway: write failed (%s)\n", strerror(errno));
        close(g);
        fflush(stdout);
        return v == BROKE ? 1 : (v == UNSURE ? 3 : 2);
    }
    static char buf[16384];
    size_t got = 0;
    for (;;) {
        ssize_t r = read(g, buf + got, sizeof buf - 1 - got);
        if (r <= 0)
            break;
        got += (size_t)r;
        if (got == sizeof buf - 1)
            break;
    }
    close(g);
    buf[got] = '\0';
    char *eol = strstr(buf, "\r\n");
    char *body = strstr(buf, "\r\n\r\n");
    if (!eol || strncmp(buf, "HTTP/", 5) != 0) {
        printf("gateway: no HTTP answer (%zu bytes)\n", got);
        fflush(stdout);
        return v == BROKE ? 1 : (v == UNSURE ? 3 : 2);
    }
    *eol = '\0';
    size_t blen = body ? got - (size_t)(body + 4 - buf) : 0;
    const char *kind = "";
    if (body && blen >= 4 && memcmp(body + 4, "TQSR", 4) == 0)
        kind = ", body is a TQSR stop receipt";
    else if (body && strstr(body + 4, "V-101"))
        kind = ", body carries the tool's answer";
    printf("gateway: %s, body %zu bytes%s\n", buf, blen, kind);
    fflush(stdout);
    return v == BROKE ? 1 : (v == UNSURE ? 3 : 0);
}
