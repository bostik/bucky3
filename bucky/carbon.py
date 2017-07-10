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


import bucky.module as module


class CarbonClient(module.MetricsPushProcess, module.TCPConnector):
    def __init__(self, *args):
        super().__init__(*args, default_port=2003)

    def push_buffer(self):
        # For TCP we probably can just pump all buffer into the wire.
        self.socket = self.socket or self.get_tcp_socket(connect=True)
        payload = ''.join(self.buffer).encode()
        self.socket.sendall(payload)

    def build_name(self, metadata):
        found_mappings = tuple(k for k in self.cfg['name_mapping'] if k in metadata)
        buf = [metadata.pop(k) for k in found_mappings]
        buf.extend(metadata[k] for k in sorted(metadata.keys()))
        return '.'.join(buf)

    def process_values(self, bucket, values, timestamp, metadata=None):
        metadata = metadata or {}
        for k, v in values.items():
            value_metadata = metadata.copy()
            value_metadata.update(bucket=bucket, value=k)
            name = self.build_name(value_metadata)
            self.buffer.append("%s %s %s\n" % (name, v, int(timestamp)))
