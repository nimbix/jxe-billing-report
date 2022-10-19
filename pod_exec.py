
#!/usr/bin/env python


import time
import re
from kubernetes import config , client
from kubernetes.client import Configuration
from kubernetes.client.api import core_v1_api
from kubernetes.client.rest import ApiException
from kubernetes.stream import stream

def get_pod_name(api_instance, pod_namespace, pod_regex):  
    ret = api_instance.list_namespaced_pod(pod_namespace)
    for i in ret.items:
        #pod_regex = 'jarvice-dal-.*-.....'
        pod_name=i.metadata.name
        if re.match(pod_regex, pod_name):
            return pod_name

def exec_command(api_instance, name, namespace, exec_command):
    name = name
    resp = None
    try:
        resp = api_instance.read_namespaced_pod(name=name,
                                                namespace=namespace)
    except ApiException as e:
        if e.status != 404:
            print("Unknown error: %s" % e)
            exit(1)

    if not resp:
        print("Pod %s does not exist. DAL pod name not valid." % name)


    resp = stream(api_instance.connect_get_namespaced_pod_exec,
                  name,
                  namespace,
                  command=exec_command,
                  stderr=True, stdin=False,
                  stdout=True, tty=False)
    return(resp)
