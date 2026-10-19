#include "controller.h"

#include <math.h>
#include <stdarg.h>
#include <stdio.h>
#include <string.h>

const char *const ALARM_NAMES[AL_COUNT] = {"SUCTION", "LOW_FLOW", "PURGE_LOW", "PURGE_HIGH", "MOTOR_STALL",
                                           "SENSOR_FAULT"};
const alarm_prio ALARM_PRIO[AL_COUNT] = {PRIO_HIGH, PRIO_MEDIUM, PRIO_MEDIUM, PRIO_HIGH, PRIO_HIGH, PRIO_MEDIUM};
const char *const FAULT_NAMES[F_COUNT] = {"suction", "occlusion", "purge_leak", "purge_block", "stall", "sensor"};
const char *const STATE_NAMES[3] = {"OFF", "RUNNING", "ALARM_STOP"};
const double PLEVEL_RPM[NUM_PLEVELS] = {0, 25000, 28000, 31000, 33000, 35000, 37000, 40000, 43000, 46000};

#define PI 3.14159265358979323846
#define BEAT_MS 800                  /* 75 beats per minute */
#define SILENCE_MS 120000u
#define LOW_FLOW_LPM 1.0
#define LOW_FLOW_MS 5000u
#define PURGE_LOW_MMHG 300.0
#define PURGE_HIGH_MMHG 1100.0
#define PURGE_MS 3000u
#define STALL_FRACTION 0.10
#define STALL_MS 1000u
#define SENSOR_MS 200u

const char *prio_name(alarm_prio p) { return p == PRIO_HIGH ? "HIGH" : p == PRIO_MEDIUM ? "MEDIUM" : "LOW"; }

static void log_event(controller *c, const char *fmt, ...) {
    char *slot;
    if (c->ev_count == EVENT_CAP) {          /* full: overwrite the oldest */
        slot = c->events[c->ev_head];
        c->ev_head = (c->ev_head + 1) % EVENT_CAP;
        c->ev_dropped++;
    } else {
        slot = c->events[(c->ev_head + c->ev_count) % EVENT_CAP];
        c->ev_count++;
    }
    int n = snprintf(slot, EVENT_LEN, "t=%llu ", (unsigned long long)c->now_ms);
    va_list ap;
    va_start(ap, fmt);
    vsnprintf(slot + n, (size_t)(EVENT_LEN - n), fmt, ap);
    va_end(ap);
}

static void set_state(controller *c, pump_state s) {
    if (c->state != s) {
        log_event(c, "type=STATE from=%s to=%s", STATE_NAMES[c->state], STATE_NAMES[s]);
        c->state = s;
    }
}

void ctl_init(controller *c) {
    memset(c, 0, sizeof *c);
    c->plevel = 2;
    c->purge = 500.0;
    c->beat_lvp_min = INFINITY;
    c->flow_valid = true;
    log_event(c, "type=STATE from=- to=OFF");
}

bool ctl_set_plevel(controller *c, int level) {
    if (level < 0 || level >= NUM_PLEVELS) return false;
    if (level != c->plevel) log_event(c, "type=PLEVEL from=%d to=%d", c->plevel, level);
    c->plevel = level;
    if (c->state == ST_RUNNING) c->target_rpm = PLEVEL_RPM[level];
    return true;
}

bool ctl_start(controller *c) {
    if (c->plevel == 0) return false;
    c->target_rpm = PLEVEL_RPM[c->plevel];
    c->stall_ms = 0;
    set_state(c, ST_RUNNING);
    return true;
}

void ctl_stop(controller *c) {
    c->target_rpm = 0;
    set_state(c, ST_OFF);
}

void ctl_inject(controller *c, fault_id f, bool on) {
    if (c->faults[f] != on) log_event(c, "type=FAULT name=%s on=%d", FAULT_NAMES[f], on);
    c->faults[f] = on;
}

/* ---- simulated patient and pump hydraulics ---- */
static void simulate(controller *c) {
    double phase = (double)(c->now_ms % BEAT_MS) / BEAT_MS;
    double s = fmax(0.0, sin(2 * PI * phase));
    double lv_dia = c->faults[F_SUCTION] ? -6.0 : 8.0;
    double lv_sys = c->faults[F_SUCTION] ? 60.0 : 100.0;
    double lvp = lv_dia + (lv_sys - lv_dia) * s * s;
    double aop = 70.0 + 35.0 * (0.5 + 0.5 * sin(2 * PI * phase - 1.0));

    /* motor: first-order response to the target; braking is faster than spin-up */
    if (c->faults[F_STALL]) c->rpm *= 0.5;
    else if (c->target_rpm < c->rpm) c->rpm *= 0.85;
    else c->rpm += (c->target_rpm - c->rpm) * 0.05;
    if (c->rpm < 50.0 && c->target_rpm == 0) c->rpm = 0;

    double flow = fmax(0.0, 0.11 * c->rpm / 1000.0 - 0.025 * (aop - lvp));
    if (c->rpm == 0) flow = 0;
    if (c->faults[F_OCCLUSION]) flow *= 0.2;
    c->flow = flow;
    c->purge = c->faults[F_PURGE_LEAK] ? 200.0 : c->faults[F_PURGE_BLOCK] ? 1200.0 : 500.0 + 20.0 * sin((double)c->now_ms / 7000.0);
    c->lvp = c->faults[F_SENSOR] ? NAN : lvp;
    c->aop = c->faults[F_SENSOR] ? NAN : aop;
}

