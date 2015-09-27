#!/usr/bin/env python
# encoding: utf-8

import codecs
from datetime import datetime
from optparse import OptionParser
import random
import re
import time
import cookielib
import urllib
import urllib2
import logging

from bs4 import BeautifulSoup, NavigableString


class Message:
    def __init__(self, thread_url, sender, recipient, timestamp, subject, content, mbox=False):
        self.thread_url = thread_url
        self.sender = sender
        self.recipient = recipient
        self.timestamp = timestamp
        self.subject = subject
        self.content = content
        self.mbox = mbox

    def __str__(self):
        if self.mbox:
            msglength = len(self.content)
            subject="OKC Message, length = " + str(msglength).zfill(4)  # leading zeros for message length
            tstamp=self.timestamp.strftime('%a %b %d %H:%M:%S %Y') if self.timestamp else None
            return """
From - %s
Date: %s
From: %s
To: %s
Subject: %s

%s
URL: %s

"""            % (  tstamp, tstamp,
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
        self.mbox = False


class ArrowFetcher:
    secure_base_url = 'https://www.okcupid.com'
    sleep_duration = 2.0  # base time to wait after each HTTP request, but this will be adjusted randomly
    encoding_pairs = [('<br />', '\n'),
                      ('<br/>', '\n'),
                      ('&#35;', '#'),
                      ('&amp;', '&'),
                      ('&#38;', '&'),
                      ('&#38;amp;', '&'),
                      ('&lt;', '<'),
                      ('&gt;', '>'),
                      ('&quot;', '"'),
                      ('&#38;quot;', '"'),
                      ('&#39;', "'"),
                      ('&rsquo;', u'\u2019'),
                      ('&mdash;', "--")]
    # TODO: make a better "guess" about the time of the broadcast, account deletion, or Quiver match.
    # Perhaps get the time of the next message/reply (there should be at least one), and set the time based on it.
    fallback_date = datetime(2000, 1, 1, 12, 0)

    def __init__(self, username, mbox=False, debug=False, indexfile=None):
        self.username = username
        self.mbox = mbox
        self.debug = debug
        self.thread_urls = []
        self.indexfile = indexfile
        if indexfile:
            self.secure_base_url = 'https://localhost'

    def _safely_soupify(self, f):
        f = f.partition("function autocoreError")[0] + '</body></html>' # wtf okc with the weirdly encoded "</scr' + 'ipt>'"-type statements in your javascript
        return(BeautifulSoup(f, "html.parser"))

    def _request_read_sleep(self, url):
        f = urllib2.urlopen(url).read()
        time.sleep(abs(self.sleep_duration + (random.randrange(-100, 100)/100.0)))
        return f

    def queue_threads(self):
        self.thread_urls = []
        try:
            for folder in range(1, 4):  # Inbox, Sent, Smiles
                page = 0
                while (page < 1 if self.debug else True):
                    logging.info("Queuing folder %s, page %s", folder, page)
                    if self.indexfile:
                        f = urllib2.urlopen('file:'+self.indexfile).read()
                    else:
                        f = self._request_read_sleep(self.secure_base_url + '/messages?folder=' + str(folder) + '&low=' + str((page * 30) + 1))
                    soup = self._safely_soupify(f)
                    end_pattern = re.compile('&folder=\d\';')
                    threads = []
                    self.threadtimes = {}
                    for li in soup.find('ul', {'id': 'messages'}).find_all('li'):
                        threads.append('/messages?readmsg=true&threadid=' + li['data-threadid'])
                        fancydate_js = li.find('span', 'timestamp').find('script').string
                        timestamp = datetime.fromtimestamp(int(fancydate_js.split(', ')[1]))
                        self.threadtimes[ li['data-threadid'] ] = timestamp

                    if len(threads) == 0:  # break out of the infinite loop when we reach the end and there are no threads on the page
                        break
                    else:
                        self.thread_urls.extend(threads)
                        page = page + 1
        except AttributeError:
            logging.error("There was an error queuing the threads to download - are you sure your username and password are correct?")

    def dedupe_threads(self):
        if self.thread_urls:
            before = len(self.thread_urls)
            logging.debug("Removing duplicate thread URLs")
            self.thread_urls = list(set(self.thread_urls))
            after = len(self.thread_urls)
            logging.debug("Removed %s thread URLs (from %s to %s)", before - after, before, after)

    def fetch_threads(self):
        self.messages = []
        for thread_url in self.thread_urls:
            try:
                thread_messages = self._fetch_thread(thread_url)
            except Exception as e:
                thread_messages = [MessageMissing(self.secure_base_url + thread_url)]
                logging.error("Fetch thread failed for URL: %s with error %s", thread_url, e)
            self.messages.extend(thread_messages)

    def write_messages(self, file_name):
        self.messages.sort(key = lambda message: (message.thread_url, message.timestamp))  # sort by sender, then time
        f = codecs.open(file_name, encoding='utf-8', mode='w')  # ugh, otherwise i think it will try to write ascii
        for message in self.messages:
            logging.debug("Writing message for thread: " + message.thread_url)
            f.write(unicode(message))
        f.close()

    def _fetch_thread(self, thread_url):
        message_list = []
        logging.info("Fetching thread: " + self.secure_base_url + thread_url)
        threadnum = thread_url.split('=')[-1]
        f = self._request_read_sleep(self.secure_base_url + thread_url)
        soup = self._safely_soupify(f)
        logging.debug("Raw full-page (type: %s): %s", type(soup), soup)
        thread_element = soup.find('ul', {'id': 'thread'})
        try:
            subject = soup.find('strong', {'id': 'message_heading'}).contents[0]
            subject = unicode(subject)
            for find, replace in self.encoding_pairs:
                subject = subject.replace(unicode(find), unicode(replace))
        except AttributeError:
            subject = unicode('')
        try:
            other_user = soup.find('input', {'name': 'buddyname'}).get('value')

        except AttributeError:
            try:
                # messages from OkCupid itself are a special case
                other_user = thread_element.find('div', 'signature').contents[0].partition('Message from ')[2]
            except AttributeError:
                other_user = ''
        mutual_match_no_messages = thread_element.find_all('a', class_='mutual_match_no_messages')
        if len(list(mutual_match_no_messages)) == 1:
            sender = other_user
            recipient = self.username
            timestamp = self.threadtimes.get(threadnum, self.fallback_date)
            body = unicode("You like each other!")
            logging.debug("No message, only mutual match: %s", body)
            message_list.append(Message(self.secure_base_url + thread_url,
                                        unicode(sender),
                                        unicode(recipient),
                                        timestamp,
                                        subject,
                                        body,
                                        mbox=self.mbox))
        else:
            messages = thread_element.find_all('li')
            logging.debug("Raw messages (type: %s): %s", type(messages), messages)
            for message in messages:
                message_type = re.sub(r'_.*$', '', message.get('id', 'unknown'))
                logging.debug("Raw message (type: %s): %s", type(message), message)
                body_contents = message.find('div', 'message_body')
                if not body_contents and message_type == 'deleted':
                    body_contents = message
                if body_contents:
                    logging.debug("Message (type: %s): %s", message_type, body_contents)
                    body = self._strip_tags(body_contents.encode_contents().decode('UTF-8')).strip()
                    logging.debug("Message after tag removing: %s", body)
                    for find, replace in self.encoding_pairs:
                        body = body.replace(unicode(find), unicode(replace))
                    logging.debug("Message after HTML entity conversion: %s", body)
                    if message_type in ['broadcast', 'deleted', 'quiver']:
                        timestamp = self.threadtimes.get(threadnum, self.fallback_date)
                    else:
                        fancydate_js = message.find('span', 'timestamp').find('script').string
                        timestamp = datetime.fromtimestamp(int(fancydate_js.split(', ')[1]))
                    sender = other_user
                    recipient = self.username
                    try:
                        if any(clazz.replace('preview', '').strip() == 'from_me' for clazz in message['class']):
                            recipient = other_user
                            sender = self.username
                    except KeyError:
                        pass
                    logging.debug("Body: %s", body)
                    message_list.append(Message(self.secure_base_url + thread_url,
                                                unicode(sender),
                                                unicode(recipient),
                                                timestamp,
                                                subject,
                                                body,
                                                mbox=self.mbox))
                else:
                    continue  # control elements are also <li>'s in their html, so non-messages
        return message_list

    # http://stackoverflow.com/questions/1765848/remove-a-tag-using-beautifulsoup-but-keep-its-contents/1766002#1766002
    def _strip_tags(self, html, invalid_tags=['em', 'a', 'span', 'strong', 'div', 'p']):
        soup = BeautifulSoup(html, "html.parser")
        for tag in soup.find_all(True):
            if tag.name in invalid_tags:
                s = ""
                for c in tag.contents:
                    if not isinstance(c, NavigableString):
                        c = self._strip_tags(unicode(c), invalid_tags)
                        s += unicode(c).strip()
                    else:
                        s += unicode(c)
                tag.replace_with(s)
        return soup.encode_contents().decode('UTF-8')

class OkcupidState:
    def __init__(self, username, filename, mbox, debug, indexfile):
        self.username = username
        self.filename = filename
        self.mbox = mbox
        self.debug = debug
        self.indexfile = indexfile
        self.cookie_jar = cookielib.CookieJar()
        self.opener = urllib2.build_opener(urllib2.HTTPCookieProcessor(self.cookie_jar))
        urllib2.install_opener(self.opener)

    def _setOpenerUrl(self, url, params=None):
        f = self.opener.open(url, params)
        f.close()
        logging.debug("Cookie jar: %s", self.cookie_jar)

    def fetch(self):
        arrow_fetcher = ArrowFetcher(
            self.username,
            mbox=self.mbox,
            debug=self.debug,
            indexfile=self.indexfile)
        arrow_fetcher.queue_threads()
        arrow_fetcher.dedupe_threads()
        try:
            arrow_fetcher.fetch_threads()
            arrow_fetcher.write_messages(self.filename)
        except KeyboardInterrupt:
            if self.debug:  # Write progress so far to the output file if we're debugging
                arrow_fetcher.write_messages(self.filename)
            raise KeyboardInterrupt

    def use_password(self, password):
        logging.debug("Using password.")
        params = urllib.urlencode(dict(username=self.username, password=password))
        self._setOpenerUrl(ArrowFetcher.secure_base_url + '/login', params)

    def use_autologin(self, autologin):
        logging.debug("Using autologin url: %s", autologin)
        self._setOpenerUrl(autologin)

    def use_indexfile(self, indexfile):
        logging.debug("Using cached index file: %s", indexfile)
        self._setOpenerUrl('file:'+indexfile)

def main():
    usage =  "okcmd -u your_username -p your_password -f 'message_output_file.txt'"
    description = "OkCupid-Message-Downloader (OKCMD): a tool for downloading your sent and received OkCupid messages to a text file."
    epilog = "See also https://github.com/lehrblogger/OkCupid-Message-Downloader"
    # TODO: add version argument based on setup.py's version number.
    #version = "okcmd 1.3"
    parser = OptionParser(usage=usage, description=description, epilog=epilog)
    parser.add_option("-u", "--username", dest="username",
                      help="your OkCupid username")
    parser.add_option("-p", "--password", dest="password",
                      help="your OkCupid password")
    parser.add_option("-a", "--autologin", dest="autologin",
                      help="a link from an OkCupid email, which contains your login credentials; use instead of a password")
    parser.add_option("-f", "--filename", dest="filename",
                      help="the file to which you want to write the data")
    parser.add_option("-m", "--mbox", dest="mbox",
                      help="format output as MBOX rather than as plaintext",
                      action='store_const', const=True, default=False)
    parser.add_option("-t", "--thunderbird", dest="mbox",
                      help="format output for Thunderbird rather than as plaintext",
                      action='store_const', const=True, default=False)
    parser.add_option("-d", "--debug", dest="debug",
                      help="limit the number of threads fetched for debugging, and output raw HTML",
                      action='store_const', const=True, default=False)
    parser.add_option("-i", "--index", dest="indexfile", default=None,
                      help="read the message index from html file, for developers. Implies --debug")
    (options, args) = parser.parse_args()
    options_ok = True
    logging_format = '%(levelname)s: %(message)s'
    if options.indexfile:
        options.debug = True
        options.username = 'staff_robot'
        options.password = 'he@rtl3ss!'

    if options.debug:
        logging.basicConfig(format=logging_format, level=logging.DEBUG)
        logging.debug("Debug mode turned on.")
    else:
        logging.basicConfig(format=logging_format, level=logging.INFO)
    if not options.username:
        logging.error("Please specify your OkCupid username with either '-u' or '--username'")
        options_ok = False
    if not options.autologin and not options.password:
        logging.error("Please specify your OkCupid password with either '-p' or '--password' (or use '-a' or '--autologin')")
        options_ok = False
    if options.autologin and options.password:
        logging.error("Don't specify both autologin and password")
        options_ok = False
    if not options.filename:
        logging.error("Please specify the destination file with either '-f' or '--filename'")
        options_ok = False
    if not options_ok:
        logging.error("See 'okcmd --help' for all options.")
    else:
        state = OkcupidState(options.username, options.filename, options.mbox, options.debug, options.indexfile)
        if options.indexfile:
            state.use_indexfile(options.indexfile)
        elif options.username and options.password:
            state.use_password(options.password)
        elif options.autologin:
            state.use_autologin(options.autologin)
        state.fetch()
    logging.info("Done.")

if __name__ == '__main__':
    main()
