#!/usr/bin/env python3

import irc.bot
import argparse
from logging import debug, info, warn, error
import sys
import threading
import yaml


mandatory_config = {'irc': ['nick', 'server'], 
                    'jabber': ['nick', 'id', 'password'],
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
    def receive(self, chan, message):
        print("[{0}] {1}".format(chan, message), file=sys.stderr)


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
        threading.Thread(target=self.run, daemon=True).start()

    def run(self):
        raise NotImplementedError

    def receive(self, chan, message):
        debug
        self._router.receive(self, chan, message)

    def register(self, chan):
        debug("Socket {0} registering {1}", self.key, chan)
        self._channels.append(chan)

    def send(self, chan, message):
        raise NotImplementedError

    def users(self):
        raise NotImplementedError


                
        

class Console(Socket):
    def start():
        return
    def receive(self, chan, message):
        info("[{0}] {1}".format(chan, message))


class FIFO(Socket):
    def run(self):
        while(True):
            try:
                with open(self._config['path'], 'r') as handle:
                    for line in handle:
                        self.receive("*", ('notice', line))
                
            except Exception as e:
                logging.exception("Could not read from fifo")

class IRC(Socket):
    def run(self):
        nick = self._config['nick']
        server = self._config['server']
        user = self._config.get('user', 'slobot')
        real = self._config.get('real', 'SLoBot Chat Bridge')


        class Bot(irc.bot.SingleServerIRCBot):
            def on_welcome(bot, c, e):
                for chan in self._channels:
                    c.join(chan)

            def on_pubmsg(bot, c, e):
                self.receive(e.target, ('message', e.arguments[0]))

            def on_notice(bot, c, e):
                self.receive(e.target, ('notice', e.arguments[0]))

        bot = Bot(irc.bot.ServerSpec(server, 6667), nick, real)
        bot.start()
    

class XMPP(Socket):
    pass

socket_types = {
    'console': Console,
    'irc': IRC,
    'xmpp': XMPP,
    'fifo': FIFO
}

class Router:
    def __init__(self, sockets, routes):
        self._routes = routes
        self._sockets = {}
        for (key, conf) in sockets.items():
            self._sockets[key] = socket_types[conf['type']](self,key,conf)
        for (key, chan) in routes.items():
            self._sockets[key].register(chan)


    def receive(self, source, source_chan, message):
        for route in self._routes:
            if route.get(source.key) == source_chan:
                for (dest_key, dest_chan) in route:
                    if source.key == dest_key:
                        next
                    dest = self._sockets[dest_key]
                    if dest.readonly:
                        next
                    dest.send(dest_chan, message)

    def start(self):
        for (key, socket) in self._sockets:
            socket.start()

def main():
    parser = argparse.ArgumentParser(description="Swisslinux.org's Jabber/IRC Bridge")
    parser.add_argument('config', nargs=1, help='YAML config file')

    args = parser.parse_args()

    config = Config(args.config)


if __name__ == '__main__':
    main()
