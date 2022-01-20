#!/usr/bin/env python
"""Create a changelog file from all the merged pull requests

Looking into the latest github milestone, print out all the pull requests for
spinalcordtoolbox/spinalcordtoolbox grouped by label and saved in `changlog.[tagId].md`
in markdown format. The command makes the assumption that the milestone title
is formatted as `Release v[MAJOR].[MINOR].[PATCH]`

How it works: Once the new tag is ready, you can simply run

`./install/sct_changlog.py`

and copy and paste the content of changlog.[tagId].md to CHANGES.md

"""
import sys, io, logging, datetime, time, collections

import requests

API_URL = 'https://api.github.com/repos/spinalcordtoolbox/spinalcordtoolbox/'


class RateLimiter(object):
    def __init__(self, get, count, period):
        self._count = count
        self._period = period
        self._requests = collections.deque()
        self._get = get

    def get(self, *args, **kw):
        if len(self._requests) < self._count:
            self._requests.append(time.time())
            return self._get(*args, **kw)

        now = time.time()
        r = self._requests.popleft()
        if now < r + self._period:
            dt = r + self._period - now
            logging.info("Waiting %.3fs so as to not go over the API rate limit", dt)
            time.sleep(dt)

        self._requests.append(time.time())
        return self._get(*args, **kw)


requests.get = RateLimiter(requests.get, 3, 10).get


def latest_milestone():
    """Get from Github the details of the latest milestone
    """
    milestone_url = API_URL + 'milestones'
    response = requests.get(milestone_url)
    data = response.json()
    logging.info('Open milestones found %d', len(data))
    logging.info('Latest Milestone: %s', data[0]['title'])
    return data[0]


def detailed_changelog(new_tag):
    """Return the Github URL comparing the last tags with the new_tag.
    """
    tags_url = API_URL + 'releases'
    response = requests.get(tags_url)
    previous_tag = response.json()[0]['tag_name']
    return ("https://github.com/spinalcordtoolbox/spinalcordtoolbox/compare/%s...%s" % (previous_tag, new_tag))


def search(milestone, label=''):
    """Return a list of merged pull requests linked to the milestone and label
    """
    search_url = 'https://api.github.com/search/issues'
    query = 'milestone:"%s" is:pr repo:spinalcordtoolbox/spinalcordtoolbox state:closed is:merged' % (milestone)
    if label:
        query += ' label:%s' % (label)
    payload = {'q': query}
    response = requests.get(search_url, params=payload)
    data = response.json()
    logging.info('Milestone: %s, Label: %s, Count: %d', milestone, label, data['total_count'])
    return data


def get_sct_function_from_label(dict_labels=''):
    """
    Return a csv string with a list of labels that corresponds to SCT functions exposed to the user (contains "sct_")
    :param dict_labels: dictionary of labels generated by Github
    :return: labels_list: list of labels
    """
    labels_list = []
    for label in dict_labels:
        # check if label contains sct
        if "sct_" in label['name']:
            labels_list.append(label['name'])
    return labels_list


def check_compatibility(dict_labels=''):
    """
    Check if label "compatibility" is included. If it is, output a string with warning about broken compatibility.
    Otherwise, output an empty string.
    :param dict_labels: dictionary of labels generated by Github
    :return: str: String with warning of broken compatibility. Or empty otherwise.
    """
    warning_compatibility = ''
    for label in dict_labels:
        # check if label contains sct
        if 'compatibility' in label['name']:
            warning_compatibility = '**WARNING: Breaks compatibility with previous versions of SCT.** '
    return warning_compatibility


if __name__ == '__main__':
    logging.basicConfig(stream=sys.stdout, level=logging.INFO, format='SCT changelog -- %(message)s')
    milestone = latest_milestone()
    title = milestone['title'].split()[-1]

    lines = [
        '## {} ({})'.format(title, datetime.date.today()),
        '[View detailed changelog](%s)' % detailed_changelog(title),
    ]

    changelog_pr = set()
    for label in ['bug', 'enhancement', 'feature', 'documentation', 'installation', 'testing']:
        pulls = search(milestone['title'], label)
        items = pulls.get('items')
        if items:
            lines.append('\n**{}**\n'.format(label.upper()))
            changelog_pr = changelog_pr.union(set([x['html_url'] for x in items]))
            for x in pulls.get('items'):
                items = [" - **%s:** %s. %s[View pull request](%s)" % (",".join(get_sct_function_from_label(x['labels'])),
                                                                x['title'],
                                                                check_compatibility(x['labels']),
                                                                x['html_url'])]
                if (len(get_sct_function_from_label(x['labels'])) == 0):
                    items[0] = items[0].replace("**:** ","")
                lines.extend(items)

    logging.info('Total number of pull requests with label: %d', len(changelog_pr))
    all_pr = set([x['html_url'] for x in search(milestone['title'])['items']])
    diff_pr = all_pr - changelog_pr
    for diff in diff_pr:
        logging.warning('Pull request not labeled: %s', diff)

    filename = 'changelog.%d.md' % milestone['number']
    with io.open(filename, "wb") as changelog:
        changelog.write('\n'.join(lines).encode("utf-8"))
    logging.info('Changelog saved in %s', filename)
    print('open {}'.format(filename))