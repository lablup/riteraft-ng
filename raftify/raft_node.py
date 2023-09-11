import asyncio
import pickle
import time
from asyncio import Queue

from rraft import (
    ConfChange,
    ConfChangeType,
    Entry,
    EntryRef,
    EntryType,
    Logger,
    LoggerRef,
    Message,
    RawNode,
    Snapshot,
    Storage,
)

from raftify.config import RaftifyConfig
from raftify.fsm import FSM
from raftify.lmdb import LMDBStorage
from raftify.logger import AbstractRaftifyLogger
from raftify.pb_adapter import ConfChangeAdapter, MessageAdapter
from raftify.peers import Peers
from raftify.protos.raft_service_pb2 import RerouteMsgType
from raftify.raft_client import RaftClient
from raftify.raft_server import RaftServer
from raftify.request_message import (
    ConfigChangeReqMessage,
    ProposeReqMessage,
    RaftReqMessage,
    ReportUnreachableReqMessage,
    RequestIdReqMessage,
    RerouteToLeaderReqMessage,
)
from raftify.response_message import (
    IdReservedRespMessage,
    JoinSuccessRespMessage,
    RaftOkRespMessage,
    RaftRespMessage,
    WrongLeaderRespMessage,
)
from raftify.utils import AtomicInteger


