use std::sync::Arc;

use napi::bindgen_prelude::*;
use napi_derive::napi;
use raftify::{
    raft::{default_logger, logger::Slogger},
    HeedStorage, Raft,
};
use slog::{self, o, Drain};
use slog_envlogger::LogBuilder;

use crate::tmp_state_machine::{HashStore, LogEntry};

#[napi]
pub struct JsRaftBootstrapper {
    inner: Raft<LogEntry, HeedStorage, HashStore>,
}

#[napi]
impl JsRaftBootstrapper {
    #[napi]
    pub fn bootstrap(node_id: u32, addr: String) -> Result<Self> {
        let addr = addr.to_string();
        let config = raftify::Config {
            log_dir: "logs".to_string(),
            ..Default::default()
        };

        let decorator = slog_term::TermDecorator::new().build();
        let drain = slog_term::FullFormat::new(decorator).build().fuse();
        let drain = slog_async::Async::new(drain).build().fuse();

        let mut builder = LogBuilder::new(drain);
        builder = builder.filter(None, slog::FilterLevel::Debug);

        if let Ok(s) = std::env::var("RUST_LOG") {
            builder = builder.parse(&s);
        }
        let drain = builder.build().fuse();

        let logger = Arc::new(Slogger {
            slog: slog::Logger::root(drain, o!()),
        });

        let log_storage = HeedStorage::create(
            &config.log_dir.clone(),
            &config.clone().into(),
            logger.clone(),
        )
        .expect("Failed to create heed storage");

        let fsm = HashStore::new();

        let raft = Raft::bootstrap(
            node_id as u64,
            addr,
            log_storage,
            fsm,
            config.into(),
            logger.clone(),
        )
        .unwrap();

        Ok(Self { inner: raft })
    }

    #[napi]
    pub async fn run(&self) -> Result<()> {
        let raft_node = self.inner.clone();
        raft_node
            .run()
            .await
            .map_err(|e| Error::new(Status::GenericFailure, format!("Failed to run: {}", e)))
    }
}
