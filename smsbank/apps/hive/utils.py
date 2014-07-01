# encoding: utf-8
import SocketServer as ss
import string
import re
from __builtin__ import Exception
import multiprocessing as mp
import json
from time import sleep
import random
import logging as log

from smsbank.apps.hive.services import (
    initialize_device,
    update_device_status,
    new_sms,
)

# from clint.textui import puts, colored

# Initialize local constants
port = 44444
host = "0.0.0.0"
devPassword = "123"
defaultRandomNumber = 4
killFlag = 0
log.basicConfig(format = u'%(filename)s[LINE:%(lineno)d]# %(levelname)-8s [%(asctime)s]  %(message)s', level = log.DEBUG)

class LocalAPIServer(mp.Process):
    host = "0.0.0.0"
    port = 13666
    queue = None
    sender = None
    

    def __init__(self, queue):
        mp.Process.__init__(self)
        #self.socket = socket
        self.queue = queue
        #self.sender = sender

    def run(self):
        locaServer = self.QueuedServer((self.host, self.port), self.LocalAPIListener)
        locaServer.queue = self.queue
        locaServer.serve_forever()

    class LocalAPIListener(ss.BaseRequestHandler):
        queue = None
        killFlag = 0

        def __init__(self, request, client_address, server):
            ss.BaseRequestHandler.__init__(self, request, client_address, server)
            #self.queue = queue

        def handle(self):
            log.debug('We got message on API Listener: ' + str(self.request[0]))
            try:
                realCommand = json.loads(self.request[0])
            finally:
                # TODO: Log This
                log.error("Unreadable JSON request: " + str(self.request[0]))
            
            if realCommand['command'] in ['USSD', 'SMS', 'TERMINATE', 'RESTART']:
                # TODO: add sanity checks on commands
                if realCommand['command'] in ['USSD', 'SMS']:
                    realCommand['seed'] = random.randrange(200000, 299999)
                log.debug('Put command on queue: ' + str(realCommand))
                self.queue.put(realCommand)
                socket = self.request[1]
                socket.sendto(self.respond(realCommand), self.client_address)
                if realCommand['command'] in ['TERMINATE', 'RESTART']:
                    log.info("Shutting down API Listener")
                    self.killFlag = 1
                    
            else:
                log.warning('Unsupported command: ' + str(self.request[0]))
                socket.sendto("400 UNSUPPORTED COMMAND", self.client_address)

            """
            id
            command
            data ->
                SMS -> recipient, message
                USSD -> code
                RAW -> command (debug command)

            """
        def respond(self, command):
            return "OK"

            """ def getQueue(self, queue):
            self.queue = queue
            """
            
    class QueuedServer(ss.UDPServer):
        queue = None
        # TODO: overload server_forever() so it can be shut down
        def finish_request(self, request, client_address):
            self.RequestHandlerClass.queue = self.queue
            ss.UDPServer.finish_request(self, request, client_address)
            
        def serve_forever(self, poll_interval=0.5):
            """Handle one request at a time until shutdown.
    
            Polls for shutdown every poll_interval seconds. Ignores
            self.timeout. If you need to do periodic tasks, do them in
            another thread.
            """
            #self.__is_shut_down.clear()
            try:
                while not self.RequestHandlerClass.killFlag:
                    # XXX: Consider using another file descriptor or
                    # connecting to the socket to wake this up instead of
                    # polling. Polling reduces our responsiveness to a
                    # shutdown request and wastes cpu at all other times.
                    r, w, e = _eintr_retry(select.select, [self], [], [],
                                           poll_interval)
                    if self in r:
                        self._handle_request_noblock()
            finally:
                pass



