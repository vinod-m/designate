# Copyright (C) 2013 eNovance SAS <licensing@enovance.com>
#
# Author: Artom Lifshitz <artom.lifshitz@enovance.com>
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.

import eventlet
import os
import socket
import ssl
from designate import exceptions
from designate.tests.test_backend import BackendTestCase
from mock import MagicMock
# impl_nsd4slave needs to register its options before being instanciated.
# Import it and pretend to use it to avoid flake8 unused import errors.
from designate.backend import impl_nsd4slave
impl_nsd4slave


class NSD4ServerStub:
    recved_command = None
    response = 'ok'
    keyfile = os.path.join(os.path.dirname(__file__), 'nsd_server.key')
    certfile = os.path.join(os.path.dirname(__file__), 'nsd_server.pem')

    def handle(self, client_sock, client_addr):
        stream = client_sock.makefile()
        self.recved_command = stream.readline()
        stream.write(self.response)
        stream.flush()

    def start(self):
        self.port = 1025
        while True:
            try:
                eventlet.spawn_n(eventlet.serve,
                                 eventlet.wrap_ssl(
                                     eventlet.listen(('127.0.0.1', self.port)),
                                     keyfile=self.keyfile,
                                     certfile=self.certfile,
                                     server_side=True),
                                 self.handle)
                break
            except socket.error:
                self.port = self.port + 1

    def stop(self):
        eventlet.StopServe()


class NSD4SlaveBackendTestCase(BackendTestCase):
    __test__ = True

    def setUp(self):
        super(NSD4SlaveBackendTestCase, self).setUp()
        self.servers = [NSD4ServerStub(), NSD4ServerStub()]
        [server.start() for server in self.servers]
        impl_nsd4slave.DEFAULT_PORT = self.servers[0].port
        self.config(backend_driver='nsd4slave', group='service:agent')
        self.config(
            servers=['127.0.0.1', '127.0.0.1:%d' % self.servers[1].port],
            group='backend:nsd4slave')
        keyfile = os.path.join(os.path.dirname(__file__), 'nsd_control.key')
        certfile = os.path.join(os.path.dirname(__file__), 'nsd_control.pem')
        self.config(keyfile=keyfile, group='backend:nsd4slave')
        self.config(certfile=certfile, group='backend:nsd4slave')
        self.config(pattern='test-pattern', group='backend:nsd4slave')
        self.nsd4 = self.get_backend_driver()

    def tearDown(self):
        super(NSD4SlaveBackendTestCase, self).tearDown()
        [server.stop() for server in self.servers]

    def test_create_domain(self):
        context = self.get_context()
        domain = self.get_domain_fixture()
        self.nsd4.create_domain(context, domain)
        command = 'NSDCT1 addzone %s test-pattern\n' % domain['name']
        [self.assertEqual(server.recved_command, command)
         for server in self.servers]

    def test_delete_domain(self):
        context = self.get_context()
        domain = self.get_domain_fixture()
        self.nsd4.delete_domain(context, domain)
        command = 'NSDCT1 delzone %s\n' % domain['name']
        [self.assertEqual(server.recved_command, command)
         for server in self.servers]

    def test_server_not_ok(self):
        self.servers[0].response = 'goat'
        context = self.get_context()
        domain = self.get_domain_fixture()
        self.assertRaises(exceptions.NSD4SlaveBackendError,
                          self.nsd4.create_domain,
                          context, domain)

    def test_ssl_error(self):
        self.nsd4._command = MagicMock(side_effet=ssl.SSLError)
        context = self.get_context()
        domain = self.get_domain_fixture()
        self.assertRaises(exceptions.NSD4SlaveBackendError,
                          self.nsd4.create_domain,
                          context, domain)

    def test_socket_error(self):
        self.nsd4._command = MagicMock(side_effet=socket.error)
        context = self.get_context()
        domain = self.get_domain_fixture()
        self.assertRaises(exceptions.NSD4SlaveBackendError,
                          self.nsd4.create_domain,
                          context, domain)
