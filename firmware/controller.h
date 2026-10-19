/* Simulated blood pump controller: motor control, alarms and a simple hemodynamic model.
 * Educational simulation; not a medical device. Time is simulated: it only advances via ctl_tick(). */
#ifndef CONTROLLER_H
#define CONTROLLER_H

#include <stdbool.h>
#include <stdint.h>

#define TICK_MS 10
#define NUM_PLEVELS 10
#define EVENT_CAP 256
#define EVENT_LEN 96

typedef enum { ST_OFF, ST_RUNNING, ST_ALARM_STOP } pump_state;
typedef enum { PRIO_LOW = 1, PRIO_MEDIUM = 2, PRIO_HIGH = 3 } alarm_prio;
typedef enum { AL_SUCTION, AL_LOW_FLOW, AL_PURGE_LOW, AL_PURGE_HIGH, AL_MOTOR_STALL, AL_SENSOR_FAULT, AL_COUNT } alarm_id;
typedef enum { F_SUCTION, F_OCCLUSION, F_PURGE_LEAK, F_PURGE_BLOCK, F_STALL, F_SENSOR, F_COUNT } fault_id;

typedef struct {
    bool active, condition, acked;
    uint64_t activated_at, silenced_until;
    uint32_t debounce_ms;
} alarm_t;

typedef struct {
    uint64_t now_ms;
    pump_state state;
    int plevel;
    double target_rpm, rpm;
    double lvp, aop, flow, purge;      /* lvp/aop are NAN on a sensor fault */
    double beat_flow_sum, beat_flow_mean, beat_lvp_min;
    int beat_samples, suction_beats;
    bool flow_valid;
    uint32_t stall_ms;
    bool faults[F_COUNT];
    alarm_t alarms[AL_COUNT];
    char events[EVENT_CAP][EVENT_LEN];
    int ev_head, ev_count, ev_dropped;
} controller;

extern const char *const ALARM_NAMES[AL_COUNT];
extern const char *const FAULT_NAMES[F_COUNT];
extern const char *const STATE_NAMES[3];
extern const alarm_prio ALARM_PRIO[AL_COUNT];
extern const double PLEVEL_RPM[NUM_PLEVELS];

void ctl_init(controller *c);
void ctl_tick(controller *c);                   /* advance TICK_MS */
bool ctl_set_plevel(controller *c, int level);  /* false if out of range */
bool ctl_start(controller *c);                  /* false if level 0 */
void ctl_stop(controller *c);
int ctl_ack(controller *c);                     /* returns alarms acknowledged */
void ctl_inject(controller *c, fault_id f, bool on);
int ctl_active_alarms(const controller *c, alarm_id out[AL_COUNT]); /* sorted: priority desc, oldest first */
const char *prio_name(alarm_prio p);

#endif
