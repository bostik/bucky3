# -*- coding: utf-8 -
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may not
# use this file except in compliance with the License. You may obtain a copy of
# the License at
#
#   http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations under
# the License.
#
# Copyright 2011 Cloudant, Inc.


import os
import sys
import signal
import logging
import optparse as op
import multiprocessing
import queue
import bucky
import bucky.cfg as cfg
import bucky.carbon as carbon
import bucky.statsd as statsd
import bucky.systemstats as systemstats
import bucky.dockerstats as dockerstats
import bucky.influxdb as influxdb
import bucky.prometheus as prometheus


log = logging.getLogger(__name__)
levels = {
    'CRITICAL': logging.CRITICAL,
    'ERROR': logging.ERROR,
    'WARNING': logging.WARNING,
    'INFO': logging.INFO,
    'DEBUG': logging.DEBUG,
}

__usage__ = "%prog [OPTIONS] [CONFIG_FILE]"
__version__ = "bucky %s" % bucky.__version__


def options():
    return [
        op.make_option(
            "--debug", dest="debug", default=False,
            action="store_true",
            help="Put server into dry-run debug mode where output"
                 "goes to stdout instead of carbon. [False]. [%default]"
        ),
        op.make_option(
            "--statsd-ip", dest="statsd_ip", metavar="IP",
            default=cfg.statsd_ip,
            help="IP address to bind for the StatsD UDP socket [%default]"
        ),
        op.make_option(
            "--statsd-port", dest="statsd_port", metavar="INT",
            type="int", default=cfg.statsd_port,
            help="Port to bind for the StatsD UDP socket [%default]"
        ),
        op.make_option(
            "--disable-statsd", dest="statsd_enabled",
            default=cfg.statsd_enabled, action="store_false",
            help="Disable the StatsD server"
        ),
        op.make_option(
            "--graphite-ip", dest="graphite_ip", metavar="IP",
            default=cfg.graphite_ip,
            help="IP address of the Graphite/Carbon server [%default]"
        ),
        op.make_option(
            "--graphite-port", dest="graphite_port", metavar="INT",
            type="int", default=cfg.graphite_port,
            help="Port of the Graphite/Carbon server [%default]"
        ),
        op.make_option(
            "--disable-graphite", dest="graphite_enabled",
            default=cfg.graphite_enabled, action="store_false",
            help="Disable the Graphite/Carbon client"
        ),
        op.make_option(
            "--enable-influxdb", dest="influxdb_enabled",
            default=cfg.influxdb_enabled, action="store_true",
            help="Enable the InfluxDB line protocol client"
        ),
        op.make_option(
            "--enable-prometheus", dest="prometheus_enabled",
            default=cfg.prometheus_enabled, action="store_true",
            help="Enable the Prometheus exposition via HTTP"
        ),
        op.make_option(
            "--enable-system-stats", dest="system_stats_enabled",
            default=cfg.system_stats_enabled, action="store_true",
            help="Enable collection of local system stats"
        ),
        op.make_option(
            "--enable-docker-stats", dest="docker_stats_enabled",
            default=cfg.docker_stats_enabled, action="store_true",
            help="Enable collection of docker containers stats"
        ),
        op.make_option(
            "--log-level", dest="log_level",
            metavar="NAME", default="INFO",
            help="Logging output verbosity [%default]"
        ),
        op.make_option("--metadata", action="append", dest="metadata")
    ]


