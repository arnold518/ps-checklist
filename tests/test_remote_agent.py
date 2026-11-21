"""Crawler URL boundaries, publication receipts, and acknowledgement recovery."""

import threading
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import requests

from crawler.remote import Agent, RemoteClient, RemoteStorageApp
from storage.app import StorageApp, StorageError


class RemoteAgentTests(unittest.TestCase):
    def test_crawler_secret_only_goes_to_https_or_loopback(self):
        token = 'a' * 64
        for url in ('http://example.com/api','https://user:password@example.com/api',
                    'https://example.com/api?token=secret'):
            with self.assertRaises(ValueError):
                RemoteClient({'DEPLOYMENT_API_URL':url,'CRAWLER_TOKEN':token})
        client = RemoteClient({'DEPLOYMENT_API_URL':'https://example.com','CRAWLER_TOKEN':token})
        self.assertEqual(client.url,'https://example.com/api')

    def test_admin_writes_use_stable_fenced_step_receipts(self):
        app = RemoteStorageApp({})
        job = {'id':'job','lease':'lease','kind':'admin'}
        with patch.object(StorageApp,'rpc',return_value={'saved':True}) as rpc:
            for _ in range(2):
                app.begin_job(job)
                app.rpc('catalog','admin_remove',{'p_id':'contest','p_version':'old'},privileged=True)
                app.end_job()
            first, second = rpc.call_args_list
            self.assertEqual(first,second)
            self.assertEqual(first.args[1],'deployment_admin_step')
            self.assertEqual(first.args[2]['p_step'],'admin_remove:1')
            self.assertEqual(first.args[2]['p_lease'],'lease')
            app.rpc('catalog','admin_catalog',{},privileged=True)
            self.assertEqual(rpc.call_args.args[1],'admin_catalog')

    @staticmethod
    def agent():
        agent = Agent.__new__(Agent)
        agent.queue = SimpleNamespace(_stop=threading.Event())
        agent.queue._stop.wait = Mock(return_value=False)
        agent.client = Mock()
        agent.app = Mock()
        agent.service = Mock()
        agent.service.fetch.return_value = {'ok':True,'data':{'source':'cf'}}
        agent.heartbeat = lambda *_: None
        return agent

    def test_lost_acknowledgement_retries_completion_without_fetching_again(self):
        agent = self.agent()
        agent.client.finish.side_effect = [requests.ConnectionError('lost response'),{'id':'job'}]
        job = {'id':'job','lease':'lease','kind':'fetch','request':{}}
        agent.execute(job)
        self.assertEqual(agent.service.fetch.call_count,1)
        self.assertEqual(agent.client.finish.call_count,2)
        self.assertEqual(agent.client.finish.call_args_list[0],agent.client.finish.call_args_list[1])

    def test_expired_lease_is_not_retried(self):
        agent = self.agent()
        agent.client.finish.side_effect = StorageError('Expired claim',409,'CONFLICT')
        agent.execute({'id':'job','lease':'lease','kind':'fetch','request':{}})
        self.assertEqual(agent.client.finish.call_count,1)
        agent.app.end_job.assert_called_once()


if __name__ == '__main__':
    unittest.main()
