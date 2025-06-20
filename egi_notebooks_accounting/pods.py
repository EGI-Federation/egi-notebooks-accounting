import argparse
import logging
import os
import time
from configparser import ConfigParser
from datetime import datetime
from typing import Dict, List

import peewee
from dirq import QueueSimple

from .model import VM, db_init
from .prometheus import Prometheus

CONFIG = "default"
PROM_CONFIG = "prometheus"
DEFAULT_CONFIG_FILE = "config.ini"
DEFAULT_FILTER = "pod=~'jupyter-.*'"
DEFAULT_FQANS: Dict[str, List[str]] = {}
DEFAULT_FQAN_KEY = "primary_group"
DEFAULT_RANGE = "24h"


def main():
    parser = argparse.ArgumentParser(
        description="Kubernetes Prometheus metrics harvester"
    )
    parser.add_argument(
        "-c", "--config", help="config file", default=DEFAULT_CONFIG_FILE
    )
    args = parser.parse_args()

    parser = ConfigParser()
    parser.read(args.config)
    config = parser[CONFIG] if CONFIG in parser else {}

    verbose = os.environ.get("VERBOSE", config.get("verbose", 0))
    verbose = logging.DEBUG if verbose == "1" else logging.INFO
    logging.basicConfig(level=verbose)
    fqan_key = os.environ.get("FQAN_KEY", config.get("fqan_key", DEFAULT_FQAN_KEY))
    spool_dir = os.environ.get("APEL_SPOOL", config.get("apel_spool"))

    prom_config = parser[PROM_CONFIG] if PROM_CONFIG in parser else {}
    flt = os.environ.get("FILTER", prom_config.get("filter", DEFAULT_FILTER))
    rng = os.environ.get("RANGE", prom_config.get("range", DEFAULT_RANGE))
    usage_queries = {
        "cpu_duration": "sum by (name) (max_over_time(container_cpu_usage_seconds_total{%s}[%s]))"
        % (flt, rng),
        "cpu_count": "sum by (uid) (max_over_time(kube_pod_container_resource_requests{%s,resource='cpu'}[%s]))"
        % (flt, rng),
        "memory": "sum by (name) (max_over_time(container_memory_max_usage_bytes{%s}[%s]))"
        % (flt, rng),
        "network_inbound": "sum by (name) (last_over_time(container_network_receive_bytes_total{%s}[%s]))"
        % (flt, rng),
        "network_outbound": "sum by (name) (last_over_time(container_network_transmit_bytes_total{%s}[%s]))"
        % (flt, rng),
    }

    VM.site = os.environ.get("SITENAME", config.get("site", VM.site))
    VM.cloud_type = os.environ.get(
        "CLOUD_TYPE", config.get("cloud_type", VM.cloud_type)
    )
    VM.cloud_compute_service = os.environ.get(
        "SERVICE", config.get("cloud_compute_service", VM.cloud_compute_service)
    )
    VM.default_cpu_count = os.environ.get(
        "DEFAULT_CPU_COUNT",
        config.get("default_cpu_count", VM.default_cpu_count),
    )
    db_file = os.environ.get("NOTEBOOKS_DB", config.get("notebooks_db", None))

    fqans = dict(DEFAULT_FQANS)
    if "VO" in parser:
        vo_config = parser["VO"]
        for vo, values in vo_config.items():
            for value in values.split(","):
                fqans[value] = vo
    logging.debug("FQAN: %s", fqans)

    db = None
    if db_file:
        db = db_init(db_file)
        db.connect()
    prom = Prometheus(parser)
    tnow = time.time()
    data = {
        "time": tnow,
    }

    # ==== START, MACHINE, VO ====
    data["query"] = "last_over_time(kube_pod_created{" + flt + "}[" + rng + "])"
    response = prom.query(data)
    for item in response["data"]["result"]:
        # print(item)
        pod = prom.get_pod(item, uid=None, default=VM())
        metric = item["metric"]
        pod.start_time = datetime.fromtimestamp(int(item["value"][1]))
        pod.machine = metric["pod"]
        pod.namespace = metric["namespace"]
    # ==== END, WALL ====
    data["query"] = "kube_pod_status_phase{" + flt + ",phase='Running'}[" + rng + "]"
    response = prom.query(data)
    for item in response["data"]["result"]:
        # print(item)
        pod = prom.get_pod(item)
        metric = item["metric"]
        if pod is None:
            logging.warning(
                "namespace %s, name %s, uid %s from kube_pod_status_phase metric not found",
                metric["namespace"],
                metric["pod"],
                metric["uid"],
            )
            continue
        running = [v[0] for v in item["values"] if v[1] == "1"]
        # last timestamp, status, and wall
        # (wall would be summary for value==1, but the initial metrics may be lost for long-term notebooks ==> better to use time from kube_pod_created here)
        if len(running) > 0:
            pod.end_time = datetime.fromtimestamp(int(running[-1]))
            # status (check the last running phase)
            if tnow - pod.end_time.timestamp() > 1.5 * 60:
                pod.status = "completed"
            else:
                pod.end_time = None
                pod.status = "started"
            pod.wall = int(running[-1]) - pod.start_time.timestamp()
        else:
            # no value==1 with phase="Running" has been scrubbed
            # => probably ended too fast or it"s recent launch
            pod.wall = 0
            if tnow - pod.start_time.timestamp() < 1.6 * 60:
                # consider it as recent launch
                pod.status = "started"
            else:
                pod.end_time = pod.start_time
                pod.status = "completed"
    # ==== USER ====
    data["query"] = "last_over_time(kube_pod_annotations{" + flt + "}[" + rng + "])"
    response = prom.query(data)
    for item in response["data"]["result"]:
        pod = prom.get_pod(item)
        metric = item["metric"]
        if pod is None:
            logging.warning(
                "namespace %s, name %s, uid %s from kube_pod_annotations metric not found",
                metric["namespace"],
                metric["pod"],
                metric["uid"],
            )
            continue
        pod.global_user_name = metric.get("annotation_hub_jupyter_org_username", None)
        pod.primary_group = metric.get("annotation_egi_eu_primary_group", None)
        pod.flavor = metric.get("annotation_egi_eu_flavor", None)
    # ==== IMAGE ====
    data["query"] = (
        "last_over_time(kube_pod_container_info{"
        + flt
        + ",container='notebook'}["
        + rng
        + "])"
    )
    response = prom.query(data)
    for item in response["data"]["result"]:
        pod = prom.get_pod(item)
        metric = item["metric"]
        if pod is None:
            logging.warning(
                "namespace %s, name %s, uid %s from kube_pod_container_info metric not found",
                metric["namespace"],
                metric["pod"],
                metric["uid"],
            )
            continue
        if "image" in metric:
            pod.image_id = metric["image"]
    # ==== resource usage queries ====
    for field, query in usage_queries.items():
        data["query"] = query
        response = prom.query(data)
        for item in response["data"]["result"]:
            # print(item)
            uid = None
            if field not in ["cpu_count"]:
                # dirty hack: parse POD uid from "name" label
                if "name" not in item["metric"]:
                    continue
                uid = item["metric"]["name"].split("_")[-2]
            pod = prom.get_pod(item, uid)
            metric = item["metric"]
            if pod is None:
                # missing is OK: it is better to query usage with bigger range,
                # also it could be too shortly running POD
                continue
            value = float(item["value"][1])
            item = getattr(pod, field)
            setattr(pod, field, item + value)
    # ==== FQANS postprocessing ====
    for pod in prom.pods.values():
        fqan_value = getattr(pod, fqan_key, None)
        logging.debug(
            "fqan evaluation: pod %s, fqan_value %s", pod.local_id, fqan_value
        )
        if fqan_value in fqans:
            pod.fqan = vo
        elif fqan_value:
            # just use the value that's in the pod
            pod.fqan = fqan_value

    if prom.pods:
        if spool_dir:
            queue = QueueSimple.QueueSimple(spool_dir)
            message = "APEL-cloud-message: v0.4\n" + "\n%%\n".join(
                (pod.dump() for (uid, pod) in prom.pods.items() if pod.valid_apel())
            )
            queue.add(message)
            logging.debug("Dumped %d records to spool dir", len(prom.pods))
        if db:
            for uid, pod in prom.pods.items():
                try:
                    pod.save(force_insert=True)
                except peewee.IntegrityError:
                    pod.save()
    if db:
        db.close()


if __name__ == "__main__":
    main()
