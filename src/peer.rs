use std::net::{SocketAddr, ToSocketAddrs};

use crate::raft_service::raft_service_client::RaftServiceClient;
use crate::{create_client, error::Result};

use serde::{Deserialize, Serialize};
use tonic::transport::Channel;

#[derive(Debug, Clone, Deserialize, Serialize)]
pub struct Peer {
    pub addr: SocketAddr,
    #[serde(skip_serializing, skip_deserializing)]
    pub client: Option<RaftServiceClient<Channel>>,
}

impl Peer {
    pub fn new<A: ToSocketAddrs>(addr: A) -> Self {
        let addr = addr.to_socket_addrs().unwrap().next().unwrap();
        return Peer { addr, client: None };
    }

    pub async fn connect(&mut self) -> Result<()> {
        let client = create_client(self.addr).await?;
        self.client = Some(client);
        Ok(())
    }
}
