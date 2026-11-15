"""Record local CPU inference and process memory; this does not establish VPS performance."""
import argparse
import json
import time
from pathlib import Path

import numpy as np
import psutil

from backend.retrieval import Encoder,fmt_query
from scripts.common import ROOT,json_write


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument("--model",type=Path,default=ROOT/"build/model-text")
    parser.add_argument("--out",type=Path,default=ROOT/"artifacts/encoder-benchmark.json")
    args=parser.parse_args();process=psutil.Process();before=process.memory_info().rss
    started=time.perf_counter();encoder=Encoder(args.model);load=time.perf_counter()-started
    queries=["Saffire oxygen pressure flame spread", "Lunar centrifugal gravity simulation and normal pressure",
             "Smoke detector response Kapton Teflon aerosol", "FLEX visible flame extinction diameter methanol heptane",
             "PMMA opposed flow oxygen calibrated concentration BASS-II", "Microgravity solid fuel combustion sample geometry"]
    times=[]
    for query in queries:
        start=time.perf_counter();encoder.encode([fmt_query(query)]);times.append(time.perf_counter()-start)
    memory=process.memory_info()
    report={"model":str(args.model),"load_seconds":load,"query_seconds":times,"warm_p95_seconds":float(np.percentile(times[1:],95)),
            "rss_before_bytes":before,"rss_after_encode_bytes":memory.rss,"peak_working_set_bytes":getattr(memory,"peak_wset",None),
            "host_available_bytes":psutil.virtual_memory().available,"platform":__import__('platform').platform(),
            "threads":2,"query_count":len(queries),"note":"Windows local builder measurements; RSS/working set are not Linux cgroup memory or host-headroom validation."}
    json_write(args.out,report);print(json.dumps(report,indent=2))


if __name__ == "__main__":main()
