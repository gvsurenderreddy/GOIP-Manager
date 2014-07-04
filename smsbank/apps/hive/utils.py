# encoding: utf-8
import string
import re
from __builtin__ import Exception
import multiprocessing as mp
import json
from time import sleep
import random
import logging as log
import socket

from django.db import connection
import redis

# from smsbank.apps.hive.services import (
#     initialize_device,
#     new_sms,
# )
from smsbank.apps.hive.tasks import (
    create_sms,
    auth_device
)

# from clint.textui import puts, colored

# Initialize local constants
port = 44444
host = "0.0.0.0"
devPassword = "123"
defaultRandomNumber = 4
killFlag = 0
log.basicConfig(
    format=(
        u'%(filename)s %(process)d [LINE:%(lineno)d]# %(levelname)-8s '
        u'[%(asctime)s] %(message)s'
    ),
    level=log.INFO
)


class LocalAPIServer(mp.Process):
    host = "0.0.0.0"
    port = 13666
    queue = None
    sender = None

    def __init__(self, queue):
        mp.Process.__init__(self)
        self.queue = queue

    def run(self):
        log.basicConfig(
            format=(
                u'%(filename)s %(process)d [LINE:%(lineno)d]# %(levelname)-8s '
                u'[%(asctime)s]  %(message)s'
            ),
            level=log.INFO
        )
        localServer = self.LocalAPIListener((self.host, self.port), self.queue)
        localServer.serve()
        log.info("Local API server process is shutting down")

    class LocalAPIListener:
        queue = None
        killFlag = 0
        sock = None
        address = None
        client_address = None
        request = None

        def __init__(self, address, queue):
            self.address = address
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.sock.bind(address)
            self.queue = queue

        def serve(self):
            while not self.killFlag:
                data, addr = self.sock.recvfrom(4096)
                self.request = data
                self.client_address = addr
                self.handle()
                sleep(0.5)

        def handle(self):
            log.debug('We got message on API Listener: ' + str(self.request))
            try:
                realCommand = json.loads(self.request)
            except:
                # TODO: Log This
                log.error("Unreadable JSON request: " + str(self.request))
            socket = self.sock
            if realCommand['command'] in [
                'USSD',
                'SMS',
                'TERMINATE',
                'RESTART'
            ]:
                # TODO: add sanity checks on commands
                if realCommand['command'] in ['USSD', 'SMS']:
                    realCommand['seed'] = random.randrange(200000, 299999)
                log.debug('Put command on queue: ' + str(realCommand))
                if realCommand['command'] in ['TERMINATE', 'RESTART']:
                    log.info("Shutting down API Listener")
                    self.killFlag = 1
                self.queue.put(realCommand)

                socket.sendto(self.respond(realCommand), self.client_address)

            else:
                log.warning('Unsupported command: ' + str(self.request))
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


