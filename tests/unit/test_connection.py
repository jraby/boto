# Copyright (c) 2013 Amazon.com, Inc. or its affiliates.  All Rights Reserved
#
# Permission is hereby granted, free of charge, to any person obtaining a
# copy of this software and associated documentation files (the
# "Software"), to deal in the Software without restriction, including
# without limitation the rights to use, copy, modify, merge, publish, dis-
# tribute, sublicense, and/or sell copies of the Software, and to permit
# persons to whom the Software is furnished to do so, subject to the fol-
# lowing conditions:
#
# The above copyright notice and this permission notice shall be included
# in all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS
# OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABIL-
# ITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT
# SHALL THE AUTHOR BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY,
# WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS
# IN THE SOFTWARE.
#
import os
import urlparse
from tests.unit import unittest
from httpretty import HTTPretty

from boto.connection import AWSQueryConnection, AWSAuthConnection
from boto.exception import BotoServerError
from boto.regioninfo import RegionInfo
from boto.compat import json
from boto.utils import ensure_bytes, ensure_string


class TestListParamsSerialization(unittest.TestCase):
    maxDiff = None

    def setUp(self):
        self.connection = AWSQueryConnection('access_key', 'secret_key')

    def test_complex_list_serialization(self):
        # This example is taken from the doc string of
        # build_complex_list_params.
        params = {}
        self.connection.build_complex_list_params(
            params, [('foo', 'bar', 'baz'), ('foo2', 'bar2', 'baz2')],
            'ParamName.member', ('One', 'Two', 'Three'))
        self.assertDictEqual({
            'ParamName.member.1.One': 'foo',
            'ParamName.member.1.Two': 'bar',
            'ParamName.member.1.Three': 'baz',
            'ParamName.member.2.One': 'foo2',
            'ParamName.member.2.Two': 'bar2',
            'ParamName.member.2.Three': 'baz2',
        }, params)

    def test_simple_list_serialization(self):
        params = {}
        self.connection.build_list_params(
            params, ['foo', 'bar', 'baz'], 'ParamName.member')
        self.assertDictEqual({
            'ParamName.member.1': 'foo',
            'ParamName.member.2': 'bar',
            'ParamName.member.3': 'baz',
        }, params)


class MockAWSService(AWSQueryConnection):
    """
    Fake AWS Service

    This is used to test the AWSQueryConnection object is behaving properly.
    """

    APIVersion = '2012-01-01'
    def _required_auth_capability(self):
        return ['sign-v2']

    def __init__(self, aws_access_key_id=None, aws_secret_access_key=None,
                 is_secure=True, host=None, port=None,
                 proxy=None, proxy_port=None,
                 proxy_user=None, proxy_pass=None, debug=0,
                 https_connection_factory=None, region=None, path='/',
                 api_version=None, security_token=None,
                 validate_certs=True):
        self.region = region
        AWSQueryConnection.__init__(self, aws_access_key_id,
                                    aws_secret_access_key,
                                    is_secure, port, proxy, proxy_port,
                                    proxy_user, proxy_pass,
                                    self.region.endpoint, debug,
                                    https_connection_factory, path,
                                    security_token,
                                    validate_certs=validate_certs)

class TestAWSAuthConnection(unittest.TestCase):
    def test_get_path(self):
        conn = AWSAuthConnection(
            'mockservice.cc-zone-1.amazonaws.com',
            aws_access_key_id='access_key',
            aws_secret_access_key='secret',
            suppress_consec_slashes=False
        )
        # Test some sample paths for mangling.
        self.assertEqual(conn.get_path('/'), '/')
        self.assertEqual(conn.get_path('image.jpg'), '/image.jpg')
        self.assertEqual(conn.get_path('folder/image.jpg'), '/folder/image.jpg')
        self.assertEqual(conn.get_path('folder//image.jpg'), '/folder//image.jpg')

        # Ensure leading slashes aren't removed.
        # See https://github.com/boto/boto/issues/1387
        self.assertEqual(conn.get_path('/folder//image.jpg'), '/folder//image.jpg')
        self.assertEqual(conn.get_path('/folder////image.jpg'), '/folder////image.jpg')
        self.assertEqual(conn.get_path('///folder////image.jpg'), '///folder////image.jpg')


