/*
 * tactiq-reftool: a reference tool for the TactiQ OS tool boundary.
 * Development image only.
 *
 * An MCP server on stdio, started by agentgateway as a child process, as
 * agentgateway-config requires of every tool. It has no socket and no port.
 * One tool, valve_status, returns one fixed answer: a constant, not a
 * reading. It reads nothing from the device and changes nothing.
 *
 * Protocol: newline-delimited JSON-RPC 2.0 on stdin and stdout. Handled:
 * initialize (the client's protocolVersion is echoed), ping, tools/list,
 * tools/call; notifications get no reply; any other request gets
 * -32601. Nothing is written to stderr: the gateway's stderr is its own.
 *
 * SPDX-License-Identifier: MIT
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define FIELD 256

static const char *skip_ws(const char *p)
{
    while (*p == ' ' || *p == '\t' || *p == '\r' || *p == '\n')
        p++;
    return p;
}

/* p at the opening quote; returns the char after the closing quote, or NULL. */
static const char *skip_string(const char *p)
{
    if (*p != '"')
        return NULL;
    for (p++; *p; p++) {
        if (*p == '\\') {
            if (!*++p)
                return NULL;
        } else if (*p == '"') {
            return p + 1;
        }
    }
    return NULL;
}

/* p at the start of any JSON value; returns the char after it, or NULL. */
static const char *skip_value(const char *p)
{
    p = skip_ws(p);
    if (*p == '"')
        return skip_string(p);
    if (*p == '{' || *p == '[') {
        int depth = 0;
        while (*p) {
            if (*p == '"') {
                p = skip_string(p);
                if (!p)
                    return NULL;
                continue;
            }
            if (*p == '{' || *p == '[')
                depth++;
            else if (*p == '}' || *p == ']') {
                if (--depth == 0)
                    return p + 1;
            }
            p++;
        }
        return NULL;
    }
    /* number, true, false, null */
    const char *s = p;
    while (*p && *p != ',' && *p != '}' && *p != ']' && *p != ' ' && *p != '\t' &&
           *p != '\r' && *p != '\n')
        p++;
    return p > s ? p : NULL;
}

/* In the object starting at obj, the value of top-level member key, or NULL. */
static const char *member(const char *obj, const char *key)
{
    const char *p = skip_ws(obj);
    if (*p != '{')
        return NULL;
    p = skip_ws(p + 1);
    size_t klen = strlen(key);
    while (*p == '"') {
        const char *ks = p + 1, *ke = skip_string(p);
        if (!ke)
            return NULL;
        p = skip_ws(ke);
        if (*p != ':')
            return NULL;
        const char *v = skip_ws(p + 1);
        if ((size_t)(ke - 1 - ks) == klen && memcmp(ks, key, klen) == 0)
            return v;
        p = skip_value(v);
        if (!p)
            return NULL;
        p = skip_ws(p);
        if (*p == ',')
            p = skip_ws(p + 1);
        else
            break;
    }
    return NULL;
}

/* The raw text of the value at v (a number or a whole quoted string) into out. */
static int raw_value(const char *v, char *out, size_t n)
{
    const char *e = v ? skip_value(v) : NULL;
    if (!e || (size_t)(e - v) >= n)
        return -1;
    memcpy(out, v, (size_t)(e - v));
    out[e - v] = '\0';
    return 0;
}

/* A string value without escapes into out (the fields read here have none). */
static int plain_string(const char *v, char *out, size_t n)
{
    if (!v || *v != '"')
        return -1;
    const char *e = skip_string(v);
    if (!e)
        return -1;
    size_t len = (size_t)(e - v - 2);
    if (len >= n || memchr(v + 1, '\\', len))
        return -1;
    memcpy(out, v + 1, len);
    out[len] = '\0';
    return 0;
}

static void reply(const char *id, const char *result)
{
    printf("{\"jsonrpc\":\"2.0\",\"id\":%s,\"result\":%s}\n", id, result);
    fflush(stdout);
}

static void error(const char *id, int code, const char *msg)
{
    printf("{\"jsonrpc\":\"2.0\",\"id\":%s,\"error\":{\"code\":%d,\"message\":\"%s\"}}\n", id,
           code, msg);
    fflush(stdout);
}

static const char TOOLS[] =
    "{\"tools\":[{\"name\":\"valve_status\","
    "\"description\":\"Reference tool: a fixed answer about valve V-101, not a reading.\","
    "\"inputSchema\":{\"type\":\"object\",\"properties\":{}}}]}";

static const char ANSWER[] =
    "{\"content\":[{\"type\":\"text\",\"text\":"
    "\"{\\\"valve\\\":\\\"V-101\\\",\\\"state\\\":\\\"closed\\\","
    "\\\"note\\\":\\\"fixed reference answer, not a reading\\\"}\"}],"
    "\"isError\":false}";

int main(void)
{
    char *line = NULL;
    size_t cap = 0;
    while (getline(&line, &cap, stdin) > 0) {
        char method[FIELD], id[FIELD];
        if (plain_string(member(line, "method"), method, sizeof method) != 0)
            continue; /* a response or garbage: nothing to answer */
        if (raw_value(member(line, "id"), id, sizeof id) != 0)
            continue; /* a notification */
        if (strcmp(method, "initialize") == 0) {
            char ver[FIELD] = "2025-06-18";
            const char *params = member(line, "params");
            if (params)
                plain_string(member(params, "protocolVersion"), ver, sizeof ver);
            char result[FIELD * 2];
            snprintf(result, sizeof result,
                     "{\"protocolVersion\":\"%s\",\"capabilities\":{\"tools\":{}},"
                     "\"serverInfo\":{\"name\":\"tactiq-reftool\",\"version\":\"1.0.0\"}}",
                     ver);
            reply(id, result);
        } else if (strcmp(method, "ping") == 0) {
            reply(id, "{}");
        } else if (strcmp(method, "tools/list") == 0) {
            reply(id, TOOLS);
        } else if (strcmp(method, "tools/call") == 0) {
            char name[FIELD] = "";
            const char *params = member(line, "params");
            if (params)
                plain_string(member(params, "name"), name, sizeof name);
            if (strcmp(name, "valve_status") == 0)
                reply(id, ANSWER);
            else
                error(id, -32602, "unknown tool");
        } else {
            error(id, -32601, "method not found");
        }
    }
    free(line);
    return 0;
}
