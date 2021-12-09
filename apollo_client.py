#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Time    : 2021
# @Author  : laurdawn
# @Email   : 652751663@qq.com
import json
import logging
import threading
import time
from telnetlib import Telnet
from typing import Any, Dict, Optional, List

import requests


class ApolloClient(object):
    """
    this module is modified from the project: https://github.com/filamoon/pyapollo
    and had commit the merge request to the original repo
    thanks for the contributors
    since the contributors had stopped to commit code to the original repo, please submit issue or commit to https://github.com/BruceWW/pyapollo
    """

    def __new__(cls, *args, **kwargs):
        """
        singleton model
        """
        tmp = {_: kwargs[_] for _ in sorted(kwargs)}
        key = f"{args},{tmp}"
        if hasattr(cls, "_instance"):
            if key not in cls._instance:
                cls._instance[key] = super().__new__(cls)
        else:
            cls._instance = {key: super().__new__(cls)}
        return cls._instance[key]

    def __init__(
            self,
            app_id: str,
            cluster: str = "default",
            env: str = "DEV",
            namespaces: List[str] = None,
            ip: str = "localhost",
            port: int = 8080,
            timeout: int = 70,
            cycle_time: int = 300,
            # cache_file_path: str = None,
            authorization: str = None
            # request_model: Optional[Any] = None,
    ):
        """
        init method
        :param app_id: application id
        :param cluster: cluster name, default value is 'default'
        :param env: environment, default value is 'DEV'
        :param timeout: http request timeout seconds, default value is 70 seconds
        :param ip: the deploy ip for grey release, default value is the localhost
        :param port: the deploy port for grey release, default value is the 8080
        :param cycle_time: the cycle time to update configuration content from server
        :param cache_file_path: local cache file store path
        """
        self.app_id = app_id
        self.cluster = cluster
        self.timeout = timeout
        self.stopped = False
        self._env = env
        self.ip = self.init_ip(ip)
        self.port = port
        self.host = f"http://{ip}:{port}"
        self._authorization = authorization
        self._request_model = None
        self._cache: Dict = {}
        self._notification_map = []
        if namespaces is None:
            self.namespaces = ["application"]
            self._notification_map.append({"namespaceName": "application", "notificationId": -1})
        else:
            self.namespaces = namespaces
            for _ in namespaces:
                self._notification_map.append({"namespaceName": _, "notificationId": -1})
        self._cycle_time = cycle_time
        self._hash: Dict = {}
        self.start()

    @staticmethod
    def init_ip(ip: Optional[str]) -> str:
        """
        for grey release
        :param ip:
        :return:
        """
        if ip is None:
            try:
                import socket
                s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                s.connect(("8.8.8.8", 53))
                ip = s.getsockname()[0]
                s.close()
            except BaseException:
                return "127.0.0.1"
        return ip

    def get_value(
            self, key: str, default_val: str = None, namespace: str = "application"
    ) -> Any:
        """
        get the configuration value
        :param key:
        :param default_val:
        :param namespace:
        :return:
        """
        try:
            # check the namespace is existed or not
            if namespace in self._cache:
                return self._cache[namespace].get(key, default_val)
            return default_val
        except Exception:
            return default_val

    def get(self, namespace: str = "application"
            ) -> Any:
        """
        get the configuration value
        :param key:
        :param default_val:
        :param namespace:
        :return:
        """
        return self._cache.get(namespace, None)

    def start(self) -> None:
        """
        Start the long polling loop.
        :return:
        """
        # check the cache is empty or not
        if len(self._cache) == 0:
            for _ in self.namespaces:
                self._pull_config(_)
        # start the thread to get config server with schedule
        t = threading.Thread(target=self._listener)
        t.setDaemon(True)
        t.start()

    def _http_get(self, url: str, params: Dict = None) -> requests.Response:
        """
        handle http request with get method
        :param url:
        :return:
        """
        if self._request_model is None:
            return self._request_get(url, params=params)
        else:
            return self._request_model(url)

    def _request_get(self, url: str, params: Dict = None) -> requests.Response:
        """

        :param url:
        :param params:
        :return:
        """
        try:
            if self._authorization:
                return requests.get(
                    url=url,
                    params=params,
                    timeout=self.timeout,
                    headers={"Authorization": self._authorization},
                )
            else:
                return requests.get(url=url, params=params, timeout=self.timeout)

        except requests.exceptions.ReadTimeout:
            # if read timeout, check the server is alive or not
            try:
                tn = Telnet(host=self.host, port=self.port, timeout=self.timeout // 2)
                tn.close()
                # if connect server succeed, raise the exception that namespace not found
                raise Exception("namespace not found")
            except ConnectionRefusedError:
                # if connection refused, raise server not response error
                raise Exception(
                    "server: %s not response" % self.host
                )

    def _pull_config(self, namespaceName: str):
        url = f"{self.host}/configs/{self.app_id}/{self.cluster}/{namespaceName}"
        try:
            r = self._http_get(url)
            if r.status_code == 404:
                # logging.getLogger(__name__).error("namespace:%s Not Found！", namespaceName)
                raise Exception("namespace:%s Not Found！" % namespaceName)
            data = r.json()
            configurations = data.get("configurations", {})
            releaseKey = data.get("releaseKey", "")
            if configurations:
                self._cache[namespaceName] = configurations
                logging.getLogger(__name__).info(
                    "Updated cache for namespace %s release key %s: %s",
                    namespaceName,
                    releaseKey,
                    repr(configurations),
                )

        except Exception as e:
            logging.getLogger(__name__).warning(str(e))

    def _notification(self) -> None:
        """

        :param namespace:
        :return:
        """
        url = f"{self.host}/notifications/v2?appId={self.app_id}&cluster={self.cluster}&notifications={json.dumps(self._notification_map)}"
        try:
            r = self._http_get(url)
            if r.status_code == 200:
                data = r.json()
                self._notification_map = data
                # 重新拉取配置
                for _ in self._notification_map:
                    self._pull_config(_["namespaceName"])
            elif r.status_code == 304:
                # 配置没有变化，返回
                pass
            else:
                logging.getLogger(__name__).warning("apollo http status excaption!!!!!!!")
        except BaseException as e:
            logging.getLogger(__name__).warning(str(e))

    def _long_poll(self) -> None:
        try:
            self._notification()
        except requests.exceptions.ReadTimeout as e:
            logging.getLogger(__name__).warning(str(e))
        except requests.exceptions.ConnectionError as e:
            logging.getLogger(__name__).warning(str(e))

    def _listener(self) -> None:
        """

        :return:
        """
        while True:
            logging.getLogger(__name__).info("Entering listener loop...")
            self._long_poll()
            time.sleep(self._cycle_time)


if __name__ == '__main__':
    client = ApolloClient(app_id="SampleApp", cluster='default', ip="10.32.12.203", port=8080)
    value = client.get()
    print("value:", value)
