from django.conf import settings
import requests
import time
import logging

graphite_api = settings.GRAPHITE_API
user = settings.GRAPHITE_USER
password = settings.GRAPHITE_PASS
graphite_from = settings.GRAPHITE_FROM
auth = (user, password)


def get_data(target_pattern):
    resp = requests.get(
        graphite_api + 'render', auth=auth,
        params={
            'target': target_pattern,
            'format': 'json',
            'from': graphite_from
        }
    )
    resp.raise_for_status()
    return resp.json


def get_matching_metrics(pattern):
    print 'Getting metrics matching %s' % pattern
    resp = requests.get(
        graphite_api + 'metrics/find/', auth=auth,
        params={
            'query': pattern,
            'format': 'completer'
        },
        headers={
            'accept': 'application/json'
        }
    )
    resp.raise_for_status()
    return resp.json


def get_all_metrics(limit=None):
    """Grabs all metrics by navigating find API recursively"""
    metrics = []

    def get_leafs_of_node(nodepath):
        for obj in get_matching_metrics(nodepath)['metrics']:
            if int(obj['is_leaf']) == 1:
                metrics.append(obj['path'])
            else:
                get_leafs_of_node(obj['path'])
    get_leafs_of_node('')
    return metrics


def parse_metric(metric, mins_to_check=5, max_age=60):
    """
    Returns dict with:
    - num_series_with_data: Number of series with data
    - num_series_no_data: Number of total series
    - max
    - min
    - average_value
    """
    ret = {
        'num_series_with_data': 0,
        'num_series_no_data': 0,
        'error': None,
        'all_values': [],
        'raw': ''
    }
    try:
        data = get_data(metric)
    except requests.exceptions.RequestException, e:
        ret['error'] = 'Error getting data from Graphite: %s' % e
        ret['raw'] = ret['error']
        logging.error('Error getting data from Graphite: %s' % e)
        return ret
    all_values = []
    now = int(time.time())
    start_time = now - (mins_to_check * 60) - 5
    for target in data:
        # Original code assumes data points are 1 minute apart.
        #values = [float(t[0])
        #          for t in target['datapoints'][-mins_to_check:] if t[0] is not None]

        # Discover all non-null values from -mins_to_check till now.
        values = []
        newest_time = 0
        for ts_value in target['datapoints']:
            if ts_value[0] is None:
                continue
            if ts_value[1] >= start_time:
                values.append(float(ts_value[0]))
                if ts_value[1] > newest_time:
                    newest_time = ts_value[1]

        # If newest value is new enough, count the series.
        if values and newest_time > (now - max_age):
            ret['num_series_with_data'] += 1
        else:
            values = []
            ret['num_series_no_data'] += 1
        all_values.extend(values)
    if all_values:
        ret['max'] = max(all_values)
        ret['min'] = min(all_values)
        ret['average_value'] = sum(all_values) / len(all_values)
    ret['all_values'] = all_values
    ret['raw'] = data
    return ret