class TestAWSQueryConnection(unittest.TestCase):
    def setUp(self):
        self.region = RegionInfo(name='cc-zone-1',
                            endpoint='mockservice.cc-zone-1.amazonaws.com',
                            connection_cls=MockAWSService)

        HTTPretty.enable()

    def tearDown(self):
        HTTPretty.disable()

class TestAWSQueryConnectionSimple(TestAWSQueryConnection):
    def test_query_connection_basis(self):
        HTTPretty.register_uri(HTTPretty.POST,
                               'https://%s/' % self.region.endpoint,
                               json.dumps({'test': 'secure'}),
                               content_type='application/json')

        conn = self.region.connect(aws_access_key_id='access_key',
                                   aws_secret_access_key='secret')

        self.assertEqual(conn.host, 'mockservice.cc-zone-1.amazonaws.com')

    def test_query_connection_noproxy(self):
        HTTPretty.register_uri(HTTPretty.POST,
                               'https://%s/' % self.region.endpoint,
                               json.dumps({'test': 'secure'}),
                               content_type='application/json')

        os.environ['no_proxy'] = self.region.endpoint

        conn = self.region.connect(aws_access_key_id='access_key',
                                   aws_secret_access_key='secret',
                                   proxy="NON_EXISTENT_HOSTNAME",
                                   proxy_port="3128")

        resp = conn.make_request('myCmd',
                                 {'par1': 'foo', 'par2': 'baz'},
                                 "/",
                                 "POST")
        del os.environ['no_proxy']
        args = urllib.parse.parse_qs(ensure_string(HTTPretty.last_request.body))
        self.assertEqual(args['AWSAccessKeyId'], ['access_key'])

    def test_query_connection_noproxy_nosecure(self):
        HTTPretty.register_uri(HTTPretty.POST,
                               'https://%s/' % self.region.endpoint,
                               json.dumps({'test': 'insecure'}),
                               content_type='application/json')

        os.environ['no_proxy'] = self.region.endpoint

        conn = self.region.connect(aws_access_key_id='access_key',
                                   aws_secret_access_key='secret',
                                   proxy="NON_EXISTENT_HOSTNAME",
                                   proxy_port="3128",
                                   is_secure = False)

        resp = conn.make_request('myCmd',
                                 {'par1': 'foo', 'par2': 'baz'},
                                 "/",
                                 "POST")
        del os.environ['no_proxy']
        args = urllib.parse.parse_qs(ensure_string(HTTPretty.last_request.body))
        self.assertEqual(args['AWSAccessKeyId'], ['access_key'])

    def test_single_command(self):
        HTTPretty.register_uri(HTTPretty.POST,
                               'https://%s/' % self.region.endpoint,
                               json.dumps({'test': 'secure'}),
                               content_type='application/json')

        conn = self.region.connect(aws_access_key_id='access_key',
                                   aws_secret_access_key='secret')
        resp = conn.make_request('myCmd',
                                 {'par1': 'foo', 'par2': 'baz'},
                                 "/",
                                 "POST")

        args = urlparse.parse_qs(HTTPretty.last_request.body)
        self.assertEqual(args[b'AWSAccessKeyId'], [b'access_key'])
        self.assertEqual(args[b'SignatureMethod'], [b'HmacSHA256'])
        self.assertEqual(args[b'Version'], [ensure_bytes(conn.APIVersion)])
        self.assertEqual(args[b'par1'], [b'foo'])
        self.assertEqual(args[b'par2'], [b'baz'])

        self.assertEqual(resp.read(), b'{"test": "secure"}')

    def test_multi_commands(self):
        """Check connection re-use"""
        HTTPretty.register_uri(HTTPretty.POST,
                               'https://%s/' % self.region.endpoint,
                               json.dumps({'test': 'secure'}),
                               content_type='application/json')

        conn = self.region.connect(aws_access_key_id='access_key',
                                   aws_secret_access_key='secret')

        resp1 = conn.make_request('myCmd1',
                                  {'par1': 'foo', 'par2': 'baz'},
                                  "/",
                                  "POST")
        body1 = urlparse.parse_qs(HTTPretty.last_request.body)

        resp2 = conn.make_request('myCmd2',
                                  {'par3': 'bar', 'par4': 'narf'},
                                  "/",
                                  "POST")
        body2 = urlparse.parse_qs(HTTPretty.last_request.body)

        self.assertEqual(body1[b'par1'], [b'foo'])
        self.assertEqual(body1[b'par2'], [b'baz'])
        with self.assertRaises(KeyError):
            body1['par3']

        self.assertEqual(body2[b'par3'], [b'bar'])
        self.assertEqual(body2[b'par4'], [b'narf'])
        with self.assertRaises(KeyError):
            body2['par1']

        self.assertEqual(resp1.read(), b'{"test": "secure"}')
        self.assertEqual(resp2.read(), b'{"test": "secure"}')

    def test_non_secure(self):
        HTTPretty.register_uri(HTTPretty.POST,
                               'http://%s/' % self.region.endpoint,
                               json.dumps({'test': 'normal'}),
                               content_type='application/json')

        conn = self.region.connect(aws_access_key_id='access_key',
                                   aws_secret_access_key='secret',
                                   is_secure=False)
        resp = conn.make_request('myCmd1',
                                 {'par1': 'foo', 'par2': 'baz'},
                                 "/",
                                 "POST")

        self.assertEqual(resp.read(), b'{"test": "normal"}')

    def test_alternate_port(self):
        HTTPretty.register_uri(HTTPretty.POST,
                               'http://%s:8080/' % self.region.endpoint,
                               json.dumps({'test': 'alternate'}),
                               content_type='application/json')

        conn = self.region.connect(aws_access_key_id='access_key',
                                   aws_secret_access_key='secret',
                                   port=8080,
                                   is_secure=False)
        resp = conn.make_request('myCmd1',
                                 {'par1': 'foo', 'par2': 'baz'},
                                 "/",
                                 "POST")

        self.assertEqual(resp.read(), b'{"test": "alternate"}')

    def test_temp_failure(self):
        responses = [HTTPretty.Response(body="{'test': 'fail'}", status=500),
                     HTTPretty.Response(body="{'test': 'success'}", status=200)]

        HTTPretty.register_uri(HTTPretty.POST,
                               'https://%s/temp_fail/' % self.region.endpoint,
                               responses=responses)

        conn = self.region.connect(aws_access_key_id='access_key',
                                   aws_secret_access_key='secret')
        resp = conn.make_request('myCmd1',
                                 {'par1': 'foo', 'par2': 'baz'},
                                 '/temp_fail/',
                                 'POST')
        self.assertEqual(resp.read(), b"{'test': 'success'}")

