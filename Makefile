PROTO_PATH = ./raftify/protos

build-pb:
	python -m grpc_tools.protoc --proto_path=$(PROTO_PATH) --python_out=$(PROTO_PATH) --grpc_python_out=$(PROTO_PATH) $(PROTO_PATH)/*.proto
	sed -i "" '1s/^/# type: ignore\n/' $(PROTO_PATH)/*.py
	sed -i '' 's/import raft_service_pb2 as raft__service__pb2/from . import raft_service_pb2 as raft__service__pb2/' $(PROTO_PATH)/{raft_service_pb2,raft_service_pb2_grpc}.py
	sed -i '' 's/import eraftpb_pb2 as eraftpb__pb2/from . import eraftpb_pb2 as eraftpb__pb2/' $(PROTO_PATH)/{raft_service_pb2,raft_service_pb2_grpc}.py
	protoc --proto_path=$(PROTO_PATH) --pyi_out=$(PROTO_PATH) $(PROTO_PATH)/*.proto
	python -m black $(PROTO_PATH)/*.{py,pyi}
	python -m isort $(PROTO_PATH)/*.{py,pyi}

lint:
	python -m black raftify
	python -m isort raftify
	python -m black examples
	python -m isort examples

install:
	pip uninstall raftify -y
	pip install .

clean:
	rm -rf *.mdb

reinstall:
	make clean
	make install

run-memstore-example:
	python -m examples.raftify-memstore.main
