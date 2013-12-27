#!/usr/bin/env python
# encoding: utf-8

import codecs
from datetime import datetime
from optparse import OptionParser
import random
import re
import time
import urllib, urllib2

from BeautifulSoup import BeautifulSoup, NavigableString


class Message:
    def __init__(self, thread_url, sender, recipient, timestamp, subject, content, thunderbird=False):
        self.thread_url = thread_url
        self.sender = sender
        self.recipient = recipient
        self.timestamp = timestamp
        self.subject = subject
        self.content = content
        self.thunderbird = thunderbird
    
    def __str__(self):
        if self.thunderbird:
            msglength=len(self.content)
            subject="OKC Message, length = " + str(msglength).zfill(4)  # leading zeros for message length
            return """
From - %s
From: %s
To: %s
Subject: %s

%s
URL: %s

"""            % (  self.timestamp.strftime('%a %b %d %H:%M:%S %Y') if self.timestamp else None,
                    self.sender,
                    self.recipient,
                    subject,
                    self.content,
                    self.thread_url)
        else:
            return """
URL: %s
From: %s
To: %s
Date: %s
Subject: %s
Content-Length: %d

%s

"""            % (  self.thread_url,
                    self.sender,
                    self.recipient,
                    self.timestamp,
                    self.subject.strip() if self.subject else None,
                    len(self.content),
                    self.content
                   )
    

class MessageMissing(Message):
    def __init__(self, thread_url):
        self.thread_url = thread_url
        self.sender = None
        self.recipient = None
        self.timestamp = None
        self.subject = None
        self.content = "ERROR: message(s) not fetched"
        self.thunderbird = False
    

