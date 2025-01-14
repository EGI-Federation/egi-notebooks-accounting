import peewee
from peewee import CharField, DateTimeField, FloatField, IntegerField, UUIDField

db = peewee.SqliteDatabase(None)


class BaseModel(peewee.Model):
    class Meta:
        database = db


class VM(BaseModel):
    site = "EGI-NOTEBOOKS"
    cloud_type = "EGI Notebooks"
    cloud_compute_service = None

    namespace = CharField()
    primary_group = None

    local_id = UUIDField(primary_key=True)
    machine = CharField()
    local_user_id = CharField(null=True)
    local_group_id = CharField(null=True)
    global_user_name = CharField(null=True)
    fqan = CharField(null=True)
    status = CharField(null=True)
    start_time = DateTimeField(null=True)
    end_time = DateTimeField(null=True)
    suspend_duration = FloatField(default=0, null=True)
    wall = FloatField(default=0, null=True)
    cpu_duration = FloatField(default=0, null=True)
    cpu_count = FloatField(default=0, null=True)
    network_type = CharField(null=True)
    network_inbound = FloatField(default=0, null=True)
    network_outbound = FloatField(default=0, null=True)
    memory = FloatField(default=0, null=True)
    disk = FloatField(default=0, null=True)
    storage_record = CharField(null=True)
    image_id = CharField(null=True)
    benchmark_type = CharField(null=True)
    benchmark = CharField(null=True)
    public_ip_count = IntegerField(default=0, null=True)
    flavor = CharField(null=True)

    def as_dict(self):
        r = {
            "VMUUID": self.local_id,
            "SiteName": self.site,
            "MachineName": self.machine,
            "LocalUserId": self.local_user_id,
            "LocalGroupId": self.local_group_id,
            "GlobalUserName": self.global_user_name,
            "FQAN": self.fqan,
            "Status": self.status,
            "StartTime": None,
            "EndTime": None,
            "SuspendDuration": int(self.suspend_duration),
            "WallDuration": int(self.wall),
            "CpuDuration": round(float(self.cpu_duration)),
            "CpuCount": round(float(self.cpu_count), 3),
            "NetworkType": self.network_type,
            "NetworkInbound": int(self.network_inbound),
            "NetworkOutbound": int(self.network_outbound),
            "Memory": int(self.memory),
            "Disk": int(self.disk),
            "StorageRecordId": self.storage_record,
            "ImageId": self.image_id,
            "CloudType": self.cloud_type,
            "CloudComputeService": self.cloud_compute_service,
            "BenchmarkType": self.benchmark_type,
            "Benchmark": self.benchmark,
            "PublicIPCount": int(self.public_ip_count),
        }
        if self.start_time:
            r["StartTime"] = int(self.start_time.timestamp())
        if self.end_time:
            r["EndTime"] = int(self.end_time.timestamp())
        return r

    def dump(self):
        record = []
        for k, v in self.as_dict().items():
            if v is not None:
                record.append("{0}: {1}".format(k, v))
        return "\n".join(record)


def db_init(db_file):
    db.init(db_file)
    db.connect()
    db.create_tables([VM])
    db.close()
    return db
