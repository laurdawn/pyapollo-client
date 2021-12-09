# pyapollo-client

协程配置中心apollo客户端

使用参考pyapollo

# Features

* 实时同步配置
* 灰度配置
* 客户端容灾

``` python
client = ApolloClient(app_id=<appId>, ip:str=<ip>, port:int=<port>, namespaces:list = <namespaces>)
#获取配置value
key_value = client.get_value(key=<key>, namespace=<namespace>)
namespace_value = client.get(namespace=<namespace>)
```


# Contribution
  * Source Code: https://github.com/filamoon/pyapollo/
  * Issue Tracker: https://github.com/filamoon/pyapollo/issues