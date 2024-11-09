use async_trait::async_trait;
use bincode::{deserialize, serialize};
use raftify::{AbstractLogEntry, AbstractStateMachine, HeedStorage, Raft as Raft_, Result};
use serde::{Deserialize, Serialize};
use std::{
    collections::HashMap,
    sync::{Arc, RwLock},
};

pub type Raft = Raft_<LogEntry, HeedStorage, HashStore>;

#[derive(Clone, Debug, Serialize, Deserialize)]
pub enum LogEntry {
    Insert { key: u64, value: String },
}

impl AbstractLogEntry for LogEntry {
    fn encode(&self) -> Result<Vec<u8>> {
        serialize(self).map_err(|e| e.into())
    }

    fn decode(bytes: &[u8]) -> Result<LogEntry> {
        let log_entry: LogEntry = deserialize(bytes)?;
        Ok(log_entry)
    }
}

#[derive(Clone, Debug, Default)]
pub struct HashStore(pub Arc<RwLock<HashMap<u64, String>>>);

impl HashStore {
    pub fn new() -> Self {
        Self(Arc::new(RwLock::new(HashMap::new())))
    }

    pub fn get(&self, id: u64) -> Option<String> {
        self.0.read().unwrap().get(&id).cloned()
    }
}

#[async_trait]
impl AbstractStateMachine for HashStore {
    async fn apply(&mut self, data: Vec<u8>) -> Result<Vec<u8>> {
        let log_entry: LogEntry = LogEntry::decode(&data)?;
        match log_entry {
            LogEntry::Insert { ref key, ref value } => {
                let mut db = self.0.write().unwrap();
                db.insert(*key, value.clone());
            }
        };
        Ok(data)
    }

    async fn snapshot(&self) -> Result<Vec<u8>> {
        Ok(serialize(&self.0.read().unwrap().clone())?)
    }

    async fn restore(&mut self, snapshot: Vec<u8>) -> Result<()> {
        let new: HashMap<u64, String> = deserialize(&snapshot[..]).expect(
            "Failed to restore state from snapshot: Snapshot data might be corrupted or incomplete",
        );
        let mut db = self.0.write().unwrap();
        let _ = std::mem::replace(&mut *db, new);
        Ok(())
    }

    fn encode(&self) -> Result<Vec<u8>> {
        serialize(&self.0.read().unwrap().clone()).map_err(|e| e.into())
    }

    fn decode(bytes: &[u8]) -> Result<Self> {
        let db: HashMap<u64, String> = deserialize(bytes)?;
        Ok(Self(Arc::new(RwLock::new(db))))
    }
}
