use napi::bindgen_prelude::*;
use napi_derive::napi;
use raftify::{HeedStorage, RaftNode};

use crate::tmp_state_machine::{HashStore, LogEntry};

#[napi]
pub enum JsInitialRole {
    Follower,
    Candidate,
    Leader,
}

#[napi]
pub struct JsRaftNode {
    inner: RaftNode<LogEntry, HeedStorage, HashStore>,
}

#[napi]
impl JsRaftNode {
    #[napi]
    pub async fn is_leader(&self) -> Result<bool> {
        Ok(self.inner.is_leader().await)
    }

    #[napi]
    pub async fn get_id(&self) -> Result<u64> {
        Ok(self.inner.get_id().await)
    }

    // #[napi]
    // pub async fn add_peer(
    //     &self,
    //     id: u32,
    //     addr: String,
    //     role: Option<JsInitialRole>,
    // ) -> Result<()> {
    //     let role = role.map(|r| r.into());
    //     self.inner.add_peer(id, addr, role).await;
    //     Ok(())
    // }
}
