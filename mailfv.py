#!/usr/bin/env python26
import imaplib2, email, os, sys, logging, threading, signal, chardet, icu
import email.parser
import email.header
import Daemonize
import logging.handlers
from ConfigParser import SafeConfigParser
from optparse import OptionParser

class stdErrWriter(object):

    def __init__(self, logger, logLevel):
        self.logLevel = logLevel
        self.logger = logger

    def write(self, buf):
        print buf
        #self.logger.log(self.logLevel, buf)

class mailFVAT(threading.Thread):

    lockEvent = threading.Event()
    killNow = False
    M = None
    config = SafeConfigParser()
    timeout = 29
    filters = []

    def __init__(self):
        threading.Thread.__init__(self)

        # setup logger
        self.logger = logging.getLogger('mailFVAT')
        self.logger.setLevel(logging.DEBUG)
        handler = logging.handlers.RotatingFileHandler('/tmp/mailfv.log', maxBytes=1048576, backupCount=10)
        handler.setLevel(logging.DEBUG)
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        handler.setFormatter(formatter)
        self.logger.addHandler(handler)

        # create logger for errors
        errLogger = logging.getLogger('stdErr')
        errLogger.setLevel(logging.ERROR)
        errHandler = logging.handlers.RotatingFileHandler('/tmp/mailfv_error.log', maxBytes=1048576, backupCount=10)
        errHandler.setLevel(logging.ERROR)
        errFormatter = logging.Formatter('%(asctime)s - %(message)s')
        errHandler.setFormatter(errFormatter)
        errLogger.addHandler(errHandler)
        # redirect stderr
        sys.stderr = stdErrWriter(errLogger, logging.ERROR)

        self.M = imaplib2.IMAP4_SSL('imap.gmail.com')

    def run(self):
        self.logger.info('Running')
        self.login(self.config.get('mail', 'username'), self.config.get('mail', 'password'))
        self.gotoFolder('Inbox')
        existingUIDs = self.search('ALL')
        fetchUIDs = self.filterMessages(existingUIDs)
        self.fetchFVAT(fetchUIDs)
        while not self.killNow:
            newUIDs = self.idle(existingUIDs)
            existingUIDs = newUIDs
        self.logout()

    def idle(self, knownUIDs):
        self.logger.debug('Starting IDLE command')

        self.lockEvent.clear()
        self.callbackSuccess = False

        def imapIDLECallback((data, cb_arg, error)):
            self.logger.info('Server state changed')
            self.callbackSuccess = data[1][0] == 'IDLE terminated (Success)'
            self.lockEvent.set()

        self.M.idle(timeout=60*self.timeout, callback=imapIDLECallback)

        self.logger.info('Waiting for IDLE server reply')
        self.lockEvent.wait()
        if not self.killNow:
            if not self.callbackSuccess:
                self.logger.error('Server error during IDLE request')

            isTimeout = self.M.response('IDLE')
            if isTimeout[1][0] != 'TIMEOUT':
                newUIDs = self.search('ALL')
                unknownUIDs = [uid for uid in newUIDs if uid not in knownUIDs]
                uidOfInterest = self.filterMessages(unknownUIDs)
                self.fetchFVAT(uidOfInterest)
                return newUIDs
            else:
                self.logger.info('IDLE request timeout occured')
        return []

    def exit(self):
        self.logger.info('Exitting')
        self.killNow = True
        self.lockEvent.set()

    def configure(self, configFile):
        self.logger.debug('Reading config file from {0}'.format(configFile))
        configs = self.config.read(configFile)
        self.prepareFilters()
        self.createDirectoryIfNotExistent(self.config.get('mail', 'directory'))

    def prepareFilters(self):

        def createFilterFunction(criteria):
            return lambda values: reduce(lambda x, y: x and y[1].find(filter(lambda crit: crit[0] == y[0], criteria)[0][1]) >= 0, values, True)

        providers = self.config.sections()
        providers.remove('mail')
        for provider in providers:
            criteria = [('From', self.config.get(provider, 'mail')), ('Subject', self.config.get(provider, 'title'))]
            self.logger.info('Configured filter for {0} with preferences {1}'.format(provider, criteria))
            self.filters.append((provider, createFilterFunction(criteria)))

    def filterMessages(self, uids):
        self.logger.debug('Currently there are {0:d} messages {1}'.format(len(uids), uids))
        uidOfInterest = []
        for uid in uids:
            filterValues = self.extractHeaderTuples(uid)
            for provider, filterFunction in self.filters:
                if filterFunction(filterValues):
                    uidOfInterest.append((provider, uid))
        self.logger.info('Found {0:d} messages for download {1}'.format(len(uidOfInterest), uidOfInterest))
        return uidOfInterest

    def extractHeaderTuples(self, uid):
        self.logger.info('Getting header information for {0:d}'.format(uid))
        parser = email.parser.HeaderParser()
        rc, data = self.M.uid('FETCH', uid, '(BODY.PEEK[HEADER.FIELDS (FROM SUBJECT)] UID)')
        headers = parser.parsestr(data[0][1])
        filterValues = []
        for header, value in headers.items():
            decodedElements = email.header.decode_header(value)
            decodedValueList = []
            for element, charset in decodedElements:
                if charset == None:
                    decodedValueList.append(element)
                else:
                    decodedValueList.append(element.decode(charset).encode('utf-8'))
            filterValues.append((header, ' '.join(decodedValueList)))
        self.logger.debug('Extracted headers for uid {0:d} - {1}'.format(uid, filterValues))
        return filterValues

    def login(self, username, password):
        rc, response = self.M.login(username, password)
        self.logger.info('Logged in {0} to imap.google.com'.format(username))
        return rc, response

    def gotoFolder(self, folder='Inbox'):
        rc, count = self.M.select(folder)
        self.logger.info('Changed folder to {0}'.format(folder))
        return rc, count

    def fetchFVAT(self, uids):
        for provider, uid in uids:
            self.getAttachments(uid, self.config.get(provider, 'folder'))
            self.addLabels(uid, self.config.get(provider, 'label'))

    def addLabels(self, uid, label):
        rc, data = self.M.uid('STORE', uid, '+X-GM-LABELS', label)
        self.logger.info('Added label {0} for uid {1:d}'.format(label, uid))

    def convert(self, data, outputCoding='utf-8'):
        coding = icu.CharsetDetector(data).detect().getName()
        print coding
        if outputCoding.upper() != coding.upper():
            data = unicode(data, coding, "replace").encode(outputCoding)
        return data

    def getAttachments(self, uid, folder):
        directory = os.path.join(self.config.get('mail', 'directory'), folder)
        self.logger.info('Fetching attachments for {0:d} to {1}'.format(uid, directory))
        self.createDirectoryIfNotExistent(directory)
        rc, data = self.M.uid('FETCH', uid, '(RFC822)')
        msg = email.message_from_string(data[0][1])
        for part in msg.walk():
            if part.has_key("Content-Disposition") and part.get("Content-Disposition").find("attachment") >= 0:
                filename = part.get_filename()
                attachment = part.get_payload(decode=True)
                attachment_file = open(os.path.join(directory, filename), 'w')
                attachment_file.write(self.convert(attachment, 'utf-8'))
                attachment_file.close()
        self.M.uid('STORE', uid, '+FLAGS', '\SEEN')

    def search(self, criteria='ALL'):
        rc, uids = self.M.uid('SEARCH', None, '({0})'.format(criteria))
        uidList = uids[0].split()
        if rc != 'OK':
            raise Error, 'massive error'
        try:
            return [int(uid) for uid in uidList]
        except ValueError:
            raise Error, "received unparsable response."

    def createDirectoryIfNotExistent(self, directory):
        if not os.path.exists(directory):
            self.logger.info('Creating directory {0}'.format(directory))
            os.makedirs(directory)

    def logout(self):
        self.logger.debug('Closing connection to imap.google.com')
        self.M.close()
        self.M.logout()

if __name__ == '__main__':

    parser = OptionParser()
    parser.add_option("-c", "--config", default='/root/.mailfv', dest="filename", help="location of config file", metavar="CONFIG")
    options, args = parser.parse_args()
    retCode = 0

    #waitDaemon = threading.Event()
    #waitDaemon.clear()
    #retCode = Daemonize.createDaemon(022, '/', 1024, waitDaemon)
    #waitDaemon.wait()

    def handler(signum, frame):
        gmail.exit()
        gmail.join()
        sys.exit(retCode)

    signal.signal(signal.SIGINT, handler)
    signal.signal(signal.SIGTERM, handler)

    gmail = mailFVAT()
    gmail.configure(options.filename)
    gmail.start()

    signal.pause()
else:
    print 'This file is not meant for inclusion'
    sys.exit(1)
