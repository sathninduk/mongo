#!/usr/bin/env python
#
# Public Domain 2014-present MongoDB, Inc.
# Public Domain 2008-2014 WiredTiger, Inc.
#
# This is free and unencumbered software released into the public domain.
#
# Anyone is free to copy, modify, publish, use, compile, sell, or
# distribute this software, either in source code form or as a compiled
# binary, for any purpose, commercial or non-commercial, and by any
# means.
#
# In jurisdictions that recognize copyright laws, the author or authors
# of this software dedicate any and all copyright interest in the
# software to the public domain. We make this dedication for the benefit
# of the public at large and to the detriment of our heirs and
# successors. We intend this dedication to be an overt act of
# relinquishment in perpetuity of all present and future rights to this
# software under copyright law.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
# EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF
# MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT.
# IN NO EVENT SHALL THE AUTHORS BE LIABLE FOR ANY CLAIM, DAMAGES OR
# OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE,
# ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR
# OTHER DEALINGS IN THE SOFTWARE.

import time, wiredtiger, wttest, unittest
from wtscenario import make_scenarios

# test_hs18.py
# Test various older reader scenarios
class test_hs18(wttest.WiredTigerTestCase):
    conn_config = 'cache_size=5MB,eviction=(threads_max=1)'
    session_config = 'isolation=snapshot'
    key_format_values = [
        ('column', dict(key_format='r')),
        ('string-row', dict(key_format='S'))
    ]
    scenarios = make_scenarios(key_format_values)

    def create_key(self, i):
        if self.key_format == 'S':
            return str(i)
        return i

    def check_value(self, cursor, value):
        cursor.set_key(self.create_key(1))
        self.assertEqual(cursor.search(), 0)
        self.assertEqual(cursor.get_value(), value)
        cursor.reset()

    def start_txn(self, sessions, cursors, values, i):
        # Start a transaction that will see update 0.
        sessions[i].begin_transaction()
        self.check_value(cursors[i], values[i])

    def test_base_scenario(self):
        uri = 'table:test_base_scenario'
        self.session.create(uri, 'key_format={},value_format=S'.format(self.key_format))
        session2 = self.setUpSessionOpen(self.conn)
        cursor = self.session.open_cursor(uri)
        cursor2 = session2.open_cursor(uri)

        value0 = 'f' * 500
        value1 = 'a' * 500
        value2 = 'b' * 500
        value3 = 'c' * 500
        value4 = 'd' * 500
        value5 = 'e' * 500

        # Insert an update at timestamp 3
        self.session.begin_transaction()
        cursor[self.create_key(1)] = value0
        self.session.commit_transaction('commit_timestamp=' + self.timestamp_str(3))

        # Start a long running transaction which could see update 0.
        session2.begin_transaction()
        self.check_value(cursor2, value0)

        # Insert an update at timestamp 5
        self.session.begin_transaction()
        cursor[self.create_key(1)] = value1
        self.session.commit_transaction('commit_timestamp=' + self.timestamp_str(5))

        # Insert another update at timestamp 10
        self.session.begin_transaction()
        cursor[self.create_key(1)] = value2
        self.session.commit_transaction('commit_timestamp=' + self.timestamp_str(10))

        # Insert a bunch of contents to fill the cache
        for i in range(2000, 10000):
            self.session.begin_transaction()
            cursor[self.create_key(i)] = value3
            self.session.commit_transaction()

        # Commit an update without a timestamp on our original key
        self.session.begin_transaction()
        cursor[self.create_key(1)] = value4
        self.session.commit_transaction()

        # Commit an update with timestamp 15
        self.session.begin_transaction()
        cursor[self.create_key(1)] = value5
        self.session.commit_transaction('commit_timestamp=' + self.timestamp_str(15))

        # Check our value is still correct.
        self.check_value(cursor2, value0)

        # Insert a bunch of other contents to trigger eviction
        for i in range(10001, 11000):
            self.session.begin_transaction()
            cursor[self.create_key(i)] = value3
            self.session.commit_transaction()

        # Check our value is still correct.
        self.check_value(cursor2, value0)

    # Test that we don't get the wrong value if we read with a timestamp originally.
    def test_read_timestamp_weirdness(self):
        uri = 'table:test_hs18'
        self.session.create(uri, 'key_format={},value_format=S'.format(self.key_format))
        cursor = self.session.open_cursor(uri)
        session2 = self.setUpSessionOpen(self.conn)
        cursor2 = session2.open_cursor(uri)
        session3 = self.setUpSessionOpen(self.conn)
        cursor3 = session3.open_cursor(uri)

        value1 = 'a' * 500
        value2 = 'b' * 500
        value3 = 'c' * 500
        value4 = 'd' * 500
        value5 = 'e' * 500

        # Insert an update at timestamp 3
        self.session.begin_transaction()
        cursor[self.create_key(1)] = value1
        self.session.commit_transaction('commit_timestamp=' + self.timestamp_str(3))

        # Start a long running transaction which could see update 0.
        session2.begin_transaction('read_timestamp=' + self.timestamp_str(5))
        # Check our value is still correct.
        self.check_value(cursor2, value1)

        # Insert another update at timestamp 10
        self.session.begin_transaction()
        cursor[self.create_key(1)] = value2
        self.session.commit_transaction('commit_timestamp=' + self.timestamp_str(10))

        # Start a long running transaction which could see update 0.
        session3.begin_transaction('read_timestamp=' + self.timestamp_str(5))
        # Check our value is still correct.
        self.check_value(cursor3, value1)

        # Insert a bunch of contents to fill the cache
        for i in range(1000, 10000):
            self.session.begin_transaction()
            cursor[self.create_key(i)] = value3
            self.session.commit_transaction()

        # Commit an update without a timestamp on our original key
        self.session.begin_transaction()
        cursor[self.create_key(1)] = value4
        self.session.commit_transaction()

        # Commit an update with timestamp 15
        self.session.begin_transaction()
        cursor[self.create_key(1)] = value5
        self.session.commit_transaction('commit_timestamp=' + self.timestamp_str(15))

        # Check our value is still correct.
        self.check_value(cursor2, value1)
        self.check_value(cursor3, value1)

        # Insert a bunch of other contents to trigger eviction
        for i in range(10001, 20000):
            self.session.begin_transaction()
            cursor[self.create_key(i)] = value3
            self.session.commit_transaction()

        # Check our value is still correct.
        self.check_value(cursor2, value1)
        # Here our value will be wrong as we're reading with a timestamp, and can now see a newer value.
        self.check_value(cursor3, value2)

    # Test that forces us to ignore tombstone in order to not remove the first non timestamped updated.
    def test_ignore_tombstone(self):
        uri = 'table:test_ignore_tombstone'
        self.session.create(uri, 'key_format={},value_format=S'.format(self.key_format))
        session2 = self.setUpSessionOpen(self.conn)
        cursor = self.session.open_cursor(uri)
        cursor2 = session2.open_cursor(uri)
        value0 = 'A' * 500
        value1 = 'a' * 500
        value2 = 'b' * 500
        value3 = 'c' * 500
        value4 = 'd' * 500

        # Insert an update without a timestamp
        self.session.begin_transaction()
        cursor[self.create_key(1)] = value0
        self.session.commit_transaction()

        # Start a long running transaction which could see update 0.
        session2.begin_transaction()

        # Check our value is still correct.
        self.check_value(cursor2, value0)

        # Insert an update at timestamp 5
        self.session.begin_transaction()
        cursor[self.create_key(1)] = value1
        self.session.commit_transaction('commit_timestamp=' + self.timestamp_str(5))

        # Insert another update at timestamp 10
        self.session.begin_transaction()
        cursor[self.create_key(1)] = value2
        self.session.commit_transaction('commit_timestamp=' + self.timestamp_str(10))

        # Insert a bunch of other contents to trigger eviction
        for i in range(2, 10000):
            self.session.begin_transaction()
            cursor[self.create_key(i)] = value3
            self.session.commit_transaction()

        # Check our value is still correct.
        self.check_value(cursor2, value0)

        # Commit an update without a timestamp on our original key
        self.session.begin_transaction()
        cursor[self.create_key(1)] = value4
        self.session.commit_transaction()

        # Insert a bunch of other contents to trigger eviction
        for i in range(10000, 11000):
            self.session.begin_transaction()
            cursor[self.create_key(i)] = value3
            self.session.commit_transaction()

        # Check our value is still correct.
        self.check_value(cursor2, value0)

    # Test older readers for each of the updates moved to the history store.
    def test_multiple_older_readers(self):
        uri = 'table:test_multiple_older_readers'
        self.session.create(uri, 'key_format={},value_format=S'.format(self.key_format))
        cursor = self.session.open_cursor(uri)

        # The ID of the session corresponds the value it should see.
        sessions = []
        cursors = []
        values = []
        for i in range(0, 5):
            sessions.append(self.setUpSessionOpen(self.conn))
            cursors.append(sessions[i].open_cursor(uri))
            values.append(str(i) * 10)

        value_junk = 'aaaaa' * 100

        # Insert an update at timestamp 3
        self.session.begin_transaction()
        cursor[self.create_key(1)] = values[0]
        self.session.commit_transaction('commit_timestamp=' + self.timestamp_str(3))

        # Start a transaction that will see update 0.
        self.start_txn(sessions, cursors, values, 0)

        # Insert an update at timestamp 5
        self.session.begin_transaction()
        cursor[self.create_key(1)] = values[1]
        self.session.commit_transaction('commit_timestamp=' + self.timestamp_str(5))

        # Start a transaction that will see update 1.
        self.start_txn(sessions, cursors, values, 1)

        # Insert another update at timestamp 10
        self.session.begin_transaction()
        cursor[self.create_key(1)] = values[2]
        self.session.commit_transaction('commit_timestamp=' + self.timestamp_str(10))

        # Start a transaction that will see update 2.
        self.start_txn(sessions, cursors, values, 2)

        # Insert a bunch of other contents to trigger eviction
        for i in range(1000, 10000):
            self.session.begin_transaction()
            cursor[self.create_key(i)] = value_junk
            self.session.commit_transaction()

        # Commit an update without a timestamp on our original key
        self.session.begin_transaction()
        cursor[self.create_key(1)] = values[3]
        self.session.commit_transaction()

        # Start a transaction that will see update 3.
        self.start_txn(sessions, cursors, values, 3)

        # Commit an update with timestamp 15
        self.session.begin_transaction()
        cursor[self.create_key(1)] = values[4]
        self.session.commit_transaction('commit_timestamp=' + self.timestamp_str(15))

        # Insert a bunch of other contents to trigger eviction
        for i in range(10001, 20000):
            self.session.begin_transaction()
            cursor[self.create_key(i)] = value_junk
            self.session.commit_transaction()

        # Validate all values are visible and correct.
        for i in range(0, 3):
            cursors[i].set_key(self.create_key(1))
            self.assertEqual(cursors[i].search(), 0)
            self.assertEqual(cursors[i].get_value(), values[i])
            cursors[i].reset()

    def test_multiple_older_readers_with_multiple_mixed_mode(self):
        uri = 'table:test_multiple_older_readers'
        self.session.create(uri, 'key_format={},value_format=S'.format(self.key_format))
        cursor = self.session.open_cursor(uri)

        # The ID of the session corresponds the value it should see.
        sessions = []
        cursors = []
        values = []
        for i in range(0, 9):
            sessions.append(self.setUpSessionOpen(self.conn))
            cursors.append(sessions[i].open_cursor(uri))
            values.append(str(i) * 10)

        value_junk = 'aaaaa' * 100

        # Insert an update at timestamp 3
        self.session.begin_transaction()
        cursor[self.create_key(1)] = values[0]
        self.session.commit_transaction('commit_timestamp=' + self.timestamp_str(3))

        # Start a transaction that will see update 0.
        self.start_txn(sessions, cursors, values, 0)

        # Insert an update at timestamp 5
        self.session.begin_transaction()
        cursor[self.create_key(1)] = values[1]
        self.session.commit_transaction('commit_timestamp=' + self.timestamp_str(5))

        # Start a transaction that will see update 1.
        self.start_txn(sessions, cursors, values, 1)

        # Insert another update at timestamp 10
        self.session.begin_transaction()
        cursor[self.create_key(1)] = values[2]
        self.session.commit_transaction('commit_timestamp=' + self.timestamp_str(10))

        # Start a transaction that will see update 2.
        self.start_txn(sessions, cursors, values, 2)

        # Insert a bunch of other contents to trigger eviction
        for i in range(1000, 10000):
            self.session.begin_transaction()
            cursor[self.create_key(i)] = value_junk
            self.session.commit_transaction()

        # Commit an update without a timestamp on our original key
        self.session.begin_transaction()
        cursor[self.create_key(1)] = values[3]
        self.session.commit_transaction()

        # Start a transaction that will see update 4.
        self.start_txn(sessions, cursors, values, 3)

        # Commit an update with timestamp 5
        self.session.begin_transaction()
        cursor[self.create_key(1)] = values[4]
        self.session.commit_transaction('commit_timestamp=' + self.timestamp_str(5))

        # Start a transaction that will see update 4.
        self.start_txn(sessions, cursors, values, 4)

        # Commit an update with timestamp 10
        self.session.begin_transaction()
        cursor[self.create_key(1)] = values[5]
        self.session.commit_transaction('commit_timestamp=' + self.timestamp_str(10))

        # Start a transaction that will see update 5.
        self.start_txn(sessions, cursors, values, 5)

        # Commit an update with timestamp 15
        self.session.begin_transaction()
        cursor[self.create_key(1)] = values[6]
        self.session.commit_transaction('commit_timestamp=' + self.timestamp_str(15))

        # Start a transaction that will see update 6.
        self.start_txn(sessions, cursors, values, 6)

        # Insert a bunch of other contents to trigger eviction
        for i in range(10001, 20000):
            self.session.begin_transaction()
            cursor[self.create_key(i)] = value_junk
            self.session.commit_transaction()

        # Validate all values are visible and correct.
        for i in range(0, 6):
            cursors[i].set_key(self.create_key(1))
            self.assertEqual(cursors[i].search(), 0)
            self.assertEqual(cursors[i].get_value(), values[i])
            cursors[i].reset()

        # Commit an update without a timestamp on our original key
        self.session.begin_transaction()
        cursor[self.create_key(1)] = values[7]
        self.session.commit_transaction()

        # Start a transaction that will see update 7.
        self.start_txn(sessions, cursors, values, 7)

        # Commit an update with timestamp 5
        self.session.begin_transaction()
        cursor[self.create_key(1)] = values[8]
        self.session.commit_transaction('commit_timestamp=' + self.timestamp_str(5))

        # Insert a bunch of other contents to trigger eviction
        for i in range(10001, 20000):
            self.session.begin_transaction()
            cursor[self.create_key(i)] = values[3]
            self.session.commit_transaction()

        # Validate all values are visible and correct.
        for i in range(0, 7):
            cursors[i].set_key(self.create_key(1))
            self.assertEqual(cursors[i].search(), 0)
            self.assertEqual(cursors[i].get_value(), values[i])
            cursors[i].reset()

    def test_modifies(self):
        uri = 'table:test_modifies'
        self.session.create(uri, 'key_format={},value_format=S'.format(self.key_format))
        cursor = self.session.open_cursor(uri)
        session_ts_reader = self.setUpSessionOpen(self.conn)
        cursor_ts_reader = session_ts_reader.open_cursor(uri)

        self.skipTest('Skip this part of test_hs18 until WT-7931 is resolved')

        # The ID of the session corresponds the value it should see.
        sessions = []
        cursors = []
        values = []
        for i in range(0, 5):
            sessions.append(self.setUpSessionOpen(self.conn))
            cursors.append(sessions[i].open_cursor(uri))

        value_junk = 'aaaaa' * 100

        values.append('f' * 10)
        values.append('a' + values[0])
        values.append('b' + values[1])
        values.append('g' * 10)
        values.append('e' + values[3])

        # Insert an update at timestamp 3
        self.session.begin_transaction()
        cursor[self.create_key(1)] = values[0]
        self.session.commit_transaction('commit_timestamp=' + self.timestamp_str(3))

        # Start a long running transaction which could see update 0.
        self.start_txn(sessions, cursors, values, 0)

        # Insert an update at timestamp 5
        self.session.begin_transaction()
        cursor.set_key(self.create_key(1))
        cursor.modify([wiredtiger.Modify('a', 0, 0)])
        self.session.commit_transaction('commit_timestamp=' + self.timestamp_str(5))

        session_ts_reader.begin_transaction('read_timestamp=3')
        self.check_value(cursor_ts_reader, values[0])

        # Start a long running transaction which could see modify 0.
        self.start_txn(sessions, cursors, values, 1)

        # Insert another modify at timestamp 10
        self.session.begin_transaction()
        cursor.set_key(self.create_key(1))
        cursor.modify([wiredtiger.Modify('b', 0, 0)])
        self.session.commit_transaction('commit_timestamp=' + self.timestamp_str(10))

        # Start a long running transaction which could see modify 1.
        self.start_txn(sessions, cursors, values, 2)

        # Insert a bunch of contents to fill the cache
        for i in range(2000, 10000):
            self.session.begin_transaction()
            cursor[self.create_key(i)] = value_junk
            self.session.commit_transaction()

        # Commit a modify without a timestamp on our original key
        self.session.begin_transaction()
        cursor[self.create_key(1)] = values[3]
        self.session.commit_transaction()

        # Start a long running transaction which could see value 5.
        self.start_txn(sessions, cursors, values, 3)

        # Commit a final modify.
        self.session.begin_transaction()
        cursor.set_key(self.create_key(1))
        cursor.modify([wiredtiger.Modify('e', 0, 0)])
        self.session.commit_transaction('commit_timestamp=' + self.timestamp_str(15))

        # Start a long running transaction which could see modify 2.
        sessions[4].begin_transaction()
        # Check our values are still correct.
        for i in range(0, 5):
            self.check_value(cursors[i], values[i])

        # Insert a bunch of other contents to trigger eviction
        for i in range(10001, 11000):
            self.session.begin_transaction()
            cursor[self.create_key(i)] = value_junk
            self.session.commit_transaction()

        # Check our values are still correct.
        for i in range(0, 5):
            self.check_value(cursors[i], values[i])

        # Check our ts reader sees the value ahead of it
        self.check_value(cursor_ts_reader, values[1])
