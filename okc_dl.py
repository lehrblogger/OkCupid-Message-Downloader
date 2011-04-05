import codecs
from datetime import datetime
from optparse import OptionParser
import re
import time
import urllib, urllib2

from BeautifulSoup import BeautifulSoup, NavigableString

class Message:
    def __init__(self, thread_url, sender, recipient, timestamp, subject, content):
        self.thread_url = thread_url
        self.sender = sender
        self.recipient = recipient
        self.timestamp = int(timestamp)
        self.subject = subject
        self.content = content
    def __str__(self):
        return """
URL: %s
From: %s
To: %s
Date: %s
Subject: %s
Content-Length: %d

%s

"""            % (self.thread_url, 
                    self.sender, 
                    self.recipient, 
                    datetime.fromtimestamp(self.timestamp), 
                    self.subject,
                    len(self.content),
                    self.content
                   )


class CupidFetcher:
    base_url = 'http://www.okcupid.com'
    sleep_duration = 0  # time to wait after each HTTP request

    def __init__(self, username, password):
        self.username = username
        self.thread_urls = []
        opener = urllib2.build_opener(urllib2.HTTPCookieProcessor())
        urllib2.install_opener(opener)
        params = urllib.urlencode(dict(username=username, password=password))
        f = opener.open(self.base_url + '/login', params)
        f.close()
    
    def _safely_soupify(self, f):
        f = f.partition("function autocoreError")[0] + '</body></html>' # wtf okc with the weirdly encoded "</scr' + 'ipt>'"-type statements in your javascript
        return(BeautifulSoup(f))
    
    def _request_read_sleep(self, url):
        f = urllib2.urlopen(url).read()
        time.sleep(self.sleep_duration)
        return f
    
    def queue_threads(self):
        self.thread_urls = []
        for folder in range(1,4):
            page = 1;
            while (page < 2):
                f = self._request_read_sleep(self.base_url + '/messages?folder=' + str(folder) + '&low=' + str((page * 30) + 1))
                soup = self._safely_soupify(f)
                end_pattern = re.compile('&folder=\d\';')
                threads = [
                    re.sub(end_pattern, '', li.find('p')['onclick'].strip("\"window.location='"))
                    for li in soup.find('ul', {'id': 'messages'}).findAll('li')
                ]
                if len(threads) == 0:
                    break
                else:
                    self.thread_urls.extend(threads)
                    page = page + 1
    
    def dedupe_threads(self):
        self.thread_urls = list(set(self.thread_urls))
    
    def fetch_threads(self):
        # self.thread_urls = ['/messages?readmsg=true&threadid=9806533583687024201', '/messages?readmsg=true&threadid=6421379663940737121', '/messages?readmsg=true&threadid=2740027005373537189']
        self.messages = []
        for thread_url in self.thread_urls:
            self.messages.extend(self._fetch_thread(thread_url))

    def write_messages(self, file_name):
        self.messages.sort(key = lambda message: message.timestamp)
        f = codecs.open(file_name, encoding='utf-8', mode='w')
        for message in self.messages:
            print "writing message for thread: " + message.thread_url
            try:
                f.write(unicode(message))
            except UnicodeDecodeError, e:
                print message.content
                raise e
            except UnicodeEncodeError, e:
                print message.content
                raise e
        f.close()
    
    def _fetch_thread(self, thread_url):
        message_list = []
        print "fetching thread: " + self.base_url + thread_url
        f = self._request_read_sleep(self.base_url + thread_url)
        soup = self._safely_soupify(f)
        try:
            subject = soup.find('strong', {'id': 'message_heading'}).contents[0]
        except AttributeError:
            subject = ''
        try:
            other_user = soup.find('ul', {'id': 'thread'}).find('a', 'buddyname ').contents[0]
        except AttributeError:
            other_user = soup.find('ul', {'id': 'thread'}).find('p', 'signature').contents[0].strip('Message from ')
        for message in soup.find('ul', {'id': 'thread'}).findAll('li'):
            body_contents = message.find('div', 'message_body')
            if body_contents:
                body = self._strip_tags(body_contents.renderContents()).renderContents().strip()
                for pair in [   ('<br />', '\n'), 
                                ('&amp;', '&'),
                                ('&lt;', '<'),
                                ('&gt;', '>'),
                                ('&quot;', '"'),
                                ('&#39;', "'")]:
                    body = body.replace(pair[0], pair[1])
                date_str = soup.find('script', text=re.compile("var d = new Date \(")).strip()
                timestamp = re.match('^var d = new Date \(([\d]{10}) \* 1000\);', date_str).group(1)
                sender = other_user
                recipient = self.username
                if message['class'].replace('preview', '').strip() == 'from_me':
                    recipient = other_user
                    sender = self.username
                message_list.append(Message(self.base_url + thread_url, 
                                            unicode(sender),
                                            unicode(recipient),
                                            timestamp,
                                            unicode(subject),
                                            body.decode('utf-8')))
            else:
                break  # control elements are also <li>'s in their html, so break when there's no more messages
        return message_list
    
    # http://stackoverflow.com/questions/1765848/remove-a-tag-using-beautifulsoup-but-keep-its-contents/1766002#1766002
    def _strip_tags(self, html, invalid_tags=['a', 'span', 'strong', 'div']):
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
    (options, args) = parser.parse_args()
    if not options.username:
        print "Please specify your OkCupid username with either '-u' or '--username'"
    if not options.password:
        print "Please specify your OkCupid password with either '-p' or '--password'"
    if not options.filename:
        print "Please specify the destination file with either '-f' or '--filename'"
    if options.username and options.password and options.filename:
        cf = CupidFetcher(options.username, options.password)
        cf.queue_threads()
        cf.dedupe_threads()
        cf.fetch_threads()
        cf.write_messages(options.filename)

if __name__ == '__main__':
    main()
    