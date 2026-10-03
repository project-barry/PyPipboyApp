# pypipboy (vendored)

The Fallout 4 Pip-Boy app protocol client from
[matzman666/PyPipboy](https://github.com/matzman666/PyPipboy) at commit
028cad2 (2016-02-04), GPL-3.0 (LICENSE here). Only the modules the Barry
app's service uses are copied.

Changes from upstream, all in network.py:

- The receive and dispatch threads are daemon threads, so the service can
  quit while connected.
- A connection that ends during the handshake raises instead of calling
  `_doLostConnection` before there is a message queue.
- A payload read that gets no bytes stops instead of looping forever.
- Sends take a lock and use `sendall`, because keep-alives (receive thread)
  and commands (HTTP threads) can be sent at the same time.
