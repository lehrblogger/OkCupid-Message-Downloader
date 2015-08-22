from distutils.core import setup
setup(
  name = 'okcmd',
  packages = ['okcmd'], # this must be the same as the name above
  scripts = ['scripts/okcmd'],
  install_requires = ['beautifulsoup4>=4.4.0'],
  version = '0.3',
  description = 'A simple Python script for downloading your sent and received OkCupid messages.',
  author = 'Steven Lehrburger',
  author_email = 'lehrburger@gmail.com',
  url = 'https://github.com/lehrblogger/OkCupid-Message-Downloader',
  download_url = 'https://github.com/lehrblogger/OkCupid-Message-Downloader/tarball/0.1',
  keywords = ['okcupid', 'okc', 'okcmd', 'dating', 'archive', 'message', 'download', 'backup'],
  classifiers = [],
)

