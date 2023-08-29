# type: ignore
# -*- coding: utf-8 -*-
# Generated by the protocol buffer compiler.  DO NOT EDIT!
# source: raft_service.proto
"""Generated protocol buffer code."""
from google.protobuf import descriptor as _descriptor
from google.protobuf import descriptor_pool as _descriptor_pool
from google.protobuf import symbol_database as _symbol_database
from google.protobuf.internal import builder as _builder

# @@protoc_insertion_point(imports)

_sym_db = _symbol_database.Default()


from . import eraftpb_pb2 as eraftpb__pb2

DESCRIPTOR = _descriptor_pool.Default().AddSerializedFile(
    b'\n\x12raft_service.proto\x12\x0braftservice\x1a\reraftpb.proto"\x19\n\x08Proposal\x12\r\n\x05inner\x18\x01 \x01(\x0c"#\n\x05\x45ntry\x12\x0b\n\x03key\x18\x01 \x01(\x04\x12\r\n\x05value\x18\x02 \x01(\t"#\n\x13RaftMessageResponse\x12\x0c\n\x04\x64\x61ta\x18\x01 \x01(\x0c"U\n\x14\x43hangeConfigResponse\x12/\n\x06result\x18\x01 \x01(\x0e\x32\x1f.raftservice.ChangeConfigResult\x12\x0c\n\x04\x64\x61ta\x18\x02 \x01(\x0c"O\n\x11IdRequestResponse\x12,\n\x06result\x18\x01 \x01(\x0e\x32\x1c.raftservice.IdRequestResult\x12\x0c\n\x04\x64\x61ta\x18\x02 \x01(\x0c"\x1d\n\rIdRequestArgs\x12\x0c\n\x04\x61\x64\x64r\x18\x01 \x01(\t"\x80\x01\n\x12RerouteMessageArgs\x12\x15\n\rproposed_data\x18\x01 \x01(\x0c\x12(\n\x0b\x63onf_change\x18\x02 \x01(\x0b\x32\x13.eraftpb.ConfChange\x12)\n\x04type\x18\x03 \x01(\x0e\x32\x1b.raftservice.RerouteMsgType*\xa6\x01\n\x12\x43hangeConfigResult\x12\x18\n\x14\x43hangeConfig_Success\x10\x00\x12\x1c\n\x18\x43hangeConfig_WrongLeader\x10\x01\x12\x1d\n\x19\x43hangeConfig_TimeoutError\x10\x02\x12\x1a\n\x16\x43hangeConfig_GrpcError\x10\x03\x12\x1d\n\x19\x43hangeConfig_UnknownError\x10\x04*X\n\x0fIdRequestResult\x12\x15\n\x11IdRequest_Success\x10\x00\x12\x13\n\x0fIdRequest_Error\x10\x01\x12\x19\n\x15IdRequest_WrongLeader\x10\x02*-\n\x0eRerouteMsgType\x12\x0e\n\nConfChange\x10\x00\x12\x0b\n\x07Propose\x10\x01\x32\xbe\x02\n\x0bRaftService\x12I\n\tRequestId\x12\x1a.raftservice.IdRequestArgs\x1a\x1e.raftservice.IdRequestResponse"\x00\x12H\n\x0c\x43hangeConfig\x12\x13.eraftpb.ConfChange\x1a!.raftservice.ChangeConfigResponse"\x00\x12\x43\n\x0bSendMessage\x12\x10.eraftpb.Message\x1a .raftservice.RaftMessageResponse"\x00\x12U\n\x0eRerouteMessage\x12\x1f.raftservice.RerouteMessageArgs\x1a .raftservice.RaftMessageResponse"\x00\x62\x06proto3'
)

_builder.BuildMessageAndEnumDescriptors(DESCRIPTOR, globals())
_builder.BuildTopDescriptorsAndMessages(DESCRIPTOR, "raft_service_pb2", globals())
if _descriptor._USE_C_DESCRIPTORS == False:
    DESCRIPTOR._options = None
    _CHANGECONFIGRESULT._serialized_start = 482
    _CHANGECONFIGRESULT._serialized_end = 648
    _IDREQUESTRESULT._serialized_start = 650
    _IDREQUESTRESULT._serialized_end = 738
    _REROUTEMSGTYPE._serialized_start = 740
    _REROUTEMSGTYPE._serialized_end = 785
    _PROPOSAL._serialized_start = 50
    _PROPOSAL._serialized_end = 75
    _ENTRY._serialized_start = 77
    _ENTRY._serialized_end = 112
    _RAFTMESSAGERESPONSE._serialized_start = 114
    _RAFTMESSAGERESPONSE._serialized_end = 149
    _CHANGECONFIGRESPONSE._serialized_start = 151
    _CHANGECONFIGRESPONSE._serialized_end = 236
    _IDREQUESTRESPONSE._serialized_start = 238
    _IDREQUESTRESPONSE._serialized_end = 317
    _IDREQUESTARGS._serialized_start = 319
    _IDREQUESTARGS._serialized_end = 348
    _REROUTEMESSAGEARGS._serialized_start = 351
    _REROUTEMESSAGEARGS._serialized_end = 479
    _RAFTSERVICE._serialized_start = 788
    _RAFTSERVICE._serialized_end = 1106
# @@protoc_insertion_point(module_scope)
