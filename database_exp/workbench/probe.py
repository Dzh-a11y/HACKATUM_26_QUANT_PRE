"""macOS process-wide resource counters; never synthesize unavailable PMU values."""
import ctypes
import os
import platform
import resource
import time

FIELDS = '''user system idle interrupt pageins wired resident footprint start exit
child_user child_system child_idle child_interrupt child_pageins child_elapsed
diskread diskwrite qos_default qos_maintenance qos_background qos_utility qos_legacy
qos_initiated qos_interactive billed_system serviced_system logical_writes
max_footprint instructions cycles billed_energy serviced_energy interval_footprint runnable'''.split()

class Usage(ctypes.Structure):
    _fields_ = [('uuid', ctypes.c_ubyte * 16)] + [(name, ctypes.c_uint64) for name in FIELDS]

LIB = ctypes.CDLL('/usr/lib/libproc.dylib', use_errno=True) if platform.system() == 'Darwin' else None
if LIB:
    LIB.proc_pid_rusage.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.c_void_p]
    LIB.proc_pid_rusage.restype = ctypes.c_int

def snapshot():
    info = Usage()
    valid = bool(LIB) and LIB.proc_pid_rusage(os.getpid(), 4, ctypes.byref(info)) == 0
    return dict(wall=time.perf_counter(), usage=resource.getrusage(resource.RUSAGE_SELF), info=info, valid=valid)

def difference(a, b):
    x, y = a['usage'], b['usage']
    valid = a['valid'] and b['valid'] and b['info'].cycles > 0 and b['info'].instructions > 0
    cycles = b['info'].cycles - a['info'].cycles if valid else None
    instructions = b['info'].instructions - a['info'].instructions if valid else None
    if valid and (cycles < 0 or instructions < 0):
        cycles = instructions = None
    return dict(wall_ms=(b['wall']-a['wall'])*1000,
                user_ms=(y.ru_utime-x.ru_utime)*1000, system_ms=(y.ru_stime-x.ru_stime)*1000,
                minor_faults=y.ru_minflt-x.ru_minflt, major_faults=y.ru_majflt-x.ru_majflt,
                voluntary_switches=y.ru_nvcsw-x.ru_nvcsw, involuntary_switches=y.ru_nivcsw-x.ru_nivcsw,
                cycles=cycles, instructions=instructions, ipc=instructions/cycles if cycles else None,
                rss_bytes=b['info'].resident if b['valid'] else None,
                threads=None, cache_misses=None, branch_misses=None)