class RaftNode:
    def __init__(
        self,
        *,
        raw_node: RawNode,
        raft_server: RaftServer,
        peers: Peers,
        chan: Queue,
        fsm: FSM,
        lmdb: LMDBStorage,
        storage: Storage,
        seq: AtomicInteger,
        last_snap_time: float,
        logger: AbstractRaftifyLogger,
        raftify_cfg: RaftifyConfig,
    ):
        self.raw_node = raw_node
        self.raft_server = raft_server
        self.peers = peers
        self.chan = chan
        self.fsm = fsm
        self.lmdb = lmdb
        self.storage = storage
        self.seq = seq
        self.last_snap_time = last_snap_time
        self.logger = logger
        self.should_exit = False
        self.raftify_cfg = raftify_cfg

    @classmethod
    def bootstrap_leader(
        cls,
        *,
        chan: Queue,
        fsm: FSM,
        raft_server: RaftServer,
        slog: Logger | LoggerRef,
        logger: AbstractRaftifyLogger,
        raftify_cfg: RaftifyConfig,
    ) -> "RaftNode":
        cfg = raftify_cfg.config

        cfg.set_id(1)
        cfg.validate()

        snapshot = Snapshot.default()
        snapshot.get_metadata().set_index(0)
        snapshot.get_metadata().set_term(0)
        snapshot.get_metadata().get_conf_state().set_voters([1])

        lmdb = LMDBStorage.create(raftify_cfg.log_dir, 1, logger)
        lmdb.apply_snapshot(snapshot)

        storage = Storage(lmdb)
        raw_node = RawNode(cfg, storage, slog)

        peers = Peers()
        seq = AtomicInteger(0)
        last_snap_time = time.time()

        raw_node.get_raft().become_candidate()
        raw_node.get_raft().become_leader()

        return cls(
            raw_node=raw_node,
            raft_server=raft_server,
            peers=peers,
            chan=chan,
            fsm=fsm,
            lmdb=lmdb,
            storage=storage,
            seq=seq,
            last_snap_time=last_snap_time,
            logger=logger,
            raftify_cfg=raftify_cfg,
        )

    @classmethod
    def new_follower(
        cls,
        *,
        chan: Queue,
        id: int,
        fsm: FSM,
        raft_server: RaftServer,
        slog: Logger | LoggerRef,
        logger: AbstractRaftifyLogger,
        raftify_cfg: RaftifyConfig,
    ) -> "RaftNode":
        cfg = raftify_cfg.config

        cfg.set_id(id)
        cfg.validate()

        lmdb = LMDBStorage.create(raftify_cfg.log_dir, id, logger)
        storage = Storage(lmdb)
        raw_node = RawNode(cfg, storage, slog)

        peers = Peers()
        seq = AtomicInteger(0)
        last_snap_time = time.time()

        return cls(
            raw_node=raw_node,
            raft_server=raft_server,
            peers=peers,
            chan=chan,
            fsm=fsm,
            lmdb=lmdb,
            storage=storage,
            seq=seq,
            last_snap_time=last_snap_time,
            logger=logger,
            raftify_cfg=raftify_cfg,
        )

    def get_id(self) -> int:
        return self.raw_node.get_raft().get_id()

    def get_leader_id(self) -> int:
        return self.raw_node.get_raft().get_leader_id()

    def is_leader(self) -> bool:
        return self.get_id() == self.get_leader_id()

    def remove_node(self, node_id: int) -> None:
        client = self.peers[node_id]
        del self.peers[node_id]

        self.seq.increase()
        conf_change = ConfChange.default()
        conf_change.set_node_id(node_id)
        conf_change.set_context(pickle.dumps(client.addr))
        conf_change.set_change_type(ConfChangeType.RemoveNode)
        context = pickle.dumps(self.seq.value)

        self.raw_node.propose_conf_change(
            context,
            conf_change,
        )

    def reserve_next_peer_id(self, addr: str) -> int:
        """
        Reserve a slot to insert node on next node addition commit.
        """
        prev_conns = [
            id for id, peer in self.peers.items() if peer and addr == str(peer.addr)
        ]

        if len(prev_conns) > 0:
            next_id = prev_conns[0]
        else:
            next_id = max(self.peers.keys()) if any(self.peers) else 1
            next_id = max(next_id + 1, self.get_id())

            # if assigned id is ourself, return next one
            if next_id == self.get_id():
                next_id += 1

        self.logger.info(f"Reserved peer id {next_id}.")
        self.peers[next_id] = None
        return next_id

    async def send_message(self, client: RaftClient, message: Message) -> None:
        """
        Attempt to send a message 'max_retry_cnt' times at 'timeout' interval.
        If 'auto_remove_node' is set to True, the send function will automatically remove the node from the cluster
        if it fails to connect more than 'connection_fail_limit' times.
        """

        current_retry = 0
        while True:
            try:
                await client.send_message(message, self.raftify_cfg.message_timeout)
                return
            except Exception:
                if current_retry < self.raftify_cfg.max_retry_cnt:
                    current_retry += 1
                else:
                    client_id = message.get_to()
                    self.logger.debug(
                        f"Failed to connect to {client_id} the {self.raftify_cfg.max_retry_cnt} times"
                    )

                    try:
                        if self.raftify_cfg.auto_remove_node:
                            failed_request_counter = self.peers[
                                client_id
                            ].failed_request_counter

                            if (
                                failed_request_counter.value
                                >= self.raftify_cfg.connection_fail_limit
                            ):
                                self.logger.debug(
                                    f"Removed 'Node {client_id}' from cluster automatically because the request kept failed"
                                )

                                self.remove_node(client_id)
                                return
                            else:
                                failed_request_counter.increase()

                        await self.chan.put(ReportUnreachableReqMessage(client_id))
                    except Exception:
                        pass
                    return

    def send_messages(self, messages: list[Message]):
        for message in messages:
            if client := self.peers.get(message.get_to()):
                asyncio.create_task(
                    self.send_message(
                        client,
                        message,
                    )
                )

    async def send_wrongleader_response(self, channel: Queue) -> None:
        # TODO: Make this follower to new cluster's leader
        assert self.get_leader_id() in self.peers, "Leader can't be an empty node!"

        try:
            # TODO: handle error here
            await channel.put(
                WrongLeaderRespMessage(
                    leader_id=self.get_leader_id(),
                    leader_addr=str(self.peers[self.get_leader_id()].addr),
                )
            )
        except Exception:
            pass

    async def handle_committed_entries(
        self,
        committed_entries: list[Entry] | list[EntryRef],
        client_senders: dict[int, Queue],
    ) -> None:
        # Mostly, you need to save the last apply index to resume applying
        # after restart. Here we just ignore this because we use a Memory storage.

        # _last_apply_index = 0

        for entry in committed_entries:
            # Empty entry, when the peer becomes Leader it will send an empty entry.
            if not entry.get_data():
                continue

            match entry.get_entry_type():
                case EntryType.EntryNormal:
                    await self.handle_normal_entry(entry, client_senders)
                case EntryType.EntryConfChange:
                    await self.handle_config_change_entry(entry, client_senders)
                case _:
                    raise NotImplementedError

    async def handle_normal_entry(
        self, entry: Entry | EntryRef, senders: dict[int, Queue]
    ) -> None:
        seq = pickle.loads(entry.get_context())
        data = await self.fsm.apply(entry.get_data())

        if sender := senders.pop(seq, None):
            sender.put_nowait(RaftRespMessage(data))

        if time.time() > self.last_snap_time + self.raftify_cfg.snapshot_interval:
            self.logger.info("Creating snapshot...")
            self.last_snap_time = time.time()
            snapshot = await self.fsm.snapshot()

            if self.raftify_cfg.use_log_compaction:
                last_applied = self.raw_node.get_raft().get_raft_log().get_applied()
                self.lmdb.compact(last_applied)

            try:
                self.lmdb.create_snapshot(snapshot, entry.get_index(), entry.get_term())
                self.logger.info("Snapshot created successfully.")
            except Exception:
                pass

    async def handle_config_change_entry(
        self, entry: Entry | EntryRef, senders: dict[int, Queue]
    ) -> None:
        seq = pickle.loads(entry.get_context())
        conf_change = ConfChange.decode(entry.get_data())
        node_id = conf_change.get_node_id()

        change_type = conf_change.get_change_type()

        match change_type:
            case ConfChangeType.AddNode | ConfChangeType.AddLearnerNode:
                addr = pickle.loads(conf_change.get_context())
                self.logger.info(
                    f"Node '{addr} (node id: {node_id})' added to the cluster."
                )
                self.peers[node_id] = RaftClient(addr)
            case ConfChangeType.RemoveNode:
                if conf_change.get_node_id() == self.get_id():
                    self.should_exit = True
                    await self.raft_server.terminate()
                    self.logger.info(f"{self.get_id()} quit the cluster.")
                else:
                    self.peers.pop(conf_change.get_node_id(), None)
            case _:
                raise NotImplementedError

        if conf_state := self.raw_node.apply_conf_change(conf_change):
            snapshot = await self.fsm.snapshot()
            self.lmdb.set_conf_state(conf_state)

            if self.raftify_cfg.use_log_compaction:
                last_applied = self.raw_node.get_raft().get_raft_log().get_applied()
                self.lmdb.compact(last_applied)

            try:
                self.lmdb.create_snapshot(snapshot, entry.get_index(), entry.get_term())
            except Exception:
                pass

        if sender := senders.pop(seq, None):
            match change_type:
                case ConfChangeType.AddNode | ConfChangeType.AddLearnerNode:
                    response = JoinSuccessRespMessage(
                        assigned_id=node_id, peer_addrs=self.peers.peer_addrs()
                    )
                case ConfChangeType.RemoveNode:
                    response = RaftOkRespMessage()
                case _:
                    raise NotImplementedError

            try:
                sender.put_nowait(response)
            except Exception:
                self.logger.error("Error occurred while sending response")

    async def run(self) -> None:
        heartbeat = 0.1

        # A map to contain sender to client responses
        client_senders: dict[int, Queue] = {}
        timer = time.time()

        while not self.should_exit:
            message = None

            try:
                message = await asyncio.wait_for(self.chan.get(), heartbeat)
            except asyncio.TimeoutError:
                pass
            except asyncio.CancelledError:
                self.logger.warning("Cancelled error occurred!")
                raise
            except Exception:
                raise

            if isinstance(message, RerouteToLeaderReqMessage):
                match message.type:
                    case RerouteMsgType.ConfChange:
                        message = ConfigChangeReqMessage(
                            conf_change=message.conf_change, chan=message.chan
                        )
                    case RerouteMsgType.Propose:
                        message = ProposeReqMessage(
                            data=message.proposed_data, chan=message.chan
                        )

            if isinstance(message, ConfigChangeReqMessage):
                conf_change = ConfChangeAdapter.from_pb(message.conf_change)

                if not self.is_leader():
                    # TODO: retry strategy in case of failure
                    await self.send_wrongleader_response(message.chan)
                else:
                    # leader assign new id to peer
                    self.logger.debug(
                        f'Received conf_change request from the "node {conf_change.get_node_id()}"'
                    )

                    self.seq.increase()
                    client_senders[self.seq.value] = message.chan
                    context = pickle.dumps(self.seq.value)
                    self.raw_node.propose_conf_change(context, conf_change)

            elif isinstance(message, ProposeReqMessage):
                if not self.is_leader():
                    # TODO: retry strategy in case of failure
                    await self.send_wrongleader_response(message.chan)
                else:
                    self.seq.increase()
                    client_senders[self.seq.value] = message.chan
                    context = pickle.dumps(self.seq.value)
                    self.raw_node.propose(context, message.data)

            elif isinstance(message, RequestIdReqMessage):
                if not self.is_leader():
                    # TODO: retry strategy in case of failure
                    await self.send_wrongleader_response(message.chan)
                else:
                    await message.chan.put(
                        IdReservedRespMessage(
                            leader_id=self.get_leader_id(),
                            reserved_id=self.reserve_next_peer_id(message.addr),
                            peer_addrs=self.peers.peer_addrs(),
                        )
                    )

            elif isinstance(message, RaftReqMessage):
                msg = MessageAdapter.from_pb(message.msg)
                self.logger.debug(
                    f'Node {msg.get_to()} Received Raft message from the "node {msg.get_from()}"'
                )

                try:
                    self.raw_node.step(msg)
                except Exception:
                    pass

            elif isinstance(message, ReportUnreachableReqMessage):
                self.raw_node.report_unreachable(message.node_id)

            now = time.time()
            elapsed = now - timer
            timer = now

            if elapsed > heartbeat:
                heartbeat = 0.1
                self.raw_node.tick()
            else:
                heartbeat -= elapsed

            await self.on_ready(client_senders)

    async def on_ready(self, client_senders: dict[int, Queue]) -> None:
        if not self.raw_node.has_ready():
            return

        ready = self.raw_node.ready()

        if msgs := ready.take_messages():
            self.send_messages(msgs)

        snapshot_default = Snapshot.default()
        if ready.snapshot() != snapshot_default.make_ref():
            snapshot = ready.snapshot()
            await self.fsm.restore(snapshot.get_data())
            self.lmdb.apply_snapshot(snapshot.clone())

        await self.handle_committed_entries(
            ready.take_committed_entries(), client_senders
        )

        if entries := ready.entries():
            self.lmdb.append(entries)

        if hs := ready.hs():
            self.lmdb.set_hard_state(hs)

        if persisted_msgs := ready.take_persisted_messages():
            self.send_messages(persisted_msgs)

        light_rd = self.raw_node.advance(ready.make_ref())

        if commit := light_rd.commit_index():
            self.lmdb.set_hard_state_comit(commit)

        self.send_messages(light_rd.take_messages())

        await self.handle_committed_entries(
            light_rd.take_committed_entries(), client_senders
        )

        self.raw_node.advance_apply()