class GoipUDPListener(ss.BaseRequestHandler):
    """
    This class works similar to the TCP handler class, except that
    self.request consists of a pair of data and client socket, and since
    there is no connection the client address must be given explicitly
    when sending data back via sendto().
    """
    devPool = {}
    senderQueue = mp.Queue()
    sender = None
    seedDic = mp.Manager().dict()
    killFlag = mp.Value('h', 0)

    def handle(self):
        sock = self.request[1]
        log.info("Received request: " + str(self.request[0]))
        query = self.parseRequest(self.request[0])
        if query != False:
            log.debug('Current query:' + str(query))
            log.debug('Current device pool :' + str(self.devPool))
            self.queryDevice(query['id'], query['pass'])
            queue = self.devPool[query['id']]['queue']
            queue.put(query)
        else:
            log.info("Unsupported command") # TODO: Log ALL unsupported commands to file
        log.debug("Process count: " + str(len(self.devPool)))


        if not self.senderQueue.empty():
            while not self.senderQueue.empty():
                data = self.senderQueue.get()
                sock.sendto(data['data'], data['host'])

        while not apiQueue.empty():
            outbound = apiQueue.get()
            if self.deviceActive(outbound['id']):
                print self.devPool[query['id']]['queue']
                outQueue = self.devPool[query['id']]['queue']
                outQueue.put(outbound)

        
    def terminateProcess(self):
        log.info('Shutdown initiated')
        self.killFlag.value = 1
        log.debug('Waiting for child processes to finish')
        sleep(5)
        for process in self.devPool:
            process['device'].join()
            if process['device'].is_alive():
                log.warn("Device worker is not closed! Trying to terminate")
                process['device'].terminate()
            if process['device'].is_alive():
                log.error("Device worker is stall and cannot be terminated")
            

    def queryDevice(self, devId, passw, auth=0):
        # authState = True
        authState = self.authDevice(devId, passw, self.client_address)
        if (not self.deviceActive(devId) and authState):
            queue = mp.Queue()
            device = deviceWorker(devId, self.client_address, queue, self.senderQueue, self.seedDic, self.killFlag)
            device.daemon = True
            device.start()
            self.devPool[devId] = {}
            self.devPool[devId]['device'] = device
            self.devPool[devId]['queue'] = queue
            self.devPool[devId]['address'] = self.client_address
        return self.devPool[devId]['device']

    def deviceActive(self, devId):
        if str(devId) in self.devPool:
            return True
        return False

    def getCommand(self, data):
        # NB: may blow up when processing dubious data
        newdata = re.search('^([a-zA-Z]+)', data)
        if newdata == None:
            return False
        return newdata.group(0)

    def parseRequest(self, data):
        command = {}
        command['command'] = self.getCommand(data)
        log.debug("Command implied by query: " + str(command['command']))
        if command['command'] in ['req', 'CGATT', 'CELLINFO', 'STATE', 'EXPIRY', 'RECEIVE', 'DELIVER']:
            reqdata = string.split(data[0:-1], ";")
            if len(reqdata) < 2:
                log.warn("Inconsistent data received. Parse failed.")
                return False
            for comBun in reqdata:
                if string.find(comBun, ":") != -1:
                    tmp = string.split(comBun,":")
                    if tmp[0] == 'password':    #correcting for Chinese protocol unevenness, when sometimes its 'pass' and sometimes its 'password'
                        tmp[0] = 'pass'
                    command[tmp[0]] = tmp[1]
                else:
                    log.error("Invalid data format! Data: " + str(comBun))
            if command['command'] == 'RECEIVE':
                msgIndex = data.find('msg:') + 4
                command['msg'] = data[msgIndex:]
        elif command['command'] in ['MSG', 'USSD', 'PASSWORD', 'SEND', 'WAIT', 'DONE', 'OK']:
            command['seed'] = data.split()[1]
            command['data'] = data
            if 'id' not in command:
                for device in self.devPool: #iterating over a dictionary, so we are getting KEYS
                    if self.devPool[device]['address'] == self.client_address:
                        command['id'] = device
                        idFound = True
                        command['pass'] = devPassword
                        # TODO: check if seed correspond with source host
                if not idFound:
                    log.error('Cannot identify device with command. Command without id came from unregistered device!')
                    log.error("Command we got: " + str(data))
                    return False
        else:
            log.error("Received command is unsupported")
            return False
        return command

    def authDevice(self, devid, password, host):
        '''
        Must check existence of such device id in DB and check password afterwards
        '''
        if password == devPassword:
            try:
                initialize_device(devid, host[0], host[1])
            except Exception as e:
                print 'Database exception: %s' % e
                return False

            return True

        return False