class ArrowFetcher:
    base_url = 'http://www.okcupid.com'
    secure_base_url = 'https://www.okcupid.com'
    sleep_duration = 2.0  # base time to wait after each HTTP request, but this will be adjusted randomly
    encoding_pairs = [('<br />', '\n'),
                      ('&#35;', '#'),
                      ('&amp;', '&'),
                      ('&#38;', '&'),
                      ('&#38;amp;', '&'),
                      ('&lt;', '<'),
                      ('&gt;', '>'),
                      ('&quot;', '"'),
                      ('&#38;quot;', '"'),
                      ('&#39;', "'"),
                      ('&mdash;', "--")]
    
    def __init__(self, username, password, thunderbird=False, debug=False):
        self.username = username
        self.thunderbird = thunderbird
        self.debug = debug
        self.thread_urls = []
        opener = urllib2.build_opener(urllib2.HTTPCookieProcessor())
        urllib2.install_opener(opener)
        params = urllib.urlencode(dict(username=username, password=password))
        f = opener.open(self.secure_base_url + '/login', params)
        f.close()
    
    def _safely_soupify(self, f):
        f = f.partition("function autocoreError")[0] + '</body></html>' # wtf okc with the weirdly encoded "</scr' + 'ipt>'"-type statements in your javascript
        return(BeautifulSoup(f))
    
    def _request_read_sleep(self, url):
        f = urllib2.urlopen(url).read()
        time.sleep(abs(self.sleep_duration + (random.randrange(-100, 100)/100.0)))
        return f
    
    def queue_threads(self):
        self.thread_urls = []
        try:
            for folder in range(1,4): # Inbox, Sent, Smiles
                page = 0;
                while (page < 1 if self.debug else True):
                    print "queuing folder %s, page %s" % (folder, page)
                    f = self._request_read_sleep(self.base_url + '/messages?folder=' + str(folder) + '&low=' + str((page * 30) + 1))
                    soup = self._safely_soupify(f)
                    end_pattern = re.compile('&folder=\d\';')
                    threads = [
                        re.sub(end_pattern, '', li.find('p').find('a')['href'].partition('&folder=')[0])
                        for li in soup.find('ul', {'id': 'messages'}).findAll('li')
                    ]
                    if len(threads) == 0:  # break out of the infinite loop when we reach the end and there are no threads on the page
                        break
                    else:
                        self.thread_urls.extend(threads)
                        page = page + 1
        except AttributeError:
            print "there was an error queueing the threads to download - are you sure your username and password are correct?"
    
    def dedupe_threads(self):
        if self.thread_urls:
            print "removing duplicate URLs"
            self.thread_urls = list(set(self.thread_urls))
    
    def fetch_threads(self):
        self.messages = []
        for thread_url in self.thread_urls:
            try:
                thread_messages = self._fetch_thread(thread_url)
            except Exception, e:
                thread_messages = [MessageMissing(self.base_url + thread_url)]
                print "fetch thread failed for URL: %s with error %s" % (thread_url, e)
            self.messages.extend(thread_messages)
    
    def strptime(self, string, format='%b %d, %Y &ndash; %I:%M%p'):
        return datetime.strptime(string.strip(), format)
    
    def write_messages(self, file_name):
        self.messages.sort(key = lambda message: (message.thread_url, message.timestamp))  # sort by sender, then time
        f = codecs.open(file_name, encoding='utf-8', mode='w')  # ugh, otherwise i think it will try to write ascii
        for message in self.messages:
            print "writing message for thread: " + message.thread_url
            f.write(unicode(message))
        f.close()
    
    def _fetch_thread(self, thread_url):
        message_list = []
        print "fetching thread: " + self.base_url + thread_url
        f = self._request_read_sleep(self.base_url + thread_url)
        soup = self._safely_soupify(f)
        try:
            subject = soup.find('strong', {'id': 'message_heading'}).contents[0]
            subject = unicode(subject)
            for find, replace in self.encoding_pairs:
                subject = subject.replace(unicode(find), unicode(replace))
        except AttributeError:
            subject = unicode('')
        try:
            other_user = soup.find('span', {'class': 'buddyname'}).find('a').contents[0]
        except AttributeError:
            try:
                # messages from OkCupid itself are a special case
                other_user = soup.find('ul', {'id': 'thread'}).find('div', 'signature').contents[0].partition('Message from ')[2]
            except AttributeError:
                other_user = ''
        for message in soup.find('ul', {'id': 'thread'}).findAll('li'):
            message_type = re.sub(r'_.*$', '', message.get('id', 'unknown'))
            body_contents = message.find('div', 'message_body')
            if body_contents:
                body = self._strip_tags(body_contents.renderContents()).renderContents().strip()
                for find, replace in self.encoding_pairs:
                    body = body.replace(find, replace)
                body = body.decode('utf-8')
                if message_type == 'broadcast':
                    # TODO: make a better "guess" about the time of the broadcast.
                    # Perhaps get the time of the next message/reply (there should be at least one), and set the time based on it.
                    unknown_time = "Jan 1, 2000 &ndash; 12:00pm"
                    timestamp = self.strptime(unknown_time)
                else:
                    timestamp = message.find('span','timestamp').find('span', 'fancydate')
                    if timestamp.decodeContents and timestamp.decodeContents():
                        timestamp = self.strptime(timestamp.decodeContents().strip())
                    else:
                        timestamp = self.strptime(timestamp.text.strip())
                sender = other_user
                recipient = self.username
                if message['class'].replace('preview', '').strip() == 'from_me':
                    recipient = other_user
                    sender = self.username
                message_list.append(Message(self.base_url + thread_url,
                                            unicode(sender),
                                            unicode(recipient),
                                            timestamp,
                                            subject,
                                            body,
                                            thunderbird=self.thunderbird))
            else:
                continue  # control elements are also <li>'s in their html, so non-messages
        return message_list
    
    # http://stackoverflow.com/questions/1765848/remove-a-tag-using-beautifulsoup-but-keep-its-contents/1766002#1766002
    def _strip_tags(self, html, invalid_tags=['em', 'a', 'span', 'strong', 'div']):
        soup = BeautifulSoup(html)
        for tag in soup.findAll(True):
            if tag.name in invalid_tags:
                s = ""
                for c in tag.contents:
                    if type(c) != NavigableString:
                        c = self._strip_tags(unicode(c), invalid_tags)
                        s += unicode(c).strip()
                    else:
                        s += unicode(c)
                tag.replaceWith(s)
        return soup
    

def main():
    parser = OptionParser()
    parser.add_option("-u", "--username", dest="username",
                      help="your OkCupid username")
    parser.add_option("-p", "--password", dest="password",
                      help="your OkCupid password")
    parser.add_option("-f", "--filename", dest="filename",
                    help="the file to which you want to write the data")
    parser.add_option("-t", "--thunderbird", dest="thunderbird",
                    help="format output for Thunderbird rather than as plaintext",
                    action='store_const', const=True, default=False)
    parser.add_option("-d", "--debug", dest="debug",
                    help="limit the number of threads fetched for debugging",
                    action='store_const', const=True, default=False)
    (options, args) = parser.parse_args()
    if not options.username:
        print "Please specify your OkCupid username with either '-u' or '--username'"
    if not options.password:
        print "Please specify your OkCupid password with either '-p' or '--password'"
    if not options.filename:
        print "Please specify the destination file with either '-f' or '--filename'"
    if options.username and options.password and options.filename:
        arrow_fetcher = ArrowFetcher(options.username, options.password, thunderbird=options.thunderbird, debug=options.debug)
        arrow_fetcher.queue_threads()
        arrow_fetcher.dedupe_threads()
        try:
            arrow_fetcher.fetch_threads()
            arrow_fetcher.write_messages(options.filename)
        except KeyboardInterrupt:
            if options.debug:  # Write progress so far to the output file if we're debugging
                arrow_fetcher.write_messages(options.filename)
            raise KeyboardInterrupt

if __name__ == '__main__':
    main()
    