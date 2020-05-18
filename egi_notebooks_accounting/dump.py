from datetime import datetime
import logging
import os
import time

import attr
from dirq import QueueSimple
import requests

from .model import db, init_db, Notebook
from .utils import get_k8s_namespace


DEFAULT_PROMETHEUS_URL = 'http://localhost:9000'


@attr.s
class VMRecord:
    local_id = attr.ib(default='')
    site = attr.ib(default=None)
    machine = attr.ib(default=None)
    local_user_id = attr.ib(default=None)
    local_group_id = attr.ib(default=None)
    global_user_name = attr.ib(default=None)
    fqan = attr.ib(default=None)
    status = attr.ib(default=None)
    start_time = attr.ib(default=None)
    end_time = attr.ib(default=None)
    suspend_duration = attr.ib(default=0)
    wall = attr.ib(default=0)
    cpu = attr.ib(default=0)
    cpu_count = attr.ib(default=1)
    network_type = attr.ib(default=None)
    network_inbound = attr.ib(default=0)
    network_outbound = attr.ib(default=0)
    memory = attr.ib(default=0)
    disk = attr.ib(default=0)
    storage_record = attr.ib(default=None)
    image_id = attr.ib(default=None)
    cloud_type = attr.ib(default=None)
    cloud_compute_service = attr.ib(default=None)
    benchmark_type = attr.ib(default=None)
    benchmark = attr.ib(default=None)
    public_ip_count = attr.ib(default=0)

    def as_dict(self):
        r = {
            'VMUUID': self.local_id,
            'SiteName': self.site,
            'MachineName': self.machine,
            'LocalUserId': self.local_user_id,
            'LocalGroupId': self.local_group_id,
            'GlobalUserName': self.global_user_name,
            'FQAN': self.fqan,
            'Status': self.status,
            'StartTime': int(self.start_time),
            'EndTime': None,
            'SuspendDuration': int(self.suspend_duration),
            'WallDuration': int(self.wall),
            'CpuDuration': int(self.cpu),
            'CpuCount': int(self.cpu_count),
            'NetworkType': self.network_type,
            'NetworkInbound': int(self.network_inbound),
            'NetworkOutbound': int(self.network_outbound),
            'Memory': int(self.memory),
            'Disk': int(self.disk),
            'StorageRecordId': self.storage_record,
            'ImageId': self.image_id,
            'CloudType': self.cloud_type,
            'CloudComputeService': self.cloud_compute_service,
            'BenchmarkType': self.benchmark_type,
            'Benchmark': self.benchmark,
            'PublicIPCount': int(self.public_ip_count)
        }
        if self.end_time:
            r['EndTime'] = int(self.end_time)
        return r

    def dump(self):
        record = []
        for k, v in self.as_dict().items():
            if v is not None:
                record.append('{0}: {1}'.format(k, v))
        return '\n'.join(record)

    @classmethod
    def from_notebook(cls, notebook, **defaults):
        record = cls(global_user_name=notebook.username,
                     local_id=notebook.uid,
                     start_time=notebook.start,
                     end_time=notebook.end,
                     machine='{0}-notebook'.format(notebook.username),
                     **defaults)
        if notebook.start:
            if notebook.end:
                record.wall = notebook.end - notebook.start
            else:
                now = datetime.now().timestamp()
                record.wall = now - notebook.start
        return record


def get_usage_stats(prometheus_url, namespace):
    logging.debug("Getting usage information from prometheus")
    end = int(time.time())
    # Go back 6 hours
    # TODO(enolfc): what's the right interval to use?
    start = end - 6 * 3600
    metrics = [
        ('network_outbound',
         'container_network_transmit_bytes_total'),
        ('network_inbound',
         'container_network_receive_bytes_total'),
        ('cpu',
         'container_cpu_usage_seconds_total'),
        ('memory',
         'container_memory_max_usage_bytes'),
    ]
    pods = {}
    for m, q in metrics:
        query_str = ("{0}{{namespace='{1}',"
                     "pod_name=~'^jupyter-.*',container_name='notebook'}}")
        # TODO(enolfc): set the step to the right value according to interval
        # above
        params = {'query': query_str.format(q, namespace),
                  'start': start, 'end': end, 'step': '4h'}
        r = requests.get('{0}/api/v1/query_range'.format(prometheus_url),
                         params=params)
        for result in r.json()['data']['result']:
            # assuming this will be always in the same format
            # not very reliable if you ask me ;)
            name = result['metric']['name'].split('_')[-2]
            # last known value
            pod_metrics = pods.get(name, {})
            pod_metrics[m] = result['values'][-1][1]
            pods[name] = pod_metrics
    return pods


def dump(prometheus_url, namespace, spool_dir, site_config={}):
    db.connect()
    pod_usage = get_usage_stats(prometheus_url, namespace)
    records = []
    processed_notebooks = []
    for notebook in Notebook.select().where(Notebook.processed == False):
        notebook_extra = pod_usage.get(notebook.uid, {})
        notebook_extra.update(site_config)
        r = VMRecord.from_notebook(notebook, **notebook_extra).dump()
        records.append(r)
        notebook.record = r
        if notebook.end:
            processed_notebooks.append(notebook)
    if records:
        message = '\n'.join(['APEL-cloud-message: v0.4',
                             '\n%%\n'.join(records)])
        queue = QueueSimple.QueueSimple(spool_dir)
        queue.add(message)
        logging.debug("Dumped %d records to spool dir", len(records))
    # once dumped, set the notebooks as processed if finished
    for notebook in processed_notebooks:
        notebook.processed = True
        notebook.save()
    db.close()


def main():
    logging.basicConfig(level=logging.DEBUG)
    init_db()

    namespace = get_k8s_namespace()
    logging.debug('namespace: %s', namespace)
    prometheus_url = os.environ.get('PROMETHEUS_URL', DEFAULT_PROMETHEUS_URL)
    logging.debug('Prometheus server at %s', prometheus_url)
    site_config = dict(site=os.environ.get('SITENAME', ''),
                       fqan=os.environ.get('VO', ''),
                       cloud_type=os.environ.get('CLOUD_TYPE', ''),
                       cloud_compute_service=os.environ.get('SERVICE', ''))
    logging.debug('Site configuration: %s', site_config)
    apel_dir = os.environ.get('APEL_SPOOL', '/tmp')
    dump(prometheus_url, namespace, apel_dir, site_config)


if __name__ == '__main__':
    main()
