#!/usr/bin/env python3

import irc.bot
from irc.client import NickMask
import argparse
import logging
from logging import debug, info, warn, error, exception
import sleekxmpp
import sys
import threading
import yaml

logger = logging.getLogger(__name__)
(debug, info, warn, error, exception) = (logger.debug, logger.info, logger.warn, logger.error, logger.exception)

mandatory_config = {'irc': ['nick', 'server'], 
                    'xmpp': ['nick', 'jid', 'password'],
                    'fifo': ['path'],
                    'console': [] }

class ConfigurationError(Exception):
    pass

class Config:
    """ Load and validate a config file """
    def __init__(self, path):
        with open(path, 'rb') as handle:
            blob = yaml.load(handle)
        
        sockets = blob.get('sockets')
        if sockets is None:
            raise ConfigurationError("Config is missing a sockets section")
        
        for (name, sock) in sockets.items():
            typ = sock.get('type')
            if typ is None:
                raise ConfigurationError("Socket '{0}' should have a type".format(name))
            
            mandatory = mandatory_config.get(typ)
            if mandatory is None:
                raise ConfigurationError("Socket '{1}' is of unknown type '{0}'".format(sock['type'], name))
            
            for key in mandatory:
                if key not in sock:
                    raise ConfigurationError("socket '{0}' of type '{1}' is missing parameter '{2}'".format(name,typ,key))

        routes = blob.get('routes')
        if routes is None:
            raise ConfigurationError("Config is missing a routing section")

        for route in routes:
            for (key, chan) in route.items():
                sock = sockets.get(key)

                if sock is None:
                    raise ConfigurationError("route link includes an unknown socket name '{0}'".format(key))

                if sock['type'] == 'irc':
                    if chan[0] != '#':
                        raise ConfigurationError("IRC Channels should start with #")

                elif sock['type'] == 'xmpp':
                    pass #TODO check correct format for xmpp channel

        self.sockets = sockets
        self.routes = routes

class DummyRouter:
    """ A debugging router that will simply dump incoming messages to stderr """
    def receive(self, source, chan, message):
        print("[{0}:{1}] {2}".format(source.key, chan, message), file=sys.stderr)


class Socket():
    """ Base class for a Socket, that has its own thread to read messages from a source, and can be sent messages to. """
    def __init__(self, router, key, config, readonly=False):
        self.readonly = readonly
        self.key = key
        self._config = config
        self._channels = set()
        if router is None:
            self._router = DummyRouter()
        else:
            self._router = router

    def start(self):
        """ Launch the thread for this socket """
        threading.Thread(target=self.run).start()

    def run(self):
        """ Override this with the behaviour of your socket """
        raise NotImplementedError

    def receive(self, chan, message):
        """ Call this from the run() method when you receive a message. Indicate the channel on which you received it..
            message should be a tuple (type, sender, text) where type can be 'message' or 'notice'."""
        debug("Receive [{0}/{1}]: {2}".format(self.key, chan, message))
        if message[0] == 'message' and message[1][0:4] == '!who' and not self.readonly:
            self._router.users(self, chan)
        else:
            self._router.receive(self, chan, message)

    def register(self, chan):
        """ This wil get called before start(), once for every channel appearing in the routes """
        debug("Socket {0} registering {1}".format(self.key, chan))
        self._channels.add(chan)

    def send(self, chan, message):
        """ Override this with whatever needs to be done to send a message. The arguments will be in the same format as for the receive()."""
        raise NotImplementedError

    def users(self, channel):
        return None



class Console(Socket):
    """ A socket type that simply dumps messages to stdout. """
    def start(self):
        return
    def send(self, chan, message):
        print("[{0}] {1}".format(chan, message))


class FIFO(Socket):
    """ A socket type that reads messages from a unix fifo. The single name for the hardcoded channel is '*'. You cannot send to this channel. """
    def run(self):
        while(True):
            try:
                with open(self._config['path'], 'r') as handle:
                    for line in handle:
                        self.receive("*", ('notice', None, line.strip()))
                
            except Exception as e:
                exception("Could not read from fifo")

    def send(self, chan, message):
        return

