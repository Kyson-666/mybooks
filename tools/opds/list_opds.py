#!/usr/bin/env python3
"""列出指定 OPDS 服务根目录中的一级导航项。"""

import argparse
import sys
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET


ATOM_NS = "{http://www.w3.org/2005/Atom}"
ATOM_MEDIA_TYPE = "application/atom+xml"


def list_first_level(url, timeout=30, username=None, password=None):
    """Fetch an OPDS root feed and return its navigation titles and URLs."""
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/atom+xml, application/xml, text/xml",
            "User-Agent": "MyBooks OPDS directory lister",
        },
    )
    if username is None:
        opener = urllib.request.build_opener()
    else:
        password_manager = urllib.request.HTTPPasswordMgrWithDefaultRealm()
        password_manager.add_password(None, url, username, password)
        opener = urllib.request.build_opener(
            urllib.request.HTTPBasicAuthHandler(password_manager)
        )

    with opener.open(request, timeout=timeout) as response:
        feed_url = response.geturl()
        feed = ET.fromstring(response.read())

    directories = []
    for entry in feed.findall(ATOM_NS + "entry"):
        title_element = entry.find(ATOM_NS + "title")
        title = title_element.text.strip() if title_element is not None and title_element.text else ""
        if not title:
            continue

        for link in entry.findall(ATOM_NS + "link"):
            href = link.get("href")
            media_type = link.get("type", "").split(";", 1)[0].strip().lower()
            if href and media_type == ATOM_MEDIA_TYPE:
                directories.append((title, urllib.parse.urljoin(feed_url, href)))
                break

    return directories


def main():
    parser = argparse.ArgumentParser(description="列出 OPDS 服务根目录中的一级导航项")
    parser.add_argument("url", help="OPDS 服务根目录 URL，例如 https://example.com/opds/")
    parser.add_argument("--timeout", type=float, default=30, help="请求超时时间（秒，默认：30）")
    parser.add_argument("--username", help="OPDS 登录用户名")
    parser.add_argument("--password", help="OPDS 登录密码")
    args = parser.parse_args()

    if (args.username is None) != (args.password is None):
        parser.error("--username 和 --password 必须同时提供")

    try:
        directories = list_first_level(
            args.url,
            timeout=args.timeout,
            username=args.username,
            password=args.password,
        )
    except (OSError, urllib.error.URLError, ET.ParseError, ValueError) as error:
        print("读取 OPDS 目录失败: {}".format(error), file=sys.stderr)
        return 1

    if not directories:
        print("未找到一级导航目录。")
        return 0

    for title, directory_url in directories:
        print("{}\t{}".format(title, directory_url))
    return 0


if __name__ == "__main__":
    sys.exit(main())