def main():
    parser = op.OptionParser(
        usage=__usage__,
        version=__version__,
        option_list=options()
    )
    opts, args = parser.parse_args()

    # Logging have to be configured before load_config,
    # where it can (and should) be already used
    logfmt = "[%(asctime)-15s][%(levelname)s] %(module)s - %(message)s"
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter(logfmt))
    handler.setLevel(logging.ERROR)  # Overridden by configuration
    logging.root.addHandler(handler)
    logging.root.setLevel(logging.DEBUG)

    if args:
        try:
            cfgfile, = args
        except ValueError:
            parser.error("Too many arguments.")
    else:
        cfgfile = None
    load_config(cfgfile)

    if cfg.debug:
        cfg.log_level = logging.DEBUG

    # Mandatory second commandline
    # processing pass to override values in cfg
    parser.parse_args(values=cfg)

    lvl = levels.get(cfg.log_level, cfg.log_level)
    handler.setLevel(lvl)

    if cfg.directory and not os.path.isdir(cfg.directory):
        try:
            os.makedirs(cfg.directory)
        except:
            log.exception("Could not create directory: %s" % cfg.directory)

    # This in place swap from list to dict is hideous :-|
    metadata = {}
    if cfg.metadata:
        for i in cfg.metadata:
            kv = i.split("=")
            if len(kv) > 1:
                metadata[kv[0]] = kv[1]
            else:
                kv = i.split(":")
                if len(kv) > 1:
                    metadata[kv[0]] = kv[1]
                else:
                    metadata[kv[0]] = None
    cfg.metadata = metadata

    bucky = Bucky(cfg)
    bucky.run()


class BuckyError(Exception):
    pass


class Bucky(object):
    def __init__(self, cfg):
        self.sampleq = multiprocessing.Queue()

        stypes = []
        if cfg.statsd_enabled:
            stypes.append(statsd.StatsDServer)
        if cfg.system_stats_enabled:
            stypes.append(systemstats.SystemStatsCollector)
        if cfg.docker_stats_enabled:
            stypes.append(dockerstats.DockerStatsCollector)

        self.servers = []
        for stype in stypes:
            self.servers.append(stype(self.sampleq, cfg))

        requested_clients = []
        if cfg.graphite_enabled:
            if cfg.graphite_pickle_enabled:
                carbon_client = carbon.PickleClient
            else:
                carbon_client = carbon.PlaintextClient
            requested_clients.append(carbon_client)
        if cfg.influxdb_enabled:
            requested_clients.append(influxdb.InfluxDBClient)
        if cfg.prometheus_enabled:
            requested_clients.append(prometheus.PrometheusClient)

        self.clients = []
        for client in requested_clients:
            send, recv = multiprocessing.Pipe()
            instance = client(cfg, recv)
            self.clients.append((instance, send))

    def run(self):
        def sigterm_handler(signum, frame):
            log.info("Received SIGTERM")
            self.sampleq.put(None)

        for server in self.servers:
            server.start()
        for client, pipe in self.clients:
            client.start()

        signal.signal(signal.SIGTERM, sigterm_handler)

        while True:
            try:
                sample = self.sampleq.get(True, 1)
                if not sample:
                    break
                for instance, pipe in self.clients:
                    if not instance.is_alive():
                        self.shutdown("Client process died. Exiting.")
                    pipe.send(sample)
            except queue.Empty:
                pass
            except IOError as exc:
                # Probably due to interrupted system call by SIGTERM
                log.debug("Bucky IOError: %s", exc)
                continue
            except KeyboardInterrupt:
                break
            for srv in self.servers:
                if not srv.is_alive():
                    self.shutdown("Server thread died. Exiting.")
        self.shutdown()

    def shutdown(self, err=''):
        log.info("Shutting down")
        for server in self.servers:
            log.info("Stopping server %s", server)
            server.close()
            server.join(cfg.process_join_timeout)
        for client, pipe in self.clients:
            log.info("Stopping client %s", client)
            pipe.send(None)
            client.join(cfg.process_join_timeout)
        children = [child for child in multiprocessing.active_children() if not child.name.startswith("SyncManager")]
        for child in children:
            log.error("Child %s didn't die gracefully, terminating", child)
            child.terminate()
            child.join(1)
        if children and not err:
            err = "Not all children died gracefully: %s" % children
        if err:
            raise BuckyError(err)


def load_config(cfgfile):
    cfg_mapping = vars(cfg)
    try:
        if cfgfile is not None:
            with open(cfgfile, 'rb') as file:
                exec(compile(file.read(), cfgfile, 'exec'), cfg_mapping)
    except Exception as e:
        log.error("Failed to read config file: %s", cfgfile)
        log.exception("Reason: %s", e)
        sys.exit(1)
    for name in dir(cfg):
        if name.startswith("_"):
            continue
        if name in cfg_mapping:
            setattr(cfg, name, cfg_mapping[name])


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        pass