class TestAWSQueryStatus(TestAWSQueryConnection):

    def test_get_status(self):
        HTTPretty.register_uri(HTTPretty.GET,
                               'https://%s/status' % self.region.endpoint,
                               '<status>ok</status>',
                               content_type='text/xml')

        conn = self.region.connect(aws_access_key_id='access_key',
                                   aws_secret_access_key='secret')
        resp = conn.get_status('getStatus',
                               {'par1': 'foo', 'par2': 'baz'},
                               'status')

        self.assertEqual(resp, "ok")

    def test_get_status_blank_error(self):
        HTTPretty.register_uri(HTTPretty.GET,
                               'https://%s/status' % self.region.endpoint,
                               '',
                               content_type='text/xml')

        conn = self.region.connect(aws_access_key_id='access_key',
                aws_secret_access_key='secret')
        with self.assertRaises(BotoServerError):
            resp = conn.get_status('getStatus',
                                   {'par1': 'foo', 'par2': 'baz'},
                                   'status')

    def test_get_status_error(self):
        HTTPretty.register_uri(HTTPretty.GET,
                               'https://%s/status' % self.region.endpoint,
                               '<status>error</status>',
                               content_type='text/xml',
                               status=400)

        conn = self.region.connect(aws_access_key_id='access_key',
                                   aws_secret_access_key='secret')
        with self.assertRaises(BotoServerError):
            resp = conn.get_status('getStatus',
                                   {'par1': 'foo', 'par2': 'baz'},
                                   'status')

if __name__ == '__main__':
    unittest.main()
