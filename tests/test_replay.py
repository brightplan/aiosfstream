from datetime import datetime, timezone, timedelta

from asynctest import TestCase, mock
from aiocometd.constants import MetaChannel

from aiosfstream.replay import ReplayMarkerStorage, ReplayMarker, \
    MappingStorage, ConstantReplayId


class ReplayMarkerStorageStub(ReplayMarkerStorage):
    async def set_replay_marker(self, subscription, replay_marker):
        pass

    async def get_replay_marker(self, subscription):
        pass


class TestReplayStorage(TestCase):
    def setUp(self):
        self.replay_storage = ReplayMarkerStorageStub()

    async def test_incoming_with_meta_channel(self):
        self.replay_storage.extract_replay_id = mock.CoroutineMock()
        message = {
            "channel": MetaChannel.HANDSHAKE
        }

        await self.replay_storage.incoming([message])

        self.replay_storage.extract_replay_id.assert_not_called()

    async def test_incoming_with_broadcast_channel(self):
        self.replay_storage.extract_replay_id = mock.CoroutineMock()
        message = {
            "channel": "/foo/bar"
        }

        await self.replay_storage.incoming([message])

        self.replay_storage.extract_replay_id.assert_called_with(message)

    async def test_outgoing_with_subscribe(self):
        self.replay_storage.insert_replay_id = mock.CoroutineMock()
        message = {
            "channel": MetaChannel.SUBSCRIBE
        }

        await self.replay_storage.outgoing([message], {})

        self.replay_storage.insert_replay_id.assert_called_with(message)

    async def test_get_replay_id(self):
        marker = ReplayMarker(date="", replay_id="id")
        self.replay_storage.get_replay_marker = mock.CoroutineMock(
            return_value=marker
        )
        subscription = "/foo/bar"

        result = await self.replay_storage.get_replay_id(subscription)

        self.assertEqual(result, marker.replay_id)
        self.replay_storage.get_replay_marker.assert_called_with(subscription)

    async def test_get_replay_id_none_marker(self):
        self.replay_storage.get_replay_marker = mock.CoroutineMock(
            return_value=None
        )
        subscription = "/foo/bar"

        result = await self.replay_storage.get_replay_id(subscription)

        self.assertIsNone(result)
        self.replay_storage.get_replay_marker.assert_called_with(subscription)

    async def test_outgoing_with_non_subscribe(self):
        self.replay_storage.insert_replay_id = mock.CoroutineMock()
        message = {
            "channel": MetaChannel.HANDSHAKE
        }

        await self.replay_storage.outgoing([message], {})

        self.replay_storage.insert_replay_id.assert_not_called()

    async def test_insert_replay_id(self):
        replay_id = "id"
        self.replay_storage.get_replay_id = mock.CoroutineMock(
            return_value=replay_id
        )
        message = {
            "channel": MetaChannel.SUBSCRIBE,
            "subscription": "/foo/bar",
            "ext": {}
        }

        await self.replay_storage.insert_replay_id(message)

        self.assertEqual(message["ext"]["replay"][message["subscription"]],
                         replay_id)
        self.replay_storage.get_replay_id.assert_called_with(
            message["subscription"])

    async def test_insert_replay_id_inserts_ext(self):
        replay_id = "id"
        self.replay_storage.get_replay_id = mock.CoroutineMock(
            return_value=replay_id
        )
        message = {
            "channel": MetaChannel.SUBSCRIBE,
            "subscription": "/foo/bar"
        }

        await self.replay_storage.insert_replay_id(message)

        self.assertEqual(message["ext"]["replay"][message["subscription"]],
                         replay_id)
        self.replay_storage.get_replay_id.assert_called_with(
            message["subscription"])

    async def test_insert_replay_id_doesnt_insert_none(self):
        replay_id = None
        self.replay_storage.get_replay_id = mock.CoroutineMock(
            return_value=replay_id
        )
        message = {
            "channel": MetaChannel.SUBSCRIBE,
            "subscription": "/foo/bar"
        }

        await self.replay_storage.insert_replay_id(message)

        self.assertNotIn("ext", message)
        self.replay_storage.get_replay_id.assert_called_with(
            message["subscription"])

    async def test_extract_replay_id_on_no_previous_id(self):
        self.replay_storage.set_replay_marker = mock.CoroutineMock()
        self.replay_storage.get_replay_marker = mock.CoroutineMock(
            return_value=None
        )
        date = datetime.now(timezone.utc).isoformat()
        id_value = "id"
        message = {
            "channel": "/foo/bar",
            "data": {
                "event": {
                    "createdDate": date,
                    "replayId": id_value
                }
            }
        }

        await self.replay_storage.extract_replay_id(message)

        self.replay_storage.set_replay_marker.assert_called_with(
            message["channel"],
            ReplayMarker(date=date, replay_id=id_value)
        )

    async def test_extract_replay_id_on_previous_id_older(self):
        self.replay_storage.set_replay_marker = mock.CoroutineMock()
        prev_marker = ReplayMarker(
            date=(datetime.now(timezone.utc) -
                  timedelta(seconds=1)).isoformat(),
            replay_id="old_id"
        )
        self.replay_storage.get_replay_marker = mock.CoroutineMock(
            return_value=prev_marker
        )
        date = datetime.now(timezone.utc).isoformat()
        id_value = "id"
        message = {
            "channel": "/foo/bar",
            "data": {
                "event": {
                    "createdDate": date,
                    "replayId": id_value
                }
            }
        }

        await self.replay_storage.extract_replay_id(message)

        self.replay_storage.set_replay_marker.assert_called_with(
            message["channel"],
            ReplayMarker(date=date, replay_id=id_value)
        )

    async def test_extract_replay_id_on_previous_id_newer(self):
        self.replay_storage.set_replay_marker = mock.CoroutineMock()
        prev_marker = ReplayMarker(
            date=(datetime.now(timezone.utc) +
                  timedelta(days=1)).isoformat(),
            replay_id="newer_id"
        )
        self.replay_storage.get_replay_marker = mock.CoroutineMock(
            return_value=prev_marker
        )
        date = datetime.now(timezone.utc).isoformat()
        id_value = "id"
        message = {
            "channel": "/foo/bar",
            "data": {
                "event": {
                    "createdDate": date,
                    "replayId": id_value
                }
            }
        }

        await self.replay_storage.extract_replay_id(message)

        self.replay_storage.set_replay_marker.assert_not_called()


