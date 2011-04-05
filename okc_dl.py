from datetime import datetime
import urllib, urllib2
from optparse import OptionParser
import time
import re
from BeautifulSoup import BeautifulSoup, NavigableString

class CupidFetcher:
    base_url = 'http://www.okcupid.com'

    def __init__(self, username, password):
        self.username = username
        self.conversation_urls = []
        opener = urllib2.build_opener(urllib2.HTTPCookieProcessor())
        urllib2.install_opener(opener)
        params = urllib.urlencode(dict(username=username, password=password))
        f = opener.open(self.base_url + '/login', params)
        f.close()
    
    def safely_soupify(self, f):
        f = f.partition("function autocoreError")[0] + '</body></html>' # wtf okc with the weirdly encoded "</scr' + 'ipt>'"-type statements in your javascript
        return(BeautifulSoup(f))
    
    def queue_conversations(self):
        self.conversation_urls = []
        for folder in range(1,4):
            page = 0;
            while (True):
                url = self.base_url + '/messages?folder=' + str(folder) + '&low=' + str((page * 30) + 1)
                f = urllib2.urlopen(url).read()
                soup = self.safely_soupify(f)
                
                conversations = [
                    li.find('p')['onclick'].strip("\"window.location='").strip("';\"")
                    for li in soup.find('ul', {'id': 'messages'}).findAll('li')
                ]
            
                if len(conversations) == 0:
                    break
                else:
                    self.conversation_urls.extend(conversations)
                    page = page + 1
                
    def fetch_conversations(self, file_name):
        # self.conversation_urls = ['/messages?readmsg=true&threadid=8605121069354857629&folder=2']
        f = open(file_name, 'w')
        for conversation_url in self.conversation_urls:
            messages = self.fetch_conversation(conversation_url)
            for message in messages:
                f.write('URL: ' + message['URL'] + '\n')
                f.write('From: ' + message['From'].encode('utf-8') + '\n')
                f.write('To: ' + message['To'].encode('utf-8') + '\n')
                f.write('Date: ' + message['Date'] + '\n')
                f.write('Subject: ' + message['Subject'].encode('utf-8') + '\n')
                f.write('Content-Length: ' + str(len(message['Content'])) + '\n\n')
                f.write(message['Content'].encode('utf-8') + '\n\n\n')
        f.close()
    
    def fetch_conversation(self, conversation_url):
        message_list = []
        print self.base_url + conversation_url
        f = urllib2.urlopen(self.base_url + conversation_url).read()
        soup = self.safely_soupify(f)
        try:
            subject = unicode(soup.find('strong', {'id': 'message_heading'}).contents[0])
        except AttributeError:
            subject = ''
        try:
            other_user = unicode(soup.find('ul', {'id': 'thread'}).find('a', 'buddyname ').contents[0])
        except AttributeError:
            other_user = soup.find('ul', {'id': 'thread'}).find('p', 'signature').contents[0].strip('Message from ')
        for message in soup.find('ul', {'id': 'thread'}).findAll('li'):
            body_contents = message.find('div', 'message_body')
            if body_contents:
                
                def strip_tags(html, invalid_tags):  # http://stackoverflow.com/questions/1765848/remove-a-tag-using-beautifulsoup-but-keep-its-contents/1766002#1766002
                    soup = BeautifulSoup(html)
                    for tag in soup.findAll(True):
                        if tag.name in invalid_tags:
                            s = ""
                            for c in tag.contents:
                                if type(c) != NavigableString:
                                    c = strip_tags(unicode(c), invalid_tags)
                                s += unicode(c).strip()
                            tag.replaceWith(s)
                    return soup

                body = strip_tags(unicode(body_contents), ['a', 'span', 'strong', 'div'])
                body = unicode(body).replace('<br />', '\n')
                date_str = soup.find('script', text=re.compile("var d = new Date \(")).strip()
                timestamp = re.match('^var d = new Date \(([\d]{10}) \* 1000\);', date_str).group(1)
                send_date = datetime.fromtimestamp(int(timestamp))
                sender = other_user
                receiver = self.username
                if message['class'].replace('preview', '').strip() == 'from_me':
                    receiver = other_user
                    sender = self.username
                message_list.append({
                    'URL': self.base_url + conversation_url,
                    'From': sender,
                    'To': receiver,
                    'Date': send_date.strftime('%c -0500'),
                    'Subject': subject,
                    'Content': body
                })
            else:
                break
        return message_list

def main():
    parser = OptionParser()
    parser.add_option("-u", "--username", dest="username",
                      help="your OkCupid username")
    parser.add_option("-p", "--password", dest="password",
                      help="your OkCupid password")
    parser.add_option("-f", "--filename", dest="filename",
                    help="the file to which you want to write the data")
    (options, args) = parser.parse_args()
    cf = CupidFetcher(options.username, options.password)
    cf.queue_conversations()
    cf.fetch_conversations(options.filename)

if __name__ == '__main__':
    main()











