'''
Created on 28 ���� 2014 �.

@author: Shido
'''

class AsteriskControl:
    devId = None
    basePath = '/usr/local/etc/asterisk/goip/'
    
    def __init__(self, devId):
        self.devId = devId
        #add   methods to get config data from files
        
    def setPassword(self):
        
        