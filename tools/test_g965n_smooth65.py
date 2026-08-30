#!/usr/bin/env python3
"""Host tests of the actual CPU profile/selector, not a live-device thermal test."""
import os
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def function(path, signature):
    text = (ROOT / path).read_text()
    start = text.index(signature)
    body = text.index('{', start)
    depth = 1
    end = body + 1
    while depth:
        depth += (text[end] == '{') - (text[end] == '}')
        end += 1
    return text[start:end] + '\n'


source = r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <limits.h>
#include <errno.h>
#include <string.h>
#include <stdio.h>
#define CONFIG_SOC_EXYNOS9810 1
#define IS_ENABLED(x) (x)
#define ARRAY_SIZE(x) (sizeof(x) / sizeof((x)[0]))
#define max(a,b) ((a) > (b) ? (a) : (b))
enum thermal_trip_type { THERMAL_TRIP_ACTIVE, THERMAL_TRIP_PASSIVE,
    THERMAL_TRIP_HOT, THERMAL_TRIP_CRITICAL };
struct thermal_trip { int temperature, hysteresis; enum thermal_trip_type type; };
struct __thermal_bind_params { unsigned int trip_id; unsigned long value; };
struct __thermal_zone { int ntrips, num_tbps; struct thermal_trip *trips;
    struct __thermal_bind_params *tbps; };
struct thermal_zone_device { const char *type; void *devdata; };
typedef struct { unsigned int bits; } cpumask_t;
static cpumask_t online, cluster = {15};
static cpumask_t *cpu_online_mask = &online;
static unsigned int idle_bits;
static int panic_cpu = -1;
#define PANIC_CPU_INVALID (-1)
#define atomic_read(x) (*(x))
#define unlikely(x) (x)
#define cpumask_clear(x) ((x)->bits = 0)
#define cpumask_and(x,a,b) ((x)->bits = (a)->bits & (b)->bits)
#define cpu_coregroup_mask(cpu) (&cluster)
#define for_each_cpu(cpu,mask) for ((cpu) = 0; (cpu) < 8; (cpu)++) if ((mask)->bits & (1U << (cpu)))
#define idle_cpu(cpu) (idle_bits & (1U << (cpu)))
#define cpumask_weight(mask) __builtin_popcount((mask)->bits)
#define cpumask_empty(mask) (!(mask)->bits)
#define cpumask_first(mask) __builtin_ctz((mask)->bits)
typedef uint64_t u64;
typedef int64_t s64;
struct sugov_policy { u64 last_freq_update_time; s64 up_rate_delay_ns,
    down_rate_delay_ns; unsigned int next_freq; };
