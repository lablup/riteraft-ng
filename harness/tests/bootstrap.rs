use harness::constant::RAFT_PORTS;
use std::{process::exit, sync::mpsc, time::Duration};
use tokio::time::sleep;

use harness::test_environment::prepare_test_environment;
use harness::{
    constant::{ONE_NODE_EXAMPLE, THREE_NODE_EXAMPLE},
    raft::{build_raft_cluster, spawn_and_join_extra_node, wait_until_rafts_ready, Raft},
    utils::load_peers,
};

#[tokio::test]
pub async fn test_static_bootstrap() {
    let test_environment = prepare_test_environment(stringify!(test_static_bootstrap));

    let (tx_raft, rx_raft) = mpsc::channel::<(u64, Raft)>();

    let peers = load_peers(&test_environment.loopback_address, THREE_NODE_EXAMPLE)
        .await
        .unwrap();
    let _raft_tasks = tokio::spawn(build_raft_cluster(
        tx_raft,
        test_environment.base_storage_path,
        peers.clone(),
    ));
    let mut rafts = wait_until_rafts_ready(None, rx_raft, 3).await;

    sleep(Duration::from_secs(1)).await;

    for (_, raft) in rafts.iter_mut() {
        raft.quit().await.expect("Failed to quit raft node");
    }
}

#[tokio::test]
pub async fn test_dynamic_bootstrap() {
    let test_environment = prepare_test_environment(stringify!(test_dynamic_bootstrap));

    let (tx_raft, rx_raft) = mpsc::channel::<(u64, Raft)>();

    let peers = load_peers(&test_environment.loopback_address.clone(), ONE_NODE_EXAMPLE)
        .await
        .unwrap();
    let _raft_tasks = tokio::spawn(build_raft_cluster(
        tx_raft.clone(),
        test_environment.base_storage_path.clone(),
        peers.clone(),
    ));

    sleep(Duration::from_secs(1)).await;

    tokio::spawn(spawn_and_join_extra_node(
        tx_raft.clone(),
        test_environment.loopback_address.clone() + ":60062",
        test_environment.loopback_address.clone() + ":" + &RAFT_PORTS[0].to_string(),
        test_environment.base_storage_path.clone(),
    ))
    .await
    .unwrap()
    .unwrap();

    tokio::spawn(spawn_and_join_extra_node(
        tx_raft.clone(),
        test_environment.loopback_address.clone() + ":60063",
        test_environment.loopback_address.clone() + ":" + &RAFT_PORTS[0].to_string(),
        test_environment.base_storage_path,
    ))
    .await
    .unwrap()
    .unwrap();

    let mut rafts = wait_until_rafts_ready(None, rx_raft, 3).await;

    for (_, raft) in rafts.iter_mut() {
        raft.quit().await.expect("Failed to quit raft node");
    }
    exit(0);
}