class GoipUDPListener:
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
    client_address = None
    address = None
    sock = None

    def __init__(self, address):
        self.address = address
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind(address)

    def serve(self):
        while not self.killFlag.value:
            data, addr = self.sock.recvfrom(4096)
            self.request = data
            self.client_address = addr
            self.handle()
            sleep(0.1)

    def handle(self):
        sock = self.sock
        log.info("Received request: " + str(self.request))
        query = self.parseRequest(self.request)
        if query is not False:
            log.debug('Current query:' + str(query))
            log.debug('Current device pool :' + str(self.devPool))
            self.queryDevice(query['id'], query['pass'])
            queue = self.devPool[query['id']]['queue']
            queue.put(query)
        else:
            # TODO: Log ALL unsupported commands to file
            log.info("Unsupported command")
        log.debug("Process count: " + str(len(self.devPool)))

        if not self.senderQueue.empty():
            while not self.senderQueue.empty():
                data = self.senderQueue.get()
                sock.sendto(data['data'], data['host'])

        while not apiQueue.empty():
            outbound = apiQueue.get()
            if outbound['command'] == 'TERMINATE':
                self.terminateProcess()
            elif self.deviceActive(outbound['id']):
                print self.devPool[query['id']]['queue']
                outQueue = self.devPool[query['id']]['queue']
                outQueue.put(outbound)

    def terminateProcess(self):
        log.info('Shutdown initiated')
        self.killFlag.value = 1
        log.info('Waiting for child processes to finish')
        sleep(5)
        for process in self.devPool:
            try:
                self.devPool[process]['device'].join()
                if self.devPool[process]['device'].is_alive():
                    log.warn(
                        "Device worker is not closed! Trying to terminate"
                    )
                    self.devPool[process]['device'].terminate()
                if self.devPool[process]['device'].is_alive():
                    log.error(
                        "Device worker is stall and cannot be terminated"
                    )
            except:
                log.critical("Something went wrong! Can't stop process!")
                log.info(str(self.devPool))
                log.info(str(self.devPool[process]))

    def queryDevice(self, devId, passw, auth=0):
        # authState = True
        authState = self.authDevice(devId, passw, self.client_address)
        if (not self.deviceActive(devId) and authState):
            # Close parent DB connection,
            # so that children won't inherit it when forking
            connection.close()

            # Initialize device worker
            queue = mp.Queue()
            device = deviceWorker(
                devId,
                self.client_address,
                queue,
                self.senderQueue,
                self.seedDic,
                self.killFlag
            )
            device.daemon = True

            # Launch device worker and update device pool
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
        if newdata is None:
            return False
        return newdata.group(0)

    def parseRequest(self, data):
        command = {}
        command['command'] = self.getCommand(data)
        log.debug("Command implied by query: " + str(command['command']))
        if command['command'] in [
            'req',
            'CGATT',
            'CELLINFO',
            'STATE',
            'EXPIRY',
            'RECEIVE',
            'DELIVER'
        ]:
            reqdata = string.split(data[0:-1], ";")
            if len(reqdata) < 2:
                log.warn("Inconsistent data received. Parse failed.")
                return False
            for comBun in reqdata:
                if string.find(comBun, ":") != -1:
                    tmp = string.split(comBun, ":")
                    # correcting for Chinese protocol unevenness,
                    # when sometimes its 'pass' and sometimes its 'password'
                    if tmp[0] == 'password':
                        tmp[0] = 'pass'
                    command[tmp[0]] = tmp[1]
                else:
                    log.error("Invalid data format! Data: " + str(comBun))
            if command['command'] == 'RECEIVE':
                msgIndex = data.find('msg:') + 4
                command['msg'] = data[msgIndex:]
                # device Id - connection check-override
                devId = self.getDeviceIdByConnection(command)
                if not devId:
                    log.warn("Message from unregistered device! Skipping.")
                elif devId != command['id']:
                    log.warn("Conflicting device id in message! Overriding.")
                    command['id'] = devId

        elif command['command'] in [
            'MSG',
            'USSD',
            'PASSWORD',
            'SEND',
            'WAIT',
            'DONE',
            'OK'
        ]:
            command['seed'] = data.split()[1]
            command['data'] = data
            if 'id' not in command:
                command['id'] = self.getDeviceIdByConnection(command)
                if not command['id']:
                    log.error("Unable to get device ID")
                    return False
        else:
            log.error("Received command is unsupported")
            return False
        return command

    def getDeviceIdByConnection(self, command):
        # iterating over a dictionary, so we are getting KEYS
        for device in self.devPool:
            if self.devPool[device]['address'] == self.client_address:
                command['id'] = device
                idFound = True
                command['pass'] = devPassword
                return device
                # TODO: check if seed correspond with source host
        if not idFound:
            log.error(
                'Cannot identify device with command.'
                'Command without id came from unregistered device!'
            )
            log.error("Command we got: " + str(command['data']))
            return False

    def authDevice(self, devid, password, host):
        '''
        Must check existence of such device id in DB
        and check password afterwards
        '''
        if password == devPassword:
            auth_device.delay(devid, host[0], host[1])

            '''
            try:
                initialize_device(devid, host[0], host[1])
            except Exception as e:
                log.error('Database exception when authorizing: %s' % e)
                return False
            '''

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
            if data['command'] in [
                'req',
                'CGATT',
                'CELLINFO',
                'STATE',
                'EXPIRY'
            ]:
                response['data'] = self.processServiceRequest(data)
            elif data['command'] in [
                'MSG',
                'USSD',
                'PASSWORD',
                'SEND',
                'WAIT',
                'DONE',
                'OK',
                'SMS',
                'USSD',
                'DELIVER'
            ]:
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
        # TODO: implement actual sms tracking
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
            return "DELIVER OK"  # NB: not implemented
        if 'seed' in data:
            data['seed'] = int(data['seed'])

        if not (
            (data['seed'] in self.msgActive) or
            data['command'] == "DELIVER"
        ):
            return
        elif data['seed'] in self.msgActive:
            message = self.msgActive[data['seed']]

        if data['command'] == 'SMS':
            message['state'] = self.state['new']
            message['message'] = data['data']['message']
            message['recipient'] = data['data']['recipient']
            response = " ".join([
                "MSG",
                str(data['seed']),
                str(len(data['data']['message'])),
                str(data['data']['message'])
            ])
        elif data['command'] == 'PASSWORD':
            message['state'] = self.state['auth']
            response = " ".join([
                data['command'],
                str(data['seed']),
                devPassword
            ])
        elif data['command'] == 'SEND':
            message['state'] = self.state['send']
            response = " ".join(
                [data['command'],
                 str(data['seed']),
                 str(message['locId']),
                 message['recipient']]
            )
        elif data['command'] == 'WAIT':
            message['state'] = self.state['waiting']
        elif data['command'] == 'OK':
            goipId = data['data'].split()[3]
            log.info(" ".join(
                "Message with seed ",
                message['seed'],
                "got following GoIP id: ",
                goipId
            ))
            self.msgActive['goipId'][goipId] = message
            message['state'] = self.state['sent']
            response = " ".join(["DONE", str(data['seed'])])
        elif data['command'] == 'DONE':
            log.info("Message sent. Seed: " + str(data['seed']))
            message['state'] = self.state['sent']
            del self.msgSeeds[data['seed']]
            del self.msgActive[data['seed']]
            # Save outbound sms to database
            create_sms(
                message['recipient'],
                message['message'],
                False,
                self.devid
            )

            '''
            try:
                # TODO: check for racing condition / use REDIS
                new_sms(
                    message['recipient'],
                    message['message'],
                    False,
                    self.devid
                )
            except Exception as e:
                log.error(
                    'Database exception when saving outbound SMS: %s' % e
                )
            '''

        elif data['command'] == 'DELIVER':
            # TODO: implement DB write on delivery
            if data['sms_no'] in self.msgActive['goipId']:
                # message delivered -> write to db
                log.info("Got delivery report!")
                del self.msgActive['goipId'][data['sms_no']]
                log.info(" ".join(
                    "Cleared info concerning active message no.",
                    str(data['sms_no']),
                    "Now active messages are:",
                    str(self.msgActive)
                ))
                response = (
                    data['command'] + " " + str(data[data['command']]) + " OK"
                )

        else:
            log.error("Unrecognized command for outbound SMS!")
            raise Exception

        # TODO: fix UnboundLocalError: local variable 'response' referenced
        # before assignment
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
        create_sms.delay(
            data['srcnum'],
            data['msg'],
            True,
            self.devid
        )
        '''
        try:
            # TODO: check for racing condition / use REDIS
            new_sms(
                data['srcnum'],
                data['msg'],
                True,
                self.devid
            )
        except Exception as e:
            log.error(
                'Database exception when saving inbound SMS: %s' % e
            )
        '''

        return response

    def processServiceRequest(self, data):
        if data['command'] == 'req':
            response = 'reg:' + str(data['req']) + ';status:200'
            # Update device status

            # Set device status in Redis
            client = redis.Redis()
            try:
                client.set(self.devid, data['gsm_status'])
            except redis.ConnectionError as e:
                log.error(
                    'Redis error when updating device status: %s' % e
                )

            return response

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
