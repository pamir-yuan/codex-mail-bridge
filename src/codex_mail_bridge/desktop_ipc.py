"""Small versioned client for the installed desktop app's local IPC.

This private protocol was verified against the installed desktop build. Fail
closed if an upgrade changes it; never edit chat databases to inject messages.
"""
import json
import socket
import struct
import time
import uuid

from .paths import desktop_socket


class DesktopError(Exception):
    def __init__(self, message, idle=False):
        super().__init__(message)
        self.idle = idle


class DesktopClient:
    def __init__(self, timeout=15):
        self.socket = socket.socket(socket.AF_UNIX)
        self.socket.settimeout(timeout)
        try:
            self.socket.connect(str(desktop_socket()))
            self.client_id = 'initializing-client'
            answer = self.request('initialize', {'clientType':'codex-email-bridge'}, 0)
            self.client_id = answer['result']['clientId']
        except BaseException:
            self.socket.close()
            raise

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.socket.close()

    def exact(self, size):
        output = bytearray()
        while len(output) < size:
            part = self.socket.recv(size-len(output))
            if not part:
                raise DesktopError('Desktop IPC disconnected')
            output.extend(part)
        return bytes(output)

    def send(self, value):
        raw = json.dumps(value, ensure_ascii=False).encode('utf-8')
        self.socket.sendall(struct.pack('<I',len(raw))+raw)

    def request(self, method, params, version, target=None):
        rid = str(uuid.uuid4())
        value = {'type':'request', 'requestId':rid, 'sourceClientId':self.client_id,
                 'version':version, 'method':method, 'params':params}
        if target:
            value['targetClientId'] = target
        self.send(value)
        deadline = time.monotonic()+30
        while time.monotonic()<deadline:
            length = struct.unpack('<I',self.exact(4))[0]
            if not 0 < length <= 8*1024*1024:
                raise DesktopError('Unexpected IPC frame length')
            answer = json.loads(self.exact(length))
            if answer.get('type') == 'client-discovery-request':
                self.send({'type':'client-discovery-response','requestId':answer['requestId'],
                           'response':{'canHandle':False}})
                continue
            if answer.get('type') != 'response' or answer.get('requestId') != rid:
                continue
            if answer.get('resultType') != 'success':
                # Raw app errors may contain message contents; keep them off logs.
                details = json.dumps(answer, ensure_ascii=False).lower()
                idle = ('active turn already ended' in details or 'no active turn to steer' in details)
                raise DesktopError('Desktop rejected the IPC request: '+method, idle=idle)
            return answer
        raise DesktopError('Desktop IPC request timed out')

    def owner(self, thread_id):
        answer = self.request('thread-owner-discovery',
                              {'hostId':'local','conversationId':thread_id},1)
        owner = answer.get('handledByClientId')
        if not owner:
            raise DesktopError('No desktop owner for this chat')
        return owner

    def read_settings(self, thread_id):
        return self.request('thread-follower-read-model-settings',
                             {'conversationId':thread_id},1,self.owner(thread_id))['result']

    def start_turn(self, thread_id, text):
        return self.request('thread-follower-start-turn',{
            'conversationId':thread_id,
            'turnStart':{'request':{'threadId':thread_id,'input':[
                {'type':'text','text':text,'text_elements':[]}]},
                         'context':{'inheritThreadSettings':True}}},2,self.owner(thread_id))

    def submit_reply(self, thread_id, text):
        owner = self.owner(thread_id)
        user_message_id = str(uuid.uuid4())
        try:
            answer = self.request('thread-follower-steer-turn', {
                'conversationId':thread_id, 'clientUserMessageId':user_message_id,
                'input':[{'type':'text','text':text,'text_elements':[]}],
                'restoreMessage':{'id':user_message_id,'context':{}}},1,owner)
            method = 'steer'
        except DesktopError as error:
            if not error.idle:
                raise
            # Only an explicit "no active turn" response permits a fresh turn.
            # A timeout is ambiguous, so it must never trigger a duplicate send.
            answer = self.start_turn(thread_id,text)
            method = 'start'
        return {'queue_id':answer.get('requestId',user_message_id),
                'resume_warning':False, 'desktop_method':method,
                'status':'desktop_accepted'}