class deviceWorker(mp.Process):
    devid = None
    expire = int(20)
    cgatt = None
    imei = None
    num = None
    voipStatus = None
    voipState = None
    imsi = None
    iccid = None
    cells = None
    gsm = None
    signal = None
    expiryTime = None
    killFlag = None
    password = None

    msgActive = {}
    msgCount = 0
    msgSeeds = None

    host = None
    port = None

    queueIn = None
    queueOut = None

    def __init__(self, devid, host, queue, outQueue, seedArray, killFlagRef):
        mp.Process.__init__(self)
        self.devid = devid
        self.queueIn = queue
        self.host = host
        self.queueOut = outQueue
        self.msgSeeds = seedArray
        self.killFlag = killFlagRef
        self.msgActive['goipId'] = {}

        self.state = {'new':        1,
                      'auth':       2,
                      'send':       3,
                      'waiting':    4,
                      'sent':       5,
                      'done':       6,
                      'delivered':  7,
                      }
        #print host
        #print "mein Konstruktor: " + str(self.devid)
        #self.newRun()



    def run(self):
        '''
        Main worker function
        '''
        while not self.killFlag.value:
            if not self.queueIn.empty():
                self.processRequest()
            else:
                sleep(1)
                log.debug("Nothing to do. Sleeping 1.")
        log.debug("killFlag is now: " + str(self.killFlag.value))
        log.info('deviceWorker daemon instance is stopping!')

    def processRequest(self):
        response = {}
        response['host'] = self.host
        while not self.queueIn.empty():
            data = self.queueIn.get()
            if data['command'] in ['req', 'CGATT', 'CELLINFO', 'STATE', 'EXPIRY']:
                response['data'] = self.processServiceRequest(data)
            elif data['command'] in ['MSG', 'USSD', 'PASSWORD', 'SEND', 'WAIT', 'DONE', 'OK', 'SMS', 'USSD', 'DELIVER']:
                response['data'] = self.processOutbound(data)
            elif data['command'] in ['RECEIVE', ]:
                response['data'] = self.processInboundSMS(data)
            else:
                log.error("Unrecognized command")
                raise Exception
                return
            if response['data'] != "":
                log.info("Sending response: " + str(response))
                self.queueOut.put(response)

    def processOutbound(self, data):
        #implement actual sms tracking
        log.debug("Outbound SMS processing. Data: " + str(data))
        if data['command'] == 'SMS':
            self.msgCount += 1
            self.msgActive[data['seed']] = {}
            self.msgActive[data['seed']]['locId'] = self.msgCount
            self.msgIdIntersectionCheck(data['seed'])
            message = self.msgActive[data['seed']]
            self.msgSeeds[data['seed']] = self.devid
            log.info("New outbound SMS! Seed " + str(data['seed']))
        response = ""
        if data['command'] == 'DELIVER':
            return "DELIVER OK" #not implemented
        if 'seed' in data:
            data['seed'] = int(data['seed'])

        if not (data['seed'] in self.msgActive) or data['command'] == "DELIVER":
            return
        elif data['seed'] in self.msgActive:
            message = self.msgActive[data['seed']]

        if data['command'] == 'SMS':
            message['state'] = self.state['new']
            message['message'] = data['data']['message']
            message['recipient'] = data['data']['recipient']
            response = " ".join(["MSG", str(data['seed']), str(len(data['data']['message'])), str(data['data']['message'])])
        elif data['command'] == 'PASSWORD':
            message['state'] = self.state['auth']
            response = " ".join([data['command'], str(data['seed']), devPassword])
        elif data['command'] == 'SEND':
            message['state'] = self.state['send']
            response = " ".join([data['command'], str(data['seed']), str(message['locId']), message['recipient']])
        elif data['command'] == 'WAIT':
            message['state'] = self.state['waiting']
        elif data['command'] == 'OK':
            goipId = data['data'].split()[3]
            log.debug(" ".join("Message with seed ", message['seed'], "got following GoIP id: ", goipId))
            self.msgActive['goipId'][goipId] = message
            message['state'] = self.state['sent']
            response = " ".join(["DONE", str(data['seed'])])
        elif data['command'] == 'DONE':
            log.info("Message sent. Seed: " + str(data['seed']))
            message['state'] = self.state['sent']
            del self.msgSeeds[data['seed']]
            del self.msgActive[data['seed']]
            # Save outbound sms to database
            try:
                new_sms(
                    message['recipient'],
                    message['message'],
                    False,
                    self.devid
                )
            except Exception as e:
                print 'Database exception: %s' % e

        elif data['command'] == 'DELIVER':
            # TODO: implement DB write on delivery
            if data['sms_no'] in self.msgActive['goipId']:
                #message delivered -> write to db
                log.info("Got delivery report!")
                del self.msgActive['goipId'][data['sms_no']]
                log.debug(" ".join("Cleared info concerning active message no.", str(data['sms_no']), "Now active messages are:", str(self.msgActive) ))
                response = data['command'] + " " + str(data[data['command']]) + " OK"
        else:
            log.error("Unrecognized command for outbound SMS!")
            raise Exception



        # TODO: fix UnboundLocalError: local variable 'response' referenced before assignment
        return response


    def msgIdIntersectionCheck(self, msgId):
        while msgId in self.msgActive:
            msgId = random.randrange(2000000, 2999999)

    def processInboundSMS(self, data):
        """
        RECEIVE:1403245796;id:1;password:123;srcnum:+79520999249;msg:MSGBODY
        """
        # TODO: log this!
        log.info("Got message. Presumably. Raw data:" + str(data))
        response = " ".join(['RECEIVE', data['RECEIVE'], 'OK'])
        print response

        # Save inbound sms to database
        try:
            new_sms(
                data['srcnum'],
                data['msg'],
                True,
                self.devid
            )
        except Exception as e:
            print 'Database exception: %s' % e

        return response


    def processServiceRequest(self, data):
        if data['command'] == 'req':
            response = 'reg:' + str(data['req']) +';status:200'
            # Update device status
            try:
                update_device_status(self.devid, data['gsm_status'])
            except Exception as e:
                print 'Database exception: %s' % e
            finally:
                return response
            
            return response
        #if not regActive(commandData["id"]):
        #    return

        if data['command'] == 'CGATT':
            self.cgatt = data['cgatt']
        elif data['command'] == 'CELLINFO':
            cells = string.split(data['info'].strip('"'), ",")
            self.cells = cells
        elif data['command'] == 'STATE':
            None
        elif data['command'] == 'EXPIRY':
            self.expire = data['exp']
        else:
            raise Exception
            return
        response = data['command'] + " " + str(data[data['command']]) + " OK"
        return response


# Initialize superglobals
apiQueue = mp.Queue()


if __name__ == "__main__":
    pass
    '''
    HOST, PORT = "0.0.0.0", 44444
    senderQueue = mp.Queue()
    #sender  = mp.Process(target=GoipUDPSender, args=(senderQueue,))
    #sender = GoipUDPSender(senderQueue,)
    #sender.start()
    #senderSocket = None

    apiQueue = mp.Queue()
    apiHandle = LocalAPIServer(apiQueue,)
    apiHandle.start()
    manager = mp.Manager()
    seedDic = manager.dict()
    #listSock = mp.Value(typecode_or_type)

    #sleep(5)

    server = ss.UDPServer((HOST, PORT), GoipUDPListener)
    server.serve_forever()
    '''
