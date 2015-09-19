# SloBot v2.0

An instant messaging bot to bridge networks together.

This project is the offspring of an evening of frustration, trying to get an obsolete JIRC bot,
relying on the unmaintained Perl POE::Component::Jabber module, to talk with a bleeding-edge
ejabberd (and discovering a boring bug in ejabberd's authentication code, but that is another story.)

## Userspace Channel Bridging

This bot simply parrots text from one connection to another. It's ugly, impractical, but it doesn't require
admin privileges on either networks on its ends, and can be run by any lambda user.

## Features

The original JIRC bot can only bridge a single IRC room to a single MUC room. SLoBot2 can:

  * Open an arbitrary number of connections to IRC, XMPP, Unix named pipe (and in the future, maybe Mumble)
  * Be present in several rooms from a single connection (no need to hammer the servers with clones)
  * Bridge any number of these locations in a single logical room (so yes, also irc-irc bridging, for instance)
  * Operate several logical rooms simultaneously
  * Display the connected people on the other sides of the bridge, one line per endpoint

## Configuration

Refer to the slobot.yaml file for examples. Every named 'socket' entry is a connection
to a chat network or other source or sink, while all the 'route' entries
are group of rooms on the different networks that should be bridged together

## Running

    $ python setup.py install
    $ slobot config.yaml