/* ---- alarm conditions ---- */
static bool debounced(alarm_t *a, bool raw, uint32_t hold_ms) {
    a->debounce_ms = raw ? a->debounce_ms + TICK_MS : 0;
    return a->debounce_ms >= hold_ms;
}

static void evaluate_conditions(controller *c) {
    bool running = c->state == ST_RUNNING;
    alarm_t *al = c->alarms;
    bool sensor_ok = !isnan(c->lvp);

    /* beat bookkeeping: suction needs the minimum LVP of complete beats */
    if (sensor_ok && c->lvp < c->beat_lvp_min) c->beat_lvp_min = c->lvp;
    c->beat_flow_sum += c->flow;
    c->beat_samples++;
    if (c->now_ms % BEAT_MS == 0) {
        c->beat_flow_mean = c->beat_flow_sum / c->beat_samples;
        c->suction_beats = (running && sensor_ok && c->beat_lvp_min < 0.0) ? c->suction_beats + 1 : 0;
        c->beat_flow_sum = 0;
        c->beat_samples = 0;
        c->beat_lvp_min = INFINITY;
    }

    al[AL_SUCTION].condition = running && c->suction_beats >= 2;
    al[AL_LOW_FLOW].condition = debounced(&al[AL_LOW_FLOW], running && c->beat_flow_mean < LOW_FLOW_LPM, LOW_FLOW_MS);
    al[AL_PURGE_LOW].condition = debounced(&al[AL_PURGE_LOW], running && c->purge < PURGE_LOW_MMHG, PURGE_MS);
    al[AL_PURGE_HIGH].condition = debounced(&al[AL_PURGE_HIGH], running && c->purge > PURGE_HIGH_MMHG, PURGE_MS);
    al[AL_SENSOR_FAULT].condition = debounced(&al[AL_SENSOR_FAULT], !sensor_ok, SENSOR_MS);
    c->flow_valid = sensor_ok;

    bool stalled = running && c->target_rpm > 0 && c->rpm < STALL_FRACTION * c->target_rpm;
    c->stall_ms = stalled ? c->stall_ms + TICK_MS : 0;
    if (c->stall_ms >= STALL_MS && !al[AL_MOTOR_STALL].condition) {
        al[AL_MOTOR_STALL].condition = true;
        c->target_rpm = 0;
        set_state(c, ST_ALARM_STOP);
    } else if (!c->faults[F_STALL]) {
        al[AL_MOTOR_STALL].condition = false;
    }
}

static void update_alarms(controller *c) {
    for (int i = 0; i < AL_COUNT; i++) {
        alarm_t *a = &c->alarms[i];
        if (a->condition && !a->active) {
            a->active = true;
            a->acked = false;
            a->activated_at = c->now_ms;
            log_event(c, "type=ALARM_ON id=%s prio=%s", ALARM_NAMES[i], prio_name(ALARM_PRIO[i]));
        } else if (!a->condition && a->active && (ALARM_PRIO[i] != PRIO_HIGH || a->acked)) {
            a->active = false;
            log_event(c, "type=ALARM_OFF id=%s", ALARM_NAMES[i]);
        } else if (a->active && a->acked && a->condition && c->now_ms >= a->silenced_until) {
            a->acked = false;   /* silence expired and the condition persists: audible again */
            log_event(c, "type=ALARM_REANNUNCIATE id=%s", ALARM_NAMES[i]);
        }
    }
}

void ctl_tick(controller *c) {
    c->now_ms += TICK_MS;
    simulate(c);
    evaluate_conditions(c);
    update_alarms(c);
}

int ctl_ack(controller *c) {
    int n = 0;
    for (int i = 0; i < AL_COUNT; i++) {
        alarm_t *a = &c->alarms[i];
        if (!a->active || a->acked) continue;
        a->acked = true;
        a->silenced_until = c->now_ms + SILENCE_MS;
        log_event(c, "type=ALARM_ACK id=%s", ALARM_NAMES[i]);
        n++;
    }
    update_alarms(c);   /* a latched HIGH alarm whose condition has cleared ends on acknowledgement */
    return n;
}

int ctl_active_alarms(const controller *c, alarm_id out[AL_COUNT]) {
    int n = 0;
    for (int i = 0; i < AL_COUNT; i++)
        if (c->alarms[i].active) out[n++] = (alarm_id)i;
    for (int i = 1; i < n; i++) {     /* insertion sort: priority desc, then oldest first */
        alarm_id x = out[i];
        int j = i - 1;
        while (j >= 0 && (ALARM_PRIO[out[j]] < ALARM_PRIO[x] ||
                          (ALARM_PRIO[out[j]] == ALARM_PRIO[x] &&
                           c->alarms[out[j]].activated_at > c->alarms[x].activated_at))) {
            out[j + 1] = out[j];
            j--;
        }
        out[j + 1] = x;
    }
    return n;
}
