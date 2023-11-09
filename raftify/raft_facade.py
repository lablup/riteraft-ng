import asyncio
import pickle
from asyncio import Queue

import grpc
from rraft import (
    ConfChange,
    ConfChangeSingle,
    ConfChangeTransition,
    ConfChangeType,
    ConfChangeV2,
    Logger,
    LoggerRef,
)

from .config import RaftifyConfig
from .error import (
    ClusterBootstrapError,
    ClusterJoinError,
    LeaderNotFoundError,
    UnknownError,
)
from .follower_role import FollowerRole
from .logger import AbstractRaftifyLogger
from .mailbox import Mailbox
from .pb_adapter import ConfChangeV2Adapter
from .peers import Peer, Peers, PeerState
from .protos import raft_service_pb2
from .raft_client import RaftClient
from .raft_node import RaftNode
from .raft_server import RaftServer
from .raft_utils import RequestIdResponse
from .request_message import ConfigChangeReqMessage
from .response_message import JoinSuccessRespMessage
from .state_machine.abc import AbstractStateMachine
from .utils import SocketAddr


class RaftFacade:
    raft_node: RaftNode | None
    raft_server: RaftServer | None
    raft_node_task: asyncio.Task | None
    raft_server_task: asyncio.Task | None

    def __init__(
        self,
        cluster_config: RaftifyConfig,
        addr: SocketAddr,
        fsm: AbstractStateMachine,
        slog: Logger | LoggerRef,
        logger: AbstractRaftifyLogger,
        initial_peers: Peers = Peers({}),
    ):
        """
        Creates a new node with the given address and store.
        """
        self.addr = addr
        self.fsm = fsm
        self.slog = slog
        self.logger = logger
        # TODO: temporary maxsize is for debugging purposes.
        # In most cases, maxsize doesn't need to be over 100.
        # Find reasonable maxsize and remove it.
        self.message_queue: Queue = Queue(maxsize=100)
        self.cluster_config = cluster_config
        self.initial_peers = initial_peers
        self.raft_node = None
        self.raft_server = None
        self.raft_node_task = None
        self.raft_server_task = None

        if self_peer_id := self.initial_peers.get_node_id_by_addr(self.addr):
            self.initial_peers.connect(self_peer_id, self.addr)

    def is_initialized(self) -> bool:
        return self.raft_node is not None and self.raft_server is not None

    @property
    def mailbox(self) -> Mailbox:
        """
        Get the node's `Mailbox`.
        """
        assert self.raft_node and self.raft_server, "The raft node is not initialized!"
        return Mailbox(self.raft_node)

    @property
    def peers(self) -> Peers:
        assert self.raft_node and self.raft_server, "The raft node is not initialized!"
        return self.raft_node.peers

    @property
    def store(self) -> AbstractStateMachine:
        return self.fsm

    async def create_snapshot(self) -> None:
        assert self.raft_node and self.raft_server, "The raft node is not initialized!"

        hs = self.raft_node.lmdb.hard_state()
        await self.raft_node.create_snapshot(
            self.raft_node.lmdb.last_index(), hs.get_term()
        )

    async def send_member_bootstrap_ready_msg(
        self, follower_id: int, leader_id: int = 1
    ) -> None:
        """
        Send a `MemberBootstrapReady` message to the leader node.
        """
        leader_addr = self.initial_peers[leader_id].addr
        leader_client = RaftClient(leader_addr)
        self.peers.connect(leader_id, leader_addr)
        await leader_client.member_bootstrap_ready(follower_id, timeout=5.0)

    # TODO: It would be great if this process is handled in the RaftFacade without exposing this.
    async def wait_for_followers_join(self) -> None:
        """
        Let the leader node wait for join requests from all other initial_peers follower nodes.
        """
        await asyncio.sleep(1)

        while not all(
            data.state == PeerState.Connected for data in self.initial_peers.values()
        ):
            self.logger.debug(
                "Waiting for all peers to make join request to the cluster..."
            )
            await asyncio.sleep(2)

        self.logger.debug(
            "Received All followers join request, preparing to bootstrap the cluster."
        )
        await self.__join_followers()

        for node_id, peer in self.initial_peers.items():
            if node_id == 1:
                continue

            raw_peers = self.initial_peers.encode()
            assert peer.client is not None
            await peer.client.cluster_bootstrap_ready(raw_peers, 5.0)

    def transfer_leader(
        self,
        node_id: int,
    ) -> bool:
        """
        Handle Leader transfer.
        """
        assert self.raft_node and self.raft_server, "The raft node is not initialized!"

        if not self.raft_node.is_leader():
            self.logger.warning("LeaderTransfer requested but not leader!")
            return False

        self.raft_node.raw_node.transfer_leader(node_id)
        return True

    async def request_id(
        self, raft_addr: SocketAddr, peer_candidates: list[SocketAddr]
    ) -> RequestIdResponse:
        """
        Get a node id from the cluster's leader through `peer_candidates`.
        """
        # TODO: Block request_id calling until the all cluster's initial peers are ready.

        for peer_addr in peer_candidates:
            self.logger.info(f'Attempting to get a node_id through "{peer_addr}"...')

            leader_addr = None
            seek_next = False

            while not leader_addr:
                client = RaftClient(peer_addr)
                try:
                    resp = await client.request_id(
                        raft_addr, timeout=self.cluster_config.message_timeout
                    )

                except grpc.aio.AioRpcError:
                    seek_next = True
                    break

                match resp.result:
                    case raft_service_pb2.IdRequest_Success:
                        leader_addr = peer_addr
                        leader_id = resp.leader_id
                        node_id = resp.reserved_id

                        peer_addrs = pickle.loads(resp.peers)

                        break
                    case raft_service_pb2.IdRequest_WrongLeader:
                        self.logger.info(
                            f"Sent message to the wrong leader, retrying with the peer at {resp.leader_addr} "
                            f"assuming that it is leader node."
                        )
                        continue
                    case raft_service_pb2.IdRequest_Error | _:
                        raise UnknownError("Failed to join the cluster!")

            if not seek_next:
                break
        else:
            raise LeaderNotFoundError()

        assert leader_id is not None and node_id is not None

        self.logger.info(
            f"Obtained node id {node_id} successfully from the leader node {leader_id}."
        )

        return RequestIdResponse(node_id, (leader_id, client), peer_addrs)

    async def __join_followers(
        self,
    ) -> None:
        """
        Commit the configuration change to add all follower nodes to the cluster.
        """
        assert self.raft_node and self.raft_server, "The raft node is not initialized!"
        assert self.raft_node.is_leader(), (
            "Only leader can add a new node to the cluster!, "
            "If you want to join the cluster in the follower, "
            "use `join_cluster` method instead."
        )

        conf_change_v2 = ConfChangeV2.default()
        conf_change_v2.set_transition(ConfChangeTransition.Explicit)
        changes = []
        node_addrs = []

        for node_id in self.initial_peers.keys():
            # Skip leader
            if self.addr == self.initial_peers[node_id].addr:
                continue

            conf_change = ConfChangeSingle.default()
            conf_change.set_node_id(node_id)
            conf_change.set_change_type(ConfChangeType.AddNode)
            changes.append(conf_change)
            node_addrs.append(self.initial_peers[node_id].addr)

        conf_change_v2.set_changes(changes)
        conf_change_v2.set_context(pickle.dumps(node_addrs))

        try:
            receiver: Queue = Queue()
            await self.raft_node.message_queue.put(
                ConfigChangeReqMessage(
                    ConfChangeV2Adapter.to_pb(conf_change_v2), receiver
                )
            )
            resp = await asyncio.wait_for(receiver.get(), 2)

        except grpc.aio.AioRpcError as e:
            raise ClusterBootstrapError(cause=e)

        except Exception as e:
            raise ClusterBootstrapError(cause=e)

        if isinstance(resp, JoinSuccessRespMessage):
            self.logger.info("All follower nodes successfully joined the cluster.")
            self.raft_node.bootstrap_done = True
            asyncio.create_task(self.raft_node.leave_joint())
            return
        # TODO: handle error cases

    async def join_cluster(
        self,
        request_id_response: RequestIdResponse,
        role: FollowerRole = FollowerRole.Voter,
    ) -> None:
        """
        Try to join the cluster with the given `request_id_response`.
        """
        assert self.raft_node and self.raft_server, "The raft node is not initialized!"
        # Cluster bootstrap should be done before calling this method.
        self.raft_node.bootstrap_done = True

        node_id = request_id_response.follower_id
        leader = request_id_response.leader
        peers = request_id_response.peers
        leader_id, leader_client = leader

        self.raft_node.peers = Peers(
            {
                **{
                    node_id: Peer(
                        peer.addr,
                        PeerState.Connected,
                    )
                    for node_id, peer in peers.items()
                },
                leader_id: Peer(
                    leader_client.addr,
                    PeerState.Connected,
                ),
            }
        )

        conf_change = ConfChange.default()
        conf_change.set_node_id(node_id)
        conf_change.set_change_type(role.to_confchange_type())
        conf_change.set_context(pickle.dumps([self.addr]))

        conf_change_v2 = conf_change.as_v2()

        # TODO: Should handle wrong leader error here because the leader might change in the meanwhile.
        # But it might be already handled by the rerouting logic. So, it should be tested first.
        while True:
            try:
                resp = await leader_client.change_config(
                    conf_change_v2, timeout=self.cluster_config.message_timeout
                )

            except grpc.aio.AioRpcError as e:
                raise ClusterJoinError(cause=e)

            except Exception as e:
                raise ClusterJoinError(cause=e)

            if resp.result == raft_service_pb2.ChangeConfig_Success:
                return
            elif resp.result == raft_service_pb2.ChangeConfig_TimeoutError:
                self.logger.info("Join request timeout. Retrying...")
                await asyncio.sleep(2)
                continue

    def run_raft(self, node_id: int) -> None:
        """
        Run RaftServer and RaftNode coroutines.
        """
        self.logger.info(
            "Start to run RaftNode. Configuration: " + str(self.cluster_config)
        )
        self.raft_server = RaftServer(self.addr, self.message_queue, self.logger)

        bootstrap_done = len(self.initial_peers) == 0

        if node_id == 1:
            self.initial_peers.connect(node_id, self.addr)

            self.raft_node = RaftNode.bootstrap_leader(
                message_queue=self.message_queue,
                fsm=self.fsm,
                raft_server=self.raft_server,
                peers=self.initial_peers,
                slog=self.slog,
                logger=self.logger,
                raftify_cfg=self.cluster_config,
                bootstrap_done=bootstrap_done,
            )
        else:
            self.raft_node = RaftNode.new_follower(
                message_queue=self.message_queue,
                id=node_id,
                fsm=self.fsm,
                raft_server=self.raft_server,
                peers=self.initial_peers,
                slog=self.slog,
                logger=self.logger,
                raftify_cfg=self.cluster_config,
                bootstrap_done=bootstrap_done,
            )

        self.raft_server_task = asyncio.create_task(self.raft_server.run())
        self.raft_node_task = asyncio.create_task(self.raft_node.run())

    async def wait_for_termination(self) -> None:
        """
        Wait for the termination of RaftServer and RaftNode coroutines.
        """
        assert self.raft_node and self.raft_server, "The raft node is not initialized!"
        assert self.raft_server_task and self.raft_node_task

        try:
            await asyncio.gather(self.raft_server_task, self.raft_node_task)
        except asyncio.CancelledError:
            self.logger.info("Raft server is cancelled. preparing to terminate...")
            await self.raft_server.terminate()