class IRC(Socket):
    """ A socket type that talks IRC """
    def __init__(self, router, key, config):
        super().__init__(router, key, config)

        nick = config['nick']
        server = config['server']
        user = config.get('user', 'slobot')
        real = config.get('real', 'SLoBot Chat Bridge')


        class Bot(irc.bot.SingleServerIRCBot):
            def on_welcome(bot, c, e):
                info("IRC {0} connected".format(self.key))
                for chan in self._channels:
                    c.join(chan)

            def on_pubmsg(bot, c, e):
                nick = NickMask(e.source).nick
                debug("Sending irc message from {0}/{1}/{2}".format(self.key, e.target, nick))
                self.receive(e.target, ('message', nick, e.arguments[0]))

            def on_notice(bot, c, e):
                nick = NickMask(e.source).nick
                debug("Sending irc message from {0}/{1}/{2}".format(self.key, e.target, nick))
                self.receive(e.target, ('notice', nick, e.arguments[0]))

        self.bot = Bot([irc.bot.ServerSpec(server, 6667)], nick, real)

    def run(self):
        self.bot.start()

    def send(self, chan, message):
        (typ, sender, contents) = message
        if sender is not None:
            contents = "<{0}> {1}".format(sender, contents)
        
        if typ == 'message':
            self.bot.connection.privmsg(chan, contents)
        elif typ == 'notice':
            self.bot.connection.notice(chan, contents)

    def users(self, channel):
        try:
            return self.bot.channels[channel].users()
        except:
            exception("Could not retrieve IRC users")
    

class XMPP(Socket):
    def __init__(self, router, key, config):
        super().__init__(router, key, config)
        bot = sleekxmpp.ClientXMPP(self._config['jid'], self._config['password'])
        bot.register_plugin('xep_0045')
        bot.add_event_handler('session_start', self._session_start)
        bot.add_event_handler('groupchat_message', self._message)
        self._bot = bot

    def run(self):
        self._bot.connect()
        self._bot.process(block=True)

    def _message(self, msg):
        if msg['mucnick'] == self._config['nick']:
        if msg['type'] == 'groupchat':
            self.receive(msg['from'].bare, ('message', msg['from'].resource, msg['body']))

    def _session_start(self, evt):
        info("[{0}] XMPP Connected".format(self.key))
        self._bot.send_presence();
        self._bot.get_roster();
        for room in self._channels:
            self._bot.plugin['xep_0045'].joinMUC(room, self._config['nick'], wait=False)

    def send(self, channel, message):
        if message[1] is not None:
            body = "<{0}> {1}".format(message[1], message[2])
        else:
            body = message[2]
        self._bot.send_message(mto=channel, mbody=body, mtype='groupchat')

    def users(self, channel):
        return self._bot.plugin['xep_0045'].getRoster(channel)

socket_types = {
    'console': Console,
    'irc': IRC,
    'xmpp': XMPP,
    'fifo': FIFO
}

class Router:
    """ Manages a collection of sockets, and relays ingress messages to all linked outbound sockets """
    def __init__(self, config):
        routes = config.routes
        sockets = config.sockets

        self._routes = routes
        self._sockets = {}

        for (key, conf) in sockets.items():
            self._sockets[key] = socket_types[conf['type']](self,key,conf)
        for route in routes:
            for (key, chan) in route.items():
                self._sockets[key].register(chan)

    def dispatch(self, source, channel):
        """ Generates all the valid destinations for a given source socket and channel """
        for route in self._routes:
            if route.get(source.key) == channel:
                for (dest_key, dest_chan) in route.items():
                    if source.key != dest_key:
                        dest = self._sockets[dest_key]
                        if not dest.readonly:
                            yield (self._sockets[dest_key], dest_chan)


    def receive(self, source, source_chan, message):
        for (dest, dest_chan) in self.dispatch(source, source_chan):
            try:
                dest.send(dest_chan, message)
            except Exception:
                exception("Could not send to [{0}/{1}]".format(dest_key, dest_chan))

    def users(self, source, chan):
        for (dest, dest_chan) in self.dispatch(source, chan):
            users = dest.users(dest_chan)
            if users is not None:
                source.send(chan, ('message', "Users on {0}: {1}.".format(dest.key, ', '.join(dest.users(dest_chan)))))

    def start(self):
        for (key, socket) in self._sockets.items():
            info("Starting {0}".format(socket))
            socket.start()

def main():
    logging.basicConfig(level=logging.DEBUG)

    parser = argparse.ArgumentParser(description="Swisslinux.org's Jabber/IRC Bridge")
    parser.add_argument('config', help='YAML config file')

    args = parser.parse_args()

    info("SLoBot starting")

    config = Config(args.config)
    info("Configuration loaded")

    router = Router(config)
    info("Starting router")
    router.start()




if __name__ == '__main__':
    main()
