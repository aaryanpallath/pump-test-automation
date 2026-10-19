/* Line protocol over stdin/stdout. Every command gets exactly one final line starting with OK or ERR. */
#include <errno.h>
#include <limits.h>
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "controller.h"

#define LINE_MAX_LEN 128
#define TICK_MAX_MS 3600000L

static controller ctl;

static bool parse_long(const char *s, long *out) {
    if (!s || !*s) return false;
    char *end;
    errno = 0;
    long v = strtol(s, &end, 10);
    if (errno || *end) return false;
    *out = v;
    return true;
}

static void cmd_status(void) {
    char flow[16];
    if (ctl.flow_valid) snprintf(flow, sizeof flow, "%.2f", ctl.flow);
    else snprintf(flow, sizeof flow, "NA");
    alarm_id ids[AL_COUNT];
    printf("OK t=%llu state=%s plevel=%d rpm=%.0f target=%.0f flow=%s beat_flow=%.2f lvp=%.1f aop=%.1f purge=%.0f "
           "alarms=%d\n",
           (unsigned long long)ctl.now_ms, STATE_NAMES[ctl.state], ctl.plevel, ctl.rpm, ctl.target_rpm, flow,
           ctl.beat_flow_mean, ctl.lvp, ctl.aop, ctl.purge, ctl_active_alarms(&ctl, ids));
}

static void cmd_alarms(void) {
    alarm_id ids[AL_COUNT];
    int n = ctl_active_alarms(&ctl, ids);
    printf("OK n=%d", n);
    for (int i = 0; i < n; i++) {
        const alarm_t *a = &ctl.alarms[ids[i]];
        printf(" %s:%s:%s:%llu", ALARM_NAMES[ids[i]], prio_name(ALARM_PRIO[ids[i]]), a->acked ? "SILENCED" : "AUDIBLE",
               (unsigned long long)a->activated_at);
    }
    printf("\n");
}

static void cmd_events(void) {
    int n = ctl.ev_count;
    for (int i = 0; i < n; i++) printf("EVT %s\n", ctl.events[(ctl.ev_head + i) % EVENT_CAP]);
    printf("OK n=%d dropped=%d\n", n, ctl.ev_dropped);
    ctl.ev_count = ctl.ev_head = ctl.ev_dropped = 0;
}

static void handle(char *line) {
    char *save = NULL;
    char *cmd = strtok_r(line, " \t\r\n", &save);
    char *a1 = strtok_r(NULL, " \t\r\n", &save);
    char *a2 = strtok_r(NULL, " \t\r\n", &save);
    char *extra = strtok_r(NULL, " \t\r\n", &save);
    long v;
    if (!cmd) { printf("ERR E_EMPTY empty command\n"); return; }
    if (extra) { printf("ERR E_ARGS too many arguments\n"); return; }
    if (!strcmp(cmd, "PING") && !a1) printf("OK PONG\n");
    else if (!strcmp(cmd, "STATUS") && !a1) cmd_status();
    else if (!strcmp(cmd, "ALARMS") && !a1) cmd_alarms();
    else if (!strcmp(cmd, "EVENTS") && !a1) cmd_events();
    else if (!strcmp(cmd, "START") && !a1) {
        if (ctl_start(&ctl)) printf("OK\n"); else printf("ERR E_STATE cannot start at P0\n");
    } else if (!strcmp(cmd, "STOP") && !a1) { ctl_stop(&ctl); printf("OK\n"); }
    else if (!strcmp(cmd, "ACK") && !a1) printf("OK acked=%d\n", ctl_ack(&ctl));
    else if (!strcmp(cmd, "RESET") && !a1) { ctl_init(&ctl); printf("OK\n"); }
    else if (!strcmp(cmd, "SET") && a1 && !strcmp(a1, "PLEVEL")) {
        if (parse_long(a2, &v) && v >= INT_MIN && v <= INT_MAX && ctl_set_plevel(&ctl, (int)v)) printf("OK\n");
        else printf("ERR E_RANGE plevel must be 0-9\n");
    } else if (!strcmp(cmd, "TICK")) {
        if (!parse_long(a1, &v) || a2 || v < TICK_MS || v > TICK_MAX_MS) {
            printf("ERR E_RANGE tick must be %d-%ld ms\n", TICK_MS, TICK_MAX_MS);
            return;
        }
        for (long i = 0; i < v / TICK_MS; i++) ctl_tick(&ctl);
        printf("OK t=%llu\n", (unsigned long long)ctl.now_ms);
    } else if (!strcmp(cmd, "INJECT") && a1 && a2) {
        int f = -1;
        for (int i = 0; i < F_COUNT; i++)
            if (!strcmp(a1, FAULT_NAMES[i])) f = i;
        bool on = !strcmp(a2, "ON");
        if (f < 0 || (!on && strcmp(a2, "OFF"))) printf("ERR E_ARGS unknown fault or state\n");
        else { ctl_inject(&ctl, (fault_id)f, on); printf("OK\n"); }
    } else printf("ERR E_UNKNOWN unknown command\n");
}

/* Read one line byte by byte. Returns its length, or -1 at EOF. Lines longer than the buffer are consumed
 * entirely and flagged, and a NUL byte anywhere in the line is flagged, so every input line maps to exactly
 * one response. (fgets cannot do this: it measures the line with strlen, which stops at the first NUL.) */
static long read_line(char *buf, size_t cap, bool *too_long, bool *has_nul) {
    size_t n = 0;
    int ch;
    *too_long = *has_nul = false;
    while ((ch = getchar()) != EOF && ch != '\n') {
        if (ch == '\0') *has_nul = true;
        if (n < cap - 1) buf[n++] = (char)ch;
        else *too_long = true;
    }
    buf[n] = '\0';
    if (ch == EOF && n == 0 && !*too_long) return -1;
    return (long)n;
}

int main(void) {
    char line[LINE_MAX_LEN];
    bool too_long, has_nul;
    ctl_init(&ctl);
    setvbuf(stdout, NULL, _IOLBF, 0);
    while (read_line(line, sizeof line, &too_long, &has_nul) >= 0) {
        if (too_long) { printf("ERR E_TOOLONG command too long\n"); continue; }
        if (has_nul) { printf("ERR E_BADCHAR NUL byte in command\n"); continue; }
        if (!strcmp(line, "QUIT") || !strcmp(line, "QUIT\r")) break;
        handle(line);
    }
    return 0;
}