#define THERMAL_CSTATE_INVALID (~0UL)
struct cpufreq_cooling_device { unsigned int *freq_table; unsigned int max_level; };
struct thermal_cooling_device { void *devdata; };
'''
source += function('drivers/thermal/samsung/exynos_tmu.c', 'static int exynos9810_apply_cpu_profile(')
source += function('kernel/sched/cpufreq_schedutil.c', 'static int sugov_select_scaling_cpu(')
source += function('kernel/sched/cpufreq_schedutil.c', 'static bool sugov_up_down_rate_limit(')
source += function('drivers/thermal/cpu_cooling.c', 'static unsigned long get_level(')
source += function('drivers/thermal/cpu_cooling.c', 'static int exynos_cpufreq_cooling_get_level(')
source += r'''
static void check_rejected(struct thermal_zone_device *tz)
{
    struct __thermal_zone *z = tz->devdata;
    struct thermal_trip before[8];
    struct __thermal_bind_params maps[8];
    memcpy(before, z->trips, sizeof(before));
    memcpy(maps, z->tbps, sizeof(maps));
    assert(exynos9810_apply_cpu_profile(tz) == -EINVAL);
    assert(!memcmp(before, z->trips, sizeof(before)));
    assert(!memcmp(maps, z->tbps, sizeof(maps)));
}
int main(void)
{
    struct thermal_trip big[8] = {
        {20000,5000,THERMAL_TRIP_ACTIVE}, {55000,2000,THERMAL_TRIP_ACTIVE},
        {83000,5000,THERMAL_TRIP_PASSIVE}, {95000,5000,THERMAL_TRIP_ACTIVE},
        {100000,5000,THERMAL_TRIP_ACTIVE}, {105000,5000,THERMAL_TRIP_ACTIVE},
        {110000,5000,THERMAL_TRIP_ACTIVE}, {115000,5000,THERMAL_TRIP_HOT}};
    struct thermal_trip little[8] = {
        {20000,5000,THERMAL_TRIP_ACTIVE}, {76000,5000,THERMAL_TRIP_ACTIVE},
        {81000,5000,THERMAL_TRIP_ACTIVE}, {86000,5000,THERMAL_TRIP_ACTIVE},
        {91000,5000,THERMAL_TRIP_ACTIVE}, {96000,5000,THERMAL_TRIP_ACTIVE},
        {101000,5000,THERMAL_TRIP_ACTIVE}, {115000,5000,THERMAL_TRIP_HOT}};
    struct __thermal_bind_params maps[8] = {
        {0,1794000}, {1,1690000}, {2,1456000}, {3,1248000},
        {4,1053000}, {5,832000}, {6,598000}, {7,455000}};
    struct __thermal_bind_params original_maps[8];
    struct thermal_trip original_big[8], original_little[8];
    struct __thermal_zone z = {8,8,big,maps};
    struct thermal_zone_device tz = {"BIG",&z};
    memcpy(original_big, big, sizeof(big));
    memcpy(original_little, little, sizeof(little));
    memcpy(original_maps, maps, sizeof(maps));
    assert(exynos9810_apply_cpu_profile(NULL) == 0);
    assert(exynos9810_apply_cpu_profile(&tz) == 1);
    assert(big[1].temperature == 65000 && big[1].hysteresis == 2000);
    for (int i = 0; i < 8; i++)
        if (i != 1) assert(!memcmp(&big[i], &original_big[i], sizeof(big[i])));
    assert(!memcmp(maps, original_maps, sizeof(maps)));
    assert(exynos9810_apply_cpu_profile(&tz) == 1); /* idempotent */
    big[2].temperature = 64000;
    check_rejected(&tz);
    big[2] = original_big[2];
    tz.type = "LITTLE"; z.trips = little;
    assert(exynos9810_apply_cpu_profile(&tz) == 1);
    assert(little[1].temperature == 65000 && little[1].hysteresis == 2000);
    assert(maps[0].value == UINT_MAX);
    for (int i = 0; i < 8; i++) {
        if (i != 1) assert(!memcmp(&little[i], &original_little[i], sizeof(little[i])));
        if (i != 0) assert(!memcmp(&maps[i], &original_maps[i], sizeof(maps[i])));
    }
    /* Firmware with early ECT steps: keep ordering and the emergency trip. */
    for (int i = 1; i < 7; i++) little[i].temperature = 40000 + 3000 * i;
    assert(exynos9810_apply_cpu_profile(&tz) == 1);
    for (int i = 1; i < 7; i++) assert(little[i].temperature == 64000 + 1000 * i);
    assert(little[7].temperature == 115000);
    little[7].temperature = 67000;
    check_rejected(&tz); /* never move emergency protection */
    little[7].temperature = 115000;
    little[4].type = THERMAL_TRIP_PASSIVE;
    check_rejected(&tz);
    little[4].type = THERMAL_TRIP_ACTIVE;
    z.ntrips = 2; check_rejected(&tz);
    z.ntrips = 9; check_rejected(&tz);
    z.ntrips = 7; check_rejected(&tz); /* no emergency entry */
    z.ntrips = 8; maps[0].trip_id = 1; check_rejected(&tz);
    maps[0].trip_id = 0;
    struct thermal_trip untouched[8];
    memcpy(untouched, little, sizeof(little));
    tz.type = "G3D"; assert(exynos9810_apply_cpu_profile(&tz) == 0);
    tz.type = "ISP"; assert(exynos9810_apply_cpu_profile(&tz) == 0);
    assert(!memcmp(untouched, little, sizeof(little)));
    /* UINT_MAX means real table state 0 on both stock and 2 GHz A55 tables. */
    unsigned int frequencies[] = {1794000,1690000,1456000,455000};
    struct cpufreq_cooling_device cd = {frequencies,3};
    struct thermal_cooling_device cdev = {&cd};
    assert(exynos_cpufreq_cooling_get_level(&cdev, UINT_MAX) == 0);
    assert(exynos_cpufreq_cooling_get_level(&cdev, 1456000) == 2);
    frequencies[0] = 2002000;
    assert(exynos_cpufreq_cooling_get_level(&cdev, UINT_MAX) == 0);
    /* Exhaust all 256 online masks and 16 possible LITTLE idle masks. */
    for (online.bits = 0; online.bits < 256; online.bits++) {
        for (idle_bits = 0; idle_bits < 16; idle_bits++) {
            int selected = sugov_select_scaling_cpu();
            unsigned int available = online.bits & 15;
            if (!available) assert(selected == -1);
            else {
                assert(selected >= 0 && selected < 4);
                assert(available & (1U << selected));
                if (available & idle_bits) assert(idle_bits & (1U << selected));
            }
        }
    }
    online.bits = 0; panic_cpu = 4;
    assert(sugov_select_scaling_cpu() == 4); /* retain panic fallback */
    struct sugov_policy policy = {0,1000000,20000000,1000000};
    assert(sugov_up_down_rate_limit(&policy, 999999, 1500000));
    assert(!sugov_up_down_rate_limit(&policy, 1000000, 1500000));
    assert(sugov_up_down_rate_limit(&policy, 19999999, 600000));
    assert(!sugov_up_down_rate_limit(&policy, 20000000, 600000));
    puts("PASS: CPU thermal boundaries/fallback, emergency preservation, cold-band cooling, 4096 CPU masks, rate-limit boundaries");
}
'''
with tempfile.TemporaryDirectory(prefix='g965n-smooth65-') as tmp:
    binary = str(Path(tmp) / 'test')
    subprocess.run(['cc', '-std=gnu11', '-Wall', '-Werror', '-fsanitize=address,undefined',
                    '-g', '-x', 'c', '-', '-o', binary], input=source, text=True, check=True)
    # These fixtures allocate no heap memory; LSan cannot inspect tasks in this sandbox.
    env = dict(os.environ, ASAN_OPTIONS=os.environ.get('ASAN_OPTIONS', '') + ':detect_leaks=0')
    subprocess.run([binary], check=True, env=env)
