import asyncio
import logging
import pickle
from asyncio import Queue

from rraft import ConfChange, ConfChangeType, Logger_Ref

from riteraft.fsm import FSM
from riteraft.mailbox import Mailbox
from riteraft.protos import raft_service_pb2
from riteraft.raft_client import RaftClient
from riteraft.raft_node import RaftNode
from riteraft.raft_server import RaftServer
from riteraft.utils import SocketAddr


class Raft:
    def __init__(self, addr: SocketAddr, fsm: FSM, logger: Logger_Ref):
        """
        Creates a new node with the given address and store.
        """
        self.addr = addr
        self.fsm = fsm
        self.logger = logger
        self.chan = Queue(maxsize=100)

    def mailbox(self) -> Mailbox:
        """
        Get the node's `Mailbox`.
        """
        return Mailbox(self.chan)

    async def lead(self) -> None:
        """
        Create a new leader for the cluster, with id 1. There has to be exactly one node in the
        cluster that is initialized that way
        """
        raft_node = RaftNode.new_leader(self.chan, self.fsm, self.logger)
        server = RaftServer(self.addr, self.chan)
        asyncio.create_task(server.run())
        node_handle = asyncio.create_task(raft_node.run())
        await node_handle
        # TODO: Resolve several issues on the console at first...
        logging.warning("Leaving leader node")

    async def join(self, peer_addr: SocketAddr) -> None:
        """
        Try to join a new cluster at `peer_addr`, getting an id from the leader, or finding it if
        `peer_addr` is not the current leader of the cluster
        """

        # 1. Discover the leader of the cluster and obtain an 'node_id'.
        logging.info(f"Attempting to join peer cluster at {str(peer_addr)}")

        leader_addr = None

        while not leader_addr:
            client = RaftClient(peer_addr)
            resp = await client.request_id()

            if resp.code == raft_service_pb2.Ok:
                leader_addr = peer_addr
                leader_id, node_id = pickle.loads(resp.data)
                break
            elif resp.code == raft_service_pb2.WrongLeader:
                _, peer_addr = pickle.loads(resp.data)
                logging.info(f"Wrong leader, retrying with leader at {peer_addr}")
                continue
            elif resp.code == raft_service_pb2.Error:
                logging.error("Error joining the cluster")
                return

        logging.info(f"Obtained ID from leader: {node_id}")

        # 2. Run server and node to prepare for joining
        raft_node = RaftNode.new_follower(self.chan, node_id, self.fsm, self.logger)
        raft_node.peers[leader_id] = client
        server = RaftServer(self.addr, self.chan)
        asyncio.create_task(server.run())
        raft_node_handle = asyncio.create_task(raft_node.run())

        # 3. Join the cluster
        change = ConfChange.default()
        change.set_node_id(node_id)
        change.set_change_type(ConfChangeType.AddNode)
        change.set_context(pickle.dumps(self.addr))

        # TODO: Should handle wrong leader error here because the leader might change in the meanwhile.
        await client.change_config(change)
        await raft_node_handle
