import asyncio
from concurrent.futures import ProcessPoolExecutor

import pytest
from constant import FIVE_NODE_EXAMPLE, THREE_NODE_EXAMPLE
from harness.raft_server import run_raft_cluster, wait_for_until
from utils import (
    RequestType,
    kill_process,
    killall,
    load_peers,
    make_request,
    read_node,
    reset_fixtures_directory,
)


@pytest.mark.asyncio
async def test_leader_election_three_node_example():
    """
    This test simulates a scenario where the leader node in a three-node cluster is terminated.
    After the leader termination, it verifies that one of the remaining two nodes is elected
    as the new leader.
    """

    reset_fixtures_directory()
    loop = asyncio.get_running_loop()
    executor = ProcessPoolExecutor()
    peers = load_peers(THREE_NODE_EXAMPLE)

    loop.run_in_executor(executor, run_raft_cluster, peers)
    await wait_for_until("cluster_size >= 3")

    leader_node = read_node(1)

    await kill_process(leader_node["pid"])

    await wait_for_until("cluster_size <= 2")

    leader = make_request(RequestType.GET, 2, "/leader")

    # Check if the leader is one of the remaining two nodes
    assert leader in ["2", "3"]

    killall()
    executor.shutdown()


@pytest.mark.asyncio
async def test_leader_election_five_node_example():
    """
    This test simulates a scenario where the leader node in a five-node cluster is terminated.
    After the leader termination, it verifies that one of the remaining four nodes is elected
    as the new leader.
    """

    reset_fixtures_directory()
    loop = asyncio.get_running_loop()
    executor = ProcessPoolExecutor()
    peers = load_peers(FIVE_NODE_EXAMPLE)

    loop.run_in_executor(executor, run_raft_cluster, peers)
    await wait_for_until("cluster_size >= 5")

    leader_node = read_node(1)

    await kill_process(leader_node["pid"])

    await wait_for_until("cluster_size <= 4")

    leader = make_request(RequestType.GET, 2, "/leader")

    # Check if the leader is one of the remaining two nodes
    assert leader in ["2", "3", "4", "5"]

    killall()
    executor.shutdown()


# TODO: Implement this test
@pytest.mark.asyncio
async def test_repetitive_leader_failures():
    """
    Test repetitive leader failures.
    """