class TestMappingReplayStorage(TestCase):
    def setUp(self):
        self.mapping = {}
        self.storage = MappingStorage(self.mapping)

    def test_init(self):
        self.assertIs(self.storage.mapping, self.mapping)

    def test_init_error_on_non_mapping(self):
        with self.assertRaisesRegex(TypeError,
                                    "mapping parameter should be an "
                                    "instance of MutableMapping."):
            MappingStorage([])

    async def test_set_replay_marker(self):
        self.storage.mapping = mock.MagicMock()
        subscription = "/foo/bar"
        marker = ReplayMarker(date="", replay_id="id")

        await self.storage.set_replay_marker(subscription, marker)

        self.storage.mapping.__setitem__.assert_called_with(subscription,
                                                            marker)

    async def test_get_replay_marker(self):
        subscription = "/foo/bar"
        marker = ReplayMarker(date="", replay_id="id")
        self.storage.mapping = mock.MagicMock()
        self.storage.mapping.__getitem__.return_value = marker

        result = await self.storage.get_replay_marker(subscription)

        self.assertEqual(result, marker)
        self.storage.mapping.__getitem__.assert_called_with(subscription)

    async def test_get_replay_marker_none_on_key_error(self):
        subscription = "/foo/bar"
        self.storage.mapping = mock.MagicMock()
        self.storage.mapping.__getitem__.side_effect = KeyError()

        result = await self.storage.get_replay_marker(subscription)

        self.assertIsNone(result)
        self.storage.mapping.__getitem__.assert_called_with(subscription)


class TestConstantReplayId(TestCase):
    def setUp(self):
        self.replay_storage = ConstantReplayId(1)

    async def test_get_replay_id(self):
        result = await self.replay_storage.get_replay_id("subscription")

        self.assertEqual(result, self.replay_storage.replay_id)

    async def test_get_replay_marker(self):
        result = await self.replay_storage.get_replay_marker("subscription")

        self.assertIsNone(result)

    async def test_set_replay_marker(self):
        marker = ReplayMarker(date="", replay_id="id")
        await self.replay_storage.set_replay_marker("subscription", marker)
