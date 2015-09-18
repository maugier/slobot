#!/usr/bin/env python3

import irc.bot
import argparse
import logging
from logging import debug, info, warn, error, exception
import sleekxmpp
import sys
import threading
import yaml


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
        threading.Thread(target=self.run).start()

    def run(self):
        raise NotImplementedError

    def receive(self, chan, message):
        debug("Receive [{0}/{1}]: {2}".format(self.key, chan, message))
        self._router.receive(self, chan, message)

    def register(self, chan):
        debug("Socket {0} registering {1}".format(self.key, chan))
        self._channels.add(chan)

    def send(self, chan, message):
        raise NotImplementedError

    def users(self, channel):
        return None


                
        

class Console(Socket):
    def start():
        return
    def send(self, chan, message):
        info("[{0}] {1}".format(chan, message))


class FIFO(Socket):
    def run(self):
        while(True):
            try:
                with open(self._config['path'], 'r') as handle:
                    for line in handle:
                        self.receive("*", ('notice', line.strip()))
                
            except Exception as e:
                exception("Could not read from fifo")

class IRC(Socket):
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
                debug("Sending irc message from {0}/{1}".format(self.key, e.target))
                self.receive(e.target, ('message', e.arguments[0]))

            def on_notice(bot, c, e):
                self.receive(e.target, ('notice', e.arguments[0]))

        self.bot = Bot([irc.bot.ServerSpec(server, 6667)], nick, real)

    def run(self):
        self.bot.start()

    def send(self, chan, message):
        (typ, contents) = message
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
        self._bot = bot
        bot.add_event_handler('session_start', self._session_start)
        bot.add_event_handler('message', self._message)

    def run(self):
        self._bot.connect()
        self._bot.process(block=True)

    def _message(self, msg):
        if msg['type'] == 'groupchat':
            self.receive(msg['from'], ('message', msg['body']))

    def _session_start(self, evt):
        info("[{0}] XMPP Connected".format(self.key))
        self._bot.send_presence();
        self._bot.get_roster();

socket_types = {
    'console': Console,
    'irc': IRC,
    'xmpp': XMPP,
    'fifo': FIFO
}

class Router:
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


    def receive(self, source, source_chan, message):
        for route in self._routes:
            if route.get(source.key) == source_chan:
                for (dest_key, dest_chan) in route.items():
                    if source.key == dest_key:
                        continue
                    dest = self._sockets[dest_key]
                    if dest.readonly:
                        continue
                    try:
                        dest.send(dest_chan, message)
                    except Exception:
                        exception("Could not send to [{0}/{1}]".format(dest_key, dest_chan))

    def start(self):
        for (key, socket) in self._sockets.items():
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
