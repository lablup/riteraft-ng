import { createRequire } from 'module';
const require = createRequire(import.meta.url);

const { JsRaftBootstrapper } = require('./index.node');

async function main() {
    const raftNode = new JsRaftBootstrapper.bootstrap(1, "127.0.0.1:60061");

    try {
      await raftNode.run();
    } catch (err) {
      console.error('Failed to run raft node:', err);
    }
  }

main();
