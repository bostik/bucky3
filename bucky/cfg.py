
sysstats = {
    # "type": "system_stats",
    "log_level": "INFO",
    "interval": 10
}

dockers = {
    # "type": "docker_stats",
    "log_level": "INFO",
    "interval": 10
}

statsd = {
    "type": "statsd_server",
    "log_level": "INFO",
    "interval": 10,
    "local_port": 8125,
    "timers_name": "stats_timers",
    "sets_name": "stats_sets",
    "gauges_name": "stats_gauges",
    "counters_name": "stats_counters",
    "timers_timeout": 60,
    "sets_timeout": 60,
    "gauges_timeout": 60,
    "counters_timeout": 60
}

carbon = {
    # "type": "carbon_client",
    "log_level": "INFO",
    "interval": 1,
    "remote_hosts": [
        "127.0.0.1:2003"
    ]
}

influxdb = {
    "type": "influxdb_client",
    "log_level": "INFO",
    "interval": 1,
    "remote_hosts": [
        "127.0.0.1:8086"
    ]
}

prometheus = {
    # "type": "prometheus_exporter",
    "log_level": "INFO",
    "interval": 60,
    "local_port": 9090,
    "local_host": "0.0.0.0",
    "http_path": "metrics",
    "values_timeout": 60
}
